"""
Route & Time Optimizer service.
Generates final itinerary by selecting POIs and assigning concrete times.

Supports two modes:
1. Classic mode (default fallback): Deterministic POI selection + local optimization
2. Smart mode (new): District-based clustering + LLM planning for optimal walking routes

Features:
- Selects best POI for each block
- Optimizes block order within reorderable clusters (minimizes travel)
- Enforces max travel time per hop constraints
- Calculates accurate travel times and distances
- [Smart mode] Groups POIs by districts for logical walking routes
"""
import logging
import asyncio
import json
import itertools
import time
from uuid import UUID
from typing import Optional
from datetime import datetime
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings, Settings
from src.domain.models import ItineraryDay, ItineraryBlock, POICandidate, BlockType, DaySkeleton
from src.domain.schemas import POIPlanBlock, ItineraryResponse
from src.application.trip_spec import TripSpecCollector
from src.application.macro_planner import MacroPlanner
from src.application.poi_selection_llm import (
    POISelectionLLMService,
    DayContext,
    BlockContext,
    build_trip_context_from_response,
)
from src.application.poi_agent import (
    POIPreferenceAgent,
    POIPreferenceProfile,
    score_candidate,
    filter_candidates_for_block,
    normalize_category,
)
from src.application.poi_planner import POICuratorAgent, SearchDirective
from src.infrastructure.travel_time import TravelTimeProvider, TravelLocation, get_travel_time_provider
from src.infrastructure.llm_client import LLMClient, get_route_engineer_llm_client
from src.infrastructure.poi_providers import haversine_distance_km
from src.infrastructure.models import ItineraryModel
from src.application.poi_selection_llm import (
    POISelectionLLMService,
    TripContext,
    DayContext,
    BlockContext,
    build_trip_context_from_response,
    normalize_category,
)
from src.application.poi_planner import SearchDirective
from src.application.poi_curator import POICuratorAgent

logger = logging.getLogger(__name__)


@dataclass
class BlockWithPOI:
    """A block paired with its selected POI for optimization."""
    original_index: int  # Original position in the day
    block_type: BlockType
    start_time: any  # datetime.time
    end_time: any  # datetime.time
    theme: Optional[str]
    poi: Optional[POICandidate]
    is_reorderable: bool = False


class RouteTimeOptimizer:
    """
    Service for generating final itinerary with selected POIs and concrete times.
    Deterministic POI selection and travel time calculation.

    Features:
    - Daily route optimization: reorders blocks to minimize travel
    - Max hop constraint: flags or replaces POIs with excessive travel time
    """

    # Block types that need POIs
    BLOCK_TYPES_NEEDING_POIS = {
        BlockType.MEAL,
        BlockType.ACTIVITY,
        BlockType.NIGHTLIFE,
    }

    # Block types that are reorderable (can be swapped to minimize travel)
    # MEAL blocks are NOT reorderable as they have fixed time windows
    REORDERABLE_BLOCK_TYPES = {
        BlockType.ACTIVITY,
        BlockType.NIGHTLIFE,
    }

    ROUTE_ORDER_SYSTEM_PROMPT = """You are a route ordering assistant.
Reorder the given blocks to minimize walking distance between consecutive POIs.
Use the algorithmic suggestions as hints, but you may override them if needed.
You must include every block exactly once and return only JSON."""

    def __init__(
        self,
        travel_time_provider: Optional[TravelTimeProvider] = None,
        app_settings: Optional[Settings] = None,
    ):
        """
        Initialize Route & Time Optimizer.

        Args:
            travel_time_provider: Travel time provider (defaults to heuristic)
            app_settings: Settings override (for testing)
        """
        self.travel_time_provider = travel_time_provider or get_travel_time_provider()
        self._settings = app_settings or settings
        self.trip_spec_collector = TripSpecCollector()
        self.macro_planner = MacroPlanner()
        self._route_order_llm_client: Optional[LLMClient] = None
        self._poi_selection_llm: Optional[POISelectionLLMService] = None

    def _block_needs_poi(self, block_type: BlockType) -> bool:
        """Check if a block type needs a POI."""
        return block_type in self.BLOCK_TYPES_NEEDING_POIS

    def _select_poi_for_block(
        self,
        day_number: int,
        block_index: int,
        poi_plan_blocks: list[POIPlanBlock],
        used_poi_ids: set[UUID],
        block_type: BlockType,
        desired_categories: list[str],
        preference_profile: POIPreferenceProfile,
        anchor_lat: Optional[float] = None,
        anchor_lon: Optional[float] = None,
        day_center_lat: Optional[float] = None,
        day_center_lon: Optional[float] = None,
        candidates_by_block: Optional[dict[tuple[int, int], list[POICandidate]]] = None,
    ) -> Optional[POICandidate]:
        """
        Select the best POI candidate for a block, avoiding duplicates.

        Args:
            day_number: Day number
            block_index: Block index within the day
            poi_plan_blocks: List of all POI plan blocks
            used_poi_ids: Set of POI IDs already selected (for deduplication)

        Returns:
            Selected POICandidate or None if not found
        """
        # Find matching POI plan block
        matching_block = None
        if candidates_by_block is not None:
            matching_candidates = candidates_by_block.get((day_number, block_index), [])
            if not matching_candidates:
                return None
            matching_block = POIPlanBlock(
                day_number=day_number,
                block_index=block_index,
                block_theme="",
                block_type=block_type,
                candidates=matching_candidates,
            )
        else:
            for poi_block in poi_plan_blocks:
                if poi_block.day_number == day_number and poi_block.block_index == block_index:
                    matching_block = poi_block
                    break

            if not matching_block or not matching_block.candidates:
                return None

        # Debug logging
        candidate_info = [(c.name, str(c.poi_id)[:8]) for c in matching_block.candidates[:5]]
        logger.info(
            f"Day {day_number}, Block {block_index}: "
            f"Selecting from {len(matching_block.candidates)} candidates: {candidate_info}"
        )
        logger.info(f"Already used POIs: {len(used_poi_ids)} unique IDs")

        available = [c for c in matching_block.candidates if c.poi_id not in used_poi_ids]
        if not available:
            logger.warning(
                f"❌ All {len(matching_block.candidates)} POI candidates for day {day_number}, "
                f"block {block_index} are already used. Leaving block without POI."
            )
            return None

        available = filter_candidates_for_block(
            candidates=available,
            profile=preference_profile,
            block_type=block_type,
        )

        scored = []
        for candidate in available:
            scored.append((
                score_candidate(
                    candidate=candidate,
                    block_type=block_type,
                    desired_categories=desired_categories,
                    profile=preference_profile,
                    anchor_lat=anchor_lat,
                    anchor_lon=anchor_lon,
                    day_center_lat=day_center_lat,
                    day_center_lon=day_center_lon,
                    distance_weight=self._settings.hotel_anchor_distance_weight,
                ),
                candidate,
            ))

        scored.sort(key=lambda item: item[0], reverse=True)
        selected = scored[0][1]
        used_poi_ids.add(selected.poi_id)
        logger.info(
            f"✓ Selected: {selected.name} (ID: {str(selected.poi_id)[:8]}...)"
        )
        return selected

    def _is_block_reorderable(self, block_type: BlockType) -> bool:
        """Check if a block type can be reordered for route optimization."""
        return block_type in self.REORDERABLE_BLOCK_TYPES

    def _calculate_travel_cost_km(
        self,
        poi1: Optional[POICandidate],
        poi2: Optional[POICandidate],
    ) -> float:
        """
        Calculate travel cost between two POIs using haversine distance.
        Uses straight-line distance as a cheap proxy for actual travel cost.

        Returns:
            Distance in km, or 0 if coordinates are missing.
        """
        if poi1 is None or poi2 is None:
            return 0.0
        if poi1.lat is None or poi1.lon is None or poi2.lat is None or poi2.lon is None:
            return 0.0
        return haversine_distance_km(poi1.lat, poi1.lon, poi2.lat, poi2.lon)

    def _calculate_cluster_travel_cost(
        self,
        blocks: list[BlockWithPOI],
        prev_poi: Optional[POICandidate],
        next_poi: Optional[POICandidate],
    ) -> float:
        """
        Calculate total travel cost for a sequence of blocks.

        Includes:
        - Travel from prev_poi to first block (if prev_poi exists)
        - Travel between all blocks in sequence
        - Travel from last block to next_poi (if next_poi exists)

        Args:
            blocks: Ordered list of blocks in the cluster
            prev_poi: POI from the block before the cluster (or None)
            next_poi: POI from the block after the cluster (or None)

        Returns:
            Total travel cost in km
        """
        if not blocks:
            return 0.0

        total_cost = 0.0

        # Travel from prev_poi to first block
        if prev_poi is not None and blocks[0].poi is not None:
            total_cost += self._calculate_travel_cost_km(prev_poi, blocks[0].poi)

        # Travel between blocks in cluster
        for i in range(len(blocks) - 1):
            total_cost += self._calculate_travel_cost_km(blocks[i].poi, blocks[i + 1].poi)

        # Travel from last block to next_poi
        if next_poi is not None and blocks[-1].poi is not None:
            total_cost += self._calculate_travel_cost_km(blocks[-1].poi, next_poi)

        return total_cost

    def _distance_from_anchor_km(
        self,
        anchor_lat: Optional[float],
        anchor_lon: Optional[float],
        poi: Optional[POICandidate],
    ) -> float:
        """Calculate distance between an anchor point and a POI."""
        if poi is None or poi.lat is None or poi.lon is None:
            return 0.0
        if anchor_lat is None or anchor_lon is None:
            return 0.0
        return haversine_distance_km(anchor_lat, anchor_lon, poi.lat, poi.lon)

    def _find_alternative_poi(
        self,
        candidates: list[POICandidate],
        used_poi_ids: set[UUID],
        current_poi: POICandidate,
        block_type: BlockType,
        desired_categories: list[str],
        preference_profile: POIPreferenceProfile,
        prev_anchor_lat: Optional[float],
        prev_anchor_lon: Optional[float],
        next_poi: Optional[POICandidate],
        day_center_lat: Optional[float],
        day_center_lon: Optional[float],
        max_hop_distance_km: float,
    ) -> Optional[POICandidate]:
        """Find a candidate that improves hop distances while preserving preferences."""
        best_candidate = None
        best_score = float("-inf")
        best_max_dist = None

        for candidate in candidates:
            if candidate.poi_id in used_poi_ids and candidate.poi_id != current_poi.poi_id:
                continue
            if candidate.lat is None or candidate.lon is None:
                continue

            dist_prev = self._distance_from_anchor_km(
                prev_anchor_lat, prev_anchor_lon, candidate
            )
            dist_next = self._calculate_travel_cost_km(candidate, next_poi)
            max_dist = max(dist_prev, dist_next)

            base_score = score_candidate(
                candidate=candidate,
                block_type=block_type,
                desired_categories=desired_categories,
                profile=preference_profile,
                anchor_lat=prev_anchor_lat,
                anchor_lon=prev_anchor_lon,
                day_center_lat=day_center_lat,
                day_center_lon=day_center_lon,
                distance_weight=self._settings.hotel_anchor_distance_weight,
            )

            score = base_score - (dist_next * self._settings.hotel_anchor_distance_weight)

            if max_dist > max_hop_distance_km:
                score -= (max_dist - max_hop_distance_km) * 2.0

            if score > best_score:
                best_candidate = candidate
                best_score = score
                best_max_dist = max_dist

        if best_candidate is None:
            return None

        current_prev = self._distance_from_anchor_km(
            prev_anchor_lat, prev_anchor_lon, current_poi
        )
        current_next = self._calculate_travel_cost_km(current_poi, next_poi)
        current_max = max(current_prev, current_next)

        if best_max_dist is None:
            return None

        if best_max_dist <= max_hop_distance_km or best_max_dist < current_max:
            return best_candidate

        return None

    def _repair_long_hops(
        self,
        blocks: list[BlockWithPOI],
        day_number: int,
        day_skeleton: DaySkeleton,
        candidates_by_block: dict[tuple[int, int], list[POICandidate]],
        used_poi_ids: set[UUID],
        preference_profile: POIPreferenceProfile,
        day_anchor_lat: Optional[float],
        day_anchor_lon: Optional[float],
        day_center_lat: Optional[float],
        day_center_lon: Optional[float],
    ) -> list[BlockWithPOI]:
        """Attempt to replace POIs that create long travel hops."""
        if not self._settings.enable_travel_hop_limit:
            return blocks

        max_hop_distance_km = self._settings.max_hop_distance_km
        if max_hop_distance_km <= 0:
            return blocks

        for _ in range(2):
            prev_poi = None
            prev_anchor_lat = day_anchor_lat
            prev_anchor_lon = day_anchor_lon

            for i, block in enumerate(blocks):
                if block.poi is None or block.poi.lat is None or block.poi.lon is None:
                    if block.poi and block.poi.lat is not None and block.poi.lon is not None:
                        prev_poi = block.poi
                        prev_anchor_lat = block.poi.lat
                        prev_anchor_lon = block.poi.lon
                    continue

                # Find next POI with coordinates
                next_poi = None
                for j in range(i + 1, len(blocks)):
                    candidate_poi = blocks[j].poi
                    if candidate_poi and candidate_poi.lat is not None and candidate_poi.lon is not None:
                        next_poi = candidate_poi
                        break

                dist_prev = self._distance_from_anchor_km(
                    prev_anchor_lat, prev_anchor_lon, block.poi
                )
                dist_next = self._calculate_travel_cost_km(block.poi, next_poi)
                max_dist = max(dist_prev, dist_next)

                if max_dist > max_hop_distance_km:
                    block_candidates = candidates_by_block.get(
                        (day_number, block.original_index), []
                    )
                    skeleton_block = day_skeleton.blocks[block.original_index]
                    replacement = self._find_alternative_poi(
                        candidates=block_candidates,
                        used_poi_ids=used_poi_ids,
                        current_poi=block.poi,
                        block_type=block.block_type,
                        desired_categories=skeleton_block.desired_categories,
                        preference_profile=preference_profile,
                        prev_anchor_lat=prev_anchor_lat,
                        prev_anchor_lon=prev_anchor_lon,
                        next_poi=next_poi,
                        day_center_lat=day_center_lat,
                        day_center_lon=day_center_lon,
                        max_hop_distance_km=max_hop_distance_km,
                    )

                    if replacement and replacement.poi_id != block.poi.poi_id:
                        logger.info(
                            f"Replacing POI to reduce hop distance: "
                            f"{block.poi.name} -> {replacement.name}"
                        )
                        used_poi_ids.discard(block.poi.poi_id)
                        used_poi_ids.add(replacement.poi_id)
                        block.poi = replacement

                prev_poi = block.poi
                if block.poi and block.poi.lat is not None and block.poi.lon is not None:
                    prev_anchor_lat = block.poi.lat
                    prev_anchor_lon = block.poi.lon

        return blocks

    def _find_reorderable_clusters(
        self,
        blocks: list[BlockWithPOI],
    ) -> list[tuple[int, int]]:
        """
        Find contiguous sequences of reorderable blocks.

        Returns:
            List of (start_index, end_index) tuples for each cluster.
            Indices are inclusive.
        """
        clusters = []
        i = 0
        while i < len(blocks):
            if blocks[i].is_reorderable and blocks[i].poi is not None:
                # Start of a potential cluster
                start = i
                while i < len(blocks) and blocks[i].is_reorderable and blocks[i].poi is not None:
                    i += 1
                end = i - 1
                # Only consider clusters with 2+ blocks
                if end > start:
                    clusters.append((start, end))
            else:
                i += 1
        return clusters

    def _get_route_order_llm_client(self) -> Optional[LLMClient]:
        """Lazy initialization of LLM client for route ordering."""
        if not self._settings.use_llm_for_route_optimization:
            return None
        if self._route_order_llm_client is not None:
            return self._route_order_llm_client
        try:
            self._route_order_llm_client = get_route_engineer_llm_client(self._settings)
        except Exception as exc:
            logger.warning(f"Route ordering LLM unavailable, using deterministic: {exc}")
            self._route_order_llm_client = None
        return self._route_order_llm_client

    def _get_poi_selection_llm(self) -> POISelectionLLMService:
        """Lazy initialization of POI selection LLM service."""
        if self._poi_selection_llm is None:
            self._poi_selection_llm = POISelectionLLMService(app_settings=self._settings)
        return self._poi_selection_llm

    def _build_preference_summary(self, profile: POIPreferenceProfile) -> dict:
        return {
            "must_include_keywords": profile.must_include_keywords,
            "avoid_keywords": profile.avoid_keywords,
            "search_keywords": profile.search_keywords,
            "category_boosts": profile.category_boosts,
            "tag_boosts": profile.tag_boosts,
            "min_rating": profile.min_rating,
            "preferred_price_levels": profile.preferred_price_levels,
            "structured_preferences": [p.model_dump() for p in profile.structured_preferences or []],
        }

    def _block_type_for_request_category(self, category: str) -> BlockType:
        if category in {"restaurant", "cafe", "bakery", "food"}:
            return BlockType.MEAL
        if category in {"bar", "nightlife"}:
            return BlockType.NIGHTLIFE
        return BlockType.ACTIVITY

    def _normalize_llm_requests(self, raw_requests: list[dict]) -> list[SearchDirective]:
        directives: list[SearchDirective] = []
        seen_categories: set[str] = set()

        for item in raw_requests or []:
            if not isinstance(item, dict):
                continue
            category = normalize_category(item.get("category"))
            if not category or category in seen_categories:
                continue
            keywords_raw = item.get("keywords", [])
            keywords: list[str] = []
            if isinstance(keywords_raw, list):
                for keyword in keywords_raw:
                    keyword = str(keyword).strip().lower()
                    if keyword and keyword not in keywords:
                        keywords.append(keyword)

            try:
                min_count = int(item.get("min_count", 0))
            except (TypeError, ValueError):
                min_count = 0
            if min_count <= 0:
                min_count = self._settings.agentic_min_candidates_per_category
            min_count = min(
                max(min_count, self._settings.agentic_min_candidates_per_category),
                self._settings.agentic_max_candidates_per_category,
            )

            priority = item.get("priority", "normal")
            if priority not in {"must", "high", "normal"}:
                priority = "normal"

            directives.append(SearchDirective(
                category=category,
                keywords=keywords[:4],
                min_count=min_count,
                priority=priority,
                block_type=self._block_type_for_request_category(category),
            ))
            seen_categories.add(category)
            if len(directives) >= 3:
                break

        return directives

    def _dedupe_day_selections(
        self,
        selected_by_block: dict[int, POICandidate],
        candidates_by_block: dict[int, list[POICandidate]],
        used_poi_ids: set[UUID],
        used_poi_names: set[str],
    ) -> dict[int, POICandidate]:
        """Ensure unique POIs (by ID and name) within a day AND across the entire trip."""
        deduped: dict[int, POICandidate] = {}
        seen_ids: set[UUID] = set()
        seen_names: set[str] = set()

        for block_index in sorted(candidates_by_block.keys()):
            candidate = selected_by_block.get(block_index)
            # STRICT: Check both within-day and trip-wide uniqueness (by ID and name)
            if (candidate and
                candidate.poi_id not in seen_ids and
                candidate.poi_id not in used_poi_ids and
                candidate.name not in seen_names and
                candidate.name not in used_poi_names):
                deduped[block_index] = candidate
                seen_ids.add(candidate.poi_id)
                seen_names.add(candidate.name)
                continue

            # Find unused replacement (strict - no reuse by ID or name across trip)
            replacement = None
            for alt in candidates_by_block.get(block_index, []):
                if (alt.poi_id in seen_ids or
                    alt.poi_id in used_poi_ids or
                    alt.name in seen_names or
                    alt.name in used_poi_names):
                    continue
                replacement = alt
                break

            if replacement:
                deduped[block_index] = replacement
                seen_ids.add(replacement.poi_id)
                seen_names.add(replacement.name)

        return deduped

    def _suggest_cluster_order(
        self,
        cluster_blocks: list[BlockWithPOI],
        prev_poi: Optional[POICandidate],
        next_poi: Optional[POICandidate],
    ) -> tuple[list[int], float]:
        """Produce a heuristic order for LLM hints."""
        remaining = [block for block in cluster_blocks]
        if not remaining:
            return [], 0.0

        def distance(a: Optional[POICandidate], b: Optional[POICandidate]) -> float:
            return self._calculate_travel_cost_km(a, b)

        current_poi = prev_poi or remaining[0].poi
        ordered: list[BlockWithPOI] = []
        while remaining:
            next_block = min(
                remaining,
                key=lambda block: distance(current_poi, block.poi),
            )
            ordered.append(next_block)
            remaining.remove(next_block)
            current_poi = next_block.poi

        improved = self._two_opt_order(ordered, prev_poi, next_poi)
        cost = self._calculate_cluster_travel_cost(improved, prev_poi, next_poi)
        return [block.original_index for block in improved], cost

    def _two_opt_order(
        self,
        blocks: list[BlockWithPOI],
        prev_poi: Optional[POICandidate],
        next_poi: Optional[POICandidate],
    ) -> list[BlockWithPOI]:
        """Lightweight 2-opt improvement on block order."""
        if len(blocks) < 3:
            return blocks

        def total_cost(order: list[BlockWithPOI]) -> float:
            return self._calculate_cluster_travel_cost(order, prev_poi, next_poi)

        best = list(blocks)
        best_cost = total_cost(best)
        improved = True
        while improved:
            improved = False
            for i in range(1, len(best) - 1):
                for j in range(i + 1, len(best)):
                    candidate = best[:i] + list(reversed(best[i:j])) + best[j:]
                    candidate_cost = total_cost(candidate)
                    if candidate_cost + 1e-3 < best_cost:
                        best = candidate
                        best_cost = candidate_cost
                        improved = True
        return best

    def _build_route_order_prompt(
        self,
        cluster_blocks: list[BlockWithPOI],
        prev_poi: Optional[POICandidate],
        next_poi: Optional[POICandidate],
    ) -> str:
        """Build prompt for LLM-based cluster ordering."""
        blocks_payload = []
        for block in cluster_blocks:
            if not block.poi or block.poi.lat is None or block.poi.lon is None:
                continue
            blocks_payload.append({
                "block_index": block.original_index,
                "type": block.block_type.value,
                "time": f"{block.start_time} - {block.end_time}",
                "poi_id": str(block.poi.poi_id),
                "name": block.poi.name,
                "lat": round(block.poi.lat, 5),
                "lon": round(block.poi.lon, 5),
                "rating": block.poi.rating,
                "category": block.poi.category,
            })

        anchor_payload = {
            "prev": {
                "lat": round(prev_poi.lat, 5),
                "lon": round(prev_poi.lon, 5),
            } if prev_poi and prev_poi.lat is not None and prev_poi.lon is not None else None,
            "next": {
                "lat": round(next_poi.lat, 5),
                "lon": round(next_poi.lon, 5),
            } if next_poi and next_poi.lat is not None and next_poi.lon is not None else None,
        }

        suggested_order, suggested_cost = self._suggest_cluster_order(
            cluster_blocks=cluster_blocks,
            prev_poi=prev_poi,
            next_poi=next_poi,
        )

        suggestion_payload = {
            "suggested_order_indices": suggested_order,
            "suggested_cost_km": round(suggested_cost, 2),
        }

        prompt = f"""Order these blocks to minimize walking distance.

Anchors (optional):
{json.dumps(anchor_payload, indent=2)}

Max hop distance (km): {self._settings.max_hop_distance_km}

Algorithmic hints:
{json.dumps(suggestion_payload, indent=2)}

Blocks:
```json
{json.dumps(blocks_payload, indent=2)}
```

Return JSON only:
```json
{{"ordered_block_indices": [0, 1, 2]}}
```
"""

        return prompt

    def _parse_route_order_response(
        self,
        response: dict,
        cluster_blocks: list[BlockWithPOI],
    ) -> Optional[list[BlockWithPOI]]:
        """Validate LLM response for ordering."""
        ordered_indices = response.get("ordered_block_indices")
        if not isinstance(ordered_indices, list):
            return None

        cluster_index_set = {block.original_index for block in cluster_blocks}
        if set(ordered_indices) != cluster_index_set:
            return None

        block_map = {block.original_index: block for block in cluster_blocks}
        ordered_blocks = [block_map[idx] for idx in ordered_indices if idx in block_map]
        if len(ordered_blocks) != len(cluster_blocks):
            return None

        return ordered_blocks

    async def _llm_optimize_cluster_order(
        self,
        cluster_blocks: list[BlockWithPOI],
        prev_poi: Optional[POICandidate],
        next_poi: Optional[POICandidate],
    ) -> Optional[list[BlockWithPOI]]:
        """Use LLM to order a cluster of blocks, with validation."""
        if any(
            block.poi is None or block.poi.lat is None or block.poi.lon is None
            for block in cluster_blocks
        ):
            return None

        llm_client = self._get_route_order_llm_client()
        if llm_client is None:
            return None

        prompt = self._build_route_order_prompt(
            cluster_blocks=cluster_blocks,
            prev_poi=prev_poi,
            next_poi=next_poi,
        )

        try:
            response = await asyncio.wait_for(
                llm_client.generate_structured(
                    prompt=prompt,
                    system_prompt=self.ROUTE_ORDER_SYSTEM_PROMPT,
                    max_tokens=256,
                ),
                timeout=6,
            )
            return self._parse_route_order_response(response, cluster_blocks)
        except asyncio.TimeoutError:
            logger.warning("Route ordering LLM timed out, using deterministic.")
            return None
        except Exception as exc:
            logger.warning(f"Route ordering LLM failed, using deterministic: {exc}")
            return None

    def _optimize_cluster_order(
        self,
        blocks: list[BlockWithPOI],
        cluster_start: int,
        cluster_end: int,
        max_cluster_size: int,
    ) -> list[BlockWithPOI]:
        """
        Find the optimal ordering of blocks within a cluster to minimize travel.

        Uses brute-force permutation search for small clusters.
        For clusters larger than max_cluster_size, returns original order.

        Args:
            blocks: Full list of blocks for the day
            cluster_start: Start index of cluster (inclusive)
            cluster_end: End index of cluster (inclusive)
            max_cluster_size: Maximum cluster size to optimize

        Returns:
            New list of blocks with optimized cluster order
        """
        cluster_size = cluster_end - cluster_start + 1

        if cluster_size > max_cluster_size:
            logger.debug(
                f"Cluster size {cluster_size} exceeds max {max_cluster_size}, skipping optimization"
            )
            return blocks

        # Get cluster blocks
        cluster_blocks = blocks[cluster_start:cluster_end + 1]

        # Get surrounding context
        prev_poi = blocks[cluster_start - 1].poi if cluster_start > 0 else None
        next_poi = blocks[cluster_end + 1].poi if cluster_end < len(blocks) - 1 else None

        # Find best permutation
        best_order = cluster_blocks
        best_cost = self._calculate_cluster_travel_cost(cluster_blocks, prev_poi, next_poi)

        for perm in itertools.permutations(cluster_blocks):
            perm_list = list(perm)
            cost = self._calculate_cluster_travel_cost(perm_list, prev_poi, next_poi)
            if cost < best_cost:
                best_cost = cost
                best_order = perm_list

        # Log optimization result
        if best_order != cluster_blocks:
            original_names = [b.poi.name if b.poi else "?" for b in cluster_blocks]
            optimized_names = [b.poi.name if b.poi else "?" for b in best_order]
            logger.info(
                f"Optimized cluster order: {original_names} -> {optimized_names} "
                f"(cost reduced by {self._calculate_cluster_travel_cost(cluster_blocks, prev_poi, next_poi) - best_cost:.1f}km)"
            )

        # Rebuild blocks list with optimized cluster
        result = list(blocks[:cluster_start]) + list(best_order) + list(blocks[cluster_end + 1:])
        return result

    def _optimize_day_route(
        self,
        blocks: list[BlockWithPOI],
    ) -> list[BlockWithPOI]:
        """
        Optimize the order of blocks within a day to minimize travel.

        Identifies reorderable clusters and optimizes each one.

        Args:
            blocks: List of blocks for the day

        Returns:
            List of blocks with optimized order
        """
        if not self._settings.enable_daily_route_optimization:
            return blocks

        max_cluster_size = self._settings.max_optimization_blocks_per_cluster
        result = list(blocks)

        # Find clusters and optimize each one
        # Note: we process from end to start to avoid index shifting issues
        clusters = self._find_reorderable_clusters(result)

        for cluster_start, cluster_end in reversed(clusters):
            result = self._optimize_cluster_order(
                result, cluster_start, cluster_end, max_cluster_size
            )

        return result

    async def _optimize_day_route_llm(
        self,
        blocks: list[BlockWithPOI],
        deadline_ts: Optional[float] = None,
    ) -> list[BlockWithPOI]:
        """Optimize daily route with optional LLM ordering per cluster."""
        if not self._settings.enable_daily_route_optimization:
            return blocks

        max_cluster_size = self._settings.max_optimization_blocks_per_cluster
        result = list(blocks)

        clusters = self._find_reorderable_clusters(result)
        for cluster_start, cluster_end in reversed(clusters):
            cluster_size = cluster_end - cluster_start + 1
            if cluster_size < 2:
                continue

            cluster_blocks = result[cluster_start:cluster_end + 1]
            prev_poi = result[cluster_start - 1].poi if cluster_start > 0 else None
            next_poi = result[cluster_end + 1].poi if cluster_end < len(result) - 1 else None

            llm_order = None
            if (
                self._settings.use_llm_for_route_optimization
                and cluster_size >= 3
                and cluster_size <= max_cluster_size
            ):
                if deadline_ts is not None:
                    remaining = deadline_ts - time.monotonic()
                    if remaining <= float(self._settings.route_engineer_llm_timeout_seconds):
                        llm_order = None
                    else:
                        llm_order = await self._llm_optimize_cluster_order(
                            cluster_blocks,
                            prev_poi,
                            next_poi,
                        )
                else:
                    llm_order = await self._llm_optimize_cluster_order(
                        cluster_blocks,
                        prev_poi,
                        next_poi,
                    )

            if llm_order:
                llm_cost = self._calculate_cluster_travel_cost(
                    llm_order, prev_poi, next_poi
                )
                deterministic = self._optimize_cluster_order(
                    result, cluster_start, cluster_end, max_cluster_size
                )
                deterministic_cluster = deterministic[cluster_start:cluster_end + 1]
                deterministic_cost = self._calculate_cluster_travel_cost(
                    deterministic_cluster, prev_poi, next_poi
                )

                if llm_cost <= deterministic_cost * 1.25:
                    result = (
                        list(result[:cluster_start])
                        + list(llm_order)
                        + list(result[cluster_end + 1:])
                    )
                else:
                    result = deterministic
            else:
                result = self._optimize_cluster_order(
                    result, cluster_start, cluster_end, max_cluster_size
                )

        return result

    def _matches_structured_preference(
        self,
        candidate: POICandidate,
        preference,
    ) -> bool:
        keyword = (preference.keyword or "").lower()
        category = normalize_category(preference.category)

        if category:
            candidate_category = (candidate.category or "").lower()
            if category not in candidate_category:
                if not candidate.tags or not any(category == tag.lower() for tag in candidate.tags):
                    return False

        if keyword:
            haystack = f"{candidate.name} {' '.join(candidate.tags or [])} {candidate.description or ''}".lower()
            if keyword not in haystack:
                return False

        if preference.price_level and candidate.price_level is not None:
            price_map = {"cheap": [0, 1], "moderate": [2], "expensive": [3, 4]}
            if candidate.price_level not in price_map.get(preference.price_level, []):
                return False

        return True

    def _select_must_include_pois(
        self,
        trip_spec,
        curated_bank,
        preference_profile: POIPreferenceProfile,
    ) -> dict[str, list[POICandidate]]:
        must_include_map: dict[str, list[POICandidate]] = {}
        if not trip_spec.structured_preferences:
            return must_include_map

        for pref in trip_spec.structured_preferences:
            candidates = [
                c for c in curated_bank.candidates
                if self._matches_structured_preference(c, pref)
            ]

            if not candidates:
                candidates = [
                    c for c in curated_bank.candidates
                    if pref.category.lower() in (c.category or "").lower()
                ]

            if not candidates:
                continue

            scored = []
            for candidate in candidates:
                score = score_candidate(
                    candidate=candidate,
                    block_type=self._block_type_for_preference(pref.category),
                    desired_categories=[pref.category],
                    profile=preference_profile,
                    anchor_lat=trip_spec.hotel_lat,
                    anchor_lon=trip_spec.hotel_lon,
                    day_center_lat=trip_spec.city_center_lat,
                    day_center_lon=trip_spec.city_center_lon,
                    distance_weight=self._settings.hotel_anchor_distance_weight,
                )
                llm_score = curated_bank.llm_scores.get(candidate.poi_id, 0.0)
                score += llm_score * self._settings.agentic_llm_score_weight
                scored.append((score, candidate))

            scored.sort(key=lambda item: item[0], reverse=True)
            quantity = pref.quantity or 1
            key = f"{pref.category}:{pref.keyword}".strip()
            must_include_map[key] = [c for _, c in scored[:quantity]]

        return must_include_map

    def _block_type_for_preference(self, category: str) -> BlockType:
        lower = (category or "").lower()
        if lower in {"restaurant", "cafe", "bakery", "food"}:
            return BlockType.MEAL
        if lower in {"bar", "nightlife", "club", "nightclub", "pub"}:
            return BlockType.NIGHTLIFE
        return BlockType.ACTIVITY

    def _assign_must_include_to_blocks(
        self,
        macro_plan,
        must_include_map: dict[str, list[POICandidate]],
    ) -> dict[tuple[int, int], POICandidate]:
        assignments: dict[tuple[int, int], POICandidate] = {}
        if not must_include_map:
            return assignments

        eligible_blocks = []
        for day in macro_plan.days:
            for block_index, block in enumerate(day.blocks):
                if block.block_type not in self.BLOCK_TYPES_NEEDING_POIS:
                    continue
                eligible_blocks.append((day.day_number, block_index, block.block_type, block))

        used_blocks = set()
        for keyword, candidates in must_include_map.items():
            for candidate in candidates:
                placed = False
                for day_number, block_index, block_type, block in eligible_blocks:
                    if (day_number, block_index) in used_blocks:
                        continue
                    if block_type != self._block_type_for_preference(candidate.category):
                        continue
                    assignments[(day_number, block_index)] = candidate
                    used_blocks.add((day_number, block_index))
                    placed = True
                    break
                if not placed:
                    for day_number, block_index, _, _ in eligible_blocks:
                        if (day_number, block_index) in used_blocks:
                            continue
                        assignments[(day_number, block_index)] = candidate
                        used_blocks.add((day_number, block_index))
                        break

        return assignments

    def _rank_candidates_for_block(
        self,
        candidates: list[POICandidate],
        skeleton_block,
        preference_profile: POIPreferenceProfile,
        trip_spec,
        curated_bank,
        anchor_lat: Optional[float],
        anchor_lon: Optional[float],
    ) -> list[POICandidate]:
        must_ids = set(curated_bank.must_visit_ids or [])
        nice_ids = set(curated_bank.nice_to_have_ids or [])
        scored = []
        for candidate in candidates:
            score = score_candidate(
                candidate=candidate,
                block_type=skeleton_block.block_type,
                desired_categories=skeleton_block.desired_categories,
                profile=preference_profile,
                anchor_lat=anchor_lat,
                anchor_lon=anchor_lon,
                day_center_lat=trip_spec.city_center_lat,
                day_center_lon=trip_spec.city_center_lon,
                distance_weight=self._settings.hotel_anchor_distance_weight,
            )
            llm_score = curated_bank.llm_scores.get(candidate.poi_id, 0.0)
            score += llm_score * self._settings.agentic_llm_score_weight
            if candidate.poi_id in must_ids:
                score += 8.0
            elif candidate.poi_id in nice_ids:
                score += 3.5
            scored.append((score, candidate))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [candidate for _, candidate in scored]

    def _build_district_summaries(
        self,
        clustering_result,
        macro_plan,
        preference_profile: POIPreferenceProfile,
    ) -> list[dict]:
        needed_categories = set()
        for day in macro_plan.days:
            for block in day.blocks:
                if self._block_needs_poi(block.block_type):
                    for category in block.desired_categories or []:
                        needed_categories.add(category)

        summaries = []
        keyword_signals = set(preference_profile.must_include_keywords) | set(preference_profile.tag_boosts.keys())

        for district in clustering_result.districts.values():
            if needed_categories and not district.has_category(list(needed_categories)):
                continue

            candidates = list(district.pois)
            scored = []
            for candidate in candidates:
                scored.append(score_candidate(
                    candidate=candidate,
                    block_type=BlockType.ACTIVITY,
                    desired_categories=list(needed_categories),
                    profile=preference_profile,
                    anchor_lat=district.center_lat,
                    anchor_lon=district.center_lon,
                    distance_weight=0.2,
                ))

            scored.sort(reverse=True)
            top_scores = scored[:5]
            preference_score = round(sum(top_scores) / len(top_scores), 2) if top_scores else 0.0

            summary = district.to_llm_summary()
            summary["preference_score"] = preference_score
            summary["category_coverage"] = [
                category for category in sorted(needed_categories)
                if district.has_category([category])
            ]

            if keyword_signals:
                hits = []
                for keyword in keyword_signals:
                    for poi in district.pois:
                        haystack = f"{poi.name} {' '.join(poi.tags or [])}".lower()
                        if keyword in haystack:
                            hits.append(keyword)
                            break
                summary["preference_signals"] = hits[:5]

            summaries.append(summary)

        return summaries

    def _collect_candidates_for_block(
        self,
        skeleton_block,
        curated_bank,
        district_id: Optional[str],
    ) -> list[POICandidate]:
        initial_count = len(curated_bank.candidates)
        candidates = curated_bank.candidates
        used_district_filter = False

        if district_id and curated_bank.clustering_result:
            district = curated_bank.clustering_result.get_district(district_id)
            if district:
                candidates = district.pois
                used_district_filter = True
                logger.debug(f"District filter: {initial_count} → {len(candidates)} candidates")

        desired = set([c.lower() for c in (skeleton_block.desired_categories or [])])
        if desired:
            before_category_filter = len(candidates)
            filtered = []
            for candidate in candidates:
                category = (candidate.category or "").lower()
                if category in desired:
                    filtered.append(candidate)
                    continue
                if candidate.tags and any(tag.lower() in desired for tag in candidate.tags):
                    filtered.append(candidate)
            candidates = filtered
            logger.debug(
                f"Category filter ({desired}): {before_category_filter} → {len(candidates)} candidates "
                f"(block_type={skeleton_block.block_type})"
            )

        # CRITICAL FALLBACK: If filtering left too few candidates, expand search
        # Lowered threshold from 3 to 10 to ensure sufficient variety
        min_candidates_threshold = 10
        if len(candidates) < min_candidates_threshold:
            logger.warning(
                f"⚠️ Only {len(candidates)} candidates after filtering (need {min_candidates_threshold}), "
                f"expanding search for {skeleton_block.block_type}"
            )
            candidates = curated_bank.candidates
            # Reapply category filter if needed
            if desired:
                filtered = []
                for candidate in candidates:
                    category = (candidate.category or "").lower()
                    if category in desired:
                        filtered.append(candidate)
                        continue
                    if candidate.tags and any(tag.lower() in desired for tag in candidate.tags):
                        filtered.append(candidate)
                candidates = filtered
                logger.info(f"✅ After city-wide expansion: {len(candidates)} candidates")

        return candidates

    async def _select_pois_for_day_agentic(
        self,
        day_skeleton,
        trip_spec,
        curated_bank,
        preference_profile: POIPreferenceProfile,
        preference_summary: dict,
        district_plan,
        must_include_assignments: dict[tuple[int, int], POICandidate],
        used_poi_ids: set[UUID],
        used_poi_names: set[str],
        enable_llm: bool = True,
        deadline_ts: Optional[float] = None,
    ) -> tuple[
        dict[int, POICandidate],
        dict[int, list[POICandidate]],
        bool,
        list[SearchDirective],
    ]:
        candidates_by_block: dict[int, list[POICandidate]] = {}
        block_contexts: dict[int, BlockContext] = {}
        llm_failed = False
        llm_requests: list[SearchDirective] = []

        anchor_lat = trip_spec.hotel_lat or trip_spec.city_center_lat
        anchor_lon = trip_spec.hotel_lon or trip_spec.city_center_lon

        for block_index, block in enumerate(day_skeleton.blocks):
            if block.block_type not in self.BLOCK_TYPES_NEEDING_POIS:
                continue

            locked = must_include_assignments.get((day_skeleton.day_number, block_index))
            if locked:
                candidates_by_block[block_index] = [locked]
                block_contexts[block_index] = BlockContext(
                    block_index=block_index,
                    block_type=block.block_type,
                    start_time=str(block.start_time),
                    end_time=str(block.end_time),
                    theme=block.theme,
                    desired_categories=block.desired_categories,
                )
                continue

            district_id = district_plan.get_district_for_block(block_index) if district_plan else None
            candidates = self._collect_candidates_for_block(block, curated_bank, district_id)
            if not candidates:
                try:
                    from src.infrastructure.database import AsyncSessionLocal
                    from src.infrastructure.poi_providers import get_poi_provider

                    async with AsyncSessionLocal() as session:
                        provider = get_poi_provider(session)
                        candidates = await provider.search_pois(
                            city=trip_spec.city,
                            desired_categories=block.desired_categories,
                            budget=trip_spec.budget,
                            limit=6,
                            center_location=trip_spec.hotel_location,
                            city_center_lat=trip_spec.city_center_lat,
                            city_center_lon=trip_spec.city_center_lon,
                            block_type=block.block_type,
                            search_keywords=preference_profile.search_keywords if (
                                preference_profile and block.block_type == BlockType.MEAL
                            ) else None,
                            fetch_details=False,
                        )
                except Exception as exc:
                    logger.warning(f"On-demand POI fetch failed: {exc}")
            candidates = filter_candidates_for_block(
                candidates=candidates,
                profile=preference_profile,
                block_type=block.block_type,
            )
            ranked = self._rank_candidates_for_block(
                candidates=candidates,
                skeleton_block=block,
                preference_profile=preference_profile,
                trip_spec=trip_spec,
                curated_bank=curated_bank,
                anchor_lat=anchor_lat,
                anchor_lon=anchor_lon,
            )
            # STRICT: Only allow unused POIs (by ID and name) - NO FALLBACK TO DUPLICATES
            before_filter = len(ranked)
            ranked = [c for c in ranked if c.poi_id not in used_poi_ids and c.name not in used_poi_names]
            after_filter = len(ranked)
            if before_filter != after_filter:
                filtered_out = [c for c in candidates if c.poi_id in used_poi_ids or c.name in used_poi_names]
                logger.warning(
                    f"🚫 Day {day_skeleton.day_number}, Block {block_index}: "
                    f"Filtered out {before_filter - after_filter} duplicate POIs: "
                    f"{[c.name for c in filtered_out[:5]]}"
                )
            if not ranked:
                logger.warning(
                    f"❌ Day {day_skeleton.day_number}, Block {block_index}: "
                    f"No unused POI candidates available! Total used IDs: {len(used_poi_ids)}, "
                    f"Total used names: {len(used_poi_names)}, "
                    f"Total candidates before filtering: {len(candidates)}"
                )
                # DO NOT use duplicates - leave block empty if no unique POIs available
                continue
            candidates_by_block[block_index] = ranked[:max(5, self._settings.agentic_day_selection_max_candidates)]
            block_contexts[block_index] = BlockContext(
                block_index=block_index,
                block_type=block.block_type,
                start_time=str(block.start_time),
                end_time=str(block.end_time),
                theme=block.theme,
                desired_categories=block.desired_categories,
            )

        selected_by_block: dict[int, POICandidate] = {}
        if candidates_by_block and enable_llm:
            trip_context = build_trip_context_from_response(trip_spec)
            day_context = DayContext(
                day_number=day_skeleton.day_number,
                date=str(day_skeleton.date),
                theme=day_skeleton.theme,
                already_selected_poi_ids=list(used_poi_ids),
            )

            selection_llm = self._get_poi_selection_llm()
            try:
                if deadline_ts is not None:
                    remaining = deadline_ts - time.monotonic()
                    if remaining <= float(self._settings.day_level_selection_llm_timeout_seconds):
                        raise TimeoutError("Insufficient time budget for day-level LLM")
                selected_by_block, raw_requests = await asyncio.wait_for(
                    selection_llm.select_pois_for_day_with_requests(
                        trip_context=trip_context,
                        day_context=day_context,
                        blocks=[block_contexts[idx] for idx in sorted(block_contexts)],
                        candidates_by_block=candidates_by_block,
                        already_selected_ids=set(used_poi_ids),
                        max_hop_distance_km=self._settings.max_hop_distance_km,
                        anchor_lat=anchor_lat,
                        anchor_lon=anchor_lon,
                        city_center_lat=trip_spec.city_center_lat,
                        city_center_lon=trip_spec.city_center_lon,
                        preference_summary=preference_summary,
                        must_visit_ids=curated_bank.must_visit_ids,
                        nice_to_have_ids=curated_bank.nice_to_have_ids,
                    ),
                    timeout=float(self._settings.day_level_selection_llm_timeout_seconds),
                )
                llm_requests = self._normalize_llm_requests(raw_requests)
            except Exception as exc:
                logger.warning(f"Agentic day-level LLM selection failed: {exc}")
                selected_by_block = {}
                llm_failed = True
        elif candidates_by_block and enable_llm is False:
            llm_failed = False

        if not selected_by_block:
            if candidates_by_block and enable_llm:
                llm_failed = True
            for block_index, candidates in candidates_by_block.items():
                if candidates:
                    selected_by_block[block_index] = candidates[0]

        if candidates_by_block:
            selected_by_block = self._dedupe_day_selections(
                selected_by_block=selected_by_block,
                candidates_by_block=candidates_by_block,
                used_poi_ids=used_poi_ids,
                used_poi_names=used_poi_names,
            )

        return selected_by_block, candidates_by_block, llm_failed, llm_requests

    async def generate_itinerary(
        self,
        trip_id: UUID,
        db: AsyncSession,
        preference_profile: Optional[POIPreferenceProfile] = None,
    ) -> ItineraryResponse:
        """
        Generate final itinerary for a trip.

        Args:
            trip_id: Trip UUID
            db: Database session

        Returns:
            ItineraryResponse with final itinerary

        Raises:
            ValueError: If trip not found or required plans missing
        """
        # 1. Load trip spec
        trip_spec = await self.trip_spec_collector.get_trip(trip_id, db)
        if not trip_spec:
            raise ValueError(f"Trip {trip_id} not found")

        # 2. Load macro plan
        macro_plan = await self.macro_planner.get_macro_plan(trip_id, db)
        if not macro_plan:
            raise ValueError(f"No macro plan found for trip {trip_id}. Generate macro plan first.")

        # 2b. Build preference profile if not provided
        if preference_profile is None:
            preference_agent = POIPreferenceAgent(app_settings=self._settings)
            preference_profile = await preference_agent.build_profile(trip_spec)

        # 3. Load POI plan (or generate if missing)
        result = await db.execute(
            select(ItineraryModel).where(ItineraryModel.trip_id == trip_id)
        )
        itinerary_model = result.scalars().first()

        if not itinerary_model or not itinerary_model.poi_plan:
            # Auto-generate POI plan if missing
            logger.info(f"POI plan missing for trip {trip_id}, generating automatically")
            from src.application.poi_planner import POIPlanner

            poi_planner = POIPlanner()
            await poi_planner.generate_poi_plan(
                trip_id,
                db,
                preference_profile=preference_profile,
            )

            # Reload itinerary model after POI plan generation
            result = await db.execute(
                select(ItineraryModel).where(ItineraryModel.trip_id == trip_id)
            )
            itinerary_model = result.scalars().first()

            if not itinerary_model or not itinerary_model.poi_plan:
                raise ValueError(f"Failed to generate POI plan for trip {trip_id}.")

        # Parse POI plan blocks
        poi_plan_blocks = [POIPlanBlock(**block_data) for block_data in itinerary_model.poi_plan]
        candidates_by_block = {
            (block.day_number, block.block_index): block.candidates
            for block in poi_plan_blocks
        }

        # Log optimization settings
        if self._settings.enable_daily_route_optimization:
            logger.info(
                f"Route optimization enabled: max_cluster_size={self._settings.max_optimization_blocks_per_cluster}"
            )

        # 4. Generate itinerary days
        itinerary_days = []

        # CRITICAL: Track POIs used across entire trip to prevent duplicates
        trip_used_poi_ids: set[UUID] = set()

        previous_day_last_poi: Optional[POICandidate] = None

        for day_skeleton in macro_plan.days:
            # Phase 1: Build BlockWithPOI objects for all blocks
            blocks_with_poi: list[BlockWithPOI] = []
            selection_anchor = None

            for block_index, skeleton_block in enumerate(day_skeleton.blocks):
                selected_poi = None
                if self._block_needs_poi(skeleton_block.block_type):
                    if selection_anchor is None:
                        selection_anchor = (
                            trip_spec.hotel_lat or trip_spec.city_center_lat,
                            trip_spec.hotel_lon or trip_spec.city_center_lon,
                        )
                    anchor_lat = selection_anchor[0] if selection_anchor else None
                    anchor_lon = selection_anchor[1] if selection_anchor else None
                    selected_poi = self._select_poi_for_block(
                        day_skeleton.day_number,
                        block_index,
                        poi_plan_blocks,
                        trip_used_poi_ids,  # Pass trip-level deduplication tracking
                        block_type=skeleton_block.block_type,
                        desired_categories=skeleton_block.desired_categories,
                        preference_profile=preference_profile,
                        anchor_lat=anchor_lat,
                        anchor_lon=anchor_lon,
                        day_center_lat=trip_spec.city_center_lat,
                        day_center_lon=trip_spec.city_center_lon,
                        candidates_by_block=candidates_by_block,
                    )
                    if selected_poi:
                        selection_anchor = (selected_poi.lat, selected_poi.lon)

                is_reorderable = self._is_block_reorderable(skeleton_block.block_type)

                block_with_poi = BlockWithPOI(
                    original_index=block_index,
                    block_type=skeleton_block.block_type,
                    start_time=skeleton_block.start_time,
                    end_time=skeleton_block.end_time,
                    theme=skeleton_block.theme,
                    poi=selected_poi,
                    is_reorderable=is_reorderable,
                )
                blocks_with_poi.append(block_with_poi)

            # Phase 2: Optimize block order within reorderable clusters
            if self._settings.use_llm_for_route_optimization:
                optimized_blocks = await self._optimize_day_route_llm(blocks_with_poi)
            else:
                optimized_blocks = self._optimize_day_route(blocks_with_poi)

            # Phase 2b: Repair long hops by swapping POIs within candidate pools
            day_anchor_lat = None
            day_anchor_lon = None
            if previous_day_last_poi and previous_day_last_poi.lat is not None and previous_day_last_poi.lon is not None:
                day_anchor_lat = previous_day_last_poi.lat
                day_anchor_lon = previous_day_last_poi.lon
            elif trip_spec.hotel_lat is not None and trip_spec.hotel_lon is not None:
                day_anchor_lat = trip_spec.hotel_lat
                day_anchor_lon = trip_spec.hotel_lon
            elif trip_spec.city_center_lat is not None and trip_spec.city_center_lon is not None:
                day_anchor_lat = trip_spec.city_center_lat
                day_anchor_lon = trip_spec.city_center_lon

            optimized_blocks = self._repair_long_hops(
                blocks=optimized_blocks,
                day_number=day_skeleton.day_number,
                day_skeleton=day_skeleton,
                candidates_by_block=candidates_by_block,
                used_poi_ids=trip_used_poi_ids,
                preference_profile=preference_profile,
                day_anchor_lat=day_anchor_lat,
                day_anchor_lon=day_anchor_lon,
                day_center_lat=trip_spec.city_center_lat,
                day_center_lon=trip_spec.city_center_lon,
            )

            # Phase 3: Build final itinerary blocks with travel info
            itinerary_blocks = []
            prev_poi = None

            for block_with_poi in optimized_blocks:
                travel_time = 0
                travel_distance = None
                travel_polyline = None

                if block_with_poi.poi is not None:
                    # Calculate travel from previous POI
                    if prev_poi is not None or block_with_poi.poi is not None:
                        origin = TravelLocation.from_poi(prev_poi)
                        destination = TravelLocation.from_poi(block_with_poi.poi)
                        travel_result = await self.travel_time_provider.estimate_travel(
                            origin,
                            destination,
                        )
                        travel_time = travel_result.duration_minutes
                        travel_distance = travel_result.distance_meters
                        travel_polyline = travel_result.polyline

                    prev_poi = block_with_poi.poi

                # Build notes for REST/TRAVEL blocks
                notes = None
                if block_with_poi.block_type == BlockType.REST:
                    notes = block_with_poi.theme or "Rest at hotel"
                elif block_with_poi.block_type == BlockType.TRAVEL:
                    notes = block_with_poi.theme or "Travel time"

                # Check for geo_suboptimal (travel time exceeds threshold)
                geo_suboptimal = False
                if (
                    self._settings.enable_travel_hop_limit
                    and travel_time > self._settings.max_travel_minutes_per_hop
                    and block_with_poi.poi is not None
                ):
                    geo_suboptimal = True
                    logger.warning(
                        f"Geo-suboptimal hop detected: {travel_time} min > "
                        f"{self._settings.max_travel_minutes_per_hop} min threshold "
                        f"(to {block_with_poi.poi.name})"
                    )

                # Create itinerary block
                itinerary_block = ItineraryBlock(
                    block_type=block_with_poi.block_type,
                    start_time=block_with_poi.start_time,
                    end_time=block_with_poi.end_time,
                    poi=block_with_poi.poi,
                    travel_time_from_prev=travel_time,
                    travel_distance_meters=travel_distance,
                    travel_polyline=travel_polyline,
                    notes=notes,
                    geo_suboptimal=geo_suboptimal,
                )
                itinerary_blocks.append(itinerary_block)

            # Create itinerary day
            itinerary_day = ItineraryDay(
                day_number=day_skeleton.day_number,
                date=day_skeleton.date,
                theme=day_skeleton.theme,
                blocks=itinerary_blocks,
            )
            itinerary_days.append(itinerary_day)

            # Track last POI for cross-day anchoring
            for block in reversed(itinerary_blocks):
                if block.poi and block.poi.lat is not None and block.poi.lon is not None:
                    previous_day_last_poi = block.poi
                    break

        # 5. Store in database
        created_at = datetime.utcnow()

        # Convert ItineraryDay list to JSON
        itinerary_json = [day.model_dump(mode='json') for day in itinerary_days]

        # Update existing itinerary record
        itinerary_model.days = itinerary_json
        itinerary_model.itinerary_created_at = created_at
        itinerary_model.updated_at = created_at

        await db.commit()
        await db.refresh(itinerary_model)

        # 6. Return response
        return ItineraryResponse(
            trip_id=trip_id,
            days=itinerary_days,
            created_at=created_at.isoformat() + "Z",
        )

    async def generate_agentic_itinerary(
        self,
        trip_id: UUID,
        db: AsyncSession,
        preference_profile: Optional["POIPreferenceProfile"] = None,
        deadline_ts: Optional[float] = None,
    ) -> ItineraryResponse:
        """
        Generate itinerary using agentic POI Curator + Route Engineer pipeline.
        """
        logger.warning(f"🚀🚀🚀 generate_agentic_itinerary STARTED for trip {trip_id}")

        # 1. Load trip spec
        trip_spec = await self.trip_spec_collector.get_trip(trip_id, db)
        if not trip_spec:
            raise ValueError(f"Trip {trip_id} not found")

        # 2. Load macro plan
        macro_plan = await self.macro_planner.get_macro_plan(trip_id, db)
        if not macro_plan:
            raise ValueError(f"No macro plan found for trip {trip_id}. Generate macro plan first.")

        # 3. Build preference profile if not provided
        if preference_profile is None:
            preference_agent = POIPreferenceAgent(app_settings=self._settings)
            preference_profile = await preference_agent.build_profile(trip_spec)

        # 4. Curate POI bank
        curator = POICuratorAgent(app_settings=self._settings)
        curated_bank = await curator.curate_poi_bank(
            trip_spec=trip_spec,
            macro_plan=macro_plan,
            db=db,
            preference_profile=preference_profile,
            deadline_ts=deadline_ts,
        )

        if not curated_bank.candidates:
            raise ValueError("POI Curator returned no candidates")

        # 5. Must-include assignments
        must_include_map = self._select_must_include_pois(
            trip_spec=trip_spec,
            curated_bank=curated_bank,
            preference_profile=preference_profile,
        )
        must_include_assignments = self._assign_must_include_to_blocks(
            macro_plan=macro_plan,
            must_include_map=must_include_map,
        )

        preference_summary = self._build_preference_summary(preference_profile)

        # 6. District planning (if clustering available)
        day_district_plans = {}
        skip_districts = False
        if deadline_ts is not None:
            remaining = deadline_ts - time.monotonic()
            if remaining < 8:
                skip_districts = True

        if (
            not skip_districts
            and curated_bank.clustering_result
            and curated_bank.clustering_result.districts
        ):
            from src.application.district_planner import DistrictPlanner

            district_planner = DistrictPlanner(
                use_llm=(
                    self._settings.use_llm_for_district_planning
                    and self._settings.agentic_use_llm_for_district_planning
                ),
                app_settings=self._settings,
            )
            district_summaries = self._build_district_summaries(
                curated_bank.clustering_result,
                macro_plan,
                preference_profile,
            )

            previous_anchor = None
            previous_district_id = None
            for day in macro_plan.days:
                try:
                    day_plan = await asyncio.wait_for(
                        district_planner.plan_districts(
                            day_skeleton=day,
                            clustering_result=curated_bank.clustering_result,
                            city=trip_spec.city,
                            district_summaries=district_summaries,
                            preference_summary=preference_summary,
                            previous_day_anchor=previous_anchor,
                            previous_day_district_id=previous_district_id,
                        ),
                        timeout=12,
                    )
                except Exception as exc:
                    logger.warning(f"District planning timed out, using deterministic: {exc}")
                    fallback_planner = DistrictPlanner(
                        use_llm=False,
                        app_settings=self._settings,
                    )
                    day_plan = await fallback_planner.plan_districts(
                        day_skeleton=day,
                        clustering_result=curated_bank.clustering_result,
                        city=trip_spec.city,
                        district_summaries=district_summaries,
                        preference_summary=preference_summary,
                        previous_day_anchor=previous_anchor,
                        previous_day_district_id=previous_district_id,
                    )
                day_district_plans[day.day_number] = day_plan
                if day_plan.assignments:
                    previous_district_id = day_plan.assignments[-1].district_id
                if previous_district_id:
                    district = curated_bank.clustering_result.get_district(previous_district_id)
                    if district:
                        previous_anchor = {"lat": district.center_lat, "lon": district.center_lon}

        # 7. Build itinerary days
        itinerary_days = []
        poi_plan_blocks = []
        trip_used_poi_ids: set[UUID] = set()
        trip_used_poi_names: set[str] = set()  # Track names to avoid duplicate businesses/chains
        previous_day_last_poi: Optional[POICandidate] = None
        day_llm_enabled = (
            self._settings.enable_day_level_poi_selection
            and self._settings.agentic_use_day_level_poi_selection
        )

        logger.warning(f"🔄🔄🔄 Starting day-by-day POI selection loop for {len(macro_plan.days)} days")

        for day_skeleton in macro_plan.days:
            logger.warning(f"📅 Processing Day {day_skeleton.day_number}, current used POIs: {len(trip_used_poi_ids)} IDs, {len(trip_used_poi_names)} names")
            district_plan = day_district_plans.get(day_skeleton.day_number)

            if deadline_ts is not None and day_llm_enabled:
                remaining = deadline_ts - time.monotonic()
                if remaining <= float(self._settings.day_level_selection_llm_timeout_seconds) + 2:
                    day_llm_enabled = False

            selected_by_block, candidates_by_block, llm_failed, llm_requests = await self._select_pois_for_day_agentic(
                day_skeleton=day_skeleton,
                trip_spec=trip_spec,
                curated_bank=curated_bank,
                preference_profile=preference_profile,
                preference_summary=preference_summary,
                district_plan=district_plan,
                must_include_assignments=must_include_assignments,
                used_poi_ids=trip_used_poi_ids,
                used_poi_names=trip_used_poi_names,
                enable_llm=day_llm_enabled,
                deadline_ts=deadline_ts,
            )
            if llm_failed:
                day_llm_enabled = False

            logger.warning(
                f"🔍 Day {day_skeleton.day_number} FIRST selection: "
                f"{len(selected_by_block)} POIs selected: "
                f"{[poi.name for poi in selected_by_block.values()]}"
            )

            if llm_requests and deadline_ts is not None:
                remaining = deadline_ts - time.monotonic()
                if remaining > 10:
                    # CRITICAL: Add POIs from first selection to used sets BEFORE retry
                    # to prevent selecting them again in different blocks
                    first_selection_ids = {poi.poi_id for poi in selected_by_block.values()}
                    first_selection_names = {poi.name for poi in selected_by_block.values()}
                    logger.warning(
                        f"🔄 Day {day_skeleton.day_number} expanding candidates, "
                        f"protecting {len(first_selection_ids)} POIs from first selection"
                    )

                    curated_bank = await curator.expand_candidates(
                        requests=llm_requests,
                        trip_spec=trip_spec,
                        db=db,
                        curated_bank=curated_bank,
                        preference_profile=preference_profile,
                        deadline_ts=deadline_ts,
                    )

                    # Pass updated used sets that include first selection
                    temp_used_poi_ids = trip_used_poi_ids | first_selection_ids
                    temp_used_poi_names = trip_used_poi_names | first_selection_names
                    selected_by_block, candidates_by_block, _, _ = await self._select_pois_for_day_agentic(
                        day_skeleton=day_skeleton,
                        trip_spec=trip_spec,
                        curated_bank=curated_bank,
                        preference_profile=preference_profile,
                        preference_summary=preference_summary,
                        district_plan=district_plan,
                        must_include_assignments=must_include_assignments,
                        used_poi_ids=temp_used_poi_ids,  # Use temp set with first selection
                        used_poi_names=temp_used_poi_names,  # Use temp set with first selection
                        enable_llm=day_llm_enabled,
                        deadline_ts=deadline_ts,
                    )

                    logger.warning(
                        f"🔍 Day {day_skeleton.day_number} SECOND selection (after expansion): "
                        f"{len(selected_by_block)} POIs selected: "
                        f"{[poi.name for poi in selected_by_block.values()]}"
                    )

            for poi in selected_by_block.values():
                logger.warning(f"➕ Adding to trip_used: {poi.name} (ID: {poi.poi_id})")
                trip_used_poi_ids.add(poi.poi_id)
                trip_used_poi_names.add(poi.name)

            # Build POI plan blocks (store top candidates per block)
            for block_index, block in enumerate(day_skeleton.blocks):
                if block.block_type not in self.BLOCK_TYPES_NEEDING_POIS:
                    continue
                candidates = candidates_by_block.get(block_index, [])
                selected = selected_by_block.get(block_index)
                if selected:
                    candidates = [selected] + [c for c in candidates if c.poi_id != selected.poi_id]
                candidate_limit = max(5, self._settings.agentic_day_selection_max_candidates)
                poi_plan_blocks.append(POIPlanBlock(
                    day_number=day_skeleton.day_number,
                    block_index=block_index,
                    block_theme=block.theme or "",
                    block_type=block.block_type,
                    candidates=candidates[:candidate_limit],
                ))

            blocks_with_poi: list[BlockWithPOI] = []
            for block_index, skeleton_block in enumerate(day_skeleton.blocks):
                selected_poi = None
                if skeleton_block.block_type in self.BLOCK_TYPES_NEEDING_POIS:
                    selected_poi = selected_by_block.get(block_index)

                blocks_with_poi.append(BlockWithPOI(
                    original_index=block_index,
                    block_type=skeleton_block.block_type,
                    start_time=skeleton_block.start_time,
                    end_time=skeleton_block.end_time,
                    theme=skeleton_block.theme,
                    poi=selected_poi,
                    is_reorderable=self._is_block_reorderable(skeleton_block.block_type),
                ))

            use_llm_route = (
                self._settings.use_llm_for_route_optimization
                and self._settings.agentic_use_llm_for_route_optimization
            )
            if use_llm_route:
                optimized_blocks = await self._optimize_day_route_llm(
                    blocks_with_poi,
                    deadline_ts=deadline_ts,
                )
            else:
                optimized_blocks = self._optimize_day_route(blocks_with_poi)

            day_anchor_lat = None
            day_anchor_lon = None
            if previous_day_last_poi and previous_day_last_poi.lat is not None and previous_day_last_poi.lon is not None:
                day_anchor_lat = previous_day_last_poi.lat
                day_anchor_lon = previous_day_last_poi.lon
            elif trip_spec.hotel_lat is not None and trip_spec.hotel_lon is not None:
                day_anchor_lat = trip_spec.hotel_lat
                day_anchor_lon = trip_spec.hotel_lon
            elif trip_spec.city_center_lat is not None and trip_spec.city_center_lon is not None:
                day_anchor_lat = trip_spec.city_center_lat
                day_anchor_lon = trip_spec.city_center_lon

            candidates_by_block_keyed = {
                (day_skeleton.day_number, block_index): candidates
                for block_index, candidates in candidates_by_block.items()
            }

            optimized_blocks = self._repair_long_hops(
                blocks=optimized_blocks,
                day_number=day_skeleton.day_number,
                day_skeleton=day_skeleton,
                candidates_by_block=candidates_by_block_keyed,
                used_poi_ids=trip_used_poi_ids,
                preference_profile=preference_profile,
                day_anchor_lat=day_anchor_lat,
                day_anchor_lon=day_anchor_lon,
                day_center_lat=trip_spec.city_center_lat,
                day_center_lon=trip_spec.city_center_lon,
            )

            itinerary_blocks = []
            prev_poi = None

            for block_with_poi in optimized_blocks:
                travel_time = 0
                travel_distance = None
                travel_polyline = None

                if block_with_poi.poi is not None:
                    origin = TravelLocation.from_poi(prev_poi)
                    destination = TravelLocation.from_poi(block_with_poi.poi)
                    travel_result = await self.travel_time_provider.estimate_travel(
                        origin,
                        destination,
                    )
                    travel_time = travel_result.duration_minutes
                    travel_distance = travel_result.distance_meters
                    travel_polyline = travel_result.polyline
                    prev_poi = block_with_poi.poi

                notes = None
                if block_with_poi.block_type == BlockType.REST:
                    notes = block_with_poi.theme or "Rest at hotel"
                elif block_with_poi.block_type == BlockType.TRAVEL:
                    notes = block_with_poi.theme or "Travel time"

                geo_suboptimal = False
                if (
                    self._settings.enable_travel_hop_limit
                    and travel_time > self._settings.max_travel_minutes_per_hop
                    and block_with_poi.poi is not None
                ):
                    geo_suboptimal = True

                itinerary_blocks.append(ItineraryBlock(
                    block_type=block_with_poi.block_type,
                    start_time=block_with_poi.start_time,
                    end_time=block_with_poi.end_time,
                    poi=block_with_poi.poi,
                    travel_time_from_prev=travel_time,
                    travel_distance_meters=travel_distance,
                    travel_polyline=travel_polyline,
                    notes=notes,
                    geo_suboptimal=geo_suboptimal,
                ))

            itinerary_day = ItineraryDay(
                day_number=day_skeleton.day_number,
                date=day_skeleton.date,
                theme=day_skeleton.theme,
                blocks=itinerary_blocks,
            )
            itinerary_days.append(itinerary_day)

            for block in reversed(itinerary_blocks):
                if block.poi and block.poi.lat is not None and block.poi.lon is not None:
                    previous_day_last_poi = block.poi
                    break

        # 8. Store in database
        created_at = datetime.utcnow()
        itinerary_json = [day.model_dump(mode='json') for day in itinerary_days]
        poi_plan_json = [block.model_dump(mode='json') for block in poi_plan_blocks]

        result = await db.execute(
            select(ItineraryModel).where(ItineraryModel.trip_id == trip_id)
        )
        itinerary_model = result.scalars().first()

        if not itinerary_model:
            itinerary_model = ItineraryModel(
                trip_id=trip_id,
                created_at=created_at,
                updated_at=created_at,
            )
            db.add(itinerary_model)

        itinerary_model.poi_plan = poi_plan_json
        itinerary_model.poi_plan_created_at = created_at
        itinerary_model.days = itinerary_json
        itinerary_model.itinerary_created_at = created_at
        itinerary_model.updated_at = created_at

        await db.commit()
        await db.refresh(itinerary_model)

        return ItineraryResponse(
            trip_id=trip_id,
            days=itinerary_days,
            created_at=created_at.isoformat() + "Z",
        )

    async def get_itinerary(
        self,
        trip_id: UUID,
        db: AsyncSession,
    ) -> Optional[ItineraryResponse]:
        """
        Get stored itinerary for a trip.

        Args:
            trip_id: Trip UUID
            db: Database session

        Returns:
            ItineraryResponse if itinerary exists, None otherwise
        """
        result = await db.execute(
            select(ItineraryModel).where(ItineraryModel.trip_id == trip_id)
        )
        itinerary_model = result.scalars().first()

        if not itinerary_model or not itinerary_model.days:
            return None

        # Parse stored JSON back into ItineraryDay objects
        itinerary_days = [ItineraryDay(**day_data) for day_data in itinerary_model.days]

        return ItineraryResponse(
            trip_id=trip_id,
            days=itinerary_days,
            created_at=itinerary_model.itinerary_created_at.isoformat() + "Z"
            if itinerary_model.itinerary_created_at else datetime.utcnow().isoformat() + "Z",
        )

    async def generate_smart_itinerary(
        self,
        trip_id: UUID,
        db: AsyncSession,
        preference_profile: Optional["POIPreferenceProfile"] = None,
        deadline_ts: Optional[float] = None,
    ) -> ItineraryResponse:
        """
        Generate itinerary using smart district-based routing.

        This method uses geographic clustering and LLM-based district planning
        to create optimal walking routes that stay within neighborhoods.

        Falls back to classic generate_itinerary() on any failure.

        Args:
            trip_id: Trip UUID
            db: Database session

        Returns:
            ItineraryResponse with optimized itinerary
        """
        if not self._settings.enable_smart_routing:
            logger.info("Smart routing disabled, using classic method")
            return await self.generate_itinerary(trip_id, db)

        try:
            if self._settings.enable_agentic_planning:
                logger.info(f"Using agentic Curator/Engineer routing for trip {trip_id}")
                return await self.generate_agentic_itinerary(
                    trip_id,
                    db,
                    preference_profile=preference_profile,
                    deadline_ts=deadline_ts,
                )

            # Import here to avoid circular imports
            from src.application.smart_route_optimizer import SmartRouteOptimizer

            smart_optimizer = SmartRouteOptimizer(
                travel_time_provider=self.travel_time_provider,
                app_settings=self._settings,
            )

            logger.info(f"Using smart district-based routing for trip {trip_id}")
            return await smart_optimizer.generate_smart_itinerary(
                trip_id,
                db,
                preference_profile=preference_profile,
            )

        except Exception as e:
            import traceback
            logger.warning(
                f"Smart routing failed for trip {trip_id}, falling back to smart optimizer: {e}"
            )
            logger.error(f"Full traceback:\n{traceback.format_exc()}")

            # Fallback to smart route optimizer first
            try:
                from src.application.smart_route_optimizer import SmartRouteOptimizer

                smart_optimizer = SmartRouteOptimizer(
                    travel_time_provider=self.travel_time_provider,
                    app_settings=self._settings,
                )
                return await smart_optimizer.generate_smart_itinerary(
                    trip_id,
                    db,
                    preference_profile=preference_profile,
                )
            except Exception as fallback_error:
                logger.warning(
                    f"Smart optimizer failed for trip {trip_id}, falling back to classic: {fallback_error}"
                )
                logger.error(f"Full traceback:\n{traceback.format_exc()}")
                return await self.generate_itinerary(trip_id, db, preference_profile=preference_profile)
