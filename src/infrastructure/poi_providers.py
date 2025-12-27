"""
POI Provider abstraction and implementations.
Supports both internal DB and external API sources for POI discovery.
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select, or_, and_, String
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.domain.models import POICandidate, BudgetLevel
from src.infrastructure.models import POIModel

logger = logging.getLogger(__name__)


# Google Places type mapping to our categories
GOOGLE_TYPE_TO_CATEGORY = {
    # Food & Drink
    "restaurant": "restaurant",
    "cafe": "cafe",
    "bar": "bar",
    "bakery": "cafe",
    "meal_delivery": "restaurant",
    "meal_takeaway": "restaurant",
    "food": "restaurant",
    # Activities
    "museum": "museum",
    "art_gallery": "museum",
    "tourist_attraction": "attraction",
    "point_of_interest": "attraction",
    "park": "park",
    "zoo": "attraction",
    "aquarium": "attraction",
    "amusement_park": "attraction",
    "stadium": "attraction",
    "shopping_mall": "shopping",
    "store": "shopping",
    "spa": "wellness",
    "gym": "wellness",
    # Nightlife
    "night_club": "nightlife",
    "casino": "nightlife",
}

# Price level mapping to BudgetLevel
PRICE_LEVEL_TO_BUDGET = {
    0: BudgetLevel.LOW,    # Free
    1: BudgetLevel.LOW,    # Inexpensive
    2: BudgetLevel.MEDIUM, # Moderate
    3: BudgetLevel.HIGH,   # Expensive
    4: BudgetLevel.HIGH,   # Very Expensive
}


@dataclass
class GooglePlaceResult:
    """Parsed result from Google Places API."""
    place_id: str
    name: str
    formatted_address: str
    types: list[str]
    rating: Optional[float]
    price_level: Optional[int]
    lat: float
    lon: float


class POIProvider(ABC):
    """Abstract base class for POI providers."""

    @abstractmethod
    async def search_pois(
        self,
        city: str,
        desired_categories: list[str],
        budget: Optional[BudgetLevel] = None,
        limit: int = 10,
        center_location: Optional[str] = None,
    ) -> list[POICandidate]:
        """
        Search for POIs matching criteria.

        Args:
            city: City name
            desired_categories: List of desired categories/tags
            budget: Budget level (low, medium, high)
            limit: Maximum number of results
            center_location: Optional center point for proximity search

        Returns:
            List of POICandidate objects, ranked by relevance
        """
        pass


class DBPOIProvider(POIProvider):
    """
    POI provider that queries the internal PostgreSQL database.
    Ranks results by category/tag overlap and rating.
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize DB POI provider.

        Args:
            db: Database session
        """
        self.db = db

    def _calculate_relevance_score(
        self,
        poi: POIModel,
        desired_categories: list[str],
        budget: Optional[BudgetLevel] = None,
    ) -> float:
        """
        Calculate relevance score for a POI.

        Scoring factors:
        - Category match: +10 points
        - Tag overlap: +2 points per matching tag
        - Rating: 0-5 points (normalized rating)
        - Budget alignment: +5 if matches, -2 if mismatch
        - Price level alignment: +3 if matches budget
        """
        score = 0.0

        # Category match
        if poi.category in desired_categories:
            score += 10.0

        # Tag overlap
        poi_tags = set(poi.tags or [])
        desired_tags = set(desired_categories)
        overlap = poi_tags & desired_tags
        score += len(overlap) * 2.0

        # Rating (0-5 range)
        if poi.rating:
            score += poi.rating

        # Budget alignment using price_level if available
        if budget and poi.price_level is not None:
            poi_budget = PRICE_LEVEL_TO_BUDGET.get(poi.price_level, BudgetLevel.MEDIUM)
            if poi_budget == budget:
                score += 5.0
            elif (budget == BudgetLevel.LOW and poi.price_level <= 1) or \
                 (budget == BudgetLevel.HIGH and poi.price_level >= 3):
                score += 3.0
            else:
                score -= 2.0
        elif budget and poi.rating:
            # Fallback to rating-based heuristic
            if budget == BudgetLevel.LOW and poi.rating <= 3.5:
                score += 5.0
            elif budget == BudgetLevel.MEDIUM and 3.0 <= poi.rating <= 4.5:
                score += 5.0
            elif budget == BudgetLevel.HIGH and poi.rating >= 4.0:
                score += 5.0
            else:
                score -= 2.0

        return score

    async def search_pois(
        self,
        city: str,
        desired_categories: list[str],
        budget: Optional[BudgetLevel] = None,
        limit: int = 10,
        center_location: Optional[str] = None,
    ) -> list[POICandidate]:
        """Search internal database for matching POIs."""
        if not desired_categories:
            return []

        # Build query: match city AND (category OR any tag)
        query = select(POIModel).where(POIModel.city == city)

        # Add category/tag filters
        filters = []
        for category in desired_categories:
            # Match by category
            filters.append(POIModel.category == category)
            # Match by tags (JSON contains operator for PostgreSQL)
            # Use cast to text for JSON array comparison
            filters.append(POIModel.tags.cast(String).contains(category))

        if filters:
            query = query.where(or_(*filters))

        # Execute query
        result = await self.db.execute(query)
        poi_models = result.scalars().all()

        # Score and rank
        scored_pois = [
            (poi, self._calculate_relevance_score(poi, desired_categories, budget))
            for poi in poi_models
        ]
        scored_pois.sort(key=lambda x: x[1], reverse=True)

        # Convert to POICandidate and limit
        candidates = []
        for poi, score in scored_pois[:limit]:
            candidate = POICandidate(
                poi_id=poi.id,
                name=poi.name,
                category=poi.category,
                tags=poi.tags or [],
                rating=poi.rating,
                location=poi.location,
                lat=poi.lat,
                lon=poi.lon,
                rank_score=score,
            )
            candidates.append(candidate)

        return candidates


class GooglePlacesPOIProvider(POIProvider):
    """
    POI provider that fetches places from Google Places API.
    Caches results into the local database for future use.
    """

    EXTERNAL_SOURCE = "google_places"

    def __init__(
        self,
        db: AsyncSession,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: int = 10,
    ):
        """
        Initialize Google Places POI provider.

        Args:
            db: Database session for caching
            api_key: Google Maps API key (defaults to settings)
            base_url: API base URL (defaults to settings)
            timeout_seconds: HTTP timeout in seconds
        """
        self.db = db
        self.api_key = api_key or settings.google_maps_api_key
        self.base_url = base_url or settings.google_places_base_url
        self.timeout_seconds = timeout_seconds or settings.google_places_timeout_seconds
        self.language = settings.google_places_default_language

    def _build_search_query(
        self,
        city: str,
        desired_categories: list[str],
        center_location: Optional[str] = None,
    ) -> str:
        """Build search query for Google Places Text Search."""
        # Combine categories into a search-friendly query
        categories_text = " ".join(desired_categories[:3])  # Limit to avoid too long queries

        if center_location:
            return f"{categories_text} near {center_location}, {city}"
        return f"{categories_text} in {city}"

    def _parse_place_result(self, place: dict) -> Optional[GooglePlaceResult]:
        """Parse a single place from Google Places API response."""
        try:
            geometry = place.get("geometry", {})
            location = geometry.get("location", {})

            return GooglePlaceResult(
                place_id=place["place_id"],
                name=place["name"],
                formatted_address=place.get("formatted_address", place.get("vicinity", "")),
                types=place.get("types", []),
                rating=place.get("rating"),
                price_level=place.get("price_level"),
                lat=location.get("lat", 0.0),
                lon=location.get("lng", 0.0),
            )
        except (KeyError, TypeError) as e:
            logger.warning(f"Failed to parse place result: {e}")
            return None

    def _map_google_types_to_category(
        self,
        google_types: list[str],
        desired_categories: list[str],
    ) -> str:
        """Map Google Places types to our category taxonomy."""
        # First, try to match with desired categories
        for gtype in google_types:
            mapped = GOOGLE_TYPE_TO_CATEGORY.get(gtype)
            if mapped and mapped in desired_categories:
                return mapped

        # Otherwise, use the first matching type
        for gtype in google_types:
            if gtype in GOOGLE_TYPE_TO_CATEGORY:
                return GOOGLE_TYPE_TO_CATEGORY[gtype]

        # Default based on desired categories
        if desired_categories:
            return desired_categories[0]
        return "attraction"

    async def _fetch_from_google(
        self,
        city: str,
        desired_categories: list[str],
        limit: int,
        center_location: Optional[str] = None,
    ) -> list[GooglePlaceResult]:
        """Fetch places from Google Places API."""
        if not self.api_key:
            logger.warning("Google Maps API key not configured, skipping external search")
            return []

        query = self._build_search_query(city, desired_categories, center_location)

        params = {
            "query": query,
            "key": self.api_key,
            "language": self.language,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                data = response.json()

            status = data.get("status", "UNKNOWN")
            if status != "OK":
                if status == "ZERO_RESULTS":
                    logger.info(f"No results from Google Places for query: {query}")
                    return []
                logger.warning(f"Google Places API returned status: {status}")
                return []

            results = []
            for place in data.get("results", [])[:limit]:
                parsed = self._parse_place_result(place)
                if parsed:
                    results.append(parsed)

            logger.info(f"Fetched {len(results)} places from Google Places API")
            return results

        except httpx.TimeoutException:
            logger.warning(f"Google Places API timeout after {self.timeout_seconds}s")
            return []
        except httpx.HTTPStatusError as e:
            logger.warning(f"Google Places API HTTP error: {e.response.status_code}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching from Google Places: {e}")
            return []

    async def _cache_place_to_db(
        self,
        place: GooglePlaceResult,
        city: str,
        desired_categories: list[str],
    ) -> POIModel:
        """Cache a Google Place result to the database."""
        # Check if already exists
        result = await self.db.execute(
            select(POIModel).where(
                and_(
                    POIModel.external_source == self.EXTERNAL_SOURCE,
                    POIModel.external_id == place.place_id,
                )
            )
        )
        existing = result.scalars().first()

        category = self._map_google_types_to_category(place.types, desired_categories)

        # Combine Google types with our category as tags
        tags = list(set(place.types + [category]))

        if existing:
            # Update existing record with fresh data
            existing.rating = place.rating
            existing.price_level = place.price_level
            existing.tags = tags
            existing.updated_at = datetime.utcnow()
            poi_model = existing
        else:
            # Create new record
            poi_model = POIModel(
                id=uuid4(),
                name=place.name,
                city=city,
                category=category,
                tags=tags,
                rating=place.rating,
                location=place.formatted_address,
                external_source=self.EXTERNAL_SOURCE,
                external_id=place.place_id,
                lat=place.lat,
                lon=place.lon,
                price_level=place.price_level,
                created_at=datetime.utcnow(),
            )
            self.db.add(poi_model)

        return poi_model

    def _calculate_relevance_score(
        self,
        place: GooglePlaceResult,
        desired_categories: list[str],
        budget: Optional[BudgetLevel] = None,
    ) -> float:
        """Calculate relevance score for a Google Place result."""
        score = 0.0

        # Type overlap with desired categories
        place_types = set(place.types)
        desired_set = set(desired_categories)

        # Direct type match
        for gtype in place.types:
            mapped = GOOGLE_TYPE_TO_CATEGORY.get(gtype)
            if mapped in desired_set:
                score += 10.0
                break

        # Tag overlap
        for gtype in place.types:
            if gtype in desired_set:
                score += 2.0

        # Rating
        if place.rating:
            score += place.rating

        # Budget alignment
        if budget and place.price_level is not None:
            place_budget = PRICE_LEVEL_TO_BUDGET.get(place.price_level, BudgetLevel.MEDIUM)
            if place_budget == budget:
                score += 5.0
            else:
                score -= 2.0

        return score

    async def search_pois(
        self,
        city: str,
        desired_categories: list[str],
        budget: Optional[BudgetLevel] = None,
        limit: int = 10,
        center_location: Optional[str] = None,
    ) -> list[POICandidate]:
        """
        Search Google Places API for POIs and cache results.

        Returns POICandidate objects with database IDs after caching.
        """
        if not desired_categories:
            return []

        # Fetch from Google
        places = await self._fetch_from_google(
            city=city,
            desired_categories=desired_categories,
            limit=limit * 2,  # Fetch more to allow for filtering
            center_location=center_location,
        )

        if not places:
            return []

        # Cache to database and build candidates
        candidates = []
        for place in places:
            # Cache to DB
            poi_model = await self._cache_place_to_db(place, city, desired_categories)

            # Calculate score
            score = self._calculate_relevance_score(place, desired_categories, budget)

            # Build candidate
            candidate = POICandidate(
                poi_id=poi_model.id,
                name=place.name,
                category=self._map_google_types_to_category(place.types, desired_categories),
                tags=place.types,
                rating=place.rating,
                location=place.formatted_address,
                lat=place.lat,
                lon=place.lon,
                rank_score=score,
            )
            candidates.append(candidate)

        # Commit cached POIs
        await self.db.commit()

        # Sort by score and limit
        candidates.sort(key=lambda c: c.rank_score, reverse=True)
        return candidates[:limit]


# Keep ExternalPOIProvider as an alias for backward compatibility
ExternalPOIProvider = GooglePlacesPOIProvider


class CompositePOIProvider(POIProvider):
    """
    Composite provider that queries internal DB first, then falls back to external APIs.
    Ensures deduplication and merges results.
    """

    def __init__(
        self,
        db_provider: DBPOIProvider,
        external_provider: Optional[GooglePlacesPOIProvider] = None,
    ):
        """
        Initialize composite provider.

        Args:
            db_provider: Internal database provider
            external_provider: Optional external API provider (Google Places)
        """
        self.db_provider = db_provider
        self.external_provider = external_provider

    async def search_pois(
        self,
        city: str,
        desired_categories: list[str],
        budget: Optional[BudgetLevel] = None,
        limit: int = 10,
        center_location: Optional[str] = None,
    ) -> list[POICandidate]:
        """
        Search POIs using composite strategy.

        Strategy:
        1. Query internal DB first
        2. If results < limit and external provider available, fetch more from Google
        3. External results are automatically cached to DB
        4. Merge and deduplicate results
        5. Return top `limit` candidates sorted by rank_score
        """
        # Query internal DB first
        db_results = await self.db_provider.search_pois(
            city=city,
            desired_categories=desired_categories,
            budget=budget,
            limit=limit,
            center_location=center_location,
        )

        logger.debug(f"DB returned {len(db_results)} POIs for {city}")

        # If we have enough results or no external provider, return DB results
        if len(db_results) >= limit or not self.external_provider:
            return db_results[:limit]

        # Fetch from external API to supplement
        remaining_needed = limit - len(db_results)

        try:
            external_results = await self.external_provider.search_pois(
                city=city,
                desired_categories=desired_categories,
                budget=budget,
                limit=remaining_needed + 5,  # Fetch a few extra for deduplication
                center_location=center_location,
            )
            logger.debug(f"External API returned {len(external_results)} POIs")
        except Exception as e:
            logger.warning(f"External POI provider failed, using DB-only results: {e}")
            return db_results[:limit]

        # Merge results and deduplicate by POI ID
        seen_ids = {candidate.poi_id for candidate in db_results}
        merged_results = db_results.copy()

        for candidate in external_results:
            if candidate.poi_id not in seen_ids:
                merged_results.append(candidate)
                seen_ids.add(candidate.poi_id)

        # Sort by rank_score and limit
        merged_results.sort(key=lambda c: c.rank_score, reverse=True)
        return merged_results[:limit]


def get_poi_provider(db: AsyncSession) -> POIProvider:
    """
    Factory function to create POI provider.

    Returns CompositePOIProvider with:
    - DBPOIProvider for internal DB
    - GooglePlacesPOIProvider for external API (if API key is configured)

    Args:
        db: Database session

    Returns:
        Composite POI provider
    """
    db_provider = DBPOIProvider(db)

    # Only create external provider if API key is configured
    external_provider = None
    if settings.google_maps_api_key:
        external_provider = GooglePlacesPOIProvider(db=db)
        logger.info("Google Places POI provider enabled")
    else:
        logger.warning(
            "GOOGLE_MAPS_API_KEY not configured. "
            "External POI search disabled, using DB-only mode."
        )

    return CompositePOIProvider(
        db_provider=db_provider,
        external_provider=external_provider,
    )
