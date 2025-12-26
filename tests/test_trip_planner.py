"""
Tests for Trip Planner Orchestrator functionality.
"""
import pytest
from uuid import uuid4
from httpx import AsyncClient

from src.main import app
from src.application.trip_planner import TripPlannerOrchestrator
from src.infrastructure.database import AsyncSessionLocal


@pytest.mark.asyncio
async def test_trip_planner_orchestrator_full_pipeline():
    """Test TripPlannerOrchestrator executes full planning pipeline."""
    # Create trip without any plans
    async with AsyncClient(app=app, base_url="http://test") as client:
        trip_response = await client.post(
            "/api/trips",
            json={
                "city": "Paris",
                "start_date": "2024-06-15",
                "end_date": "2024-06-16",
                "interests": ["food", "culture"]
            }
        )
        trip_id = trip_response.json()["id"]

    # Mock LLM for macro planning
    from src.application import macro_planner
    original_factory = macro_planner.get_macro_planning_llm_client
    from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

    macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

    try:
        # Run orchestrator
        async with AsyncSessionLocal() as db:
            orchestrator = TripPlannerOrchestrator()
            itinerary = await orchestrator.plan_trip(trip_id, db)

        # Verify itinerary was generated
        assert itinerary.trip_id == trip_id
        assert len(itinerary.days) > 0
        assert itinerary.created_at

        # Verify structure
        for day in itinerary.days:
            assert day.day_number >= 1
            assert len(day.blocks) > 0

    finally:
        macro_planner.get_macro_planning_llm_client = original_factory


@pytest.mark.asyncio
async def test_trip_planner_orchestrator_reuses_macro_plan():
    """Test that orchestrator reuses existing macro plan."""
    # Create trip and macro plan
    async with AsyncClient(app=app, base_url="http://test") as client:
        trip_response = await client.post(
            "/api/trips",
            json={
                "city": "Tokyo",
                "start_date": "2024-07-01",
                "end_date": "2024-07-02",
            }
        )
        trip_id = trip_response.json()["id"]

        # Create macro plan first
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/macro-plan")

            # Now run orchestrator (should reuse macro plan)
            async with AsyncSessionLocal() as db:
                orchestrator = TripPlannerOrchestrator()
                itinerary = await orchestrator.plan_trip(trip_id, db)

            # Should succeed and return itinerary
            assert itinerary.trip_id == trip_id
            assert len(itinerary.days) > 0

        finally:
            macro_planner.get_macro_planning_llm_client = original_factory


@pytest.mark.asyncio
async def test_trip_planner_orchestrator_reuses_poi_plan():
    """Test that orchestrator reuses existing POI plan."""
    # Create trip with macro and POI plans
    async with AsyncClient(app=app, base_url="http://test") as client:
        trip_response = await client.post(
            "/api/trips",
            json={
                "city": "Barcelona",
                "start_date": "2024-08-01",
                "end_date": "2024-08-02",
            }
        )
        trip_id = trip_response.json()["id"]

        # Create both plans first
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/macro-plan")
            await client.post(f"/api/trips/{trip_id}/poi-plan")

            # Now run orchestrator (should reuse both plans)
            async with AsyncSessionLocal() as db:
                orchestrator = TripPlannerOrchestrator()
                itinerary = await orchestrator.plan_trip(trip_id, db)

            # Should succeed
            assert itinerary.trip_id == trip_id
            assert len(itinerary.days) > 0

        finally:
            macro_planner.get_macro_planning_llm_client = original_factory


@pytest.mark.asyncio
async def test_trip_planner_orchestrator_trip_not_found():
    """Test that orchestrator fails when trip doesn't exist."""
    fake_trip_id = uuid4()

    async with AsyncSessionLocal() as db:
        orchestrator = TripPlannerOrchestrator()

        with pytest.raises(ValueError) as exc_info:
            await orchestrator.plan_trip(fake_trip_id, db)

        assert "not found" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_get_itinerary_via_orchestrator():
    """Test getting itinerary through orchestrator."""
    # Create trip and generate itinerary
    async with AsyncClient(app=app, base_url="http://test") as client:
        trip_response = await client.post(
            "/api/trips",
            json={
                "city": "Rome",
                "start_date": "2024-09-01",
                "end_date": "2024-09-02",
            }
        )
        trip_id = trip_response.json()["id"]

    # Mock LLM and generate itinerary
    from src.application import macro_planner
    original_factory = macro_planner.get_macro_planning_llm_client
    from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

    macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

    try:
        async with AsyncSessionLocal() as db:
            orchestrator = TripPlannerOrchestrator()
            await orchestrator.plan_trip(trip_id, db)

            # Get itinerary
            stored_itinerary = await orchestrator.get_itinerary(trip_id, db)

        assert stored_itinerary is not None
        assert stored_itinerary.trip_id == trip_id

    finally:
        macro_planner.get_macro_planning_llm_client = original_factory


@pytest.mark.asyncio
async def test_get_itinerary_not_found_via_orchestrator():
    """Test getting itinerary when none exists."""
    # Create trip without itinerary
    async with AsyncClient(app=app, base_url="http://test") as client:
        trip_response = await client.post(
            "/api/trips",
            json={
                "city": "Berlin",
                "start_date": "2024-10-01",
                "end_date": "2024-10-02",
            }
        )
        trip_id = trip_response.json()["id"]

    # Try to get itinerary
    async with AsyncSessionLocal() as db:
        orchestrator = TripPlannerOrchestrator()

        with pytest.raises(ValueError) as exc_info:
            await orchestrator.get_itinerary(trip_id, db)

        assert "no itinerary" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_trip_planner_orchestrator_generates_all_stages():
    """Test that orchestrator generates macro plan, POI plan, and itinerary when all are missing."""
    # Create trip only
    async with AsyncClient(app=app, base_url="http://test") as client:
        trip_response = await client.post(
            "/api/trips",
            json={
                "city": "Amsterdam",
                "start_date": "2024-11-01",
                "end_date": "2024-11-02",
            }
        )
        trip_id = trip_response.json()["id"]

    # Mock LLM
    from src.application import macro_planner
    original_factory = macro_planner.get_macro_planning_llm_client
    from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

    macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

    try:
        # Run orchestrator (should generate everything)
        async with AsyncSessionLocal() as db:
            orchestrator = TripPlannerOrchestrator()
            itinerary = await orchestrator.plan_trip(trip_id, db)

            # Verify macro plan was created
            macro_plan = await orchestrator.macro_planner.get_macro_plan(trip_id, db)
            assert macro_plan is not None

            # Verify POI plan was created
            poi_plan = await orchestrator.poi_planner.get_poi_plan(trip_id, db)
            assert poi_plan is not None

            # Verify itinerary was created
            assert itinerary is not None
            assert itinerary.trip_id == trip_id

    finally:
        macro_planner.get_macro_planning_llm_client = original_factory
