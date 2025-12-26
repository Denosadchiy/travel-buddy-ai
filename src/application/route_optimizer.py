"""
Route & Time Optimizer service.
Generates final itinerary by selecting POIs and assigning concrete times.
Purely deterministic - no LLM calls.
"""
from uuid import UUID
from typing import Optional
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models import ItineraryDay, ItineraryBlock, POICandidate, BlockType, DaySkeleton
from src.domain.schemas import POIPlanBlock, ItineraryResponse
from src.application.trip_spec import TripSpecCollector
from src.application.macro_planner import MacroPlanner
from src.infrastructure.travel_time import TravelTimeProvider, TravelLocation, get_travel_time_provider
from src.infrastructure.models import ItineraryModel


class RouteTimeOptimizer:
    """
    Service for generating final itinerary with selected POIs and concrete times.
    Deterministic POI selection and travel time calculation.
    """

    # Block types that need POIs
    BLOCK_TYPES_NEEDING_POIS = {
        BlockType.MEAL,
        BlockType.ACTIVITY,
        BlockType.NIGHTLIFE,
    }

    def __init__(self, travel_time_provider: Optional[TravelTimeProvider] = None):
        """
        Initialize Route & Time Optimizer.

        Args:
            travel_time_provider: Travel time provider (defaults to heuristic)
        """
        self.travel_time_provider = travel_time_provider or get_travel_time_provider()
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
    ) -> Optional[POICandidate]:
        """
        Select the best POI candidate for a block.

        Args:
            day_number: Day number
            block_index: Block index within the day
            poi_plan_blocks: List of all POI plan blocks

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

        # Select top-ranked candidate (first in list, already sorted by rank_score)
        return matching_block.candidates[0]

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

        # 4. Generate itinerary days
        itinerary_days = []

        for day_skeleton in macro_plan.days:
            itinerary_blocks = []
            prev_poi = None  # Track previous POI for travel time calculation

            for block_index, skeleton_block in enumerate(day_skeleton.blocks):
                # Determine if this block needs a POI
                selected_poi = None
                travel_time = 0
                travel_distance = None
                travel_polyline = None

                if self._block_needs_poi(skeleton_block.block_type):
                    # Select POI from candidates
                    selected_poi = self._select_poi_for_block(
                        day_skeleton.day_number,
                        block_index,
                        poi_plan_blocks,
                    )

                    # Calculate travel from previous block
                    if prev_poi or selected_poi:
                        origin = TravelLocation.from_poi(prev_poi)
                        destination = TravelLocation.from_poi(selected_poi)
                        travel_result = await self.travel_time_provider.estimate_travel(
                            origin,
                            destination,
                        )
                        travel_time = travel_result.duration_minutes
                        travel_distance = travel_result.distance_meters
                        travel_polyline = travel_result.polyline

                    # Update prev_poi for next iteration
                    prev_poi = selected_poi

                # Build notes for REST/TRAVEL blocks
                notes = None
                if skeleton_block.block_type == BlockType.REST:
                    notes = skeleton_block.theme or "Rest at hotel"
                elif skeleton_block.block_type == BlockType.TRAVEL:
                    notes = skeleton_block.theme or "Travel time"

                # Create itinerary block
                itinerary_block = ItineraryBlock(
                    block_type=skeleton_block.block_type,
                    start_time=skeleton_block.start_time,
                    end_time=skeleton_block.end_time,
                    poi=selected_poi,
                    travel_time_from_prev=travel_time,
                    travel_distance_meters=travel_distance,
                    travel_polyline=travel_polyline,
                    notes=notes,
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
