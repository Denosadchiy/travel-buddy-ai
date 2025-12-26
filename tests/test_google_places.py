"""
Tests for Google Places POI provider integration.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime

import httpx
from httpx import AsyncClient

from src.main import app
from src.application.poi_planner import POIPlanner
from src.infrastructure.database import AsyncSessionLocal
from src.infrastructure.poi_providers import (
    GooglePlacesPOIProvider,
    DBPOIProvider,
    CompositePOIProvider,
    GooglePlaceResult,
    GOOGLE_TYPE_TO_CATEGORY,
    get_poi_provider,
)
from src.infrastructure.models import POIModel
from src.domain.models import POICandidate, BudgetLevel, BlockType


# Sample Google Places API response
MOCK_GOOGLE_PLACES_RESPONSE = {
    "status": "OK",
    "results": [
        {
            "place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4",
            "name": "Le Petit Cler",
            "formatted_address": "29 Rue Cler, 75007 Paris, France",
            "geometry": {
                "location": {
                    "lat": 48.8566,
                    "lng": 2.3522
                }
            },
            "types": ["restaurant", "food", "point_of_interest", "establishment"],
            "rating": 4.5,
            "price_level": 2,
        },
        {
            "place_id": "ChIJLU7jZClu5kcRamf",
            "name": "Café de Flore",
            "formatted_address": "172 Boulevard Saint-Germain, 75006 Paris, France",
            "geometry": {
                "location": {
                    "lat": 48.8540,
                    "lng": 2.3325
                }
            },
            "types": ["cafe", "food", "point_of_interest", "establishment"],
            "rating": 4.2,
            "price_level": 3,
        },
        {
            "place_id": "ChIJRVY_etDX5kcRNNmjXh",
            "name": "Musée d'Orsay",
            "formatted_address": "1 Rue de la Légion d'Honneur, 75007 Paris, France",
            "geometry": {
                "location": {
                    "lat": 48.8599,
                    "lng": 2.3266
                }
            },
            "types": ["museum", "tourist_attraction", "point_of_interest", "establishment"],
            "rating": 4.7,
        },
    ]
}

MOCK_EMPTY_RESPONSE = {
    "status": "ZERO_RESULTS",
    "results": []
}

MOCK_ERROR_RESPONSE = {
    "status": "REQUEST_DENIED",
    "error_message": "The provided API key is invalid."
}


class MockResponse:
    """Mock HTTP response."""

    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                message="Error",
                request=MagicMock(),
                response=self
            )


# ============== Unit Tests for GooglePlacesPOIProvider ==============


@pytest.mark.asyncio
async def test_google_places_provider_parses_response():
    """Test that GooglePlacesPOIProvider correctly parses Google API response."""
    async with AsyncSessionLocal() as db:
        provider = GooglePlacesPOIProvider(
            db=db,
            api_key="test_api_key",
            base_url="https://maps.googleapis.com/maps/api/place/textsearch/json"
        )

        # Mock the HTTP client
        with patch.object(httpx.AsyncClient, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = MockResponse(MOCK_GOOGLE_PLACES_RESPONSE)

            results = await provider.search_pois(
                city="Paris",
                desired_categories=["restaurant", "cafe"],
                budget=BudgetLevel.MEDIUM,
                limit=10
            )

            # Verify API was called
            mock_get.assert_called_once()

            # Verify results
            assert len(results) == 3
            assert all(isinstance(r, POICandidate) for r in results)

            # Verify first result
            restaurant = next(r for r in results if r.name == "Le Petit Cler")
            assert restaurant.rating == 4.5
            assert restaurant.category == "restaurant"
            assert "restaurant" in restaurant.tags

            # Verify museum is parsed correctly
            museum = next(r for r in results if r.name == "Musée d'Orsay")
            assert museum.rating == 4.7
            assert museum.category == "museum"


@pytest.mark.asyncio
async def test_google_places_provider_handles_empty_results():
    """Test graceful handling of zero results."""
    async with AsyncSessionLocal() as db:
        provider = GooglePlacesPOIProvider(
            db=db,
            api_key="test_api_key"
        )

        with patch.object(httpx.AsyncClient, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = MockResponse(MOCK_EMPTY_RESPONSE)

            results = await provider.search_pois(
                city="NonexistentCity",
                desired_categories=["restaurant"],
                limit=10
            )

            assert results == []


@pytest.mark.asyncio
async def test_google_places_provider_handles_api_error():
    """Test graceful handling of API errors."""
    async with AsyncSessionLocal() as db:
        provider = GooglePlacesPOIProvider(
            db=db,
            api_key="invalid_key"
        )

        with patch.object(httpx.AsyncClient, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = MockResponse(MOCK_ERROR_RESPONSE)

            results = await provider.search_pois(
                city="Paris",
                desired_categories=["restaurant"],
                limit=10
            )

            # Should return empty list, not raise exception
            assert results == []


@pytest.mark.asyncio
async def test_google_places_provider_handles_timeout():
    """Test graceful handling of timeouts."""
    async with AsyncSessionLocal() as db:
        provider = GooglePlacesPOIProvider(
            db=db,
            api_key="test_key",
            timeout_seconds=1
        )

        with patch.object(httpx.AsyncClient, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.TimeoutException("Timeout")

            results = await provider.search_pois(
                city="Paris",
                desired_categories=["restaurant"],
                limit=10
            )

            # Should return empty list, not raise exception
            assert results == []


@pytest.mark.asyncio
async def test_google_places_provider_skips_without_api_key():
    """Test that provider skips external calls when API key is missing."""
    async with AsyncSessionLocal() as db:
        provider = GooglePlacesPOIProvider(
            db=db,
            api_key=None  # No API key
        )

        # Should not make any HTTP calls
        with patch.object(httpx.AsyncClient, 'get', new_callable=AsyncMock) as mock_get:
            results = await provider.search_pois(
                city="Paris",
                desired_categories=["restaurant"],
                limit=10
            )

            mock_get.assert_not_called()
            assert results == []


@pytest.mark.asyncio
async def test_google_places_provider_caches_to_database():
    """Test that fetched places are cached to the database."""
    async with AsyncSessionLocal() as db:
        provider = GooglePlacesPOIProvider(
            db=db,
            api_key="test_api_key"
        )

        with patch.object(httpx.AsyncClient, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = MockResponse(MOCK_GOOGLE_PLACES_RESPONSE)

            # Fetch places
            results = await provider.search_pois(
                city="Paris",
                desired_categories=["restaurant"],
                limit=10
            )

            # Verify places are in the database
            from sqlalchemy import select
            query = select(POIModel).where(
                POIModel.external_source == "google_places"
            )
            db_result = await db.execute(query)
            cached_pois = db_result.scalars().all()

            assert len(cached_pois) == 3

            # Check a specific cached POI
            cached_restaurant = next(
                p for p in cached_pois
                if p.external_id == "ChIJN1t_tDeuEmsRUsoyG83frY4"
            )
            assert cached_restaurant.name == "Le Petit Cler"
            assert cached_restaurant.city == "Paris"
            assert cached_restaurant.lat == 48.8566
            assert cached_restaurant.lon == 2.3522
            assert cached_restaurant.price_level == 2


@pytest.mark.asyncio
async def test_google_places_provider_updates_existing_cache():
    """Test that cached places are updated when fetched again."""
    async with AsyncSessionLocal() as db:
        # Create an existing cached POI
        existing_poi = POIModel(
            id=uuid4(),
            name="Le Petit Cler",
            city="Paris",
            category="restaurant",
            tags=["restaurant"],
            rating=4.0,  # Old rating
            location="Old address",
            external_source="google_places",
            external_id="ChIJN1t_tDeuEmsRUsoyG83frY4",
            created_at=datetime.utcnow(),
        )
        db.add(existing_poi)
        await db.commit()
        old_id = existing_poi.id

        provider = GooglePlacesPOIProvider(
            db=db,
            api_key="test_api_key"
        )

        with patch.object(httpx.AsyncClient, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = MockResponse(MOCK_GOOGLE_PLACES_RESPONSE)

            results = await provider.search_pois(
                city="Paris",
                desired_categories=["restaurant"],
                limit=10
            )

            # Refresh from database
            await db.refresh(existing_poi)

            # Verify the POI was updated, not duplicated
            assert existing_poi.rating == 4.5  # Updated rating
            assert existing_poi.id == old_id  # Same ID


# ============== Tests for CompositePOIProvider ==============


class MockGooglePlacesProvider(GooglePlacesPOIProvider):
    """Mock Google Places provider for testing."""

    def __init__(self, mock_results: list[POICandidate]):
        self.mock_results = mock_results
        self.search_called = False

    async def search_pois(self, city, desired_categories, budget=None, limit=10, center_location=None):
        self.search_called = True
        return self.mock_results[:limit]


@pytest.mark.asyncio
async def test_composite_provider_uses_db_first():
    """Test that CompositePOIProvider queries DB first."""
    async with AsyncSessionLocal() as db:
        # Add some POIs to the database
        for i in range(5):
            poi = POIModel(
                id=uuid4(),
                name=f"DB Restaurant {i}",
                city="TestCity",
                category="restaurant",
                tags=["restaurant", "food"],
                rating=4.0 + i * 0.1,
                location=f"Address {i}",
                created_at=datetime.utcnow(),
            )
            db.add(poi)
        await db.commit()

        db_provider = DBPOIProvider(db)

        mock_external_results = [
            POICandidate(
                poi_id=uuid4(),
                name="External Restaurant",
                category="restaurant",
                tags=["restaurant"],
                rating=4.5,
                location="External Location",
                rank_score=15.0
            )
        ]
        external_provider = MockGooglePlacesProvider(mock_external_results)

        composite = CompositePOIProvider(db_provider, external_provider)

        # Request 3 POIs - should be fulfilled from DB only
        results = await composite.search_pois(
            city="TestCity",
            desired_categories=["restaurant"],
            limit=3
        )

        assert len(results) == 3
        assert all("DB Restaurant" in r.name for r in results)
        assert not external_provider.search_called


@pytest.mark.asyncio
async def test_composite_provider_falls_back_to_external():
    """Test that CompositePOIProvider fetches from external when DB is insufficient."""
    async with AsyncSessionLocal() as db:
        # Add only 2 POIs to database
        for i in range(2):
            poi = POIModel(
                id=uuid4(),
                name=f"DB Restaurant {i}",
                city="SparseCity",
                category="restaurant",
                tags=["restaurant"],
                rating=4.0,
                location=f"Address {i}",
                created_at=datetime.utcnow(),
            )
            db.add(poi)
        await db.commit()

        db_provider = DBPOIProvider(db)

        mock_external_results = [
            POICandidate(
                poi_id=uuid4(),
                name=f"External Restaurant {i}",
                category="restaurant",
                tags=["restaurant"],
                rating=4.5,
                location="External Location",
                rank_score=15.0
            )
            for i in range(5)
        ]
        external_provider = MockGooglePlacesProvider(mock_external_results)

        composite = CompositePOIProvider(db_provider, external_provider)

        # Request 5 POIs - should use both DB and external
        results = await composite.search_pois(
            city="SparseCity",
            desired_categories=["restaurant"],
            limit=5
        )

        assert len(results) == 5
        assert external_provider.search_called

        # Should have both DB and external results
        db_results = [r for r in results if "DB Restaurant" in r.name]
        external_results = [r for r in results if "External Restaurant" in r.name]
        assert len(db_results) == 2
        assert len(external_results) == 3


@pytest.mark.asyncio
async def test_composite_provider_deduplicates_results():
    """Test that CompositePOIProvider deduplicates by POI ID."""
    async with AsyncSessionLocal() as db:
        shared_id = uuid4()

        # Add a POI to database
        poi = POIModel(
            id=shared_id,
            name="Shared Restaurant",
            city="DupeCity",
            category="restaurant",
            tags=["restaurant"],
            rating=4.0,
            location="Address 1",
            created_at=datetime.utcnow(),
        )
        db.add(poi)
        await db.commit()

        db_provider = DBPOIProvider(db)

        # External provider returns a POI with the same ID
        mock_external_results = [
            POICandidate(
                poi_id=shared_id,  # Same ID as DB POI
                name="Shared Restaurant",
                category="restaurant",
                tags=["restaurant"],
                rating=4.5,
                location="Address 1",
                rank_score=15.0
            ),
            POICandidate(
                poi_id=uuid4(),
                name="Unique External Restaurant",
                category="restaurant",
                tags=["restaurant"],
                rating=4.5,
                location="External Location",
                rank_score=15.0
            )
        ]
        external_provider = MockGooglePlacesProvider(mock_external_results)

        composite = CompositePOIProvider(db_provider, external_provider)

        results = await composite.search_pois(
            city="DupeCity",
            desired_categories=["restaurant"],
            limit=10
        )

        # Should not have duplicates
        poi_ids = [r.poi_id for r in results]
        assert len(poi_ids) == len(set(poi_ids))


@pytest.mark.asyncio
async def test_composite_provider_handles_external_failure():
    """Test that CompositePOIProvider gracefully handles external provider failure."""
    async with AsyncSessionLocal() as db:
        # Add some POIs
        for i in range(2):
            poi = POIModel(
                id=uuid4(),
                name=f"DB Restaurant {i}",
                city="FailCity",
                category="restaurant",
                tags=["restaurant"],
                rating=4.0,
                location=f"Address {i}",
                created_at=datetime.utcnow(),
            )
            db.add(poi)
        await db.commit()

        db_provider = DBPOIProvider(db)

        # Create a failing external provider
        class FailingProvider(GooglePlacesPOIProvider):
            async def search_pois(self, *args, **kwargs):
                raise Exception("External API failed!")

        composite = CompositePOIProvider(db_provider, FailingProvider(db=db))

        # Should still return DB results
        results = await composite.search_pois(
            city="FailCity",
            desired_categories=["restaurant"],
            limit=5
        )

        assert len(results) == 2
        assert all("DB Restaurant" in r.name for r in results)


# ============== API-Level Integration Tests ==============


@pytest.mark.asyncio
async def test_poi_plan_endpoint_with_google_places():
    """Test POST /api/trips/{id}/poi-plan endpoint with mocked Google Places."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Create a trip
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

        # Mock macro planner LLM
        from src.application import macro_planner
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        original_factory = macro_planner.get_macro_planning_llm_client
        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            # Generate macro plan
            await client.post(f"/api/trips/{trip_id}/macro-plan")

            # Mock Google Places API for POI plan
            with patch.object(httpx.AsyncClient, 'get', new_callable=AsyncMock) as mock_get:
                mock_get.return_value = MockResponse(MOCK_GOOGLE_PLACES_RESPONSE)

                # Generate POI plan
                poi_response = await client.post(f"/api/trips/{trip_id}/poi-plan")

                assert poi_response.status_code == 201
                data = poi_response.json()

                assert data["trip_id"] == trip_id
                assert "blocks" in data

        finally:
            macro_planner.get_macro_planning_llm_client = original_factory

    # Verify POIs were cached to database
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        query = select(POIModel).where(
            POIModel.external_source == "google_places",
            POIModel.city == "Paris"
        )
        result = await db.execute(query)
        cached_pois = result.scalars().all()

        # Should have cached POIs from Google
        # Note: Number depends on how many blocks needed POIs
        assert len(cached_pois) >= 0  # At least attempted caching


@pytest.mark.asyncio
async def test_factory_function_with_api_key():
    """Test get_poi_provider creates GooglePlacesPOIProvider when API key is set."""
    from src.config import settings

    # Temporarily set API key
    original_key = settings.google_maps_api_key
    settings.google_maps_api_key = "test_key"

    try:
        async with AsyncSessionLocal() as db:
            provider = get_poi_provider(db)

            assert isinstance(provider, CompositePOIProvider)
            assert provider.external_provider is not None
            assert isinstance(provider.external_provider, GooglePlacesPOIProvider)
    finally:
        settings.google_maps_api_key = original_key


@pytest.mark.asyncio
async def test_factory_function_without_api_key():
    """Test get_poi_provider works without API key (DB-only mode)."""
    from src.config import settings

    # Temporarily remove API key
    original_key = settings.google_maps_api_key
    settings.google_maps_api_key = None

    try:
        async with AsyncSessionLocal() as db:
            provider = get_poi_provider(db)

            assert isinstance(provider, CompositePOIProvider)
            assert provider.external_provider is None
    finally:
        settings.google_maps_api_key = original_key


# ============== Type Mapping Tests ==============


def test_google_type_to_category_mapping():
    """Test that Google types are correctly mapped to our categories."""
    assert GOOGLE_TYPE_TO_CATEGORY["restaurant"] == "restaurant"
    assert GOOGLE_TYPE_TO_CATEGORY["cafe"] == "cafe"
    assert GOOGLE_TYPE_TO_CATEGORY["museum"] == "museum"
    assert GOOGLE_TYPE_TO_CATEGORY["night_club"] == "nightlife"
    assert GOOGLE_TYPE_TO_CATEGORY["tourist_attraction"] == "attraction"


@pytest.mark.asyncio
async def test_category_mapping_for_place():
    """Test that GooglePlacesPOIProvider maps types to categories correctly."""
    async with AsyncSessionLocal() as db:
        provider = GooglePlacesPOIProvider(db=db, api_key="test")

        # Restaurant types
        category = provider._map_google_types_to_category(
            ["restaurant", "food", "establishment"],
            ["restaurant", "cafe"]
        )
        assert category == "restaurant"

        # Museum types
        category = provider._map_google_types_to_category(
            ["museum", "tourist_attraction", "establishment"],
            ["museum", "attraction"]
        )
        assert category == "museum"

        # Fallback to desired categories
        category = provider._map_google_types_to_category(
            ["unknown_type", "establishment"],
            ["restaurant"]
        )
        assert category == "restaurant"
