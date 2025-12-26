"""
Tests for Google Maps Travel Time Provider.
Tests the GoogleMapsTravelTimeProvider with mocked HTTP responses.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import httpx

from src.infrastructure.travel_time import (
    GoogleMapsTravelTimeProvider,
    SimpleHeuristicTravelTimeProvider,
    TravelLocation,
    TravelTimeResult,
)


# Sample Google Routes API response
MOCK_GOOGLE_ROUTES_RESPONSE = {
    "routes": [
        {
            "duration": "1234s",
            "distanceMeters": 5678,
            "polyline": {
                "encodedPolyline": "a~l~Fjk~uOwHJy@P"
            }
        }
    ]
}

MOCK_GOOGLE_ROUTES_RESPONSE_MINIMAL = {
    "routes": [
        {
            "duration": "600s",
            "distanceMeters": 2000,
        }
    ]
}

MOCK_EMPTY_ROUTES_RESPONSE = {
    "routes": []
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


# ============== Unit Tests for GoogleMapsTravelTimeProvider ==============


@pytest.mark.asyncio
async def test_google_routes_provider_parses_response():
    """Test that GoogleMapsTravelTimeProvider correctly parses Routes API response."""
    provider = GoogleMapsTravelTimeProvider(
        api_key="test_api_key",
        base_url="https://routes.googleapis.com/directions/v2:computeRoutes"
    )

    origin = TravelLocation(lat=48.8566, lon=2.3522)
    destination = TravelLocation(lat=48.8584, lon=2.2945)

    with patch.object(httpx.AsyncClient, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MockResponse(MOCK_GOOGLE_ROUTES_RESPONSE)

        result = await provider.estimate_travel(origin, destination)

        # Verify API was called
        mock_post.assert_called_once()

        # Verify result
        assert isinstance(result, TravelTimeResult)
        # 1234 seconds = 21 minutes (rounded up)
        assert result.duration_minutes == 21
        assert result.distance_meters == 5678
        assert result.polyline == "a~l~Fjk~uOwHJy@P"


@pytest.mark.asyncio
async def test_google_routes_provider_handles_minimal_response():
    """Test parsing response without polyline."""
    provider = GoogleMapsTravelTimeProvider(api_key="test_api_key")

    origin = TravelLocation(lat=48.8566, lon=2.3522)
    destination = TravelLocation(lat=48.8584, lon=2.2945)

    with patch.object(httpx.AsyncClient, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MockResponse(MOCK_GOOGLE_ROUTES_RESPONSE_MINIMAL)

        result = await provider.estimate_travel(origin, destination)

        # 600 seconds = 10 minutes
        assert result.duration_minutes == 10
        assert result.distance_meters == 2000
        assert result.polyline is None


@pytest.mark.asyncio
async def test_google_routes_provider_handles_empty_routes():
    """Test graceful handling of empty routes response."""
    provider = GoogleMapsTravelTimeProvider(api_key="test_api_key")

    origin = TravelLocation(lat=48.8566, lon=2.3522)
    destination = TravelLocation(lat=48.8584, lon=2.2945)

    with patch.object(httpx.AsyncClient, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MockResponse(MOCK_EMPTY_ROUTES_RESPONSE)

        result = await provider.estimate_travel(origin, destination)

        # Should fall back to heuristic
        assert isinstance(result, TravelTimeResult)
        assert result.duration_minutes > 0


@pytest.mark.asyncio
async def test_google_routes_provider_handles_timeout():
    """Test graceful handling of timeouts."""
    provider = GoogleMapsTravelTimeProvider(
        api_key="test_api_key",
        timeout_seconds=1
    )

    origin = TravelLocation(lat=48.8566, lon=2.3522)
    destination = TravelLocation(lat=48.8584, lon=2.2945)

    with patch.object(httpx.AsyncClient, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Timeout")

        result = await provider.estimate_travel(origin, destination)

        # Should fall back to heuristic
        assert isinstance(result, TravelTimeResult)
        assert result.duration_minutes > 0


@pytest.mark.asyncio
async def test_google_routes_provider_handles_http_error():
    """Test graceful handling of HTTP errors."""
    provider = GoogleMapsTravelTimeProvider(api_key="test_api_key")

    origin = TravelLocation(lat=48.8566, lon=2.3522)
    destination = TravelLocation(lat=48.8584, lon=2.2945)

    with patch.object(httpx.AsyncClient, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.HTTPStatusError(
            message="Error",
            request=MagicMock(),
            response=MockResponse({}, status_code=500)
        )

        result = await provider.estimate_travel(origin, destination)

        # Should fall back to heuristic
        assert isinstance(result, TravelTimeResult)
        assert result.duration_minutes > 0


@pytest.mark.asyncio
async def test_google_routes_provider_missing_origin_coordinates():
    """Test fallback when origin has no coordinates."""
    provider = GoogleMapsTravelTimeProvider(api_key="test_api_key")

    origin = TravelLocation()  # No coordinates
    destination = TravelLocation(lat=48.8584, lon=2.2945)

    with patch.object(httpx.AsyncClient, 'post', new_callable=AsyncMock) as mock_post:
        result = await provider.estimate_travel(origin, destination)

        # Should not call API, use fallback
        mock_post.assert_not_called()
        assert isinstance(result, TravelTimeResult)


@pytest.mark.asyncio
async def test_google_routes_provider_missing_destination_coordinates():
    """Test fallback when destination has no coordinates."""
    provider = GoogleMapsTravelTimeProvider(api_key="test_api_key")

    origin = TravelLocation(lat=48.8566, lon=2.3522)
    destination = TravelLocation()  # No coordinates

    with patch.object(httpx.AsyncClient, 'post', new_callable=AsyncMock) as mock_post:
        result = await provider.estimate_travel(origin, destination)

        # Should not call API, use fallback
        mock_post.assert_not_called()
        assert isinstance(result, TravelTimeResult)


@pytest.mark.asyncio
async def test_google_routes_provider_sends_correct_headers():
    """Test that correct headers are sent to Google Routes API."""
    provider = GoogleMapsTravelTimeProvider(api_key="my_secret_key")

    origin = TravelLocation(lat=48.8566, lon=2.3522)
    destination = TravelLocation(lat=48.8584, lon=2.2945)

    with patch.object(httpx.AsyncClient, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MockResponse(MOCK_GOOGLE_ROUTES_RESPONSE)

        await provider.estimate_travel(origin, destination)

        # Verify headers
        call_kwargs = mock_post.call_args
        headers = call_kwargs.kwargs.get('headers', {})

        assert headers.get('X-Goog-Api-Key') == 'my_secret_key'
        assert 'X-Goog-FieldMask' in headers
        assert 'duration' in headers['X-Goog-FieldMask']
        assert 'distanceMeters' in headers['X-Goog-FieldMask']
        assert 'polyline' in headers['X-Goog-FieldMask']


@pytest.mark.asyncio
async def test_google_routes_provider_sends_correct_body():
    """Test that correct request body is sent to Google Routes API."""
    provider = GoogleMapsTravelTimeProvider(api_key="test_key")

    origin = TravelLocation(lat=48.8566, lon=2.3522)
    destination = TravelLocation(lat=48.8584, lon=2.2945)

    with patch.object(httpx.AsyncClient, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MockResponse(MOCK_GOOGLE_ROUTES_RESPONSE)

        await provider.estimate_travel(origin, destination, mode="WALK")

        # Verify request body
        call_kwargs = mock_post.call_args
        body = call_kwargs.kwargs.get('json', {})

        assert body['origin']['location']['latLng']['latitude'] == 48.8566
        assert body['origin']['location']['latLng']['longitude'] == 2.3522
        assert body['destination']['location']['latLng']['latitude'] == 48.8584
        assert body['destination']['location']['latLng']['longitude'] == 2.2945
        assert body['travelMode'] == 'WALK'


@pytest.mark.asyncio
async def test_google_routes_provider_requires_api_key():
    """Test that GoogleMapsTravelTimeProvider requires API key."""
    with pytest.raises(ValueError) as exc_info:
        GoogleMapsTravelTimeProvider(api_key=None)

    assert "API key" in str(exc_info.value)


@pytest.mark.asyncio
async def test_google_routes_duration_parsing():
    """Test various duration string formats."""
    provider = GoogleMapsTravelTimeProvider(api_key="test_key")

    # Test standard format
    assert provider._parse_duration_string("60s") == 1
    assert provider._parse_duration_string("120s") == 2
    assert provider._parse_duration_string("90s") == 2  # Rounds up
    assert provider._parse_duration_string("3600s") == 60

    # Edge cases
    assert provider._parse_duration_string("1s") == 1  # Minimum 1 minute
    assert provider._parse_duration_string("invalid") == 15  # Fallback
    assert provider._parse_duration_string("") == 15  # Fallback


# ============== Unit Tests for SimpleHeuristicTravelTimeProvider ==============


@pytest.mark.asyncio
async def test_heuristic_provider_calculates_distance():
    """Test that heuristic provider uses Haversine formula for distance."""
    provider = SimpleHeuristicTravelTimeProvider()

    # Eiffel Tower to Louvre - approximately 3.5 km
    origin = TravelLocation(lat=48.8584, lon=2.2945)  # Eiffel Tower
    destination = TravelLocation(lat=48.8606, lon=2.3376)  # Louvre

    result = await provider.estimate_travel(origin, destination, mode="DRIVE")

    # Should calculate reasonable travel time for ~3.5 km
    assert result.duration_minutes > 0
    assert result.distance_meters is not None
    assert result.distance_meters > 3000  # At least 3 km (with 1.3x adjustment)
    assert result.polyline is None  # Heuristic doesn't provide polyline


@pytest.mark.asyncio
async def test_heuristic_provider_walk_vs_drive():
    """Test that walking takes longer than driving."""
    provider = SimpleHeuristicTravelTimeProvider()

    origin = TravelLocation(lat=48.8584, lon=2.2945)
    destination = TravelLocation(lat=48.8606, lon=2.3376)

    walk_result = await provider.estimate_travel(origin, destination, mode="WALK")
    drive_result = await provider.estimate_travel(origin, destination, mode="DRIVE")

    assert walk_result.duration_minutes > drive_result.duration_minutes


@pytest.mark.asyncio
async def test_heuristic_provider_missing_coordinates():
    """Test fallback when coordinates are missing."""
    provider = SimpleHeuristicTravelTimeProvider()

    origin = TravelLocation()  # No coordinates
    destination = TravelLocation(lat=48.8606, lon=2.3376)

    result = await provider.estimate_travel(origin, destination)

    # Should return default time
    assert result.duration_minutes == SimpleHeuristicTravelTimeProvider.DEFAULT_TRAVEL_TIME_MINUTES
    assert result.distance_meters is None


@pytest.mark.asyncio
async def test_heuristic_provider_minimum_time():
    """Test that minimum travel time is 5 minutes."""
    provider = SimpleHeuristicTravelTimeProvider()

    # Very close locations
    origin = TravelLocation(lat=48.8584, lon=2.2945)
    destination = TravelLocation(lat=48.8585, lon=2.2946)

    result = await provider.estimate_travel(origin, destination)

    # Should be at least 5 minutes
    assert result.duration_minutes >= 5


# ============== Tests for TravelLocation ==============


def test_travel_location_has_coordinates():
    """Test TravelLocation.has_coordinates method."""
    loc_full = TravelLocation(lat=48.8566, lon=2.3522)
    assert loc_full.has_coordinates() is True

    loc_no_lat = TravelLocation(lon=2.3522)
    assert loc_no_lat.has_coordinates() is False

    loc_no_lon = TravelLocation(lat=48.8566)
    assert loc_no_lon.has_coordinates() is False

    loc_empty = TravelLocation()
    assert loc_empty.has_coordinates() is False


def test_travel_location_from_poi():
    """Test TravelLocation.from_poi class method."""
    from src.domain.models import POICandidate
    from uuid import uuid4

    poi = POICandidate(
        poi_id=uuid4(),
        name="Test POI",
        category="restaurant",
        location="Test Address",
        lat=48.8566,
        lon=2.3522,
    )

    loc = TravelLocation.from_poi(poi)

    assert loc.lat == 48.8566
    assert loc.lon == 2.3522
    assert loc.address == "Test Address"


def test_travel_location_from_none():
    """Test TravelLocation.from_poi with None."""
    loc = TravelLocation.from_poi(None)

    assert loc.lat is None
    assert loc.lon is None
    assert loc.address is None


# ============== Integration Tests with RouteTimeOptimizer ==============

# Check if FastAPI and other dependencies are available
try:
    from httpx import AsyncClient
    from src.main import app
    from src.application.route_optimizer import RouteTimeOptimizer
    from src.infrastructure.database import AsyncSessionLocal
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_FASTAPI, reason="FastAPI not installed")
async def test_route_optimizer_stores_travel_details():
    """Test that RouteTimeOptimizer stores travel distance and polyline."""
    # Create a custom mock provider
    class MockGoogleProvider(GoogleMapsTravelTimeProvider):
        def __init__(self):
            self._fallback_provider = SimpleHeuristicTravelTimeProvider()

        async def estimate_travel(self, origin, destination, mode="DRIVE"):
            if origin.has_coordinates() and destination.has_coordinates():
                return TravelTimeResult(
                    duration_minutes=12,
                    distance_meters=2500,
                    polyline="encodedPolylineData123",
                )
            return await self._fallback_provider.estimate_travel(origin, destination, mode)

    async with AsyncClient(app=app, base_url="http://test") as client:
        trip_response = await client.post(
            "/api/trips",
            json={
                "city": "Vienna",
                "start_date": "2024-07-01",
                "end_date": "2024-07-02",
            }
        )
        trip_id = trip_response.json()["id"]

        # Create plans with mocked LLM
        from src.application import macro_planner
        from tests.test_macro_plan import MockLLMClient, mock_macro_plan_response

        original_factory = macro_planner.get_macro_planning_llm_client
        macro_planner.get_macro_planning_llm_client = lambda: MockLLMClient(mock_macro_plan_response())

        try:
            await client.post(f"/api/trips/{trip_id}/macro-plan")
            await client.post(f"/api/trips/{trip_id}/poi-plan")
        finally:
            macro_planner.get_macro_planning_llm_client = original_factory

    # Generate itinerary with mock Google provider
    async with AsyncSessionLocal() as db:
        optimizer = RouteTimeOptimizer(travel_time_provider=MockGoogleProvider())
        itinerary = await optimizer.generate_itinerary(trip_id, db)

    # Verify travel details are stored
    has_travel_details = False
    for day in itinerary.days:
        for block in day.blocks:
            if block.poi and block.travel_distance_meters:
                has_travel_details = True
                assert block.travel_distance_meters == 2500
                assert block.travel_polyline == "encodedPolylineData123"
                break
        if has_travel_details:
            break
