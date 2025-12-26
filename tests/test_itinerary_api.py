"""
Tests for Itinerary API endpoints.
"""
import pytest
from uuid import uuid4
from httpx import AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_plan_trip_endpoint_success():
    """Test POST /api/trips/{trip_id}/plan endpoint."""
    # Create trip
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
            # Generate full plan
            plan_response = await client.post(f"/api/trips/{trip_id}/plan")

            assert plan_response.status_code == 201
            data = plan_response.json()

            assert data["trip_id"] == trip_id
            assert "days" in data
            assert "created_at" in data
            assert len(data["days"]) > 0

            # Verify day structure
            for day in data["days"]:
                assert "day_number" in day
                assert "date" in day
                assert "theme" in day
                assert "blocks" in day
                assert len(day["blocks"]) > 0

                # Verify block structure
                for block in day["blocks"]:
                    assert "block_type" in block
                    assert "start_time" in block
                    assert "end_time" in block
                    assert "travel_time_from_prev" in block

        finally:
            macro_planner.get_macro_planning_llm_client = original_factory


@pytest.mark.asyncio
async def test_plan_trip_endpoint_trip_not_found():
    """Test POST /api/trips/{trip_id}/plan with non-existent trip."""
    fake_trip_id = uuid4()

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(f"/api/trips/{fake_trip_id}/plan")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_plan_trip_endpoint_idempotent():
    """Test that calling /plan multiple times is idempotent."""
    # Create trip
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

        # Mock LLM
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            # Generate plan first time
            first_response = await client.post(f"/api/trips/{trip_id}/plan")
            assert first_response.status_code == 201

            # Generate plan second time (should succeed)
            second_response = await client.post(f"/api/trips/{trip_id}/plan")
            assert second_response.status_code == 201

            # Both should have valid data
            first_data = first_response.json()
            second_data = second_response.json()

            assert first_data["trip_id"] == trip_id
            assert second_data["trip_id"] == trip_id

        finally:
            macro_planner.get_macro_planning_llm_client = original_factory


@pytest.mark.asyncio
async def test_get_itinerary_endpoint_success():
    """Test GET /api/trips/{trip_id}/itinerary endpoint."""
    # Create trip and generate plan
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

        # Mock LLM and generate plan
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/plan")

            # Get itinerary
            get_response = await client.get(f"/api/trips/{trip_id}/itinerary")

            assert get_response.status_code == 200
            data = get_response.json()

            assert data["trip_id"] == trip_id
            assert "days" in data
            assert "created_at" in data
            assert len(data["days"]) > 0

        finally:
            macro_planner.get_macro_planning_llm_client = original_factory


@pytest.mark.asyncio
async def test_get_itinerary_endpoint_not_found():
    """Test GET /api/trips/{trip_id}/itinerary when no itinerary exists."""
    # Create trip without generating plan
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

        # Try to get itinerary
        response = await client.get(f"/api/trips/{trip_id}/itinerary")

    assert response.status_code == 404
    assert "no itinerary" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_itinerary_endpoint_trip_not_found():
    """Test GET /api/trips/{trip_id}/itinerary with non-existent trip."""
    fake_trip_id = uuid4()

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(f"/api/trips/{fake_trip_id}/itinerary")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_plan_trip_endpoint_with_existing_macro_plan():
    """Test that /plan reuses existing macro plan."""
    # Create trip and macro plan
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

        # Mock LLM
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            # Create macro plan first
            await client.post(f"/api/trips/{trip_id}/macro-plan")

            # Now generate full plan (should reuse macro plan)
            plan_response = await client.post(f"/api/trips/{trip_id}/plan")

            assert plan_response.status_code == 201
            data = plan_response.json()
            assert data["trip_id"] == trip_id
            assert len(data["days"]) > 0

        finally:
            macro_planner.get_macro_planning_llm_client = original_factory


@pytest.mark.asyncio
async def test_plan_trip_endpoint_with_existing_poi_plan():
    """Test that /plan reuses existing POI plan."""
    # Create trip with macro and POI plans
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
            # Create both plans first
            await client.post(f"/api/trips/{trip_id}/macro-plan")
            await client.post(f"/api/trips/{trip_id}/poi-plan")

            # Now generate full plan (should reuse both)
            plan_response = await client.post(f"/api/trips/{trip_id}/plan")

            assert plan_response.status_code == 201
            data = plan_response.json()
            assert data["trip_id"] == trip_id
            assert len(data["days"]) > 0

        finally:
            macro_planner.get_macro_planning_llm_client = original_factory


@pytest.mark.asyncio
async def test_itinerary_has_poi_details():
    """Test that itinerary includes POI details."""
    # Create trip and generate plan
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

        # Mock LLM
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            # Generate plan
            plan_response = await client.post(f"/api/trips/{trip_id}/plan")
            data = plan_response.json()

            # Check for POI details
            has_poi = False
            for day in data["days"]:
                for block in day["blocks"]:
                    if block["poi"]:
                        has_poi = True
                        # Verify POI structure
                        assert "poi_id" in block["poi"]
                        assert "name" in block["poi"]
                        assert "category" in block["poi"]
                        assert "location" in block["poi"]

            # Should have at least some POIs
            assert has_poi

        finally:
            macro_planner.get_macro_planning_llm_client = original_factory


@pytest.mark.asyncio
async def test_itinerary_has_travel_times():
    """Test that itinerary includes travel times."""
    # Create trip and generate plan
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

        # Mock LLM
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            # Generate plan
            plan_response = await client.post(f"/api/trips/{trip_id}/plan")
            data = plan_response.json()

            # Check for travel times
            for day in data["days"]:
                for block in day["blocks"]:
                    assert "travel_time_from_prev" in block
                    assert isinstance(block["travel_time_from_prev"], int)
                    assert block["travel_time_from_prev"] >= 0

        finally:
            macro_planner.get_macro_planning_llm_client = original_factory
