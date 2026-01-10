"""
POI Provider abstraction and implementations.
Supports both internal DB and external API sources for POI discovery.
"""
import logging
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select, or_, and_, String
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.domain.models import POICandidate, BudgetLevel, BlockType
from src.infrastructure.models import POIModel

logger = logging.getLogger(__name__)

# Default maximum radius from city center (km)
DEFAULT_MAX_RADIUS_KM = 15.0  # Strict 15km radius to exclude places outside the city


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points on Earth in kilometers.

    Uses the Haversine formula.

    Args:
        lat1, lon1: Latitude and longitude of first point (degrees)
        lat2, lon2: Latitude and longitude of second point (degrees)

    Returns:
        Distance in kilometers
    """
    R = 6371.0  # Earth's radius in km

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2 +
        math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


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

# BlockType to allowed Google Places types mapping
# This ensures we only return POIs that match the expected block type
BLOCK_TYPE_ALLOWED_GOOGLE_TYPES: dict[BlockType, set[str]] = {
    BlockType.MEAL: {
        "restaurant", "cafe", "bakery", "bar", "food",
        "meal_delivery", "meal_takeaway",
    },
    BlockType.ACTIVITY: {
        "tourist_attraction", "museum", "art_gallery", "park", "zoo",
        "aquarium", "amusement_park", "stadium", "shopping_mall", "store",
        "spa", "gym", "point_of_interest", "church", "hindu_temple",
        "mosque", "synagogue", "library", "movie_theater", "bowling_alley",
    },
    BlockType.NIGHTLIFE: {
        "night_club", "bar", "casino",
    },
}

# BlockType to allowed internal categories mapping
BLOCK_TYPE_ALLOWED_CATEGORIES: dict[BlockType, set[str]] = {
    BlockType.MEAL: {"restaurant", "cafe", "bar", "bakery", "food"},
    BlockType.ACTIVITY: {"museum", "attraction", "park", "shopping", "wellness"},
    BlockType.NIGHTLIFE: {"nightlife", "bar"},
}

# Heuristic name-based filters for meal blocks
# These keywords in POI names indicate the place is NOT suitable for meals
MEAL_EXCLUDE_NAME_KEYWORDS = {
    "class", "classes", "school", "course", "courses", "workshop",
    "lesson", "lessons", "tour", "tours", "cooking class", "wine tasting class",
    "academy", "institute", "training", "education",
}


def is_poi_suitable_for_block_type(
    poi_name: str,
    poi_category: str,
    poi_tags: list[str],
    block_type: BlockType,
) -> bool:
    """
    Check if a POI is suitable for a given block type.

    Args:
        poi_name: Name of the POI
        poi_category: POI category
        poi_tags: POI tags (Google types or internal tags)
        block_type: Type of block (MEAL, ACTIVITY, NIGHTLIFE, etc.)

    Returns:
        True if the POI is suitable for the block type
    """
    # REST and TRAVEL blocks don't need POIs
    if block_type in (BlockType.REST, BlockType.TRAVEL):
        return True

    # Check category allowlist
    allowed_categories = BLOCK_TYPE_ALLOWED_CATEGORIES.get(block_type)
    if allowed_categories and poi_category not in allowed_categories:
        # Also check if any tag matches
        if not any(tag in allowed_categories for tag in poi_tags):
            return False

    # For meals, apply heuristic name-based filtering
    if block_type == BlockType.MEAL:
        name_lower = poi_name.lower()
        for keyword in MEAL_EXCLUDE_NAME_KEYWORDS:
            if keyword in name_lower:
                logger.debug(f"Excluding '{poi_name}' from meals due to keyword '{keyword}'")
                return False

    return True


@dataclass
class GooglePlaceResult:
    """Parsed result from Google Places API."""
    place_id: str
    name: str
    formatted_address: str
    types: list[str]
    rating: Optional[float]
    user_ratings_total: Optional[int]
    price_level: Optional[int]
    business_status: Optional[str]
    open_now: Optional[bool]
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
        city_center_lat: Optional[float] = None,
        city_center_lon: Optional[float] = None,
        max_radius_km: float = DEFAULT_MAX_RADIUS_KM,
        block_type: Optional[BlockType] = None,
        search_keywords: Optional[list[str]] = None,
        fetch_details: bool = True,
    ) -> list[POICandidate]:
        """
        Search for POIs matching criteria.

        Args:
            city: City name
            desired_categories: List of desired categories/tags
            budget: Budget level (low, medium, high)
            limit: Maximum number of results
            center_location: Optional center point for proximity search
            city_center_lat: City center latitude for radius filtering
            city_center_lon: City center longitude for radius filtering
            max_radius_km: Maximum radius from city center in km (default: 20km)
            block_type: Type of block (MEAL, ACTIVITY, etc.) for category filtering
            fetch_details: Whether to fetch full place details for external sources

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

    async def search_pois_bulk(
        self,
        city: str,
        all_categories: set[str],
        budget: Optional[BudgetLevel] = None,
        limit_per_category: int = 30,
        city_center_lat: Optional[float] = None,
        city_center_lon: Optional[float] = None,
        max_radius_km: float = DEFAULT_MAX_RADIUS_KM,
        min_rating: float = 4.5,
        include_tags: bool = True,
    ) -> dict[str, list[POICandidate]]:
        """
        Fetch POIs for ALL categories in a single DB query.

        This is optimized for fast_draft_planner to avoid sequential queries.

        Args:
            city: City name
            all_categories: Set of all categories to fetch
            budget: Budget level for scoring
            limit_per_category: Max POIs per category
            city_center_lat/lon: For radius filtering
            max_radius_km: Max distance from city center
            min_rating: Minimum rating filter

        Returns:
            Dict mapping category -> list of POICandidates
        """
        if not all_categories:
            return {}

        # Build query: match city AND (category OR any tag)
        query = select(POIModel).where(POIModel.city == city)

        # Add category/tag filters for ALL categories at once
        filters = []
        for category in all_categories:
            filters.append(POIModel.category == category)
            if include_tags:
                filters.append(POIModel.tags.cast(String).contains(category))

        if filters:
            query = query.where(or_(*filters))

        if min_rating is not None:
            query = query.where(POIModel.rating >= min_rating)

        # Execute single query
        result = await self.db.execute(query)
        poi_models = result.scalars().all()

        # Apply post-query filtering and sort into category pools
        has_city_center = city_center_lat is not None and city_center_lon is not None
        category_pools: dict[str, list[tuple[POIModel, float]]] = {cat: [] for cat in all_categories}

        for poi in poi_models:
            # Radius filtering
            if has_city_center and poi.lat is not None and poi.lon is not None:
                distance_km = haversine_distance_km(
                    city_center_lat, city_center_lon, poi.lat, poi.lon
                )
                if distance_km > max_radius_km:
                    continue

            # Rating filtering
            if (poi.rating or 0) < min_rating:
                continue

            # Score the POI
            score = self._calculate_relevance_score(poi, list(all_categories), budget)

            # Add to matching category pools
            if poi.category in all_categories:
                category_pools[poi.category].append((poi, score))

            # Also add to pools matching tags
            for tag in (poi.tags or []):
                if tag in all_categories and tag != poi.category:
                    category_pools[tag].append((poi, score))

        # Convert to POICandidate and sort each pool by score
        result_pools: dict[str, list[POICandidate]] = {}

        for category, scored_pois in category_pools.items():
            scored_pois.sort(key=lambda x: x[1], reverse=True)

            candidates = []
            for poi, score in scored_pois[:limit_per_category]:
                candidates.append(POICandidate(
                    poi_id=poi.id,
                    name=poi.name,
                    category=poi.category,
                    tags=poi.tags or [],
                    rating=poi.rating,
                    user_ratings_total=poi.user_ratings_total,
                    price_level=poi.price_level,
                    business_status=poi.business_status,
                    open_now=(poi.opening_hours or {}).get("open_now") if isinstance(poi.opening_hours, dict) else None,
                    location=poi.location,
                    lat=poi.lat,
                    lon=poi.lon,
                    rank_score=score,
                ))
            result_pools[category] = candidates

        return result_pools

    async def search_pois(
        self,
        city: str,
        desired_categories: list[str],
        budget: Optional[BudgetLevel] = None,
        limit: int = 10,
        center_location: Optional[str] = None,
        city_center_lat: Optional[float] = None,
        city_center_lon: Optional[float] = None,
        max_radius_km: float = DEFAULT_MAX_RADIUS_KM,
        block_type: Optional[BlockType] = None,
        search_keywords: Optional[list[str]] = None,
        fetch_details: bool = True,
    ) -> list[POICandidate]:
        """Search internal database for matching POIs with radius and category filtering."""
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

        # Apply post-query filtering
        filtered_pois = []
        has_city_center = city_center_lat is not None and city_center_lon is not None

        for poi in poi_models:
            # Radius filtering: skip POIs outside max radius
            if has_city_center and poi.lat is not None and poi.lon is not None:
                distance_km = haversine_distance_km(
                    city_center_lat, city_center_lon, poi.lat, poi.lon
                )
                if distance_km > max_radius_km:
                    logger.info(
                        f"⊘ Excluded POI '{poi.name}' - {distance_km:.1f}km from city center "
                        f"(max: {max_radius_km}km) - Location: {poi.location[:50]}"
                    )
                    continue

            # BlockType filtering: skip POIs that don't match the block type
            if block_type and not is_poi_suitable_for_block_type(
                poi.name, poi.category, poi.tags or [], block_type
            ):
                continue

            filtered_pois.append(poi)

        # Score and rank
        scored_pois = [
            (poi, self._calculate_relevance_score(poi, desired_categories, budget))
            for poi in filtered_pois
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
                user_ratings_total=poi.user_ratings_total,
                price_level=poi.price_level,
                business_status=poi.business_status,
                open_now=(poi.opening_hours or {}).get("open_now") if isinstance(poi.opening_hours, dict) else None,
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
        search_keywords: Optional[list[str]] = None,
    ) -> str:
        """Build search query for Google Places Text Search."""
        # Combine categories into a search-friendly query
        categories_text = " ".join(desired_categories[:3])  # Limit to avoid too long queries
        keyword_text = ""
        if search_keywords:
            keyword_text = " " + " ".join(search_keywords[:3])

        if center_location:
            return f"{categories_text}{keyword_text} near {center_location}, {city}"
        return f"{categories_text}{keyword_text} in {city}"

    def _parse_place_result(self, place: dict) -> Optional[GooglePlaceResult]:
        """Parse a single place from Google Places API response."""
        try:
            geometry = place.get("geometry", {})
            location = geometry.get("location", {})
            opening_hours = place.get("opening_hours", {})

            return GooglePlaceResult(
                place_id=place["place_id"],
                name=place["name"],
                formatted_address=place.get("formatted_address", place.get("vicinity", "")),
                types=place.get("types", []),
                rating=place.get("rating"),
                user_ratings_total=place.get("user_ratings_total"),
                price_level=place.get("price_level"),
                business_status=place.get("business_status"),
                open_now=opening_hours.get("open_now") if isinstance(opening_hours, dict) else None,
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
        # Prioritize the primary Google type
        if google_types:
            primary_type = google_types[0]
            if primary_type in GOOGLE_TYPE_TO_CATEGORY:
                return GOOGLE_TYPE_TO_CATEGORY[primary_type]

        # First, try to match with desired categories
        for gtype in google_types:
            mapped = GOOGLE_TYPE_TO_CATEGORY.get(gtype)
            if mapped and mapped in desired_categories:
                return mapped

        # Otherwise, use the first matching type from the remaining types
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
        search_keywords: Optional[list[str]] = None,
    ) -> list[GooglePlaceResult]:
        """Fetch places from Google Places API."""
        if not self.api_key:
            logger.warning("Google Maps API key not configured, skipping external search")
            return []

        query = self._build_search_query(city, desired_categories, center_location, search_keywords)

        params = {
            "query": query,
            "key": self.api_key,
            "language": self.language,
        }

        print(f"🌐 Google Places Text Search API: query='{query}'")
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                data = response.json()

            status = data.get("status", "UNKNOWN")
            if status != "OK":
                if status == "ZERO_RESULTS":
                    print(f"⚪ Google Places Text Search API: No results for query='{query}'")
                    logger.info(f"No results from Google Places for query: {query}")
                    return []
                print(f"❌ Google Places Text Search API: Status {status} for query='{query}'")
                logger.warning(f"Google Places API returned status: {status}")
                return []

            results = []
            for place in data.get("results", [])[:limit]:
                parsed = self._parse_place_result(place)
                if parsed:
                    results.append(parsed)

            print(f"✅ Google Places Text Search API: {len(results)} places for query='{query}'")
            logger.info(f"Fetched {len(results)} places from Google Places API")
            return results

        except httpx.TimeoutException:
            print(f"❌ Google Places Text Search API: Timeout ({self.timeout_seconds}s) for query='{query}'")
            logger.warning(f"Google Places API timeout after {self.timeout_seconds}s")
            return []
        except httpx.HTTPStatusError as e:
            print(f"❌ Google Places Text Search API: HTTP {e.response.status_code} for query='{query}'")
            logger.warning(f"Google Places API HTTP error: {e.response.status_code}")
            return []
        except Exception as e:
            print(f"❌ Google Places Text Search API: {type(e).__name__}: {e} for query='{query}'")
            logger.error(f"Unexpected error fetching from Google Places: {e}")
            return []

    async def _cache_place_to_db(
        self,
        place: GooglePlaceResult,
        city: str,
        desired_categories: list[str],
        fetch_details: bool = True,
    ) -> POIModel:
        """
        Cache a Google Place result to the database.
        Optionally fetches full details before caching.
        """
        from sqlalchemy.exc import IntegrityError
        from src.infrastructure.google_place_details import fetch_place_details

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

        details = None
        if fetch_details:
            has_details = existing and (existing.description or existing.reviews)
            if not has_details:
                try:
                    details = await fetch_place_details(place.place_id)
                except Exception as e:
                    logger.warning(f"Failed to fetch details for {place.name}: {e}")
                    details = None

        category = self._map_google_types_to_category(place.types, desired_categories)
        tags = list(set(place.types + [category]))

        if existing:
            # Update existing record
            existing.rating = place.rating
            existing.price_level = place.price_level
            existing.user_ratings_total = place.user_ratings_total
            existing.business_status = place.business_status
            existing.tags = tags
            if details:
                existing.description = details.editorial_summary
                existing.reviews = [r.text for r in details.reviews]
            if place.open_now is not None:
                existing.opening_hours = {"open_now": place.open_now}
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
                user_ratings_total=place.user_ratings_total,
                location=place.formatted_address,
                external_source=self.EXTERNAL_SOURCE,
                external_id=place.place_id,
                lat=place.lat,
                lon=place.lon,
                price_level=place.price_level,
                business_status=place.business_status,
                description=details.editorial_summary if details else None,
                reviews=[r.text for r in details.reviews] if details else [],
                opening_hours={"open_now": place.open_now} if place.open_now is not None else None,
                created_at=datetime.utcnow(),
            )

            try:
                self.db.add(poi_model)
                await self.db.flush()
            except IntegrityError:
                await self.db.rollback()
                result = await self.db.execute(
                    select(POIModel).where(
                        and_(
                            POIModel.external_source == self.EXTERNAL_SOURCE,
                            POIModel.external_id == place.place_id,
                        )
                    )
                )
                poi_model = result.scalars().first()
                if not poi_model:
                    raise RuntimeError(f"POI {place.place_id} disappeared after IntegrityError")

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
        city_center_lat: Optional[float] = None,
        city_center_lon: Optional[float] = None,
        max_radius_km: float = DEFAULT_MAX_RADIUS_KM,
        block_type: Optional[BlockType] = None,
        search_keywords: Optional[list[str]] = None,
        fetch_details: bool = True,
    ) -> list[POICandidate]:
        """
        Search Google Places API for POIs and cache results.

        Returns POICandidate objects with database IDs after caching.
        Applies radius and block type filtering.
        """
        if not desired_categories:
            return []

        # Fetch from Google
        places = await self._fetch_from_google(
            city=city,
            desired_categories=desired_categories,
            limit=limit * 2,  # Fetch more to allow for filtering
            center_location=center_location,
            search_keywords=search_keywords,
        )

        if not places:
            return []

        has_city_center = city_center_lat is not None and city_center_lon is not None

        # Filter, cache, and build candidates
        candidates = []
        for place in places:
            if len(candidates) >= limit:
                break

            # Radius filtering
            if has_city_center:
                distance_km = haversine_distance_km(
                    city_center_lat, city_center_lon, place.lat, place.lon
                )
                if distance_km > max_radius_km:
                    continue

            category = self._map_google_types_to_category(place.types, desired_categories)
            if block_type and not is_poi_suitable_for_block_type(
                place.name, category, place.types, block_type
            ):
                continue

            poi_model = await self._cache_place_to_db(
                place,
                city,
                desired_categories,
                fetch_details=fetch_details,
            )
            score = self._calculate_relevance_score(place, desired_categories, budget)

            candidate = POICandidate(
                poi_id=poi_model.id,
                name=place.name,
                category=category,
                tags=place.types,
                rating=place.rating,
                user_ratings_total=place.user_ratings_total,
                price_level=place.price_level,
                business_status=place.business_status,
                open_now=place.open_now,
                location=place.formatted_address,
                lat=place.lat,
                lon=place.lon,
                description=poi_model.description,
                reviews=poi_model.reviews,
                rank_score=score,
            )
            candidates.append(candidate)

        await self.db.commit()

        candidates.sort(key=lambda c: c.rank_score, reverse=True)
        return candidates


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
        city_center_lat: Optional[float] = None,
        city_center_lon: Optional[float] = None,
        max_radius_km: float = DEFAULT_MAX_RADIUS_KM,
        block_type: Optional[BlockType] = None,
        search_keywords: Optional[list[str]] = None,
        fetch_details: bool = True,
    ) -> list[POICandidate]:
        """
        Search POIs using composite strategy with radius and block type filtering.

        Strategy:
        1. Query internal DB first (with filtering)
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
            city_center_lat=city_center_lat,
            city_center_lon=city_center_lon,
            max_radius_km=max_radius_km,
            block_type=block_type,
            search_keywords=search_keywords,
            fetch_details=fetch_details,
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
                city_center_lat=city_center_lat,
                city_center_lon=city_center_lon,
                max_radius_km=max_radius_km,
                block_type=block_type,
                search_keywords=search_keywords,
                fetch_details=fetch_details,
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
