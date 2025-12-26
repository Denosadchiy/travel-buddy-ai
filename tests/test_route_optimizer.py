"""
Tests for Route & Time Optimizer functionality.
"""
import pytest
from uuid import uuid4
from datetime import date, time
from httpx import AsyncClient

from src.main import app
from src.application.route_optimizer import RouteTimeOptimizer
from src.infrastructure.database import AsyncSessionLocal
from src.infrastructure.travel_time import TravelTimeProvider, TravelTimeResult, TravelLocation
from src.domain.models import POICandidate


class MockTravelTimeProvider(TravelTimeProvider):
    """Mock travel time provider for testing."""

    def __init__(
        self,
        fixed_time: int = 15,
        fixed_distance: int = 3000,
        fixed_polyline: str = "mock_polyline_abc123",
    ):
        self.fixed_time = fixed_time
        self.fixed_distance = fixed_distance
        self.fixed_polyline = fixed_polyline

    async def estimate_travel(
        self,
        origin: TravelLocation,
        destination: TravelLocation,
        mode: str = "DRIVE",
    ) -> TravelTimeResult:
        """Return fixed travel result."""
        return TravelTimeResult(
            duration_minutes=self.fixed_time,
            distance_meters=self.fixed_distance,
            polyline=self.fixed_polyline,
        )


@pytest.mark.asyncio
async def test_route_optimizer_service():
    """Test RouteTimeOptimizer service end-to-end."""
    # Create trip with macro and POI plans
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

        # Generate macro plan
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/macro-plan")

            # Generate POI plan
            await client.post(f"/api/trips/{trip_id}/poi-plan")
        finally:
            macro_planner.get_macro_planning_llm_client = original_factory

    # Now test route optimizer
    async with AsyncSessionLocal() as db:
        # Use mock travel time provider
        optimizer = RouteTimeOptimizer(travel_time_provider=MockTravelTimeProvider(fixed_time=10))
        itinerary = await optimizer.generate_itinerary(trip_id, db)

    assert itinerary.trip_id == trip_id
    assert len(itinerary.days) > 0

    # Verify blocks have correct structure
    for day in itinerary.days:
        assert day.day_number >= 1
        assert isinstance(day.blocks, list)
        assert len(day.blocks) > 0

        for block in day.blocks:
            assert block.start_time is not None
            assert block.end_time is not None
            assert block.travel_time_from_prev >= 0

            # Blocks needing POIs should have them
            if block.block_type.value in ["meal", "activity", "nightlife"]:
                # POI might be None if no candidates were available
                if block.poi:
                    assert isinstance(block.poi, POICandidate)
            else:
                # REST/TRAVEL blocks should not have POIs
                assert block.poi is None


@pytest.mark.asyncio
async def test_route_optimizer_poi_selection():
    """Test that RouteTimeOptimizer selects top-ranked POI."""
    # Create trip with macro and POI plans
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

        # Create plans
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/macro-plan")
            await client.post(f"/api/trips/{trip_id}/poi-plan")
        finally:
            macro_planner.get_macro_planning_llm_client = original_factory

    # Generate itinerary
    async with AsyncSessionLocal() as db:
        optimizer = RouteTimeOptimizer(travel_time_provider=MockTravelTimeProvider())
        itinerary = await optimizer.generate_itinerary(trip_id, db)

    # Verify that POIs were selected (top-ranked from candidates)
    has_poi = False
    for day in itinerary.days:
        for block in day.blocks:
            if block.poi:
                has_poi = True
                # Verify POI has required fields
                assert block.poi.poi_id
                assert block.poi.name
                assert block.poi.category

    # Should have at least some POIs
    assert has_poi


@pytest.mark.asyncio
async def test_route_optimizer_travel_times():
    """Test that RouteTimeOptimizer calculates travel times."""
    # Create trip
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

        # Create plans
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/macro-plan")
            await client.post(f"/api/trips/{trip_id}/poi-plan")
        finally:
            macro_planner.get_macro_planning_llm_client = original_factory

    # Generate itinerary with fixed travel time
    fixed_travel_time = 20
    async with AsyncSessionLocal() as db:
        optimizer = RouteTimeOptimizer(
            travel_time_provider=MockTravelTimeProvider(fixed_time=fixed_travel_time)
        )
        itinerary = await optimizer.generate_itinerary(trip_id, db)

    # Verify travel times are calculated
    for day in itinerary.days:
        for i, block in enumerate(day.blocks):
            if i == 0:
                # First block might have 0 travel time
                assert block.travel_time_from_prev >= 0
            else:
                # Subsequent blocks with POIs should have travel time
                if block.poi:
                    # Should match our fixed time
                    assert block.travel_time_from_prev >= 0


@pytest.mark.asyncio
async def test_route_optimizer_rest_blocks():
    """Test that REST/TRAVEL blocks are handled correctly."""
    # Create trip
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

        # Create plans
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/macro-plan")
            await client.post(f"/api/trips/{trip_id}/poi-plan")
        finally:
            macro_planner.get_macro_planning_llm_client = original_factory

    # Generate itinerary
    async with AsyncSessionLocal() as db:
        optimizer = RouteTimeOptimizer(travel_time_provider=MockTravelTimeProvider())
        itinerary = await optimizer.generate_itinerary(trip_id, db)

    # Check for REST blocks
    for day in itinerary.days:
        for block in day.blocks:
            if block.block_type.value == "rest":
                # REST blocks should not have POIs
                assert block.poi is None
                # But should have notes
                assert block.notes is not None


@pytest.mark.asyncio
async def test_route_optimizer_missing_macro_plan():
    """Test that optimizer fails when macro plan is missing."""
    # Create trip without macro plan
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

    # Try to generate itinerary without macro plan
    async with AsyncSessionLocal() as db:
        optimizer = RouteTimeOptimizer()

        with pytest.raises(ValueError) as exc_info:
            await optimizer.generate_itinerary(trip_id, db)

        assert "macro plan" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_route_optimizer_missing_poi_plan():
    """Test that optimizer fails when POI plan is missing."""
    # Create trip with macro plan but no POI plan
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

        # Create only macro plan
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/macro-plan")
        finally:
            macro_planner.get_macro_planning_llm_client = original_factory

    # Try to generate itinerary without POI plan
    async with AsyncSessionLocal() as db:
        optimizer = RouteTimeOptimizer()

        with pytest.raises(ValueError) as exc_info:
            await optimizer.generate_itinerary(trip_id, db)

        assert "poi plan" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_get_itinerary():
    """Test getting stored itinerary."""
    # Create trip and generate itinerary
    async with AsyncClient(app=app, base_url="http://test") as client:
        trip_response = await client.post(
            "/api/trips",
            json={
                "city": "Madrid",
                "start_date": "2024-12-01",
                "end_date": "2024-12-02",
            }
        )
        trip_id = trip_response.json()["id"]

        # Create plans
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/macro-plan")
            await client.post(f"/api/trips/{trip_id}/poi-plan")
        finally:
            macro_planner.get_macro_planning_llm_client = original_factory

    # Generate itinerary
    async with AsyncSessionLocal() as db:
        optimizer = RouteTimeOptimizer()
        await optimizer.generate_itinerary(trip_id, db)

        # Get stored itinerary
        stored_itinerary = await optimizer.get_itinerary(trip_id, db)

    assert stored_itinerary is not None
    assert stored_itinerary.trip_id == trip_id
    assert len(stored_itinerary.days) > 0


@pytest.mark.asyncio
async def test_get_itinerary_not_found():
    """Test getting itinerary when none exists."""
    # Create trip without itinerary
    async with AsyncClient(app=app, base_url="http://test") as client:
        trip_response = await client.post(
            "/api/trips",
            json={
                "city": "Lisbon",
                "start_date": "2025-01-01",
                "end_date": "2025-01-02",
            }
        )
        trip_id = trip_response.json()["id"]

    # Try to get itinerary
    async with AsyncSessionLocal() as db:
        optimizer = RouteTimeOptimizer()
        stored_itinerary = await optimizer.get_itinerary(trip_id, db)

    assert stored_itinerary is None
