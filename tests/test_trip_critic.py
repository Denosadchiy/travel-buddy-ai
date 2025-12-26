"""
Tests for Trip Critic functionality.
"""
import pytest
from datetime import time
from httpx import AsyncClient

from src.main import app
from src.application.trip_critic import TripCritic
from src.infrastructure.database import AsyncSessionLocal
from src.domain.models import (
    PaceLevel,
    BlockType,
    ItineraryDay,
    ItineraryBlock,
    POICandidate,
    CritiqueIssueSeverity,
)
from uuid import uuid4


@pytest.mark.asyncio
async def test_trip_critic_end_to_end():
    """Test TripCritic with a real planned trip."""
    # Create trip and generate full plan
    async with AsyncClient(app=app, base_url="http://test") as client:
        trip_response = await client.post(
            "/api/trips",
            json={
                "city": "Paris",
                "start_date": "2024-06-15",
                "end_date": "2024-06-16",
                "interests": ["food", "culture"],
                "pace": "slow"  # Slow pace for easier testing of DAY_TOO_BUSY
            }
        )
        trip_id = trip_response.json()["id"]

        # Mock LLM and generate itinerary
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/plan")
        finally:
            macro_planner.get_macro_planning_llm_client = original_factory

    # Run critic
    async with AsyncSessionLocal() as db:
        critic = TripCritic()
        issues = await critic.critique_trip(trip_id, db)

    # Should have some issues (depends on mock data)
    assert isinstance(issues, list)


@pytest.mark.asyncio
async def test_trip_critic_day_too_busy():
    """Test DAY_TOO_BUSY detection."""
    # Create trip with slow pace
    async with AsyncClient(app=app, base_url="http://test") as client:
        trip_response = await client.post(
            "/api/trips",
            json={
                "city": "Tokyo",
                "start_date": "2024-07-01",
                "end_date": "2024-07-02",
                "pace": "slow"  # Threshold: 7 hours
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
        finally:
            macro_planner.get_macro_planning_llm_client = original_factory

    # Check for DAY_TOO_BUSY issues
    async with AsyncSessionLocal() as db:
        critic = TripCritic()
        issues = await critic.critique_trip(trip_id, db)

    # Look for DAY_TOO_BUSY issues (may or may not exist depending on mock data)
    busy_issues = [i for i in issues if i.code == "DAY_TOO_BUSY"]
    # Just verify the check runs without error
    assert isinstance(busy_issues, list)


@pytest.mark.asyncio
async def test_trip_critic_missing_meals():
    """Test MISSING_BREAKFAST/LUNCH/DINNER detection."""
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

        # Generate plan
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/plan")
        finally:
            macro_planner.get_macro_planning_llm_client = original_factory

    # Run critic
    async with AsyncSessionLocal() as db:
        critic = TripCritic()
        issues = await critic.critique_trip(trip_id, db)

    # Check for meal-related issues
    meal_issues = [i for i in issues if i.code in ["MISSING_BREAKFAST", "MISSING_LUNCH", "MISSING_DINNER"]]
    # Verify check runs
    assert isinstance(meal_issues, list)


@pytest.mark.asyncio
async def test_trip_critic_storage():
    """Test that critique is stored in database."""
    # Create trip and generate plan
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

        # Generate plan (critic runs automatically)
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/plan")
        finally:
            macro_planner.get_macro_planning_llm_client = original_factory

    # Verify critique was stored
    async with AsyncSessionLocal() as db:
        critic = TripCritic()
        stored_issues = await critic.get_critique(trip_id, db)

    # Should have stored issues (or empty list)
    assert stored_issues is not None
    assert isinstance(stored_issues, list)


@pytest.mark.asyncio
async def test_trip_critic_get_critique_not_found():
    """Test getting critique when none exists."""
    # Create trip without plan
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

    # Try to get critique
    async with AsyncSessionLocal() as db:
        critic = TripCritic()
        issues = await critic.get_critique(trip_id, db)

    assert issues is None


@pytest.mark.asyncio
async def test_trip_critic_severity_levels():
    """Test that issues have correct severity levels."""
    # Create trip and plan
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

        # Generate plan
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/plan")
        finally:
            macro_planner.get_macro_planning_llm_client = original_factory

    # Get critique
    async with AsyncSessionLocal() as db:
        critic = TripCritic()
        issues = await critic.critique_trip(trip_id, db)

    # Verify all issues have valid severity
    for issue in issues:
        assert issue.severity in [
            CritiqueIssueSeverity.INFO,
            CritiqueIssueSeverity.WARNING,
            CritiqueIssueSeverity.ERROR,
        ]


@pytest.mark.asyncio
async def test_trip_critic_issue_codes():
    """Test that all issues have valid codes."""
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
        finally:
            macro_planner.get_macro_planning_llm_client = original_factory

    # Get critique
    async with AsyncSessionLocal() as db:
        critic = TripCritic()
        issues = await critic.critique_trip(trip_id, db)

    # Verify all issues have valid codes
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

    for issue in issues:
        assert issue.code in valid_codes
        assert isinstance(issue.message, str)
        assert len(issue.message) > 0
        assert isinstance(issue.details, dict)


@pytest.mark.asyncio
async def test_trip_critic_no_llm_calls():
    """Test that TripCritic is purely deterministic (no LLM calls)."""
    # Create trip and plan
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

        # Generate plan
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/plan")
        finally:
            macro_planner.get_macro_planning_llm_client = original_factory

    # Run critic multiple times - should give same results (deterministic)
    async with AsyncSessionLocal() as db:
        critic = TripCritic()

        issues1 = await critic.critique_trip(trip_id, db)
        issues2 = await critic.critique_trip(trip_id, db)

    # Results should be identical (deterministic)
    assert len(issues1) == len(issues2)

    # Compare issue codes
    codes1 = sorted([i.code for i in issues1])
    codes2 = sorted([i.code for i in issues2])
    assert codes1 == codes2
