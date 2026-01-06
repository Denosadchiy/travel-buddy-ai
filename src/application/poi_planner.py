"""
POI Planner service.
Selects candidate POIs for each block in the macro plan.

Supports two modes:
1. Deterministic mode (default): Uses rank_score from POI providers
2. LLM-assisted mode (optional): Uses LLM to select/re-rank candidates

The LLM mode is enabled via USE_LLM_FOR_POI_SELECTION config flag.
When enabled, the LLM can ONLY choose from deterministically-filtered candidates.
"""
import logging
import asyncio
import time
from uuid import UUID
from typing import Optional
from dataclasses import dataclass, field
from collections import Counter, defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings, Settings
from src.domain.models import DaySkeleton, BlockType
from src.domain.schemas import POIPlanBlock, POIPlanResponse
from src.application.trip_spec import TripSpecCollector
from src.application.macro_planner import MacroPlanner
from src.application.poi_selection_llm import (
    POISelectionLLMService,
    TripContext,
    DayContext,
    BlockContext,
    build_trip_context_from_response,
)
from src.application.poi_agent import (
    POIPreferenceAgent,
    POIPreferenceProfile,
    score_candidate,
    filter_candidates_for_block,
)
from src.infrastructure.poi_providers import POIProvider, get_poi_provider, haversine_distance_km
from src.infrastructure.llm_client import (
    get_curator_llm_client,
    get_poi_selection_llm_client,
)
from src.infrastructure.models import ItineraryModel
from src.domain.models import POICandidate

logger = logging.getLogger(__name__)


class POIPlanner:
    """
    Service for selecting POI candidates for trip blocks.

    Modes:
    - Deterministic (default): Uses rank_score from POI providers
    - LLM-assisted (optional): Uses LLM to select from deterministic candidates

    The LLM mode provides smarter selection while maintaining safety:
    - LLM can ONLY choose from deterministically-filtered candidates
    - Falls back to deterministic selection on any LLM failure
    """

    # Block types that need POI candidates
    BLOCK_TYPES_NEEDING_POIS = {
        BlockType.MEAL,
        BlockType.ACTIVITY,
        BlockType.NIGHTLIFE,
    }

    # Number of candidates to fetch from provider (before LLM selection)
    # When LLM is enabled, we fetch more candidates for LLM to choose from
    # IMPORTANT: Keep MORE candidates to ensure diversity after deduplication filtering
    CANDIDATES_PER_BLOCK = 5  # Increased from 3 to provide more options after filtering duplicates
    CANDIDATES_FOR_LLM_SELECTION = 15  # Increased from 10 for better LLM selection

    def __init__(
        self,
        poi_provider: Optional[POIProvider] = None,
        poi_selection_llm: Optional[POISelectionLLMService] = None,
        app_settings: Optional[Settings] = None,
    ):
        """
        Initialize POI Planner.

        Args:
            poi_provider: POI provider (defaults to composite provider)
            poi_selection_llm: LLM selection service (for testing/DI)
            app_settings: Settings override (for testing)
        """
        self.poi_provider = poi_provider  # Will be set per request if None
        self._poi_selection_llm = poi_selection_llm
        self._settings = app_settings or settings
        self.trip_spec_collector = TripSpecCollector()
        self.macro_planner = MacroPlanner()

    @property
    def poi_selection_llm(self) -> POISelectionLLMService:
        """Lazy initialization of LLM selection service."""
        if self._poi_selection_llm is None:
            self._poi_selection_llm = POISelectionLLMService(
                app_settings=self._settings
            )
        return self._poi_selection_llm

    @property
    def use_llm_selection(self) -> bool:
        """Check if LLM-based POI selection is enabled."""
        return self._settings.use_llm_for_poi_selection

    def _block_needs_pois(self, block_type: BlockType) -> bool:
        """Check if a block type needs POI candidates."""
        return block_type in self.BLOCK_TYPES_NEEDING_POIS

    def _apply_hotel_anchor_bias(
        self,
        candidates: list[POICandidate],
        hotel_lat: float,
        hotel_lon: float,
        distance_weight: float,
    ) -> list[POICandidate]:
        """
        Apply hotel proximity bias to candidate scores.

        Adjusts rank_score by subtracting: distance_weight * distance_from_hotel_km
        This creates a preference for POIs closer to the hotel.

        Args:
            candidates: List of POI candidates
            hotel_lat: Hotel latitude
            hotel_lon: Hotel longitude
            distance_weight: Weight for distance penalty (higher = stronger preference for nearby)

        Returns:
            New list of candidates with adjusted scores, sorted by new score
        """
        if not candidates:
            return candidates

        adjusted_candidates = []
        for candidate in candidates:
            if candidate.lat is not None and candidate.lon is not None:
                distance_km = haversine_distance_km(
                    hotel_lat, hotel_lon, candidate.lat, candidate.lon
                )
                # Apply distance penalty: closer = higher score
                adjusted_score = candidate.rank_score - (distance_weight * distance_km)
            else:
                # No coordinates, keep original score
                adjusted_score = candidate.rank_score

            # Create a copy with adjusted score
            adjusted = POICandidate(
                poi_id=candidate.poi_id,
                name=candidate.name,
                category=candidate.category,
                tags=candidate.tags,
                rating=candidate.rating,
                location=candidate.location,
                lat=candidate.lat,
                lon=candidate.lon,
                rank_score=adjusted_score,
            )
            adjusted_candidates.append(adjusted)

        # Sort by adjusted score (descending)
        adjusted_candidates.sort(key=lambda c: c.rank_score, reverse=True)

        logger.debug(
            f"Applied hotel anchor bias: distance_weight={distance_weight}, "
            f"top candidate={adjusted_candidates[0].name if adjusted_candidates else 'none'}"
        )

        return adjusted_candidates

    async def _validate_and_repair_day_plan(
        self,
        day_context: DayContext,
        selected_by_block: dict[int, POICandidate],
        day_block_candidates: dict[int, list[POICandidate]],
        trip_selected_poi_ids: set[UUID],
        day_anchor_lat: Optional[float],
        day_anchor_lon: Optional[float],
        preference_profile: POIPreferenceProfile,
        day_skeleton: DaySkeleton,
    ) -> dict[int, POICandidate]:
        """Validate and repair a day's POI plan for geographic continuity."""
        if not self._settings.enable_travel_hop_limit or self._settings.max_hop_distance_km <= 0:
            return selected_by_block

        max_hop_distance_km = self._settings.max_hop_distance_km
        sorted_block_indices = sorted(selected_by_block.keys())
        
        prev_lat, prev_lon = day_anchor_lat, day_anchor_lon

        for i, block_index in enumerate(sorted_block_indices):
            current_poi = selected_by_block[block_index]

            if current_poi.lat is None or current_poi.lon is None:
                continue

            if prev_lat is not None and prev_lon is not None:
                distance = haversine_distance_km(prev_lat, prev_lon, current_poi.lat, current_poi.lon)
                if distance > max_hop_distance_km:
                    logger.warning(
                        f"Long hop detected in POI plan for Day {day_context.day_number}, Block {block_index}: "
                        f"{current_poi.name} is {distance:.2f}km from previous point (max: {max_hop_distance_km}km)."
                    )
                    
                    # Attempt to find a replacement
                    candidates = day_block_candidates.get(block_index, [])
                    skeleton_block = day_skeleton.blocks[block_index]
                    
                    best_replacement = None
                    best_score = -1

                    for candidate in candidates:
                        if candidate.poi_id == current_poi.poi_id or candidate.poi_id in trip_selected_poi_ids:
                            continue
                        
                        if candidate.lat is not None and candidate.lon is not None:
                            candidate_dist = haversine_distance_km(prev_lat, prev_lon, candidate.lat, candidate.lon)
                            if candidate_dist <= max_hop_distance_km:
                                score = score_candidate(
                                    candidate=candidate,
                                    block_type=skeleton_block.block_type,
                                    desired_categories=skeleton_block.desired_categories,
                                    profile=preference_profile,
                                    anchor_lat=prev_lat,
                                    anchor_lon=prev_lon,
                                    distance_weight=self._settings.hotel_anchor_distance_weight * 2, # Higher penalty for distance
                                )
                                if score > best_score:
                                    best_score = score
                                    best_replacement = candidate

                    if best_replacement:
                        logger.info(f"Replacing {current_poi.name} with {best_replacement.name} to fix long hop.")
                        
                        # Update sets of used POI IDs
                        trip_selected_poi_ids.discard(current_poi.poi_id)
                        trip_selected_poi_ids.add(best_replacement.poi_id)

                        selected_by_block[block_index] = best_replacement
                        current_poi = best_replacement
                    else:
                        logger.warning(f"Could not find a suitable replacement for {current_poi.name}.")

            prev_lat, prev_lon = current_poi.lat, current_poi.lon

        return selected_by_block

    async def generate_poi_plan(
        self,
        trip_id: UUID,
        db: AsyncSession,
        preference_profile: Optional[POIPreferenceProfile] = None,
    ) -> POIPlanResponse:
        """
        Generate POI plan for a trip.

        Args:
            trip_id: Trip UUID
            db: Database session

        Returns:
            POIPlanResponse with candidates for each block

        Raises:
            ValueError: If trip not found or macro plan missing
        """
        # 1. Load trip spec
        trip_spec = await self.trip_spec_collector.get_trip(trip_id, db)
        if not trip_spec:
            raise ValueError(f"Trip {trip_id} not found")

        # 2. Load macro plan
        macro_plan = await self.macro_planner.get_macro_plan(trip_id, db)
        if not macro_plan:
            raise ValueError(f"No macro plan found for trip {trip_id}. Generate macro plan first.")

        # 2b. Build preference profile (POI agent)
        poi_agent = POIPreferenceAgent(app_settings=self._settings)
        if preference_profile is None:
            preference_profile = await poi_agent.build_profile(trip_spec)

        preference_summary = {
            "must_include_keywords": preference_profile.must_include_keywords,
            "avoid_keywords": preference_profile.avoid_keywords,
            "search_keywords": preference_profile.search_keywords,
            "category_boosts": preference_profile.category_boosts,
            "tag_boosts": preference_profile.tag_boosts,
            "min_rating": preference_profile.min_rating,
            "preferred_price_levels": preference_profile.preferred_price_levels,
        }

        # 3. Initialize POI provider if not set
        if not self.poi_provider:
            self.poi_provider = get_poi_provider(db)

        # 4. Log selection mode
        if self.use_llm_selection:
            logger.info(f"POI selection mode: LLM-assisted (trip_id={trip_id})")
        else:
            logger.info(f"POI selection mode: Deterministic (trip_id={trip_id})")

        # 5. Build trip context for LLM (if needed)
        trip_context = None
        if self.use_llm_selection:
            trip_context = build_trip_context_from_response(trip_spec)

        # 6. Check if hotel anchor should be applied
        hotel_anchor_enabled = (
            self._settings.hotel_anchor_enabled
            and trip_spec.hotel_lat is not None
            and trip_spec.hotel_lon is not None
        )
        hotel_anchor_blocks = self._settings.hotel_anchor_blocks
        hotel_anchor_weight = self._settings.hotel_anchor_distance_weight

        if hotel_anchor_enabled:
            logger.info(
                f"Hotel anchor enabled: blocks={hotel_anchor_blocks}, "
                f"weight={hotel_anchor_weight}, hotel=({trip_spec.hotel_lat}, {trip_spec.hotel_lon})"
            )

        # 7. Generate POI candidates for each block
        poi_blocks = []

        # CRITICAL: Track POIs selected across ALL days to prevent duplicates in multi-day trips
        trip_selected_poi_ids: set[UUID] = set()
        previous_day_anchor: Optional[tuple[float, float]] = None

        for day in macro_plan.days:
            # Track POIs already selected for this day (for LLM deduplication)
            day_selected_poi_ids: set[UUID] = set()
            # Count POI-needing blocks in this day for hotel anchor
            poi_block_count_in_day = 0

            day_block_candidates: dict[int, list[POICandidate]] = {}
            day_block_contexts: dict[int, BlockContext] = {}

            # Determine day-level anchor (previous day last POI, else hotel/city center)
            day_anchor_lat = None
            day_anchor_lon = None
            if previous_day_anchor:
                day_anchor_lat, day_anchor_lon = previous_day_anchor
            elif trip_spec.hotel_lat is not None and trip_spec.hotel_lon is not None:
                day_anchor_lat, day_anchor_lon = trip_spec.hotel_lat, trip_spec.hotel_lon
            elif trip_spec.city_center_lat is not None and trip_spec.city_center_lon is not None:
                day_anchor_lat, day_anchor_lon = trip_spec.city_center_lat, trip_spec.city_center_lon

            for block_index, block in enumerate(day.blocks):
                # Skip blocks that don't need POIs
                if not self._block_needs_pois(block.block_type):
                    continue

                # Increment POI block counter for hotel anchor
                poi_block_count_in_day += 1

                # Determine how many candidates to fetch
                # Fetch MORE than needed to account for deduplication filtering
                base_limit = (
                    self.CANDIDATES_FOR_LLM_SELECTION
                    if self.use_llm_selection
                    else self.CANDIDATES_PER_BLOCK
                )
                # Multiply by 2 to ensure we have enough candidates after filtering duplicates
                fetch_limit = base_limit * 2

                # Search for POI candidates with radius and block type filtering
                candidates = await self.poi_provider.search_pois(
                    city=trip_spec.city,
                    desired_categories=block.desired_categories,
                    budget=trip_spec.budget,
                    limit=fetch_limit,
                    center_location=trip_spec.hotel_location,
                    city_center_lat=trip_spec.city_center_lat,
                    city_center_lon=trip_spec.city_center_lon,
                    block_type=block.block_type,
                    search_keywords=preference_profile.search_keywords if (
                        preference_profile and block.block_type == BlockType.MEAL
                    ) else None,
                )

                # Apply hotel anchor bias for first N POI-needing blocks of the day
                if hotel_anchor_enabled and poi_block_count_in_day <= hotel_anchor_blocks:
                    logger.debug(
                        f"Applying hotel anchor to day {day.day_number}, "
                        f"POI block {poi_block_count_in_day} of {hotel_anchor_blocks}"
                    )
                    anchor_lat = trip_spec.hotel_lat
                    anchor_lon = trip_spec.hotel_lon
                    if previous_day_anchor:
                        anchor_lat, anchor_lon = previous_day_anchor
                    candidates = self._apply_hotel_anchor_bias(
                        candidates=candidates,
                        hotel_lat=anchor_lat,
                        hotel_lon=anchor_lon,
                        distance_weight=hotel_anchor_weight,
                    )

                # CRITICAL: Filter out POIs already used in previous days/blocks
                # This prevents the same museum/restaurant from appearing multiple times in the trip
                original_count = len(candidates)
                filtered_out = [c for c in candidates if c.poi_id in trip_selected_poi_ids]
                candidates = [c for c in candidates if c.poi_id not in trip_selected_poi_ids]

                if original_count > len(candidates):
                    filtered_names = [c.name for c in filtered_out[:3]]
                    logger.info(
                        f"Day {day.day_number}, Block {block_index}: "
                        f"Filtered {original_count - len(candidates)} duplicate POIs: {filtered_names}"
                    )
                    logger.info(f"Trip has {len(trip_selected_poi_ids)} unique POIs selected so far")

                # Preference-aware filtering and scoring
                candidates = filter_candidates_for_block(
                    candidates=candidates,
                    profile=preference_profile,
                    block_type=block.block_type,
                )

                anchor_lat = None
                anchor_lon = None
                if hotel_anchor_enabled and poi_block_count_in_day <= hotel_anchor_blocks:
                    anchor_lat = trip_spec.hotel_lat
                    anchor_lon = trip_spec.hotel_lon
                    if previous_day_anchor:
                        anchor_lat, anchor_lon = previous_day_anchor

                scored_candidates = [
                    (
                        score_candidate(
                            candidate=candidate,
                            block_type=block.block_type,
                            desired_categories=block.desired_categories,
                            profile=preference_profile,
                            anchor_lat=anchor_lat,
                            anchor_lon=anchor_lon,
                            day_center_lat=trip_spec.city_center_lat,
                            day_center_lon=trip_spec.city_center_lon,
                            distance_weight=self._settings.hotel_anchor_distance_weight,
                        ),
                        candidate,
                    )
                    for candidate in candidates
                ]
                scored_candidates.sort(key=lambda item: item[0], reverse=True)
                candidates = [candidate for _, candidate in scored_candidates]

                day_block_candidates[block_index] = candidates

                if self.use_llm_selection:
                    day_block_contexts[block_index] = BlockContext(
                        block_index=block_index,
                        block_type=block.block_type,
                        start_time=str(block.start_time),
                        end_time=str(block.end_time),
                        theme=block.theme,
                        desired_categories=block.desired_categories,
                    )

            # Day-level LLM selection (one call per day)
            selected_by_block: dict[int, POICandidate] = {}
            if (
                self.use_llm_selection
                and self._settings.enable_day_level_poi_selection
                and day_block_contexts
            ):
                day_context = DayContext(
                    day_number=day.day_number,
                    date=str(day.date),
                    theme=day.theme,
                    already_selected_poi_ids=list(trip_selected_poi_ids),
                )
                selected_by_block = await self.poi_selection_llm.select_pois_for_day(
                    trip_context=trip_context,
                    day_context=day_context,
                    blocks=[day_block_contexts[idx] for idx in sorted(day_block_contexts)],
                    candidates_by_block=day_block_candidates,
                    already_selected_ids=set(trip_selected_poi_ids),
                    max_hop_distance_km=self._settings.max_hop_distance_km,
                    anchor_lat=day_anchor_lat,
                    anchor_lon=day_anchor_lon,
                    city_center_lat=trip_spec.city_center_lat,
                    city_center_lon=trip_spec.city_center_lon,
                    preference_summary=preference_summary,
                )

                if selected_by_block:
                    selected_by_block = await self._validate_and_repair_day_plan(
                        day_context=day_context,
                        selected_by_block=selected_by_block,
                        day_block_candidates=day_block_candidates,
                        trip_selected_poi_ids=trip_selected_poi_ids,
                        day_anchor_lat=day_anchor_lat,
                        day_anchor_lon=day_anchor_lon,
                        preference_profile=preference_profile,
                        day_skeleton=day,
                    )


            for block_index, block in enumerate(day.blocks):
                if not self._block_needs_pois(block.block_type):
                    continue

                candidates = day_block_candidates.get(block_index, [])

                # Select final candidates
                selected_candidates: list[POICandidate] = []
                if selected_by_block.get(block_index):
                    selected = selected_by_block[block_index]
                    selected_candidates = [selected] + [
                        c for c in candidates if c.poi_id != selected.poi_id
                    ]
                    selected_candidates = selected_candidates[:self.CANDIDATES_PER_BLOCK]
                    day_selected_poi_ids.add(selected.poi_id)
                    trip_selected_poi_ids.add(selected.poi_id)
                    candidates = selected_candidates
                elif self.use_llm_selection and candidates:
                    # Fallback to per-block LLM selection if day-level was skipped or incomplete
                    day_context = DayContext(
                        day_number=day.day_number,
                        date=str(day.date),
                        theme=day.theme,
                        already_selected_poi_ids=list(day_selected_poi_ids),
                    )
                    block_context = day_block_contexts.get(block_index)
                    if block_context:
                        selected_candidates = await self.poi_selection_llm.select_pois_for_block(
                            trip_context=trip_context,
                            day_context=day_context,
                            block_context=block_context,
                            candidates=candidates,
                            max_results=self.CANDIDATES_PER_BLOCK,
                        )

                    for c in selected_candidates:
                        day_selected_poi_ids.add(c.poi_id)
                        trip_selected_poi_ids.add(c.poi_id)

                    candidates = selected_candidates if selected_candidates else candidates[:self.CANDIDATES_PER_BLOCK]
                else:
                    # Deterministic mode: use candidates as-is (already sorted by rank_score)
                    for c in candidates[:self.CANDIDATES_PER_BLOCK]:
                        day_selected_poi_ids.add(c.poi_id)
                        trip_selected_poi_ids.add(c.poi_id)
                    candidates = candidates[:self.CANDIDATES_PER_BLOCK]

                # Create POIPlanBlock
                poi_block = POIPlanBlock(
                    day_number=day.day_number,
                    block_index=block_index,
                    block_theme=block.theme or "",
                    block_type=block.block_type,
                    candidates=candidates,
                )
                poi_blocks.append(poi_block)

            # Update previous-day anchor based on last selected POI in this day
            last_poi = None
            for block in reversed(poi_blocks):
                if block.day_number != day.day_number:
                    break
                if block.candidates:
                    last_poi = block.candidates[0]
                    break
            if last_poi and last_poi.lat is not None and last_poi.lon is not None:
                previous_day_anchor = (last_poi.lat, last_poi.lon)

        # 5. Store in database
        created_at = datetime.utcnow()

        # Get or create itinerary record
        result = await db.execute(
            select(ItineraryModel).where(ItineraryModel.trip_id == trip_id)
        )
        itinerary_model = result.scalars().first()

        # Convert POIPlanBlock list to JSON
        poi_plan_json = [block.model_dump(mode='json') for block in poi_blocks]

        if itinerary_model:
            # Update existing record
            itinerary_model.poi_plan = poi_plan_json
            itinerary_model.poi_plan_created_at = created_at
            itinerary_model.updated_at = created_at
        else:
            # Create new record (shouldn't happen if macro plan exists, but handle it)
            itinerary_model = ItineraryModel(
                trip_id=trip_id,
                poi_plan=poi_plan_json,
                poi_plan_created_at=created_at,
                created_at=created_at,
                updated_at=created_at,
            )
            db.add(itinerary_model)

        await db.commit()
        await db.refresh(itinerary_model)

        # 6. Return response
        return POIPlanResponse(
            trip_id=trip_id,
            blocks=poi_blocks,
            created_at=created_at.isoformat() + "Z",
        )

    async def get_poi_plan(
        self,
        trip_id: UUID,
        db: AsyncSession,
    ) -> Optional[POIPlanResponse]:
        """
        Get stored POI plan for a trip.

        Args:
            trip_id: Trip UUID
            db: Database session

        Returns:
            POIPlanResponse if plan exists, None otherwise
        """
        result = await db.execute(
            select(ItineraryModel).where(ItineraryModel.trip_id == trip_id)
        )
        itinerary_model = result.scalars().first()

        if not itinerary_model or not itinerary_model.poi_plan:
            return None

        # Parse stored JSON back into POIPlanBlock objects
        poi_blocks = [POIPlanBlock(**block_data) for block_data in itinerary_model.poi_plan]

        return POIPlanResponse(
            trip_id=trip_id,
            blocks=poi_blocks,
            created_at=itinerary_model.poi_plan_created_at.isoformat() + "Z"
            if itinerary_model.poi_plan_created_at else datetime.utcnow().isoformat() + "Z",
        )


@dataclass
class SearchDirective:
    """LLM-guided search directive for POI curation."""
    category: str
    keywords: list[str] = field(default_factory=list)
    min_count: int = 0
    priority: str = "normal"  # "must", "high", "normal"
    block_type: BlockType = BlockType.ACTIVITY


@dataclass
class CuratedPOIBank:
    """Curated POI bank produced by POI Curator agent."""
    candidates: list[POICandidate]
    candidates_by_category: dict[str, list[POICandidate]]
    llm_scores: dict[UUID, float]
    directives: list[SearchDirective]
    clustering_result: Optional["ClusteringResult"]
    must_visit_ids: list[UUID]
    nice_to_have_ids: list[UUID]
    curator_notes: Optional[str] = None


class POICuratorAgent:
    """
    Agentic POI Curator.
    Uses LLM to generate search directives, fetches POIs via providers,
    and optionally assigns LLM-based relevance scores.
    """
    VALID_CATEGORIES = {
        "restaurant",
        "cafe",
        "bar",
        "bakery",
        "food",
        "museum",
        "attraction",
        "park",
        "shopping",
        "wellness",
        "nightlife",
    }
    CATEGORY_ALIASES = [
        ("fine dining", "restaurant"),
        ("seafood", "restaurant"),
        ("tapas", "restaurant"),
        ("cuisine", "restaurant"),
        ("restaurant", "restaurant"),
        ("cafe", "cafe"),
        ("coffee", "cafe"),
        ("bakery", "bakery"),
        ("breakfast", "cafe"),
        ("bar", "bar"),
        ("pub", "bar"),
        ("brewery", "bar"),
        ("nightclub", "nightlife"),
        ("club", "nightlife"),
        ("live music", "nightlife"),
        ("nightlife", "nightlife"),
        ("museum", "museum"),
        ("gallery", "museum"),
        ("art", "museum"),
        ("history", "attraction"),
        ("historical", "attraction"),
        ("architecture", "attraction"),
        ("landmark", "attraction"),
        ("monument", "attraction"),
        ("sightseeing", "attraction"),
        ("attraction", "attraction"),
        ("park", "park"),
        ("nature", "park"),
        ("viewpoint", "park"),
        ("garden", "park"),
        ("shopping", "shopping"),
        ("market", "shopping"),
        ("boutique", "shopping"),
        ("spa", "wellness"),
        ("wellness", "wellness"),
        ("gym", "wellness"),
    ]

    SEARCH_SYSTEM_PROMPT = """You are a POI curator. Generate search directives for finding places in a city.
Return ONLY JSON with the schema:
{
  "directives": [
    {
      "category": "restaurant",
      "keywords": ["craft beer", "local"],
      "min_count": 20,
      "priority": "must|high|normal"
    }
  ]
}
Rules:
- Use categories from the provided list.
- Keep keywords short (<= 4 per directive).
- min_count must be an integer >= 10.
"""

    SCORE_SYSTEM_PROMPT = """You are a POI curator. Score candidates for this trip.
Return ONLY JSON:
{
  "scores": [
    {"candidate_id": "uuid", "score": 0-100, "reason": "short"}
    ]
}
Rules:
- Use only provided candidate_id values.
- Score higher when a place strongly matches preferences or must-include keywords.
"""

    PRIORITIZE_SYSTEM_PROMPT = """You are a POI curator. Identify must-visit and nice-to-have places.
Return ONLY JSON:
{
  "must_visit_ids": ["uuid"],
  "nice_to_have_ids": ["uuid"],
  "notes": "short"
}
Rules:
- Use only provided candidate_id values.
- must_visit_ids should be <= 10, nice_to_have_ids <= 20.
"""

    def __init__(
        self,
        poi_provider: Optional[POIProvider] = None,
        app_settings: Optional[Settings] = None,
    ):
        self.poi_provider = poi_provider
        self._settings = app_settings or settings
        self._planning_llm = None
        self._scoring_llm = None

    def _get_planning_llm(self):
        if self._planning_llm is None:
            self._planning_llm = get_curator_llm_client(self._settings)
        return self._planning_llm

    def _get_scoring_llm(self):
        if self._scoring_llm is None:
            self._scoring_llm = get_poi_selection_llm_client(self._settings)
        return self._scoring_llm

    def _block_type_for_category(self, category: str) -> BlockType:
        lower = category.lower()
        if lower in {"restaurant", "cafe", "bakery", "food"}:
            return BlockType.MEAL
        if lower in {"bar", "nightlife", "club", "nightclub", "pub"}:
            return BlockType.NIGHTLIFE
        return BlockType.ACTIVITY

    def _normalize_keywords(self, keywords: list[str]) -> list[str]:
        result = []
        for keyword in keywords or []:
            cleaned = str(keyword).strip().lower()
            if cleaned and cleaned not in result:
                result.append(cleaned)
        return result

    def _candidate_matches_preference(self, candidate: POICandidate, preference) -> bool:
        keyword = (preference.keyword or "").lower()
        category = self._normalize_category(preference.category)
        if category:
            candidate_category = (candidate.category or "").lower()
            if category not in candidate_category:
                if not candidate.tags or not any(category == tag.lower() for tag in candidate.tags):
                    return False
        if keyword:
            haystack = f"{candidate.name} {' '.join(candidate.tags or [])}".lower()
            if keyword not in haystack:
                return False
        if preference.price_level and candidate.price_level is not None:
            price_map = {"cheap": [0, 1], "moderate": [2], "expensive": [3, 4]}
            if candidate.price_level not in price_map.get(preference.price_level, []):
                return False
        return True

    def _normalize_category(self, raw_category: Optional[str]) -> Optional[str]:
        if not raw_category:
            return None
        value = str(raw_category).strip().lower()
        if value in self.VALID_CATEGORIES:
            return value
        for keyword, mapped in self.CATEGORY_ALIASES:
            if keyword in value:
                return mapped
        return None

    def _build_deterministic_directives(self, macro_plan, trip_spec) -> list[SearchDirective]:
        category_counts = Counter()
        for day in macro_plan.days:
            for block in day.blocks:
                if block.block_type not in POIPlanner.BLOCK_TYPES_NEEDING_POIS:
                    continue
                for category in block.desired_categories or []:
                    normalized = self._normalize_category(category)
                    if normalized:
                        category_counts[normalized] += 1

        directives = []
        min_per_category = self._settings.agentic_min_candidates_per_category
        max_per_category = self._settings.agentic_max_candidates_per_category
        multiplier = max(2, self._settings.agentic_candidate_multiplier)
        max_categories = max(6, self._settings.agentic_llm_scoring_max_categories * 3)
        top_categories = [cat for cat, _ in category_counts.most_common(max_categories)]

        for category in top_categories:
            count = category_counts[category]
            min_count = max(min_per_category, count * multiplier)
            min_count = min(min_count, max_per_category)
            directives.append(SearchDirective(
                category=category,
                keywords=[],
                min_count=min_count,
                priority="high" if count >= 3 else "normal",
                block_type=self._block_type_for_category(category),
            ))

        for pref in trip_spec.structured_preferences or []:
            normalized_category = self._normalize_category(pref.category)
            if not normalized_category:
                continue
            keyword = pref.keyword.strip() if pref.keyword else ""
            min_count = min_per_category
            if pref.quantity:
                min_count = max(min_count, pref.quantity * multiplier)
            min_count = min(min_count, max_per_category)
            directives.append(SearchDirective(
                category=normalized_category,
                keywords=[keyword] if keyword else [],
                min_count=min_count,
                priority="must",
                block_type=self._block_type_for_category(normalized_category),
            ))

        return directives

    async def _build_llm_directives(
        self,
        trip_spec,
        macro_plan,
        base_directives: list[SearchDirective],
        preference_profile: Optional["POIPreferenceProfile"],
    ) -> list[SearchDirective]:
        categories = sorted({d.category for d in base_directives})
        structured = [p.model_dump() for p in (trip_spec.structured_preferences or [])]
        preference_signals = []
        if preference_profile:
            preference_signals = (
                preference_profile.must_include_keywords
                + preference_profile.search_keywords
                + list(preference_profile.tag_boosts.keys())
            )
        if not structured and not preference_signals:
            return []

        prompt = f"""Trip: {trip_spec.city}, {trip_spec.start_date} to {trip_spec.end_date}
Pace: {trip_spec.pace.value}
Budget: {trip_spec.budget.value}
Interests: {', '.join(trip_spec.interests or []) or 'general'}
Structured preferences: {structured}
Available categories: {categories}

Suggest search directives for Google Places. Use only available categories.
"""

        try:
            response = await asyncio.wait_for(
                self._get_planning_llm().generate_structured(
                    prompt=prompt,
                    system_prompt=self.SEARCH_SYSTEM_PROMPT,
                    max_tokens=512,
                ),
                timeout=float(self._settings.curator_llm_timeout_seconds),
            )
        except Exception as exc:
            logger.warning(f"Curator LLM search planning failed: {exc}")
            return []

        directives = []
        for item in response.get("directives", []) if isinstance(response, dict) else []:
            category = str(item.get("category", "")).strip()
            if not category or category not in categories:
                continue
            keywords = self._normalize_keywords(item.get("keywords", []))
            try:
                min_count = int(item.get("min_count", 0))
            except (TypeError, ValueError):
                min_count = 0
            if min_count < 10:
                min_count = 10
            priority = str(item.get("priority", "normal")).lower()
            if priority not in {"must", "high", "normal"}:
                priority = "normal"
            directives.append(SearchDirective(
                category=category,
                keywords=keywords,
                min_count=min_count,
                priority=priority,
                block_type=self._block_type_for_category(category),
            ))

        return directives

    def _merge_directives(
        self,
        base_directives: list[SearchDirective],
        llm_directives: list[SearchDirective],
    ) -> list[SearchDirective]:
        merged = {}
        for directive in base_directives + llm_directives:
            key = (directive.category, tuple(directive.keywords))
            existing = merged.get(key)
            if existing is None:
                merged[key] = directive
                continue
            existing.min_count = max(existing.min_count, directive.min_count)
            if directive.priority == "must":
                existing.priority = "must"
            elif directive.priority == "high" and existing.priority != "must":
                existing.priority = "high"
        return list(merged.values())

    async def _fetch_candidates(
        self,
        directives: list[SearchDirective],
        trip_spec,
        db: AsyncSession,
        preference_profile: Optional["POIPreferenceProfile"] = None,
        deadline_ts: Optional[float] = None,
    ) -> dict[str, list[POICandidate]]:
        if not directives:
            return {}

        semaphore = asyncio.Semaphore(5)
        max_per_category = self._settings.agentic_max_candidates_per_category
        from src.infrastructure.database import AsyncSessionLocal
        from src.infrastructure.poi_providers import DBPOIProvider

        categories = {d.category for d in directives}
        min_rating = self._settings.smart_routing_min_rating
        if preference_profile:
            min_rating = max(min_rating, preference_profile.min_rating)

        db_provider = DBPOIProvider(db)
        base_pools = await db_provider.search_pois_bulk(
            city=trip_spec.city,
            all_categories=categories,
            budget=trip_spec.budget,
            limit_per_category=max_per_category,
            city_center_lat=trip_spec.city_center_lat,
            city_center_lon=trip_spec.city_center_lon,
            max_radius_km=50.0,
            min_rating=min_rating,
            include_tags=True,
        )

        async def fetch_one(directive: SearchDirective, limit_override: Optional[int] = None) -> tuple[str, list[POICandidate]]:
            async with semaphore:
                async with AsyncSessionLocal() as session:
                    provider = get_poi_provider(session)
                    limit = limit_override or min(max(directive.min_count, 6), max_per_category)
                    candidates = await provider.search_pois(
                        city=trip_spec.city,
                        desired_categories=[directive.category],
                        budget=trip_spec.budget,
                        limit=limit,
                        center_location=trip_spec.hotel_location,
                        city_center_lat=trip_spec.city_center_lat,
                        city_center_lon=trip_spec.city_center_lon,
                        block_type=directive.block_type,
                        search_keywords=directive.keywords or None,
                        fetch_details=False,
                    )
                    return directive.category, candidates

        missing = []
        for directive in directives:
            existing = base_pools.get(directive.category, [])
            needed = max(0, directive.min_count - len(existing))
            if needed <= 0:
                continue
            priority_score = 2 if directive.priority == "must" else 1 if directive.priority == "high" else 0
            missing.append((priority_score, needed, directive))

        missing.sort(key=lambda item: (item[0], item[1]), reverse=True)
        max_external_categories = max(4, self._settings.agentic_llm_scoring_max_categories + 1)
        missing = missing[:max_external_categories]

        results = []
        if missing:
            if deadline_ts is not None:
                remaining = deadline_ts - time.monotonic()
                if remaining <= 0:
                    return base_pools
                if remaining < 8:
                    return base_pools
            total_candidates = sum(len(pool) for pool in base_pools.values())
            allow_normal = total_candidates < 40
            budget_remaining = 12
            if deadline_ts is not None:
                remaining = deadline_ts - time.monotonic()
                if remaining < 15:
                    budget_remaining = min(budget_remaining, 6)
            tasks = []
            for _, needed, directive in missing:
                if directive.priority == "normal" and not allow_normal:
                    continue
                if budget_remaining <= 0:
                    break
                limit = min(needed, budget_remaining, max_per_category)
                tasks.append(fetch_one(directive, limit_override=limit))
                budget_remaining -= limit
            if tasks:
                if deadline_ts is None:
                    results = await asyncio.gather(*tasks)
                else:
                    remaining = max(1.0, deadline_ts - time.monotonic())
                    try:
                        results = await asyncio.wait_for(
                            asyncio.gather(*tasks),
                            timeout=remaining,
                        )
                    except Exception:
                        results = []

        by_category: dict[str, list[POICandidate]] = defaultdict(list)
        for category, candidates in base_pools.items():
            if candidates:
                by_category[category].extend(candidates)
        for category, candidates in results:
            if candidates:
                by_category[category].extend(candidates)
        return by_category

    async def _score_candidates_with_llm(
        self,
        trip_spec,
        preference_profile: Optional["POIPreferenceProfile"],
        candidates_by_category: dict[str, list[POICandidate]],
        directives: list[SearchDirective],
    ) -> dict[UUID, float]:
        if (
            not candidates_by_category
            or not self._settings.enable_agentic_planning
            or self._settings.agentic_llm_scoring_max_categories <= 0
        ):
            return {}
        preference_signals = []
        if preference_profile:
            preference_signals = (
                preference_profile.must_include_keywords
                + list(preference_profile.tag_boosts.keys())
                + preference_profile.search_keywords
            )
        if not (trip_spec.structured_preferences or preference_signals):
            return {}

        categories_priority = []
        for directive in directives:
            if directive.priority == "must":
                priority_score = 2
            elif directive.priority == "high":
                priority_score = 1
            else:
                priority_score = 0
            categories_priority.append((priority_score, directive.category))

        categories_priority.sort(reverse=True)
        selected_categories = []
        for _, category in categories_priority:
            if category not in selected_categories:
                selected_categories.append(category)
            if len(selected_categories) >= self._settings.agentic_llm_scoring_max_categories:
                break

        llm_scores: dict[UUID, float] = {}
        for category in selected_categories:
            candidates = candidates_by_category.get(category, [])
            if not candidates:
                continue

            candidates.sort(key=lambda c: (c.rank_score or 0.0, c.rating or 0.0), reverse=True)
            sample = candidates[:self._settings.poi_selection_max_candidates]

            payload = []
            for candidate in sample:
                payload.append({
                    "candidate_id": str(candidate.poi_id),
                    "name": candidate.name,
                    "category": candidate.category,
                    "tags": candidate.tags[:5] if candidate.tags else [],
                    "rating": candidate.rating,
                    "price_level": candidate.price_level,
                    "description": (candidate.description or "")[:140],
                    "reviews": candidate.reviews[:1] if candidate.reviews else [],
                })

            preference_summary = {
                "interests": trip_spec.interests,
                "budget": trip_spec.budget.value,
                "pace": trip_spec.pace.value,
                "structured_preferences": [p.model_dump() for p in (trip_spec.structured_preferences or [])],
            }

            prompt = f"""Trip preferences:
{preference_summary}

Category: {category}

Candidates:
{payload}
"""

            try:
                response = await asyncio.wait_for(
                    self._get_scoring_llm().generate_structured(
                        prompt=prompt,
                        system_prompt=self.SCORE_SYSTEM_PROMPT,
                        max_tokens=768,
                    ),
                    timeout=10,
                )
            except Exception as exc:
                logger.warning(f"Curator LLM scoring failed for {category}: {exc}")
                continue

            for item in response.get("scores", []) if isinstance(response, dict) else []:
                candidate_id = item.get("candidate_id")
                try:
                    score = float(item.get("score", 0))
                except (TypeError, ValueError):
                    continue
                if not candidate_id:
                    continue
                for candidate in sample:
                    if str(candidate.poi_id) == str(candidate_id):
                        llm_scores[candidate.poi_id] = max(0.0, min(100.0, score))
                        break

        return llm_scores

    async def _prioritize_candidates_with_llm(
        self,
        trip_spec,
        preference_profile: Optional["POIPreferenceProfile"],
        candidates: list[POICandidate],
        clustering_result: Optional["ClusteringResult"],
        deadline_ts: Optional[float],
    ) -> tuple[list[UUID], list[UUID], Optional[str]]:
        if not candidates or not self._settings.enable_agentic_planning:
            return [], [], None
        if deadline_ts is not None:
            remaining = deadline_ts - time.monotonic()
            if remaining <= float(self._settings.curator_llm_timeout_seconds):
                return [], [], None

        ranked = sorted(
            candidates,
            key=lambda c: (c.rank_score or 0.0, c.rating or 0.0),
            reverse=True,
        )
        sample = ranked[:40]
        district_lookup = {}
        if clustering_result and clustering_result.districts:
            for district in clustering_result.districts.values():
                for poi in district.pois:
                    district_lookup[poi.poi_id] = district.district_id

        payload = []
        for candidate in sample:
            payload.append({
                "candidate_id": str(candidate.poi_id),
                "name": candidate.name,
                "category": candidate.category,
                "tags": candidate.tags[:5] if candidate.tags else [],
                "rating": candidate.rating,
                "price_level": candidate.price_level,
                "district_id": district_lookup.get(candidate.poi_id),
            })

        preference_summary = {
            "interests": trip_spec.interests,
            "budget": trip_spec.budget.value,
            "pace": trip_spec.pace.value,
            "structured_preferences": [p.model_dump() for p in (trip_spec.structured_preferences or [])],
            "must_include_keywords": preference_profile.must_include_keywords if preference_profile else [],
        }

        prompt = f"""Trip preferences:
{preference_summary}

Candidates:
{payload}
"""

        try:
            response = await asyncio.wait_for(
                self._get_scoring_llm().generate_structured(
                    prompt=prompt,
                    system_prompt=self.PRIORITIZE_SYSTEM_PROMPT,
                    max_tokens=512,
                ),
                timeout=float(self._settings.curator_llm_timeout_seconds),
            )
        except Exception as exc:
            logger.warning(f"Curator LLM prioritization failed: {exc}")
            return [], [], None

        must_ids = []
        nice_ids = []
        notes = None
        if isinstance(response, dict):
            must_ids = [item for item in response.get("must_visit_ids", []) if isinstance(item, str)]
            nice_ids = [item for item in response.get("nice_to_have_ids", []) if isinstance(item, str)]
            notes = response.get("notes")

        valid_ids = {str(c.poi_id) for c in sample}
        parsed_must = []
        for item in must_ids:
            if item not in valid_ids:
                continue
            try:
                parsed_must.append(UUID(item))
            except ValueError:
                continue
        parsed_must = parsed_must[:10]

        parsed_nice = []
        for item in nice_ids:
            if item not in valid_ids:
                continue
            if item in {str(mid) for mid in parsed_must}:
                continue
            try:
                parsed_nice.append(UUID(item))
            except ValueError:
                continue
        parsed_nice = parsed_nice[:20]
        return parsed_must, parsed_nice, notes
        return must_ids, nice_ids, notes

    def _prioritize_candidates_heuristic(
        self,
        trip_spec,
        preference_profile: Optional["POIPreferenceProfile"],
        candidates: list[POICandidate],
    ) -> tuple[list[UUID], list[UUID]]:
        if not candidates:
            return [], []
        must_ids = []
        nice_ids = []

        if preference_profile:
            for pref in trip_spec.structured_preferences or []:
                for candidate in candidates:
                    if self._candidate_matches_preference(candidate, pref):
                        must_ids.append(candidate.poi_id)

            for keyword in preference_profile.must_include_keywords:
                keyword = keyword.lower()
                for candidate in candidates:
                    haystack = f"{candidate.name} {' '.join(candidate.tags or [])}".lower()
                    if keyword and keyword in haystack:
                        must_ids.append(candidate.poi_id)

        must_unique = []
        seen = set()
        for poi_id in must_ids:
            if poi_id not in seen:
                must_unique.append(poi_id)
                seen.add(poi_id)
        must_unique = must_unique[:10]

        ranked = sorted(
            candidates,
            key=lambda c: (c.rank_score or 0.0, c.rating or 0.0),
            reverse=True,
        )
        for candidate in ranked:
            if candidate.poi_id in seen:
                continue
            nice_ids.append(candidate.poi_id)
            if len(nice_ids) >= 20:
                break
        return must_unique, nice_ids

    async def expand_candidates(
        self,
        requests: list[SearchDirective],
        trip_spec,
        db: AsyncSession,
        curated_bank: CuratedPOIBank,
        preference_profile: Optional["POIPreferenceProfile"],
        deadline_ts: Optional[float],
    ) -> CuratedPOIBank:
        if not requests:
            return curated_bank

        if deadline_ts is not None:
            remaining = deadline_ts - time.monotonic()
            if remaining <= 0:
                return curated_bank

        semaphore = asyncio.Semaphore(3)
        from src.infrastructure.database import AsyncSessionLocal

        async def fetch_one(directive: SearchDirective) -> tuple[str, list[POICandidate]]:
            async with semaphore:
                async with AsyncSessionLocal() as session:
                    provider = get_poi_provider(session)
                    limit = min(max(directive.min_count, 4), self._settings.agentic_max_candidates_per_category)
                    candidates = await provider.search_pois(
                        city=trip_spec.city,
                        desired_categories=[directive.category],
                        budget=trip_spec.budget,
                        limit=limit,
                        center_location=trip_spec.hotel_location,
                        city_center_lat=trip_spec.city_center_lat,
                        city_center_lon=trip_spec.city_center_lon,
                        block_type=directive.block_type,
                        search_keywords=directive.keywords or None,
                        fetch_details=False,
                    )
                    return directive.category, candidates

        tasks = []
        for directive in requests[:3]:
            tasks.append(fetch_one(directive))

        results = []
        if tasks:
            if deadline_ts is None:
                results = await asyncio.gather(*tasks)
            else:
                remaining = max(1.0, deadline_ts - time.monotonic())
                try:
                    results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=remaining)
                except Exception:
                    results = []

        if not results:
            return curated_bank

        deduped: dict[UUID, POICandidate] = {c.poi_id: c for c in curated_bank.candidates}
        for _, candidates in results:
            for candidate in candidates:
                existing = deduped.get(candidate.poi_id)
                if not existing or (candidate.rank_score or 0) > (existing.rank_score or 0):
                    deduped[candidate.poi_id] = candidate
        curated_bank.candidates = list(deduped.values())

        for category, candidates in results:
            if not candidates:
                continue
            curated_bank.candidates_by_category.setdefault(category, [])
            curated_bank.candidates_by_category[category].extend(candidates)

        return curated_bank

    def _cluster_candidates(self, candidates: list[POICandidate], trip_spec):
        if not candidates:
            return None

        from src.application.geo_clustering import GeoClusterer

        clusterer = GeoClusterer(
            cell_size_km=self._settings.cluster_cell_size_km,
            min_pois_per_district=self._settings.min_pois_per_district,
            max_districts=self._settings.max_districts_per_city,
        )
        return clusterer.cluster_pois(
            pois=[c for c in candidates if c.lat is not None and c.lon is not None],
            hotel_lat=trip_spec.hotel_lat,
            hotel_lon=trip_spec.hotel_lon,
            city_center_lat=trip_spec.city_center_lat,
            city_center_lon=trip_spec.city_center_lon,
        )

    async def curate_poi_bank(
        self,
        trip_spec,
        macro_plan,
        db: AsyncSession,
        preference_profile: Optional["POIPreferenceProfile"] = None,
        deadline_ts: Optional[float] = None,
    ) -> CuratedPOIBank:
        base_directives = self._build_deterministic_directives(macro_plan, trip_spec)
        llm_directives = []
        if self._settings.enable_agentic_planning:
            if deadline_ts is not None:
                remaining = deadline_ts - time.monotonic()
                if remaining <= float(self._settings.curator_llm_timeout_seconds):
                    remaining = 0
            else:
                remaining = None
            if remaining is None or remaining > 0:
                llm_directives = await self._build_llm_directives(
                    trip_spec,
                    macro_plan,
                    base_directives,
                    preference_profile,
                )
        directives = self._merge_directives(base_directives, llm_directives)

        candidates_by_category = await self._fetch_candidates(
            directives,
            trip_spec,
            db,
            preference_profile=preference_profile,
            deadline_ts=deadline_ts,
        )

        # Deduplicate and keep best rank_score
        deduped: dict[UUID, POICandidate] = {}
        for candidates in candidates_by_category.values():
            for candidate in candidates:
                existing = deduped.get(candidate.poi_id)
                if not existing or (candidate.rank_score or 0) > (existing.rank_score or 0):
                    deduped[candidate.poi_id] = candidate

        candidates = list(deduped.values())
        llm_scores = await self._score_candidates_with_llm(
            trip_spec,
            preference_profile,
            candidates_by_category,
            directives,
        )

        clustering_result = self._cluster_candidates(candidates, trip_spec)

        must_ids, nice_ids, notes = await self._prioritize_candidates_with_llm(
            trip_spec=trip_spec,
            preference_profile=preference_profile,
            candidates=candidates,
            clustering_result=clustering_result,
            deadline_ts=deadline_ts,
        )
        if not must_ids and not nice_ids:
            must_ids, nice_ids = self._prioritize_candidates_heuristic(
                trip_spec=trip_spec,
                preference_profile=preference_profile,
                candidates=candidates,
            )

        return CuratedPOIBank(
            candidates=candidates,
            candidates_by_category=candidates_by_category,
            llm_scores=llm_scores,
            directives=directives,
            clustering_result=clustering_result,
            must_visit_ids=must_ids,
            nice_to_have_ids=nice_ids,
            curator_notes=notes,
        )
