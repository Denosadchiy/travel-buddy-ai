"""
Zone Discovery — Phase 1 of the City Seeder.

Discovers tourist zones in a city by:
  1. Fetching POIs from Google Places Nearby Search (multiple place types).
  2. De-duplicating by google_place_id and filtering by rating/review count.
  3. Clustering with DBSCAN (haversine metric) to find geographic concentrations.
  4. Building a ProposedZone per cluster (convex hull boundary, auto-name, theme hint).

Pedestrian-network note
-----------------------
The convex hull produced here is a spatial envelope around tourist POIs —
it does NOT guarantee every point inside is walkable.  Actual placement of
guide_points onto the pedestrian network (OpenStreetMap) is performed in Step 5
(PointPlacement + GraphBuilder).  However, we do validate in the orchestrator
that a meaningful pedestrian network exists inside each proposed zone before
persisting it (see CitySeederOrchestrator._has_pedestrian_network()).
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from typing import Any

import numpy as np
from sklearn.cluster import DBSCAN
from shapely.geometry import MultiPoint, mapping

from src.config import settings
from src.guide.infrastructure.google_places_client import GuideGooglePlacesClient
from src.guide.application.seeder.types import POICandidate, ProposedZone

logger = logging.getLogger(__name__)

# Tourist-relevant Google Places types for zone discovery.
# Ordered loosely by visitor significance (affects rate-limit prioritisation).
TOURIST_POI_TYPES: list[str] = [
    "tourist_attraction",
    "museum",
    "art_gallery",
    "church",
    "hindu_temple",
    "mosque",
    "synagogue",
    "park",
    "amusement_park",
    "zoo",
    "aquarium",
    "library",
    "stadium",
    "university",
    "city_hall",
]

# Types classified as each theme for heuristic theme_hint detection.
_THEME_TYPES: dict[str, set[str]] = {
    "cultural":  {"museum", "art_gallery", "library"},
    "religious": {"church", "hindu_temple", "mosque", "synagogue"},
    "nature":    {"park", "zoo", "aquarium", "amusement_park"},
}

# Earth's radius in km — used to convert eps_m → radians for haversine DBSCAN.
_EARTH_RADIUS_KM = 6371.0


class ZoneDiscovery:
    """
    Discovers and proposes tourist zones for a city.

    Dependencies are injected via the constructor so the class is fully
    unit-testable with mock clients and settings overrides.

    Usage::

        discovery = ZoneDiscovery(places_client)
        zones = await discovery.discover("Paris", 48.8566, 2.3522, radius_km=12.0)
    """

    def __init__(
        self,
        places_client: GuideGooglePlacesClient | None = None,
        *,
        dbscan_eps_m: float | None = None,
        dbscan_min_samples: int | None = None,
        min_poi_rating: float | None = None,
        min_poi_reviews: int | None = None,
        max_pois_per_type: int | None = None,
        max_parallel_requests: int | None = None,
    ) -> None:
        self._client = places_client or GuideGooglePlacesClient()

        # Allow test overrides; fall back to settings
        self._eps_m = dbscan_eps_m if dbscan_eps_m is not None else settings.seeder_dbscan_eps_m
        self._min_samples = dbscan_min_samples if dbscan_min_samples is not None else settings.seeder_dbscan_min_samples
        self._min_rating = min_poi_rating if min_poi_rating is not None else settings.seeder_min_poi_rating
        self._min_reviews = min_poi_reviews if min_poi_reviews is not None else settings.seeder_min_poi_reviews
        self._max_per_type = max_pois_per_type if max_pois_per_type is not None else settings.seeder_max_pois_per_type
        self._max_parallel = max_parallel_requests if max_parallel_requests is not None else settings.seeder_max_parallel_poi_requests

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def discover(
        self,
        city_name: str,
        center_lat: float,
        center_lng: float,
        radius_km: float = 15.0,
    ) -> list[ProposedZone]:
        """
        Main entry point: fetch POIs, cluster, and return proposed zones.

        Args:
            city_name: Human-readable city name (for logging only).
            center_lat, center_lng: City centre coordinates.
            radius_km: Search radius from city centre (default 15 km).

        Returns:
            List of ProposedZone ready to be persisted with is_approved=FALSE.
            An empty list means no tourist clusters were found (e.g. small town
            with insufficient rated POIs).
        """
        radius_m = int(radius_km * 1000)
        logger.info(
            "ZoneDiscovery: starting for %s (%.4f, %.4f) r=%dm",
            city_name, center_lat, center_lng, radius_m,
        )

        pois = await self._fetch_tourist_pois(center_lat, center_lng, radius_m)
        logger.info("ZoneDiscovery: %d unique qualifying POIs fetched for %s", len(pois), city_name)

        if not pois:
            logger.warning("ZoneDiscovery: no POIs found — no zones proposed for %s", city_name)
            return []

        clusters = self._cluster_pois(pois)
        logger.info("ZoneDiscovery: %d clusters found for %s", len(clusters), city_name)

        zones = [self._build_zone_from_cluster(cluster) for cluster in clusters]
        return zones

    # -------------------------------------------------------------------------
    # Step 1: Fetch POIs from Google Places
    # -------------------------------------------------------------------------

    async def _fetch_tourist_pois(
        self,
        center_lat: float,
        center_lng: float,
        radius_m: int,
    ) -> list[POICandidate]:
        """
        Fetch and merge POIs for all TOURIST_POI_TYPES.

        Rate-limited to self._max_parallel concurrent requests.
        Deduplicates by google_place_id.
        Filters by rating >= min_poi_rating and reviews >= min_poi_reviews.
        """
        semaphore = asyncio.Semaphore(self._max_parallel)

        async def fetch_one(place_type: str) -> list[POICandidate]:
            async with semaphore:
                try:
                    raw = await self._client.nearby_search(
                        center_lat, center_lng, radius_m, place_type,
                        max_results=self._max_per_type,
                    )
                    return [self._parse_raw_place(p) for p in raw if self._parse_raw_place(p)]
                except Exception as exc:
                    logger.warning("ZoneDiscovery: failed to fetch type=%s: %s", place_type, exc)
                    return []

        results = await asyncio.gather(*[fetch_one(t) for t in TOURIST_POI_TYPES])

        # Flatten and deduplicate
        seen: set[str] = set()
        merged: list[POICandidate] = []
        for batch in results:
            for poi in batch:
                if poi.google_place_id not in seen:
                    seen.add(poi.google_place_id)
                    merged.append(poi)

        # Filter quality
        qualified = [
            p for p in merged
            if (p.rating is not None and p.rating >= self._min_rating)
            and (p.user_ratings_total is not None and p.user_ratings_total >= self._min_reviews)
        ]

        logger.debug(
            "ZoneDiscovery: %d raw POIs → %d after dedup → %d after quality filter",
            sum(len(b) for b in results), len(merged), len(qualified),
        )
        return qualified

    def _parse_raw_place(self, place: dict[str, Any]) -> POICandidate | None:
        """Convert a raw Google Places dict to a POICandidate. Returns None on missing data."""
        try:
            geometry = place.get("geometry", {})
            location = geometry.get("location", {})
            lat = location.get("lat")
            lng = location.get("lng")
            if lat is None or lng is None:
                return None

            return POICandidate(
                google_place_id=place["place_id"],
                name=place.get("name", ""),
                lat=float(lat),
                lng=float(lng),
                rating=place.get("rating"),
                user_ratings_total=place.get("user_ratings_total"),
                types=place.get("types", []),
            )
        except (KeyError, TypeError, ValueError):
            return None

    # -------------------------------------------------------------------------
    # Step 2: DBSCAN clustering
    # -------------------------------------------------------------------------

    def _cluster_pois(self, pois: list[POICandidate]) -> list[list[POICandidate]]:
        """
        Cluster POIs with DBSCAN using haversine distance metric.

        DBSCAN hyperparameters:
          eps   = settings.seeder_dbscan_eps_m metres (default 400 m)
                  converted to radians: eps_rad = eps_m / 1000 / EARTH_RADIUS_KM
          min_samples = settings.seeder_dbscan_min_samples (default 10)

        Outlier points (label == -1) are discarded — they represent isolated
        POIs that don't form a walkable tourist cluster.

        Returns:
            List of clusters (each cluster = list of POICandidate).
            Empty list if no clusters formed.
        """
        if len(pois) < self._min_samples:
            logger.info(
                "ZoneDiscovery: only %d POIs, need at least %d for any cluster",
                len(pois), self._min_samples,
            )
            return []

        # Convert to radians for haversine metric
        coords_rad = np.radians([[p.lat, p.lng] for p in pois])
        eps_rad = (self._eps_m / 1000.0) / _EARTH_RADIUS_KM

        db = DBSCAN(
            eps=eps_rad,
            min_samples=self._min_samples,
            algorithm="ball_tree",
            metric="haversine",
        ).fit(coords_rad)

        labels = db.labels_

        # Group by cluster label (skip -1 outliers)
        cluster_map: dict[int, list[POICandidate]] = {}
        for poi, label in zip(pois, labels):
            if label == -1:
                continue
            cluster_map.setdefault(label, []).append(poi)

        clusters = list(cluster_map.values())
        logger.debug(
            "ZoneDiscovery: DBSCAN → %d clusters, %d outliers discarded",
            len(clusters),
            int(np.sum(labels == -1)),
        )
        return clusters

    # -------------------------------------------------------------------------
    # Step 3: Build ProposedZone from cluster
    # -------------------------------------------------------------------------

    def _build_zone_from_cluster(self, cluster: list[POICandidate]) -> ProposedZone:
        """
        Compute convex hull, name, theme and centroid for a POI cluster.

        Naming rule: POI with highest composite score
            score = rating × log10(user_ratings_total + 1)
        is used as the zone name.

        Theme heuristic (majority vote on Google Place types):
          >50% museum / art_gallery / library  → "cultural"
          >50% church / mosque / temple / ...  → "religious"
          >50% park / zoo / aquarium / ...     → "nature"
          otherwise                            → "historic"

        Pedestrian-network note:
          The convex hull is a geographic bounding shape — it may include
          non-walkable areas (roads, water). Step 5 (PointPlacement) will snap
          all guide_points to the actual OSM pedestrian network inside this hull.
        """
        points = MultiPoint([(p.lng, p.lat) for p in cluster])
        hull = points.convex_hull

        # shapely may return a Point or LineString for tiny clusters; wrap if needed
        if hull.geom_type == "Point":
            # Single point cluster — expand to a small polygon (~50m radius)
            hull = hull.buffer(0.0005)  # ≈55m at equator
        elif hull.geom_type == "LineString":
            hull = hull.buffer(0.0002)

        boundary_wkt = hull.wkt
        boundary_geojson: dict = mapping(hull)  # type: ignore[arg-type]

        # Centroid
        centroid = hull.centroid
        centroid_lat = centroid.y
        centroid_lng = centroid.x

        # Scoring function
        def score(poi: POICandidate) -> float:
            r = poi.rating or 0.0
            n = poi.user_ratings_total or 0
            return r * math.log10(n + 1)

        ranked = sorted(cluster, key=score, reverse=True)

        # Zone name from top-ranked POI
        zone_name = ranked[0].name if ranked else "Tourist Zone"

        # Top-5 POI names for admin display
        top_poi_names = [p.name for p in ranked[:5]]

        # Theme hint (majority vote across all types in the cluster)
        all_types: list[str] = [t for poi in cluster for t in poi.types]
        n_total = len(all_types) if all_types else 1
        theme_hint: str | None = None
        for theme, type_set in _THEME_TYPES.items():
            count = sum(1 for t in all_types if t in type_set)
            if count / n_total > 0.5:
                theme_hint = theme
                break
        if theme_hint is None:
            theme_hint = "historic"

        return ProposedZone(
            name=zone_name,
            boundary_wkt=boundary_wkt,
            boundary_geojson=boundary_geojson,
            poi_count=len(cluster),
            top_poi_names=top_poi_names,
            theme_hint=theme_hint,
            centroid_lat=centroid_lat,
            centroid_lng=centroid_lng,
        )
