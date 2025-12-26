"""
Tests for macro planning functionality.
"""
import pytest
from unittest.mock import AsyncMock
from uuid import uuid4
from httpx import AsyncClient
from datetime import date

from src.main import app
from src.application.macro_planner import MacroPlanner
from src.infrastructure.database import AsyncSessionLocal


class MockLLMClient:
    """Mock LLM client for testing macro planning."""

    def __init__(self, response: dict):
        self.response = response

    async def generate_structured(self, prompt: str, system_prompt: str = None, max_tokens: int = 2048):
        """Return mocked structured response."""
        return self.response


@pytest.fixture
def mock_macro_plan_response():
    """Mock LLM response for macro planning."""
    return {
        "days": [
            {
                "day_number": 1,
                "date": "2024-06-15",
                "theme": "Historic Center & Local Food",
                "blocks": [
                    {
                        "block_type": "meal",
                        "start_time": "08:30:00",
                        "end_time": "09:30:00",
                        "theme": "Breakfast",
                        "desired_categories": ["cafe", "breakfast", "bakery"]
                    },
                    {
                        "block_type": "activity",
                        "start_time": "10:00:00",
                        "end_time": "13:00:00",
                        "theme": "Historic landmarks",
                        "desired_categories": ["landmark", "architecture", "culture"]
                    },
                    {
                        "block_type": "meal",
                        "start_time": "13:00:00",
                        "end_time": "14:30:00",
                        "theme": "Lunch",
                        "desired_categories": ["restaurant", "local cuisine"]
                    },
                    {
                        "block_type": "activity",
                        "start_time": "15:00:00",
                        "end_time": "18:00:00",
                        "theme": "Shopping and cafes",
                        "desired_categories": ["shopping", "cafe"]
                    },
                    {
                        "block_type": "meal",
                        "start_time": "19:30:00",
                        "end_time": "21:30:00",
                        "theme": "Dinner",
                        "desired_categories": ["restaurant", "fine dining"]
                    }
                ]
            },
            {
                "day_number": 2,
                "date": "2024-06-16",
                "theme": "Parks & Nightlife",
                "blocks": [
                    {
                        "block_type": "meal",
                        "start_time": "09:00:00",
                        "end_time": "10:00:00",
                        "theme": "Breakfast",
                        "desired_categories": ["cafe", "breakfast"]
                    },
                    {
                        "block_type": "activity",
                        "start_time": "10:30:00",
                        "end_time": "13:00:00",
                        "theme": "Parks and views",
                        "desired_categories": ["park", "viewpoint", "nature"]
                    },
                    {
                        "block_type": "meal",
                        "start_time": "13:30:00",
                        "end_time": "15:00:00",
                        "theme": "Lunch",
                        "desired_categories": ["restaurant", "outdoor seating"]
                    },
                    {
                        "block_type": "rest",
                        "start_time": "15:00:00",
                        "end_time": "17:00:00",
                        "theme": "Rest at hotel",
                        "desired_categories": []
                    },
                    {
                        "block_type": "meal",
                        "start_time": "20:00:00",
                        "end_time": "22:00:00",
                        "theme": "Dinner",
                        "desired_categories": ["restaurant", "local cuisine"]
                    },
                    {
                        "block_type": "nightlife",
                        "start_time": "23:00:00",
                        "end_time": "02:00:00",
                        "theme": "Techno nightlife",
                        "desired_categories": ["nightlife", "techno", "club"]
                    }
                ]
            }
        ]
    }


@pytest.mark.asyncio
async def test_macro_planner_service(mock_macro_plan_response):
    """Test MacroPlanner service directly."""
    # Create a trip
    async with AsyncClient(app=app, base_url="http://test") as client:
        create_response = await client.post(
            "/api/trips",
            json={
                "city": "Paris",
                "start_date": "2024-06-15",
                "end_date": "2024-06-16",
                "interests": ["food", "culture", "nightlife"]
            }
        )
        trip_id = create_response.json()["id"]

    # Test macro planner directly
    async with AsyncSessionLocal() as db:
        mock_llm = MockLLMClient(mock_macro_plan_response)
        planner = MacroPlanner(llm_client=mock_llm)

        macro_plan = await planner.generate_macro_plan(trip_id, db)

    # Verify response
    assert macro_plan.trip_id == trip_id
    assert len(macro_plan.days) == 2

    # Verify day 1
    day1 = macro_plan.days[0]
    assert day1.day_number == 1
    assert day1.theme == "Historic Center & Local Food"
    assert len(day1.blocks) == 5

    # Verify blocks
    breakfast = day1.blocks[0]
    assert breakfast.block_type.value == "meal"
    assert "cafe" in breakfast.desired_categories

    activity = day1.blocks[1]
    assert activity.block_type.value == "activity"
    assert "landmark" in activity.desired_categories

    # Verify day 2 has nightlife
    day2 = macro_plan.days[1]
    nightlife_block = day2.blocks[-1]
    assert nightlife_block.block_type.value == "nightlife"
    assert "techno" in nightlife_block.desired_categories


@pytest.mark.asyncio
async def test_macro_plan_endpoint_create(mock_macro_plan_response):
    """Test POST /api/trips/{trip_id}/macro-plan endpoint."""
    # Create a trip
    async with AsyncClient(app=app, base_url="http://test") as client:
        create_response = await client.post(
            "/api/trips",
            json={
                "city": "Barcelona",
                "start_date": "2024-08-01",
                "end_date": "2024-08-03",
            }
        )
        trip_id = create_response.json()["id"]

        # Mock the LLM client
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response)

        try:
            # Generate macro plan
            plan_response = await client.post(f"/api/trips/{trip_id}/macro-plan")

            assert plan_response.status_code == 201
            data = plan_response.json()

            assert data["trip_id"] == trip_id
            assert "days" in data
            assert len(data["days"]) == 2
            assert "created_at" in data

        finally:
            # Restore original factory
            macro_planner.get_macro_planning_llm_client = original_factory


@pytest.mark.asyncio
async def test_macro_plan_endpoint_get(mock_macro_plan_response):
    """Test GET /api/trips/{trip_id}/macro-plan endpoint."""
    # Create a trip
    async with AsyncClient(app=app, base_url="http://test") as client:
        create_response = await client.post(
            "/api/trips",
            json={
                "city": "Tokyo",
                "start_date": "2024-07-01",
                "end_date": "2024-07-02",
            }
        )
        trip_id = create_response.json()["id"]

        # Mock and create macro plan
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response)

        try:
            # Create macro plan
            await client.post(f"/api/trips/{trip_id}/macro-plan")

            # Get macro plan
            get_response = await client.get(f"/api/trips/{trip_id}/macro-plan")

            assert get_response.status_code == 200
            data = get_response.json()

            assert data["trip_id"] == trip_id
            assert len(data["days"]) == 2

        finally:
            macro_planner.get_macro_planning_llm_client = original_factory


@pytest.mark.asyncio
async def test_macro_plan_trip_not_found():
    """Test macro planning with non-existent trip."""
    fake_trip_id = str(uuid4())

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(f"/api/trips/{fake_trip_id}/macro-plan")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_macro_plan_not_found():
    """Test getting macro plan when none exists."""
    # Create a trip without macro plan
    async with AsyncClient(app=app, base_url="http://test") as client:
        create_response = await client.post(
            "/api/trips",
            json={
                "city": "Berlin",
                "start_date": "2024-09-01",
                "end_date": "2024-09-03",
            }
        )
        trip_id = create_response.json()["id"]

        # Try to get macro plan (should not exist yet)
        get_response = await client.get(f"/api/trips/{trip_id}/macro-plan")

    assert get_response.status_code == 404
    assert "no macro plan" in get_response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_macro_plan_stored_in_database(mock_macro_plan_response):
    """Test that macro plan is persisted in database."""
    # Create a trip
    async with AsyncClient(app=app, base_url="http://test") as client:
        create_response = await client.post(
            "/api/trips",
            json={
                "city": "Amsterdam",
                "start_date": "2024-10-01",
                "end_date": "2024-10-02",
            }
        )
        trip_id = create_response.json()["id"]

    # Generate macro plan
    async with AsyncSessionLocal() as db:
        mock_llm = MockLLMClient(mock_macro_plan_response)
        planner = MacroPlanner(llm_client=mock_llm)

        await planner.generate_macro_plan(trip_id, db)

    # Verify it's stored
    async with AsyncSessionLocal() as db:
        planner = MacroPlanner()
        retrieved_plan = await planner.get_macro_plan(trip_id, db)

    assert retrieved_plan is not None
    assert str(retrieved_plan.trip_id) == trip_id
    assert len(retrieved_plan.days) == 2


@pytest.mark.asyncio
async def test_macro_plan_respects_trip_spec(mock_macro_plan_response):
    """Test that macro planner receives correct trip context."""
    # Create a trip with specific preferences
    async with AsyncClient(app=app, base_url="http://test") as client:
        create_response = await client.post(
            "/api/trips",
            json={
                "city": "Rome",
                "start_date": "2024-11-01",
                "end_date": "2024-11-02",
                "pace": "slow",
                "budget": "high",
                "interests": ["food", "architecture"],
                "daily_routine": {
                    "wake_time": "09:00:00",
                    "sleep_time": "22:00:00"
                }
            }
        )
        trip_id = create_response.json()["id"]

    # Test that context is built correctly
    async with AsyncSessionLocal() as db:
        from src.application.trip_spec import TripSpecCollector

        collector = TripSpecCollector()
        trip_spec = await collector.get_trip(trip_id, db)

        planner = MacroPlanner()
        context = planner._build_trip_context(trip_spec)

        # Verify context includes key details
        assert "Rome" in context
        assert "slow" in context
        assert "high" in context
        assert "food" in context
        assert "architecture" in context
        assert "09:00:00" in context
