"""
PointPlacement — Phase 2 of the City Seeder.

Projects tourist POIs onto the OSMnx pedestrian walk network and generates
connector nodes at regular intervals along pedestrian edges.

Pedestrian-only principle
-------------------------
All guide_points MUST lie on the pedestrian network so the Navigation Engine
can compute valid walking routes between them.  This phase enforces that:

  * Each POI is snapped to its nearest OSM pedestrian node via ox.nearest_nodes().
  * POIs with a snap distance > seeder_max_snap_distance_m are marked
    is_approved=False and require manual review (e.g. POI on an island or inside
    a closed complex).
  * Connector points are generated only at real OSM graph nodes — never at
    arbitrary coordinates.
  * The graph G loaded here is passed directly to GraphBuilder so OSMnx data
    is fetched only once per zone.
"""
from __future__ import annotations

import logging
import math
from typing import Any
from uuid import UUID

from src.guide.application.seeder.types import (
    POICandidate,
    PlacedPoint,
    PointPlacementResult,
)

logger = logging.getLogger(__name__)


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance between two WGS-84 coordinate pairs, in metres."""
    R = 6_371_000.0
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


class PointPlacement:
    """
    Places tourist POIs and connector points on the OSMnx pedestrian network.

    Dependencies are injected via constructor parameters so the class is fully
    unit-testable without real OSMnx or Google Places calls.

    Args:
        max_snap_distance_m:   POIs further than this from any OSM node get
                               is_approved=False (default: seeder_max_snap_distance_m).
        connector_interval_m:  Minimum spacing between connector nodes (default:
                               seeder_connector_interval_m).
        osmnx_cache_dir:       Directory for OSMnx HTTP cache (default:
                               seeder_osmnx_cache_dir).
    """

    def __init__(
        self,
        max_snap_distance_m: float | None = None,
        connector_interval_m: float | None = None,
        osmnx_cache_dir: str | None = None,
    ) -> None:
        from src.config import settings

        self._max_snap_m = (
            max_snap_distance_m
            if max_snap_distance_m is not None
            else settings.seeder_max_snap_distance_m
        )
        self._connector_interval_m = (
            connector_interval_m
            if connector_interval_m is not None
            else settings.seeder_connector_interval_m
        )
        self._osmnx_cache_dir = (
            osmnx_cache_dir
            if osmnx_cache_dir is not None
            else settings.seeder_osmnx_cache_dir
        )

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def place_points_in_zone(
        self,
        zone_id: UUID,
        boundary_wkt: str,
        pois: list[POICandidate],
    ) -> tuple[PointPlacementResult, Any]:
        """
        Snap POIs to the OSMnx pedestrian graph and generate connector nodes.

        Args:
            zone_id:       UUID of the guide_zones row being processed.
            boundary_wkt:  WKT Polygon boundary of the zone (from PostGIS ST_AsText).
            pois:          Tourist POI candidates to project onto the graph.

        Returns:
            (PointPlacementResult, G) — the result summary and the networkx graph.
            G is returned so GraphBuilder can reuse it without a second OSMnx fetch.

        Raises:
            Any exception from _load_walk_graph is propagated to the caller
            (orchestrator catches it and marks the job as failed).
        """
        from shapely import wkt as shapely_wkt
        from shapely.geometry import Point as ShapelyPoint

        polygon = shapely_wkt.loads(boundary_wkt)

        # Phase 2a: load OSMnx pedestrian walk graph for zone boundary
        G = self._load_walk_graph(polygon)

        if not G or len(G.nodes) == 0:
            logger.warning(
                "PointPlacement: empty walk graph for zone %s — no points placed",
                zone_id,
            )
            return PointPlacementResult(
                zone_id=zone_id,
                placed_points=[],
                poi_count=0,
                connector_count=0,
                rejected_pois=[(p, "empty walk graph") for p in pois],
                graph_nodes_count=0,
                graph_edges_count=0,
            ), G

        logger.info(
            "PointPlacement: zone %s — walk graph has %d nodes, %d edges",
            zone_id,
            len(G.nodes),
            len(G.edges),
        )

        # Phase 2b: snap each POI to its nearest pedestrian node
        placed_points: list[PlacedPoint] = []
        rejected_pois: list[tuple[POICandidate, str]] = []
        seen_osm_nodes: set[int] = set()  # deduplication by OSM node ID

        for poi in pois:
            try:
                nearest_node = self._nearest_node(G, poi.lng, poi.lat)
            except Exception as exc:
                reason = f"nearest_node failed: {exc}"
                logger.warning(
                    "PointPlacement: POI '%s' rejected — %s", poi.name, reason
                )
                rejected_pois.append((poi, reason))
                continue

            node_data = G.nodes[nearest_node]
            node_lat: float = node_data["y"]
            node_lng: float = node_data["x"]

            snap_dist = haversine_m(poi.lat, poi.lng, node_lat, node_lng)
            is_approved = snap_dist <= self._max_snap_m

            if not is_approved:
                logger.warning(
                    "PointPlacement: POI '%s' snap distance %.1fm > threshold %.1fm "
                    "— placed with is_approved=False (requires manual review)",
                    poi.name,
                    snap_dist,
                    self._max_snap_m,
                )

            # Deduplicate: two POIs mapping to the same OSM node → keep the first
            if nearest_node in seen_osm_nodes:
                logger.debug(
                    "PointPlacement: POI '%s' maps to already-used node %d — skipped",
                    poi.name,
                    nearest_node,
                )
                continue

            seen_osm_nodes.add(nearest_node)
            placed_points.append(
                PlacedPoint(
                    point_type="poi",
                    lat=node_lat,
                    lng=node_lng,
                    osm_node_id=nearest_node,
                    name=poi.name,
                    google_place_id=poi.google_place_id,
                    source_poi=poi,
                    snap_distance_m=snap_dist,
                    is_approved=is_approved,
                )
            )

        poi_count = len(placed_points)
        logger.info(
            "PointPlacement: zone %s — %d POIs snapped (%d rejected, %d deduped)",
            zone_id,
            poi_count,
            len(rejected_pois),
            len(pois) - poi_count - len(rejected_pois),
        )

        # Phase 2c: generate connector nodes at regular intervals
        connector_ids = self._generate_connector_nodes(
            G, seen_osm_nodes, polygon, self._connector_interval_m
        )

        for node_id in connector_ids:
            node_data = G.nodes[node_id]
            placed_points.append(
                PlacedPoint(
                    point_type="connector",
                    lat=node_data["y"],
                    lng=node_data["x"],
                    osm_node_id=node_id,
                    is_approved=True,
                )
            )

        connector_count = len(connector_ids)
        logger.info(
            "PointPlacement: zone %s — %d connector nodes generated",
            zone_id,
            connector_count,
        )

        return PointPlacementResult(
            zone_id=zone_id,
            placed_points=placed_points,
            poi_count=poi_count,
            connector_count=connector_count,
            rejected_pois=rejected_pois,
            graph_nodes_count=len(G.nodes),
            graph_edges_count=len(G.edges),
        ), G

    # -------------------------------------------------------------------------
    # OSMnx wrappers — extracted for testability
    # -------------------------------------------------------------------------

    def _load_walk_graph(self, polygon: Any) -> Any:
        """
        Load the OSMnx pedestrian walk graph for the given shapely Polygon.

        Extracted as a separate method so unit tests can patch it and avoid
        any real network requests to the Overpass API.

        OSMnx cache is enabled to avoid redundant downloads on repeated runs.
        """
        import osmnx as ox

        ox.settings.use_cache = True
        ox.settings.cache_folder = self._osmnx_cache_dir
        ox.settings.log_console = False

        G = ox.graph_from_polygon(polygon, network_type="walk", simplify=True)
        G = ox.add_edge_speeds(G, fallback=4.5)   # 4.5 km/h = comfortable walking pace
        G = ox.add_edge_travel_times(G)
        return G

    def _nearest_node(self, G: Any, lng: float, lat: float) -> int:
        """
        Return the OSM node ID nearest to (lng, lat) in graph G.

        Extracted for testability — tests patch this method to avoid real
        spatial-index operations.
        """
        import osmnx as ox

        return ox.nearest_nodes(G, X=lng, Y=lat)

    # -------------------------------------------------------------------------
    # Connector node generation
    # -------------------------------------------------------------------------

    def _generate_connector_nodes(
        self,
        G: Any,
        poi_nodes: set[int],
        polygon: Any,
        interval_m: float,
    ) -> list[int]:
        """
        Select OSM nodes as connector points at regular spatial intervals.

        Strategy (MVP):
          1. Collect all graph nodes that are NOT POI nodes and have degree >= 2
             (dead-end nodes are excluded — they create navigation dead-ends).
          2. Sort by node ID for deterministic selection order.
          3. For each candidate, select it only if:
             a. It lies inside the zone polygon.
             b. It is at least interval_m from every already-selected connector
                AND from every POI node.

        Complexity: O(C × (P + S)) where C = candidate nodes, P = POI nodes,
        S = selected connectors.  Acceptable for zone-scale graphs (~2000 nodes).
        A spatial-index optimisation can be added in a future iteration.
        """
        from shapely.geometry import Point as ShapelyPoint

        candidates: list[int] = sorted(
            n for n in G.nodes if n not in poi_nodes and G.degree(n) >= 2
        )

        selected: list[int] = []
        poi_list: list[int] = list(poi_nodes)  # cache for inner loop

        for node in candidates:
            node_lat: float = G.nodes[node]["y"]
            node_lng: float = G.nodes[node]["x"]

            # Must lie inside zone polygon
            if not polygon.contains(ShapelyPoint(node_lng, node_lat)):
                continue

            # Must be sufficiently far from all POI nodes and already-selected connectors
            too_close = False
            for other in poi_list + selected:
                other_lat: float = G.nodes[other]["y"]
                other_lng: float = G.nodes[other]["x"]
                if haversine_m(node_lat, node_lng, other_lat, other_lng) < interval_m:
                    too_close = True
                    break

            if not too_close:
                selected.append(node)

        return selected
