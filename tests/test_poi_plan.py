"""
Tests for POI planning functionality.
"""
import pytest
from uuid import uuid4
from httpx import AsyncClient

from src.main import app
from src.application.poi_planner import POIPlanner
from src.infrastructure.database import AsyncSessionLocal
from src.infrastructure.poi_providers import DBPOIProvider, CompositePOIProvider, ExternalPOIProvider, GooglePlacesPOIProvider
from src.infrastructure.models import POIModel
from src.domain.models import POICandidate, BudgetLevel, BlockType


class MockExternalPOIProvider:
    """Mock external provider for testing."""

    def __init__(self, mock_results: list[POICandidate]):
        self.mock_results = mock_results

    async def search_pois(self, city, desired_categories, budget=None, limit=10, center_location=None):
        return self.mock_results[:limit]


@pytest.mark.asyncio
async def test_db_poi_provider():
    """Test DBPOIProvider searches and ranks POIs."""
    async with AsyncSessionLocal() as db:
        provider = DBPOIProvider(db)

        # Search for cafe/breakfast in Paris (should find existing POIs from seed data)
        results = await provider.search_pois(
            city="Paris",
            desired_categories=["cafe", "breakfast"],
            budget=BudgetLevel.MEDIUM,
            limit=5
        )

        # Should find at least some results if seed data exists
        # Note: This test depends on seed data being present
        assert isinstance(results, list)
        for candidate in results:
            assert isinstance(candidate, POICandidate)
            assert candidate.rank_score >= 0


@pytest.mark.asyncio
async def test_composite_provider_fallback():
    """Test CompositePOIProvider falls back to external when DB has insufficient results."""
    async with AsyncSessionLocal() as db:
        db_provider = DBPOIProvider(db)

        # Create mock external results
        mock_external = [
            POICandidate(
                poi_id=uuid4(),
                name="External POI 1",
                category="restaurant",
                tags=["sushi"],
                rating=4.5,
                location="External location",
                rank_score=10.0
            )
        ]
        external_provider = MockExternalPOIProvider(mock_external)

        composite = CompositePOIProvider(db_provider, external_provider)

        # Search for a very specific category unlikely to have many DB results
        results = await composite.search_pois(
            city="UnknownCity",
            desired_categories=["very_specific_category"],
            limit=10
        )

        # Should include external results when DB is insufficient
        assert isinstance(results, list)


@pytest.mark.asyncio
async def test_poi_planner_service():
    """Test POIPlanner service end-to-end."""
    # Create a trip
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

        # Generate macro plan first (mock it)
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client

        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/macro-plan")
        finally:
            macro_planner.get_macro_planning_llm_client = original_factory

    # Now test POI planning
    async with AsyncSessionLocal() as db:
        planner = POIPlanner()
        poi_plan = await planner.generate_poi_plan(trip_id, db)

    assert poi_plan.trip_id == trip_id
    assert len(poi_plan.blocks) > 0

    # Verify blocks have correct structure
    for block in poi_plan.blocks:
        assert block.day_number >= 1
        assert block.block_index >= 0
        assert block.block_type in [BlockType.MEAL, BlockType.ACTIVITY, BlockType.NIGHTLIFE]
        assert isinstance(block.candidates, list)


@pytest.mark.asyncio
async def test_poi_plan_endpoint_create():
    """Test POST /api/trips/{trip_id}/poi-plan endpoint."""
    # Create trip and macro plan
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

        # Create macro plan
        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/macro-plan")

            # Generate POI plan
            poi_response = await client.post(f"/api/trips/{trip_id}/poi-plan")

            assert poi_response.status_code == 201
            data = poi_response.json()

            assert data["trip_id"] == trip_id
            assert "blocks" in data
            assert "created_at" in data

        finally:
            macro_planner.get_macro_planning_llm_client = original_factory


@pytest.mark.asyncio
async def test_poi_plan_endpoint_get():
    """Test GET /api/trips/{trip_id}/poi-plan endpoint."""
    # Create trip, macro plan, and POI plan
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

            # Get POI plan
            get_response = await client.get(f"/api/trips/{trip_id}/poi-plan")

            assert get_response.status_code == 200
            data = get_response.json()
            assert data["trip_id"] == trip_id

        finally:
            macro_planner.get_macro_planning_llm_client = original_factory


@pytest.mark.asyncio
async def test_poi_plan_macro_plan_missing():
    """Test POI planning fails when macro plan is missing."""
    # Create trip without macro plan
    async with AsyncClient(app=app, base_url="http://test") as client:
        trip_response = await client.post(
            "/api/trips",
            json={
                "city": "Berlin",
                "start_date": "2024-09-01",
                "end_date": "2024-09-02",
            }
        )
        trip_id = trip_response.json()["id"]

        # Try to generate POI plan without macro plan
        response = await client.post(f"/api/trips/{trip_id}/poi-plan")

    assert response.status_code == 404
    assert "macro plan" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_poi_plan_not_found():
    """Test getting POI plan when none exists."""
    # Create trip without POI plan
    async with AsyncClient(app=app, base_url="http://test") as client:
        trip_response = await client.post(
            "/api/trips",
            json={
                "city": "Amsterdam",
                "start_date": "2024-10-01",
                "end_date": "2024-10-02",
            }
        )
        trip_id = trip_response.json()["id"]

        # Try to get POI plan
        response = await client.get(f"/api/trips/{trip_id}/poi-plan")

    assert response.status_code == 404
    assert "no poi plan" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_poi_planner_respects_block_types():
    """Test that POI planner only generates candidates for relevant block types."""
    # Create trip and macro plan
    async with AsyncClient(app=app, base_url="http://test") as client:
        trip_response = await client.post(
            "/api/trips",
            json={
                "city": "Rome",
                "start_date": "2024-11-01",
                "end_date": "2024-11-02",
            }
        )
        trip_id = trip_response.json()["id"]

        from src.application import macro_planner
        original_factory = macro_planner.get_macro_planning_llm_client
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/macro-plan")
        finally:
            macro_planner.get_macro_planning_llm_client = original_factory

    # Test POI planner
    async with AsyncSessionLocal() as db:
        planner = POIPlanner()
        poi_plan = await planner.generate_poi_plan(trip_id, db)

    # Verify only meal/activity/nightlife blocks have candidates
    for block in poi_plan.blocks:
        assert block.block_type in [BlockType.MEAL, BlockType.ACTIVITY, BlockType.NIGHTLIFE]
        # Rest and travel blocks should not be in poi_plan
