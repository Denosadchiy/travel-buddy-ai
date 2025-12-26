"""
Travel time provider abstraction.
Calculates estimated travel time, distance, and route between POIs.
"""
import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import httpx

from src.config import settings
from src.domain.models import POICandidate

logger = logging.getLogger(__name__)


@dataclass
class TravelLocation:
    """A location for travel time calculation."""
    lat: Optional[float] = None
    lon: Optional[float] = None
    address: Optional[str] = None

    def has_coordinates(self) -> bool:
        """Check if this location has valid coordinates."""
        return self.lat is not None and self.lon is not None

    @classmethod
    def from_poi(cls, poi: Optional[POICandidate]) -> "TravelLocation":
        """Create TravelLocation from a POICandidate."""
        if poi is None:
            return cls()
        return cls(
            lat=poi.lat,
            lon=poi.lon,
            address=poi.location,
        )


@dataclass
class TravelTimeResult:
    """Result of a travel time estimation."""
    duration_minutes: int
    distance_meters: Optional[int] = None
    polyline: Optional[str] = None


class TravelTimeProvider(ABC):
    """
    Abstract base class for travel time estimation.
    Allows swapping between heuristic and real Maps API implementations.
    """

    @abstractmethod
    async def estimate_travel(
        self,
        origin: TravelLocation,
        destination: TravelLocation,
        mode: str = "DRIVE",
    ) -> TravelTimeResult:
        """
        Estimate travel time between two locations.

        Args:
            origin: Starting point
            destination: Ending point
            mode: Travel mode ("DRIVE", "WALK", "BICYCLE", "TRANSIT")

        Returns:
            TravelTimeResult with duration, distance, and polyline
        """
        pass

    async def get_travel_time_minutes(
        self,
        origin_poi: Optional[POICandidate],
        destination_poi: Optional[POICandidate],
    ) -> int:
        """
        Legacy method for backward compatibility.
        Get estimated travel time between two POIs in minutes.
        """
        origin = TravelLocation.from_poi(origin_poi)
        destination = TravelLocation.from_poi(destination_poi)
        result = await self.estimate_travel(origin, destination)
        return result.duration_minutes


class SimpleHeuristicTravelTimeProvider(TravelTimeProvider):
    """
    Simple heuristic-based travel time estimation.
    Uses distance-based calculation when coordinates are available,
    otherwise returns a default time.
    """

    DEFAULT_TRAVEL_TIME_MINUTES = 15
    AVERAGE_WALKING_SPEED_KMH = 5.0
    AVERAGE_DRIVING_SPEED_KMH = 30.0  # Urban driving

    def _calculate_distance_km(
        self,
        origin: TravelLocation,
        destination: TravelLocation,
    ) -> Optional[float]:
        """
        Calculate straight-line distance in kilometers using Haversine formula.
        """
        if not origin.has_coordinates() or not destination.has_coordinates():
            return None

        # Haversine formula
        R = 6371  # Earth's radius in km

        lat1 = math.radians(origin.lat)
        lat2 = math.radians(destination.lat)
        dlat = math.radians(destination.lat - origin.lat)
        dlon = math.radians(destination.lon - origin.lon)

        a = (math.sin(dlat / 2) ** 2 +
             math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    async def estimate_travel(
        self,
        origin: TravelLocation,
        destination: TravelLocation,
        mode: str = "DRIVE",
    ) -> TravelTimeResult:
        """
        Estimate travel time using distance-based heuristic.
        """
        distance_km = self._calculate_distance_km(origin, destination)

        if distance_km is not None:
            # Calculate time based on mode
            speed = (self.AVERAGE_WALKING_SPEED_KMH if mode == "WALK"
                     else self.AVERAGE_DRIVING_SPEED_KMH)

            # Add 30% for real-world routing (not straight line)
            adjusted_distance = distance_km * 1.3
            duration_hours = adjusted_distance / speed
            duration_minutes = max(5, int(duration_hours * 60))

            return TravelTimeResult(
                duration_minutes=duration_minutes,
                distance_meters=int(adjusted_distance * 1000),
                polyline=None,
            )

        # Default fallback
        return TravelTimeResult(
            duration_minutes=self.DEFAULT_TRAVEL_TIME_MINUTES,
            distance_meters=None,
            polyline=None,
        )


class GoogleMapsTravelTimeProvider(TravelTimeProvider):
    """
    Google Maps Routes API-based travel time provider.
    Uses the Routes API v2 for accurate travel time, distance, and polylines.
    """

    FALLBACK_DURATION_MINUTES = 15

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        timeout_seconds: int = 10,
        default_mode: str = "DRIVE",
    ):
        """
        Initialize Google Maps travel time provider.

        Args:
            api_key: Google Maps API key
            base_url: Routes API base URL (defaults to settings)
            timeout_seconds: HTTP request timeout
            default_mode: Default travel mode ("DRIVE", "WALK", etc.)
        """
        if not api_key:
            raise ValueError("Google Maps API key is required")

        self.api_key = api_key
        self.base_url = base_url or settings.google_routes_base_url
        self.timeout_seconds = timeout_seconds
        self.default_mode = default_mode
        self._fallback_provider = SimpleHeuristicTravelTimeProvider()

    def _parse_duration_string(self, duration_str: str) -> int:
        """
        Parse Google Routes duration string (e.g., "1234s") to minutes.
        """
        try:
            # Format is like "1234s" (seconds)
            if duration_str.endswith("s"):
                seconds = int(duration_str[:-1])
                return max(1, (seconds + 59) // 60)  # Round up
            return self.FALLBACK_DURATION_MINUTES
        except (ValueError, TypeError):
            logger.warning(f"Failed to parse duration: {duration_str}")
            return self.FALLBACK_DURATION_MINUTES

    async def _fetch_route(
        self,
        origin: TravelLocation,
        destination: TravelLocation,
        mode: str,
    ) -> Optional[dict]:
        """
        Fetch route from Google Routes API.
        """
        headers = {
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline",
            "Content-Type": "application/json",
        }

        body = {
            "origin": {
                "location": {
                    "latLng": {
                        "latitude": origin.lat,
                        "longitude": origin.lon,
                    }
                }
            },
            "destination": {
                "location": {
                    "latLng": {
                        "latitude": destination.lat,
                        "longitude": destination.lon,
                    }
                }
            },
            "travelMode": mode,
            "computeAlternativeRoutes": False,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    self.base_url,
                    headers=headers,
                    json=body,
                )
                response.raise_for_status()
                return response.json()

        except httpx.TimeoutException:
            logger.warning(f"Google Routes API timeout after {self.timeout_seconds}s")
            return None
        except httpx.HTTPStatusError as e:
            logger.warning(f"Google Routes API HTTP error: {e.response.status_code}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error calling Google Routes API: {e}")
            return None

    def _parse_route_response(self, data: dict) -> Optional[TravelTimeResult]:
        """
        Parse Google Routes API response into TravelTimeResult.
        """
        try:
            routes = data.get("routes", [])
            if not routes:
                logger.warning("No routes returned from Google Routes API")
                return None

            route = routes[0]

            # Parse duration
            duration_str = route.get("duration", "")
            duration_minutes = self._parse_duration_string(duration_str)

            # Parse distance
            distance_meters = route.get("distanceMeters")

            # Parse polyline
            polyline = None
            polyline_data = route.get("polyline", {})
            if polyline_data:
                polyline = polyline_data.get("encodedPolyline")

            return TravelTimeResult(
                duration_minutes=duration_minutes,
                distance_meters=distance_meters,
                polyline=polyline,
            )

        except Exception as e:
            logger.error(f"Failed to parse Google Routes response: {e}")
            return None

    async def estimate_travel(
        self,
        origin: TravelLocation,
        destination: TravelLocation,
        mode: str = "DRIVE",
    ) -> TravelTimeResult:
        """
        Estimate travel time using Google Routes API.

        Falls back to heuristic if:
        - Coordinates are missing
        - API call fails
        - Response is invalid
        """
        # Check for valid coordinates
        if not origin.has_coordinates() or not destination.has_coordinates():
            logger.debug("Missing coordinates, using fallback heuristic")
            return await self._fallback_provider.estimate_travel(origin, destination, mode)

        # Fetch route from API
        response_data = await self._fetch_route(origin, destination, mode)
        if response_data is None:
            logger.debug("API call failed, using fallback heuristic")
            return await self._fallback_provider.estimate_travel(origin, destination, mode)

        # Parse response
        result = self._parse_route_response(response_data)
        if result is None:
            logger.debug("Failed to parse response, using fallback heuristic")
            return await self._fallback_provider.estimate_travel(origin, destination, mode)

        logger.debug(f"Google Routes: {result.duration_minutes}min, {result.distance_meters}m")
        return result


def get_travel_time_provider() -> TravelTimeProvider:
    """
    Factory function to get travel time provider based on settings.

    Returns:
        TravelTimeProvider instance
    """
    provider_type = settings.travel_time_provider.lower()

    if provider_type == "google_maps":
        if settings.google_maps_api_key:
            logger.info("Using Google Maps travel time provider")
            return GoogleMapsTravelTimeProvider(
                api_key=settings.google_maps_api_key,
                timeout_seconds=settings.google_routes_timeout_seconds,
            )
        else:
            logger.warning(
                "GOOGLE_MAPS_API_KEY not set, falling back to simple heuristic. "
                "Set TRAVEL_TIME_PROVIDER=simple to suppress this warning."
            )
            return SimpleHeuristicTravelTimeProvider()

    # Default to simple heuristic
    logger.info("Using simple heuristic travel time provider")
    return SimpleHeuristicTravelTimeProvider()
