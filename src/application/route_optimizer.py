"""
Route & Time Optimizer service.
Generates final itinerary by selecting POIs and assigning concrete times.
Purely deterministic - no LLM calls.

Features:
- Selects best POI for each block
- Optimizes block order within reorderable clusters (minimizes travel)
- Enforces max travel time per hop constraints
- Calculates accurate travel times and distances
"""
import logging
import itertools
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
from src.infrastructure.travel_time import TravelTimeProvider, TravelLocation, get_travel_time_provider
from src.infrastructure.poi_providers import haversine_distance_km
from src.infrastructure.models import ItineraryModel

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

    def _block_needs_poi(self, block_type: BlockType) -> bool:
        """Check if a block type needs a POI."""
        return block_type in self.BLOCK_TYPES_NEEDING_POIS

    def _select_poi_for_block(
        self,
        day_number: int,
        block_index: int,
        poi_plan_blocks: list[POIPlanBlock],
        used_poi_ids: set[UUID],
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
        for poi_block in poi_plan_blocks:
            if poi_block.day_number == day_number and poi_block.block_index == block_index:
                matching_block = poi_block
                break

        if not matching_block or not matching_block.candidates:
            return None

        # CRITICAL: Select first candidate that hasn't been used yet
        # This prevents duplicate POIs in the final itinerary

        # Debug logging
        candidate_info = [(c.name, str(c.poi_id)[:8]) for c in matching_block.candidates[:5]]
        logger.info(
            f"Day {day_number}, Block {block_index}: "
            f"Selecting from {len(matching_block.candidates)} candidates: {candidate_info}"
        )
        logger.info(f"Already used POIs: {len(used_poi_ids)} unique IDs")

        for candidate in matching_block.candidates:
            if candidate.poi_id not in used_poi_ids:
                used_poi_ids.add(candidate.poi_id)  # Mark as used
                logger.info(
                    f"✓ Selected: {candidate.name} (ID: {str(candidate.poi_id)[:8]}...)"
                )
                return candidate
            else:
                logger.debug(
                    f"✗ Skipped duplicate: {candidate.name} (ID: {str(candidate.poi_id)[:8]}...)"
                )

        # If all candidates are duplicates, log warning and skip
        logger.warning(
            f"❌ All {len(matching_block.candidates)} POI candidates for day {day_number}, "
            f"block {block_index} are already used. Leaving block without POI."
        )
        return None

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

    async def generate_itinerary(
        self,
        trip_id: UUID,
        db: AsyncSession,
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

        # 3. Load POI plan
        result = await db.execute(
            select(ItineraryModel).where(ItineraryModel.trip_id == trip_id)
        )
        itinerary_model = result.scalars().first()

        if not itinerary_model or not itinerary_model.poi_plan:
            raise ValueError(f"No POI plan found for trip {trip_id}. Generate POI plan first.")

        # Parse POI plan blocks
        poi_plan_blocks = [POIPlanBlock(**block_data) for block_data in itinerary_model.poi_plan]

        # Log optimization settings
        if self._settings.enable_daily_route_optimization:
            logger.info(
                f"Route optimization enabled: max_cluster_size={self._settings.max_optimization_blocks_per_cluster}"
            )

        # 4. Generate itinerary days
        itinerary_days = []

        # CRITICAL: Track POIs used across entire trip to prevent duplicates
        trip_used_poi_ids: set[UUID] = set()

        for day_skeleton in macro_plan.days:
            # Phase 1: Build BlockWithPOI objects for all blocks
            blocks_with_poi: list[BlockWithPOI] = []

            for block_index, skeleton_block in enumerate(day_skeleton.blocks):
                selected_poi = None
                if self._block_needs_poi(skeleton_block.block_type):
                    selected_poi = self._select_poi_for_block(
                        day_skeleton.day_number,
                        block_index,
                        poi_plan_blocks,
                        trip_used_poi_ids,  # Pass trip-level deduplication tracking
                    )

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
            optimized_blocks = self._optimize_day_route(blocks_with_poi)

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
