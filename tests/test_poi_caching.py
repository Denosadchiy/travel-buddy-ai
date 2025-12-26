"""
Tests for POI caching functionality.
Verifies that GooglePlacesPOIProvider caches results to database
and CompositePOIProvider reuses cached POIs.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from src.infrastructure.poi_providers import (
    DBPOIProvider,
    GooglePlacesPOIProvider,
    CompositePOIProvider,
    GooglePlaceResult,
)
from src.infrastructure.models import POIModel
from src.domain.models import BudgetLevel, POICandidate


# Mock Google Places API responses
MOCK_GOOGLE_PLACES = [
    GooglePlaceResult(
        place_id="ChIJtest123",
        name="Café Test",
        formatted_address="123 Test St, Paris, France",
        types=["cafe", "restaurant"],
        rating=4.5,
        price_level=2,
        lat=48.8566,
        lon=2.3522,
    ),
    GooglePlaceResult(
        place_id="ChIJtest456",
        name="Breakfast Spot",
        formatted_address="456 Breakfast Ave, Paris, France",
        types=["cafe", "breakfast_restaurant"],
        rating=4.7,
        price_level=1,
        lat=48.8584,
        lon=2.2945,
    ),
]


@pytest.mark.asyncio
async def test_google_places_provider_caches_to_db():
    """Test that GooglePlacesPOIProvider caches fetched places to database."""
    # Create a mock database session
    mock_db = AsyncMock()

    # Mock the execute method to return no existing POIs (first run)
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = None
    mock_db.execute.return_value = mock_result

    # Create provider with mocked _fetch_from_google
    provider = GooglePlacesPOIProvider(
        db=mock_db,
        api_key="test_key",
        base_url="https://test.com",
    )

    # Mock the _fetch_from_google method to return test data
    provider._fetch_from_google = AsyncMock(return_value=MOCK_GOOGLE_PLACES)

    # Search for POIs
    candidates = await provider.search_pois(
        city="Paris",
        desired_categories=["cafe"],
        budget=BudgetLevel.MEDIUM,
        limit=5,
    )

    # Verify results
    assert len(candidates) == 2
    assert candidates[0].name == "Café Test"
    assert candidates[1].name == "Breakfast Spot"

    # Verify that db.add was called to cache POIs
    assert mock_db.add.call_count == 2

    # Verify that db.commit was called
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_google_places_provider_updates_existing_pois():
    """Test that GooglePlacesPOIProvider updates existing POIs instead of creating duplicates."""
    # Create a mock database session
    mock_db = AsyncMock()

    # Mock the execute method to return an existing POI
    existing_poi = POIModel(
        id=uuid4(),
        name="Café Test (old)",
        city="Paris",
        category="cafe",
        tags=["cafe"],
        rating=4.0,  # Old rating
        location="123 Test St, Paris, France",
        external_source="google_places",
        external_id="ChIJtest123",
        lat=48.8566,
        lon=2.3522,
    )

    mock_result = MagicMock()
    mock_result.scalars().first.return_value = existing_poi
    mock_db.execute.return_value = mock_result

    # Create provider
    provider = GooglePlacesPOIProvider(
        db=mock_db,
        api_key="test_key",
    )

    # Mock the _fetch_from_google method
    provider._fetch_from_google = AsyncMock(return_value=[MOCK_GOOGLE_PLACES[0]])

    # Search for POIs
    candidates = await provider.search_pois(
        city="Paris",
        desired_categories=["cafe"],
        budget=BudgetLevel.MEDIUM,
        limit=5,
    )

    # Verify results
    assert len(candidates) == 1

    # Verify that the existing POI was updated (rating changed from 4.0 to 4.5)
    assert existing_poi.rating == 4.5

    # Verify that db.add was NOT called (no new POI created)
    mock_db.add.assert_not_called()

    # Verify that db.commit was still called
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_composite_provider_uses_db_cache():
    """Test that CompositePOIProvider returns cached POIs from DB without calling external API."""
    # Create mock DB provider that returns cached POIs
    db_provider = AsyncMock(spec=DBPOIProvider)

    cached_pois = [
        POICandidate(
            poi_id=uuid4(),
            name="Cached Café",
            category="cafe",
            tags=["cafe"],
            rating=4.6,
            location="789 Cached St, Paris, France",
            lat=48.8600,
            lon=2.3400,
            rank_score=18.0,
        )
    ]

    db_provider.search_pois.return_value = cached_pois

    # Create mock external provider
    external_provider = AsyncMock(spec=GooglePlacesPOIProvider)

    # Create composite provider
    composite = CompositePOIProvider(
        db_provider=db_provider,
        external_provider=external_provider,
    )

    # Search for POIs (limit=1, DB returns 1, so external should not be called)
    results = await composite.search_pois(
        city="Paris",
        desired_categories=["cafe"],
        budget=BudgetLevel.MEDIUM,
        limit=1,
    )

    # Verify DB was queried
    db_provider.search_pois.assert_called_once()

    # Verify external provider was NOT called (DB had enough results)
    external_provider.search_pois.assert_not_called()

    # Verify results match cached POIs
    assert len(results) == 1
    assert results[0].name == "Cached Café"


@pytest.mark.asyncio
async def test_composite_provider_supplements_with_external():
    """Test that CompositePOIProvider fetches from external API when DB doesn't have enough results."""
    # Create mock DB provider that returns only 1 POI
    db_provider = AsyncMock(spec=DBPOIProvider)

    cached_poi = POICandidate(
        poi_id=uuid4(),
        name="Cached Café",
        category="cafe",
        tags=["cafe"],
        rating=4.6,
        location="789 Cached St, Paris, France",
        lat=48.8600,
        lon=2.3400,
        rank_score=18.0,
    )

    db_provider.search_pois.return_value = [cached_poi]

    # Create mock external provider that returns additional POIs
    external_provider = AsyncMock(spec=GooglePlacesPOIProvider)

    external_poi = POICandidate(
        poi_id=uuid4(),
        name="New External Café",
        category="cafe",
        tags=["cafe"],
        rating=4.8,
        location="999 External Ave, Paris, France",
        lat=48.8700,
        lon=2.3500,
        rank_score=19.0,
    )

    external_provider.search_pois.return_value = [external_poi]

    # Create composite provider
    composite = CompositePOIProvider(
        db_provider=db_provider,
        external_provider=external_provider,
    )

    # Search for POIs (limit=5, DB has 1, so external should be called)
    results = await composite.search_pois(
        city="Paris",
        desired_categories=["cafe"],
        budget=BudgetLevel.MEDIUM,
        limit=5,
    )

    # Verify DB was queried
    db_provider.search_pois.assert_called_once()

    # Verify external provider WAS called (DB didn't have enough)
    external_provider.search_pois.assert_called_once()

    # Verify results include both DB and external POIs
    assert len(results) == 2
    result_names = {r.name for r in results}
    assert "Cached Café" in result_names
    assert "New External Café" in result_names


@pytest.mark.asyncio
async def test_composite_provider_deduplicates_by_id():
    """Test that CompositePOIProvider doesn't return duplicate POIs."""
    # Create mock providers
    db_provider = AsyncMock(spec=DBPOIProvider)
    external_provider = AsyncMock(spec=GooglePlacesPOIProvider)

    # Create a POI with a specific ID
    shared_id = uuid4()

    db_poi = POICandidate(
        poi_id=shared_id,  # Same ID
        name="Café from DB",
        category="cafe",
        rating=4.5,
        location="Paris",
        lat=48.8566,
        lon=2.3522,
        rank_score=15.0,
    )

    external_poi = POICandidate(
        poi_id=shared_id,  # Same ID (shouldn't happen in practice, but test dedup logic)
        name="Café from External",
        category="cafe",
        rating=4.5,
        location="Paris",
        lat=48.8566,
        lon=2.3522,
        rank_score=15.0,
    )

    db_provider.search_pois.return_value = [db_poi]
    external_provider.search_pois.return_value = [external_poi]

    # Create composite provider
    composite = CompositePOIProvider(
        db_provider=db_provider,
        external_provider=external_provider,
    )

    # Search for POIs
    results = await composite.search_pois(
        city="Paris",
        desired_categories=["cafe"],
        limit=5,
    )

    # Verify only one POI is returned (deduplication works)
    assert len(results) == 1
    assert results[0].name == "Café from DB"  # DB result takes precedence


@pytest.mark.asyncio
async def test_composite_provider_handles_external_failure():
    """Test that CompositePOIProvider gracefully handles external API failures."""
    # Create mock DB provider
    db_provider = AsyncMock(spec=DBPOIProvider)

    cached_poi = POICandidate(
        poi_id=uuid4(),
        name="Cached Café",
        category="cafe",
        rating=4.6,
        location="Paris",
        lat=48.8600,
        lon=2.3400,
        rank_score=18.0,
    )

    db_provider.search_pois.return_value = [cached_poi]

    # Create mock external provider that raises an exception
    external_provider = AsyncMock(spec=GooglePlacesPOIProvider)
    external_provider.search_pois.side_effect = Exception("API error")

    # Create composite provider
    composite = CompositePOIProvider(
        db_provider=db_provider,
        external_provider=external_provider,
    )

    # Search for POIs (external will fail, but should return DB results)
    results = await composite.search_pois(
        city="Paris",
        desired_categories=["cafe"],
        limit=5,
    )

    # Verify DB results are returned despite external failure
    assert len(results) == 1
    assert results[0].name == "Cached Café"
