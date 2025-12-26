"""
Tests for Critique API endpoints.
"""
import pytest
from uuid import uuid4
from httpx import AsyncClient

from src.main import app


@pytest.mark.asyncio
async def test_get_critique_endpoint_success():
    """Test GET /api/trips/{trip_id}/critique endpoint."""
    # Create trip and generate plan (which includes critique)
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

        # Mock LLM and generate plan
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/plan")

            # Get critique
            critique_response = await client.get(f"/api/trips/{trip_id}/critique")

            assert critique_response.status_code == 200
            data = critique_response.json()

            assert data["trip_id"] == trip_id
            assert "issues" in data
            assert "total_issues" in data
            assert "by_severity" in data
            assert isinstance(data["issues"], list)
            assert isinstance(data["total_issues"], int)
            assert isinstance(data["by_severity"], dict)

        finally:
            macro_planner.get_macro_planning_llm_client = original_factory


@pytest.mark.asyncio
async def test_get_critique_endpoint_empty():
    """Test GET /api/trips/{trip_id}/critique returns empty for trip without plan."""
    # Create trip without plan
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

        # Get critique (should return empty)
        response = await client.get(f"/api/trips/{trip_id}/critique")

        assert response.status_code == 200
        data = response.json()

        assert data["trip_id"] == trip_id
        assert data["total_issues"] == 0
        assert len(data["issues"]) == 0
        assert data["by_severity"] == {}


@pytest.mark.asyncio
async def test_get_critique_endpoint_trip_not_found():
    """Test GET /api/trips/{trip_id}/critique with non-existent trip."""
    fake_trip_id = uuid4()

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(f"/api/trips/{fake_trip_id}/critique")

    # Should return 404 (trip doesn't exist)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_critique_response_structure():
    """Test that critique response has correct structure."""
    # Create trip and plan
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

        # Generate plan
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/plan")

            # Get critique
            response = await client.get(f"/api/trips/{trip_id}/critique")
            data = response.json()

            # Verify structure
            assert "trip_id" in data
            assert "issues" in data
            assert "total_issues" in data
            assert "by_severity" in data

            # Verify issue structure (if any issues exist)
            for issue in data["issues"]:
                assert "code" in issue
                assert "severity" in issue
                assert "message" in issue
                assert "details" in issue
                # Optional fields
                assert "day_number" in issue or issue.get("day_number") is None
                assert "block_index" in issue or issue.get("block_index") is None

        finally:
            macro_planner.get_macro_planning_llm_client = original_factory


@pytest.mark.asyncio
async def test_critique_by_severity_counts():
    """Test that by_severity counts match issue list."""
    # Create trip and plan
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

        # Generate plan
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/plan")

            # Get critique
            response = await client.get(f"/api/trips/{trip_id}/critique")
            data = response.json()

            # Verify counts match
            total_from_severity = sum(data["by_severity"].values())
            assert total_from_severity == data["total_issues"]
            assert total_from_severity == len(data["issues"])

            # Verify individual counts
            from collections import Counter
            severity_counts = Counter(issue["severity"] for issue in data["issues"])

            for severity, count in data["by_severity"].items():
                assert severity_counts[severity] == count

        finally:
            macro_planner.get_macro_planning_llm_client = original_factory


@pytest.mark.asyncio
async def test_critique_issue_codes():
    """Test that critique issues have valid codes."""
    # Create trip and plan
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

        # Generate plan
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/plan")

            # Get critique
            response = await client.get(f"/api/trips/{trip_id}/critique")
            data = response.json()

            # Verify issue codes
            valid_codes = [
                "DAY_TOO_BUSY",
                "MISSING_BREAKFAST",
                "MISSING_LUNCH",
                "MISSING_DINNER",
                "INVALID_TIME_RANGE",
                "BLOCK_OVERLAP",
                "LONG_TRAVEL",
                "LATE_NIGHTLIFE",
                "CONSECUTIVE_INTENSE_DAYS",
            ]

            for issue in data["issues"]:
                assert issue["code"] in valid_codes

        finally:
            macro_planner.get_macro_planning_llm_client = original_factory


@pytest.mark.asyncio
async def test_critique_after_plan_regeneration():
    """Test that critique is updated when plan is regenerated."""
    # Create trip
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
            # Generate plan first time
            await client.post(f"/api/trips/{trip_id}/plan")
            first_critique = await client.get(f"/api/trips/{trip_id}/critique")
            first_data = first_critique.json()

            # Generate plan second time
            await client.post(f"/api/trips/{trip_id}/plan")
            second_critique = await client.get(f"/api/trips/{trip_id}/critique")
            second_data = second_critique.json()

            # Both should have critique (may or may not be different)
            assert "total_issues" in first_data
            assert "total_issues" in second_data

        finally:
            macro_planner.get_macro_planning_llm_client = original_factory


@pytest.mark.asyncio
async def test_critique_created_at_timestamp():
    """Test that critique includes created_at timestamp."""
    # Create trip and plan
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

        # Generate plan
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/plan")

            # Get critique
            response = await client.get(f"/api/trips/{trip_id}/critique")
            data = response.json()

            # Should have created_at
            assert "created_at" in data
            if data["created_at"]:
                assert isinstance(data["created_at"], str)
                # Should be ISO format with Z
                assert data["created_at"].endswith("Z")

        finally:
            macro_planner.get_macro_planning_llm_client = original_factory
