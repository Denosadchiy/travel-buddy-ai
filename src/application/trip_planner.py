"""
Trip Planner Orchestrator service.
Coordinates the full planning pipeline: Macro Plan → POI Plan → Route & Time Optimization → Critique.
"""
from uuid import UUID
from collections import Counter

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.schemas import ItineraryResponse, CritiqueResponse, CritiqueIssueSchema
from src.application.trip_spec import TripSpecCollector
from src.application.macro_planner import MacroPlanner
from src.application.poi_planner import POIPlanner
from src.application.route_optimizer import RouteTimeOptimizer
from src.application.trip_critic import TripCritic


class TripPlannerOrchestrator:
    """
    Orchestrates the full trip planning pipeline.

    Pipeline stages:
    1. Verify trip exists (TripSpec)
    2. Generate macro plan if missing (MacroPlanner)
    3. Generate POI plan if missing (POIPlanner)
    4. Generate final itinerary (RouteTimeOptimizer)
    5. Run Trip Critic for validation

    Returns the final itinerary.
    """

    def __init__(self):
        """Initialize orchestrator with all planning services."""
        self.trip_spec_collector = TripSpecCollector()
        self.macro_planner = MacroPlanner()
        self.poi_planner = POIPlanner()
        self.route_optimizer = RouteTimeOptimizer()
        self.trip_critic = TripCritic()

    async def plan_trip(
        self,
        trip_id: UUID,
        db: AsyncSession,
    ) -> ItineraryResponse:
        """
        Execute full planning pipeline for a trip.

        Args:
            trip_id: Trip UUID
            db: Database session

        Returns:
            ItineraryResponse with final itinerary

        Raises:
            ValueError: If trip not found or planning fails
        """
        # 1. Verify trip exists
        trip_spec = await self.trip_spec_collector.get_trip(trip_id, db)
        if not trip_spec:
            raise ValueError(f"Trip {trip_id} not found")

        # 2. Generate macro plan if missing
        macro_plan = await self.macro_planner.get_macro_plan(trip_id, db)
        if not macro_plan:
            # Generate macro plan
            macro_plan = await self.macro_planner.generate_macro_plan(trip_id, db)

        # 3. Generate POI plan if missing
        poi_plan = await self.poi_planner.get_poi_plan(trip_id, db)
        if not poi_plan:
            # Generate POI plan
            poi_plan = await self.poi_planner.generate_poi_plan(trip_id, db)

        # 4. Generate final itinerary (always regenerate for now)
        # In the future, we could cache this and only regenerate if macro/POI plans change
        itinerary = await self.route_optimizer.generate_itinerary(trip_id, db)

        # 5. Run Trip Critic for validation
        critique_issues = await self.trip_critic.critique_trip(trip_id, db)
        await self.trip_critic.store_critique(trip_id, critique_issues, db)

        return itinerary

    async def get_itinerary(
        self,
        trip_id: UUID,
        db: AsyncSession,
    ) -> ItineraryResponse:
        """
        Get stored itinerary for a trip.

        Args:
            trip_id: Trip UUID
            db: Database session

        Returns:
            ItineraryResponse with stored itinerary

        Raises:
            ValueError: If no itinerary exists for this trip
        """
        itinerary = await self.route_optimizer.get_itinerary(trip_id, db)

        if not itinerary:
            raise ValueError(f"No itinerary found for trip {trip_id}. Generate one using /plan endpoint.")

        return itinerary

    async def get_critique(
        self,
        trip_id: UUID,
        db: AsyncSession,
    ) -> CritiqueResponse:
        """
        Get stored critique for a trip.

        Args:
            trip_id: Trip UUID
            db: Database session

        Returns:
            CritiqueResponse with critique issues

        Raises:
            ValueError: If no critique exists for this trip
        """
        # Get critique issues
        issues = await self.trip_critic.get_critique(trip_id, db)

        if issues is None:
            # Return empty critique instead of error
            return CritiqueResponse(
                trip_id=trip_id,
                issues=[],
                total_issues=0,
                by_severity={},
                created_at=None,
            )

        # Convert to schema
        issue_schemas = [CritiqueIssueSchema(**issue.model_dump()) for issue in issues]

        # Calculate summary stats
        total_issues = len(issues)
        severity_counts = Counter(issue.severity.value for issue in issues)
        by_severity = dict(severity_counts)

        # Get created_at timestamp
        from sqlalchemy import select
        from src.infrastructure.models import ItineraryModel

        result = await db.execute(
            select(ItineraryModel).where(ItineraryModel.trip_id == trip_id)
        )
        itinerary_model = result.scalars().first()

        created_at = None
        if itinerary_model and itinerary_model.critique_created_at:
            created_at = itinerary_model.critique_created_at.isoformat() + "Z"

        return CritiqueResponse(
            trip_id=trip_id,
            issues=issue_schemas,
            total_issues=total_issues,
            by_severity=by_severity,
            created_at=created_at,
        )
