"""
Wikipedia REST API v1 client for the Live Audio Guide City Seeder — KnowledgeCollector.

Uses the Wikipedia REST API (not the legacy Action API) to fetch article summaries.
Supports two languages: 'en' (English) and 'ru' (Russian).

Three-step search strategy:
  1. Direct lookup: GET /page/summary/{urlencoded_title}
  2. If disambiguation: resolve via legacy search API + coordinate filter
  3. Not found → None (normal — e.g. a local café without a Wikipedia article)

Wikipedia policy requires a descriptive User-Agent header for all requests.
Configure via WIKIPEDIA_USER_AGENT in settings or pass user_agent= to constructor.
"""
from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

_REST_BASE = "https://{lang}.wikipedia.org/api/rest_v1"
_LEGACY_API_BASE = "https://{lang}.wikipedia.org/w/api.php"

# Maximum distance from near_lat/near_lng to accept a candidate article (metres).
# Beyond this, disambiguation candidates are skipped.
_COORD_RADIUS_M = 5_000.0


@dataclass
class WikipediaSummary:
    """Parsed result of a Wikipedia summary API response."""

    title: str
    extract: str                            # First paragraph (plain text)
    description: str | None                 # Short description (e.g. "lattice iron tower")
    wikibase_item: str | None               # Q-ID for subsequent Wikidata lookup (e.g. "Q243")
    coordinates: tuple[float, float] | None  # (lat, lon) or None if not geotagged
    page_url: str                           # Full desktop page URL


class WikipediaClient:
    """
    Thin Wikipedia REST API v1 wrapper.

    Never raises from public methods — all errors are caught and return None.
    This matches the graceful-degradation principle of KnowledgeCollector.
    """

    def __init__(
        self,
        timeout_seconds: int | None = None,
        user_agent: str | None = None,
    ) -> None:
        self._timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.wikipedia_timeout_seconds
        )
        self._user_agent = user_agent or settings.wikipedia_user_agent

    @property
    def _headers(self) -> dict[str, str]:
        return {"User-Agent": self._user_agent}

    # =========================================================================
    # Public API
    # =========================================================================

    async def search_and_get_summary(
        self,
        query: str,
        language: str = "en",
        near_lat: float | None = None,
        near_lng: float | None = None,
    ) -> WikipediaSummary | None:
        """
        Find the best Wikipedia article for *query* and return its summary.

        Args:
            query:     Article title or search query (e.g. "Eiffel Tower").
            language:  Language edition — "en" or "ru" (others work but untested).
            near_lat:  Latitude used to pick the most geographically relevant
                       candidate when disambiguation is needed.
            near_lng:  Longitude used the same way.

        Returns:
            WikipediaSummary on success, None if nothing found or on any error.
        """
        try:
            async with httpx.AsyncClient(
                headers=self._headers,
                timeout=self._timeout,
            ) as client:
                return await self._search(client, query, language, near_lat, near_lng)
        except Exception as exc:
            logger.warning(
                "WikipediaClient: unexpected error for query=%r language=%s: %s",
                query, language, exc,
            )
            return None

    # =========================================================================
    # Internal orchestration
    # =========================================================================

    async def _search(
        self,
        client: httpx.AsyncClient,
        query: str,
        language: str,
        near_lat: float | None,
        near_lng: float | None,
    ) -> WikipediaSummary | None:
        # Step 1: direct lookup by query as article title
        summary = await self._get_page_summary(client, query, language)
        if summary is not None:
            if self._is_disambiguation(summary):
                return await self._resolve_disambiguation(
                    client, query, language, near_lat, near_lng
                )
            return summary

        # Step 2: full-text search → try each candidate
        candidates = await self._legacy_search(client, query, language)
        for title in candidates:
            s = await self._get_page_summary(client, title, language)
            if s is None or self._is_disambiguation(s):
                continue
            # Accept immediately if caller has no coordinates to filter by
            if near_lat is None or near_lng is None:
                return s
            # Prefer geotagged articles close to the given location
            if s.coordinates is not None:
                dist = _haversine(near_lat, near_lng, s.coordinates[0], s.coordinates[1])
                if dist <= _COORD_RADIUS_M:
                    return s
            # Non-geotagged candidate — accept as fallback (last resort)
            # Don't return here; keep looking for a geotagged one first

        # Last resort: return first non-disambiguation candidate regardless of coords
        for title in candidates:
            s = await self._get_page_summary(client, title, language)
            if s is not None and not self._is_disambiguation(s):
                return s

        return None

    async def _resolve_disambiguation(
        self,
        client: httpx.AsyncClient,
        query: str,
        language: str,
        near_lat: float | None,
        near_lng: float | None,
    ) -> WikipediaSummary | None:
        """Resolve a disambiguation page by searching and filtering by coordinates."""
        candidates = await self._legacy_search(client, query, language)
        for title in candidates:
            s = await self._get_page_summary(client, title, language)
            if s is None or self._is_disambiguation(s):
                continue
            if near_lat is None or near_lng is None:
                return s
            if s.coordinates is not None:
                dist = _haversine(near_lat, near_lng, s.coordinates[0], s.coordinates[1])
                if dist <= _COORD_RADIUS_M:
                    return s
        return None

    # =========================================================================
    # HTTP helpers
    # =========================================================================

    async def _get_page_summary(
        self,
        client: httpx.AsyncClient,
        title: str,
        language: str,
        max_attempts: int = 3,
    ) -> WikipediaSummary | None:
        url = f"{_REST_BASE.format(lang=language)}/page/summary/{quote(title, safe='')}"
        for attempt in range(max_attempts):
            try:
                resp = await client.get(url)
                if resp.status_code == 404:
                    return None
                if resp.status_code in (429, 500, 502, 503, 504):
                    wait = 2 ** attempt
                    logger.warning(
                        "Wikipedia REST API HTTP %s (attempt %d/%d) — retry in %ds",
                        resp.status_code, attempt + 1, max_attempts, wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                return self._parse_summary(resp.json())
            except httpx.TimeoutException:
                wait = 2 ** attempt
                logger.warning(
                    "Wikipedia timeout for title=%r (attempt %d/%d) — retry in %ds",
                    title, attempt + 1, max_attempts, wait,
                )
                if attempt < max_attempts - 1:
                    await asyncio.sleep(wait)
            except httpx.HTTPStatusError as exc:
                logger.warning("Wikipedia HTTP error for title=%r: %s", title, exc)
                return None
        return None

    async def _legacy_search(
        self,
        client: httpx.AsyncClient,
        query: str,
        language: str,
        limit: int = 5,
    ) -> list[str]:
        """Return a list of article titles from Wikipedia's legacy search API."""
        url = _LEGACY_API_BASE.format(lang=language)
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": limit,
            "format": "json",
        }
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            return [r["title"] for r in data.get("query", {}).get("search", [])]
        except Exception as exc:
            logger.warning(
                "Wikipedia legacy search failed for query=%r: %s", query, exc
            )
            return []

    # =========================================================================
    # Parsing helpers
    # =========================================================================

    @staticmethod
    def _parse_summary(data: dict[str, Any]) -> WikipediaSummary:
        coords = data.get("coordinates")
        coord_tuple: tuple[float, float] | None = (
            (coords["lat"], coords["lon"]) if coords else None
        )
        page_url: str = (
            data.get("content_urls", {}).get("desktop", {}).get("page", "")
        )
        return WikipediaSummary(
            title=data.get("title", ""),
            extract=data.get("extract", ""),
            description=data.get("description"),
            wikibase_item=data.get("wikibase_item"),
            coordinates=coord_tuple,
            page_url=page_url,
        )

    @staticmethod
    def _is_disambiguation(summary: WikipediaSummary) -> bool:
        """Return True if the summary represents a disambiguation page."""
        if summary.description and "disambiguation" in summary.description.lower():
            return True
        # Wikipedia REST API also sets type="disambiguation" for disambiguation pages
        return False


# ============================================================================
# Module-level helper
# ============================================================================

def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Straight-line distance in metres between two WGS-84 points."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))
