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
from uuid import UUID
from typing import Optional
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
from src.infrastructure.poi_providers import POIProvider, get_poi_provider, haversine_distance_km
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

    async def generate_poi_plan(
        self,
        trip_id: UUID,
        db: AsyncSession,
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
        trip_selected_poi_ids = []

        for day in macro_plan.days:
            # Track POIs already selected for this day (for LLM deduplication)
            day_selected_poi_ids = []
            # Count POI-needing blocks in this day for hotel anchor
            poi_block_count_in_day = 0

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
                )

                # Apply hotel anchor bias for first N POI-needing blocks of the day
                if hotel_anchor_enabled and poi_block_count_in_day <= hotel_anchor_blocks:
                    logger.debug(
                        f"Applying hotel anchor to day {day.day_number}, "
                        f"POI block {poi_block_count_in_day} of {hotel_anchor_blocks}"
                    )
                    candidates = self._apply_hotel_anchor_bias(
                        candidates=candidates,
                        hotel_lat=trip_spec.hotel_lat,
                        hotel_lon=trip_spec.hotel_lon,
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

                # Select final candidates
                if self.use_llm_selection and candidates:
                    # Use LLM to select from candidates
                    day_context = DayContext(
                        day_number=day.day_number,
                        date=str(day.date),
                        theme=day.theme,
                        already_selected_poi_ids=day_selected_poi_ids.copy(),
                    )
                    block_context = BlockContext(
                        block_index=block_index,
                        block_type=block.block_type,
                        start_time=str(block.start_time),
                        end_time=str(block.end_time),
                        theme=block.theme,
                        desired_categories=block.desired_categories,
                    )

                    selected_candidates = await self.poi_selection_llm.select_pois_for_block(
                        trip_context=trip_context,
                        day_context=day_context,
                        block_context=block_context,
                        candidates=candidates,
                        max_results=self.CANDIDATES_PER_BLOCK,
                    )

                    # Track selected POIs for both day-level AND trip-level deduplication
                    for c in selected_candidates:
                        day_selected_poi_ids.append(c.poi_id)
                        trip_selected_poi_ids.append(c.poi_id)

                    candidates = selected_candidates
                else:
                    # Deterministic mode: use candidates as-is (already sorted by rank_score)
                    # Track for both day-level AND trip-level deduplication
                    for c in candidates[:self.CANDIDATES_PER_BLOCK]:
                        day_selected_poi_ids.append(c.poi_id)
                        trip_selected_poi_ids.append(c.poi_id)
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
