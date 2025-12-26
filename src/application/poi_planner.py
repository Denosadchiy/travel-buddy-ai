"""
POI Planner service.
Selects candidate POIs for each block in the macro plan.
"""
from uuid import UUID
from typing import Optional
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models import DaySkeleton, BlockType
from src.domain.schemas import POIPlanBlock, POIPlanResponse
from src.application.trip_spec import TripSpecCollector
from src.application.macro_planner import MacroPlanner
from src.infrastructure.poi_providers import POIProvider, get_poi_provider
from src.infrastructure.models import ItineraryModel


class POIPlanner:
    """
    Service for selecting POI candidates for trip blocks.
    Uses deterministic ranking based on DB and external API data.
    """

    # Block types that need POI candidates
    BLOCK_TYPES_NEEDING_POIS = {
        BlockType.MEAL,
        BlockType.ACTIVITY,
        BlockType.NIGHTLIFE,
    }

    # Number of candidates to request per block
    CANDIDATES_PER_BLOCK = 3

    def __init__(self, poi_provider: Optional[POIProvider] = None):
        """
        Initialize POI Planner.

        Args:
            poi_provider: POI provider (defaults to composite provider)
        """
        self.poi_provider = poi_provider  # Will be set per request if None
        self.trip_spec_collector = TripSpecCollector()
        self.macro_planner = MacroPlanner()

    def _block_needs_pois(self, block_type: BlockType) -> bool:
        """Check if a block type needs POI candidates."""
        return block_type in self.BLOCK_TYPES_NEEDING_POIS

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

        # 4. Generate POI candidates for each block
        poi_blocks = []

        for day in macro_plan.days:
            for block_index, block in enumerate(day.blocks):
                # Skip blocks that don't need POIs
                if not self._block_needs_pois(block.block_type):
                    continue

                # Search for POI candidates
                candidates = await self.poi_provider.search_pois(
                    city=trip_spec.city,
                    desired_categories=block.desired_categories,
                    budget=trip_spec.budget,
                    limit=self.CANDIDATES_PER_BLOCK,
                    center_location=trip_spec.hotel_location,
                )

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
