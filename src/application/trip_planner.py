"""
Trip Planner Orchestrator service.
Coordinates the full planning pipeline: Macro Plan → POI Plan → Route & Time Optimization → Critique.

Supports two modes:
1. Classic mode: Macro Plan → POI Plan → Route Optimization (separate steps)
2. Smart mode: Macro Plan → Smart Route Optimization (integrated POI + routing)
"""
import logging
import time
from uuid import UUID
from collections import Counter

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.domain.schemas import ItineraryResponse, CritiqueResponse, CritiqueIssueSchema
from src.application.trip_spec import TripSpecCollector
from src.application.macro_planner import MacroPlanner
from src.application.poi_planner import POIPlanner
from src.application.route_optimizer import RouteTimeOptimizer
from src.application.trip_critic import TripCritic
from src.application.poi_agent import POIPreferenceAgent

logger = logging.getLogger(__name__)


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

        Uses smart district-based routing when enabled, falls back to classic pipeline.

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

        start_ts = time.monotonic()
        deadline_ts = start_ts + settings.planning_deadline_seconds

        def remaining_seconds() -> float:
            return max(0.0, deadline_ts - time.monotonic())

        # 2. Generate macro plan if missing
        macro_plan = await self.macro_planner.get_macro_plan(trip_id, db)
        if not macro_plan:
            logger.info(f"Generating macro plan for trip {trip_id}")
            macro_plan = await self.macro_planner.generate_macro_plan(trip_id, db)

        # 2b. Build preference profile once (POI agent)
        preference_agent = POIPreferenceAgent(app_settings=settings)
        pref_timeout = min(
            float(settings.poi_preference_llm_timeout_seconds),
            remaining_seconds(),
        )
        preference_profile = await preference_agent.build_profile(
            trip_spec,
            timeout_seconds=pref_timeout,
        )

        # 3. Choose routing mode
        if settings.enable_smart_routing:
            # Smart mode: integrated POI selection + routing
            logger.info(f"Using smart district-based routing for trip {trip_id}")
            itinerary = await self.route_optimizer.generate_smart_itinerary(
                trip_id,
                db,
                preference_profile=preference_profile,
                deadline_ts=deadline_ts,
            )
        else:
            # Classic mode: separate POI plan + route optimization
            logger.info(f"Using classic routing for trip {trip_id}")

            # Generate POI plan if missing
            poi_plan = await self.poi_planner.get_poi_plan(trip_id, db)
            if not poi_plan:
                poi_plan = await self.poi_planner.generate_poi_plan(
                    trip_id,
                    db,
                    preference_profile=preference_profile,
                )

            # Generate final itinerary
            itinerary = await self.route_optimizer.generate_itinerary(
                trip_id,
                db,
                preference_profile=preference_profile,
            )

        # 4. Run Trip Critic for validation
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
