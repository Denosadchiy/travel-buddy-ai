"""
Thin Google Places Nearby Search client for the Live Audio Guide City Seeder.

Note: The main project uses GooglePlacesPOIProvider (src/infrastructure/poi_providers.py)
with Text Search for trip planning. That provider's search_pois() API is designed for
category-based POI retrieval with DB caching — not suitable for zone discovery which
needs raw Nearby Search results across many place types without caching overhead.

This wrapper is a minimal addition for the seeder use-case only.
"""
import asyncio
import logging
from typing import Any

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

NEARBY_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
PLACE_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"


class GuideGooglePlacesClient:
    """
    Minimal Google Places Nearby Search client for the City Seeder.

    Only exposes nearby_search() — all other Places API calls go through
    the existing GooglePlacesPOIProvider in src/infrastructure/poi_providers.py.
    """

    def __init__(
        self,
        api_key: str | None = None,
        timeout_seconds: int = 15,
    ) -> None:
        self._api_key = api_key or settings.google_maps_api_key or ""
        self._timeout = timeout_seconds

    async def nearby_search(
        self,
        lat: float,
        lng: float,
        radius_m: int,
        place_type: str,
        max_results: int = 60,
    ) -> list[dict[str, Any]]:
        """
        Call Google Places Nearby Search for a single place type.

        Args:
            lat, lng: Center coordinates.
            radius_m: Search radius in metres (max 50_000 per Google).
            place_type: A single Google Places type string (e.g. "museum").
            max_results: Cap on returned results (Google returns max 60 via pagination).

        Returns:
            List of raw place dicts from the API response.

        Raises:
            httpx.HTTPStatusError: On non-retryable HTTP errors.
            RuntimeError: If API key is not configured.
        """
        if not self._api_key:
            raise RuntimeError(
                "GOOGLE_MAPS_API_KEY is not configured. "
                "Set it in .env before running the City Seeder."
            )

        params: dict[str, Any] = {
            "location": f"{lat},{lng}",
            "radius": radius_m,
            "type": place_type,
            "key": self._api_key,
        }

        results: list[dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            page = 0
            next_page_token: str | None = None

            while len(results) < max_results:
                if next_page_token:
                    params = {"pagetoken": next_page_token, "key": self._api_key}
                    # Google requires a short delay before using a page token
                    await asyncio.sleep(2.0)

                response = await self._request_with_retry(client, params)
                if response is None:
                    break

                data = response
                batch = data.get("results", [])
                results.extend(batch)

                next_page_token = data.get("next_page_token")
                if not next_page_token:
                    break

                page += 1
                if page >= 2:  # max 3 pages × 20 results = 60
                    break

        return results[:max_results]

    async def place_details(self, place_id: str) -> dict[str, Any] | None:
        """
        Fetch full Place Details for a Google Places ID.

        Fields requested: name, rating, user_ratings_total, reviews, photos,
        editorial_summary, opening_hours, formatted_address, website, types.

        Returns the 'result' dict from the API response, or None on error.
        Note: editorial_summary is only available for significant landmarks —
        its absence is normal and not treated as an error.
        """
        if not self._api_key:
            raise RuntimeError(
                "GOOGLE_MAPS_API_KEY is not configured. "
                "Set it in .env before running the City Seeder."
            )

        params: dict[str, Any] = {
            "place_id": place_id,
            "fields": (
                "name,rating,user_ratings_total,reviews,photos,"
                "editorial_summary,opening_hours,formatted_address,website,types"
            ),
            "key": self._api_key,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            data = await self._request_with_retry(client, params, url=PLACE_DETAILS_URL)

        if data is None:
            return None

        api_status = data.get("status", "UNKNOWN")
        if api_status != "OK":
            logger.warning(
                "Google Place Details API status=%s for place_id=%s", api_status, place_id
            )
            return None

        return data.get("result")

    async def reverse_geocode(
        self, lat: float, lng: float
    ) -> dict[str, Any] | None:
        """
        Reverse geocode (lat, lng) to get the nearest street address.

        Filters result_type to route|street_address|intersection for cleaner results.
        Returns the first result dict, or None if no results or on error.
        """
        if not self._api_key:
            raise RuntimeError(
                "GOOGLE_MAPS_API_KEY is not configured. "
                "Set it in .env before running the City Seeder."
            )

        params: dict[str, Any] = {
            "latlng": f"{lat},{lng}",
            "result_type": "route|street_address|intersection",
            "key": self._api_key,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            data = await self._request_with_retry(client, params, url=GEOCODE_URL)

        if data is None:
            return None

        results = data.get("results", [])
        return results[0] if results else None

    @staticmethod
    def extract_street_name(geocode_result: dict[str, Any]) -> str | None:
        """
        Extract the street/route name from a reverse geocode result.

        Searches address_components for a component with type 'route' and
        returns its long_name. Returns None if no route component is found.
        """
        for component in geocode_result.get("address_components", []):
            if "route" in component.get("types", []):
                return component.get("long_name")
        return None

    async def get_walking_directions(
        self,
        from_lat: float,
        from_lng: float,
        to_lat: float,
        to_lng: float,
        language: str = "ru",
    ) -> dict[str, Any] | None:
        """
        Google Maps Directions API — walking route between two points.

        Returns dict with:
          geometry: [[lat, lng], ...] — decoded polyline
          street_sequence: ["улица X", "переулок Y", ...] — streets in order
          total_distance_m: float
          total_duration_s: float
          steps: list of step dicts
        Or None on error.
        """
        import re as _re
        try:
            import polyline as _polyline
        except ImportError:
            logger.error("polyline package not installed (pip install polyline)")
            return None

        params: dict[str, Any] = {
            "origin": f"{from_lat},{from_lng}",
            "destination": f"{to_lat},{to_lng}",
            "mode": "walking",
            "language": language,
            "key": self._api_key,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            data = await self._request_with_retry(client, params, url=DIRECTIONS_URL)

        if data is None or data.get("status") != "OK":
            status = data.get("status") if data else "no response"
            logger.warning("Google Directions API error: %s", status)
            return None

        route = data["routes"][0]
        leg = route["legs"][0]

        # Decode overview polyline
        encoded = route["overview_polyline"]["points"]
        geometry = [[lat, lng] for lat, lng in _polyline.decode(encoded)]

        # Pin endpoints to exact coordinates
        if geometry:
            geometry[0] = [from_lat, from_lng]
            geometry[-1] = [to_lat, to_lng]

        # Extract street names and steps
        street_sequence: list[str] = []
        steps: list[dict] = []
        for step in leg["steps"]:
            raw_instr = step.get("html_instructions", "")
            clean_instr = _re.sub(r"<[^>]+>", "", raw_instr)
            distance_m = step["distance"]["value"]
            duration_s = step["duration"]["value"]

            # Extract street name from instruction
            street_name = ""
            # Try "по ул. X" / "на X" / "через X" patterns
            m = _re.search(r"(?:по|на|через|вдоль)\s+(.+?)(?:\s*$)", clean_instr)
            if m:
                candidate = m.group(1).strip().rstrip(".")
                # Skip directional words (не улицы)
                if candidate.lower() not in (
                    "северо-запад", "северо-восток", "юго-запад", "юго-восток",
                    "север", "юг", "запад", "восток",
                ):
                    street_name = candidate

            if street_name and (not street_sequence or street_sequence[-1] != street_name):
                street_sequence.append(street_name)

            steps.append({
                "instruction": clean_instr,
                "distance_m": distance_m,
                "duration_s": duration_s,
                "street_name": street_name,
            })

        return {
            "geometry": geometry,
            "street_sequence": street_sequence,
            "steps": steps,
            "total_distance_m": leg["distance"]["value"],
            "total_duration_s": leg["duration"]["value"],
        }

    async def _request_with_retry(
        self,
        client: httpx.AsyncClient,
        params: dict[str, Any],
        max_attempts: int = 3,
        url: str = NEARBY_SEARCH_URL,
    ) -> dict[str, Any] | None:
        """GET with exponential backoff on 429/5xx."""
        for attempt in range(max_attempts):
            try:
                resp = await client.get(url, params=params)

                if resp.status_code in (429, 500, 502, 503, 504):
                    wait = 2 ** attempt
                    logger.warning(
                        "Google Places Nearby Search HTTP %s — retry %d/%d in %ds",
                        resp.status_code, attempt + 1, max_attempts, wait,
                    )
                    await asyncio.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()

                api_status = data.get("status", "UNKNOWN")
                if api_status == "ZERO_RESULTS":
                    return {"results": [], "status": api_status}
                if api_status not in ("OK", "UNKNOWN"):
                    logger.warning(
                        "Google Places API status=%s for params=%s", api_status, params
                    )
                    return None

                return data

            except httpx.TimeoutException:
                wait = 2 ** attempt
                logger.warning(
                    "Google Places Nearby Search timeout — retry %d/%d in %ds",
                    attempt + 1, max_attempts, wait,
                )
                await asyncio.sleep(wait)

            except httpx.HTTPStatusError as exc:
                logger.error("Google Places HTTP error: %s", exc)
                return None

        logger.error("Google Places Nearby Search: all %d attempts failed", max_attempts)
        return None
