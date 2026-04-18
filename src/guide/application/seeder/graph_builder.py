"""
GraphBuilder — Phase 3 of the City Seeder.

Builds directed pedestrian-graph edges between guide_points using networkx
shortest-path over the OSMnx pedestrian network loaded by PointPlacement.

Pedestrian-only principle
-------------------------
Edges are computed via networkx.shortest_path_length over the real pedestrian
graph — never as straight-line distances.  walk_seconds uses OSMnx travel_time
weights (speed capped at 4.5 km/h, the value set by PointPlacement).

Pre-filter optimisation
-----------------------
Before calling nx.shortest_path_length (expensive), candidates are pre-filtered
by straight-line haversine distance (< seeder_max_neighbor_distance_m).  This
is always safe: pedestrian-network distance >= straight-line distance.
"""
from __future__ import annotations

import logging
import math
from typing import Any
from uuid import UUID

from src.guide.application.seeder.types import (
    BuiltEdge,
    GraphBuildResult,
    PlacedPoint,
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


def _compute_bearing(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Compute the compass bearing (azimuth) from point A to point B.

    Returns degrees in [0, 360) where 0 = north, 90 = east.
    """
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlng = math.radians(lng2 - lng1)
    x = math.sin(dlng) * math.cos(lat2_r)
    y = (
        math.cos(lat1_r) * math.sin(lat2_r)
        - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dlng)
    )
    bearing = math.atan2(x, y)
    return (math.degrees(bearing) + 360) % 360


class GraphBuilder:
    """
    Builds directed pedestrian-graph edges between guide_points.

    Args:
        max_neighbor_distance_m: Pre-filter straight-line radius for shortest-path
                                 candidates (default: seeder_max_neighbor_distance_m).
        k_neighbors:             Maximum outgoing edges per point (default:
                                 seeder_k_neighbors).
    """

    def __init__(
        self,
        max_neighbor_distance_m: float | None = None,
        k_neighbors: int | None = None,
    ) -> None:
        from src.config import settings

        self._max_dist_m = (
            max_neighbor_distance_m
            if max_neighbor_distance_m is not None
            else settings.seeder_max_neighbor_distance_m
        )
        self._k = (
            k_neighbors
            if k_neighbors is not None
            else settings.seeder_k_neighbors
        )

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def build_graph_for_zone(
        self,
        zone_id: UUID,
        placed_points: list[PlacedPoint],
        G: Any,
    ) -> tuple[GraphBuildResult, list[BuiltEdge]]:
        """
        Compute directed pedestrian edges between all approved placed_points.

        Args:
            zone_id:        UUID of the zone (for logging / result tagging).
            placed_points:  PlacedPoints from PointPlacement (POI + connector).
            G:              networkx MultiDiGraph from OSMnx — reused from
                            PointPlacement to avoid a second Overpass API fetch.

        Returns:
            (GraphBuildResult, list[BuiltEdge]) — summary and edges ready for
            SeederRepository.bulk_insert_edges().

        Algorithm for each approved point P:
          1. Pre-filter: candidates within MAX_DIST_M by straight-line distance.
          2. For each candidate Q: nx.shortest_path_length (travel_time + length).
             Skip pairs where no pedestrian path exists.
          3. Take the K-nearest by walk_seconds, emit directed edges P→Q.
        """
        import networkx as nx

        active = [p for p in placed_points if p.is_approved]
        if not active:
            logger.warning(
                "GraphBuilder: no approved points for zone %s — no edges built", zone_id
            )
            return GraphBuildResult(
                zone_id=zone_id,
                edges_built=0,
                avg_neighbors_per_point=0.0,
                isolated_points=[],
            ), []

        edges_out: list[BuiltEdge] = []
        isolated_nodes: list[int] = []

        for p in active:
            # Step 1: pre-filter by straight-line haversine distance
            candidates = [
                (q, haversine_m(p.lat, p.lng, q.lat, q.lng))
                for q in active
                if q.osm_node_id != p.osm_node_id
                and haversine_m(p.lat, p.lng, q.lat, q.lng) <= self._max_dist_m
            ]

            if not candidates:
                isolated_nodes.append(p.osm_node_id)
                continue

            # Sort by straight-line distance for deterministic tie-breaking
            candidates.sort(key=lambda x: x[1])

            # Step 2: compute real pedestrian distances via networkx
            walk_distances: list[tuple[PlacedPoint, float, float]] = []
            for q, _ in candidates:
                try:
                    walk_time = nx.shortest_path_length(
                        G, p.osm_node_id, q.osm_node_id, weight="travel_time"
                    )
                    walk_len = nx.shortest_path_length(
                        G, p.osm_node_id, q.osm_node_id, weight="length"
                    )
                    walk_distances.append((q, walk_len, walk_time))
                except nx.NetworkXNoPath:
                    # Points are on disconnected graph components — no edge
                    continue
                except nx.NodeNotFound:
                    logger.warning(
                        "GraphBuilder: node %d or %d not in graph — edge skipped",
                        p.osm_node_id,
                        q.osm_node_id,
                    )
                    continue

            if not walk_distances:
                isolated_nodes.append(p.osm_node_id)
                continue

            # Step 3: take K nearest by walk_seconds, emit directed edges P→Q
            walk_distances.sort(key=lambda x: x[2])
            nearest = walk_distances[: self._k]

            for q, walk_len, walk_time in nearest:
                bearing = _compute_bearing(p.lat, p.lng, q.lat, q.lng)
                edges_out.append(
                    BuiltEdge(
                        from_osm_node=p.osm_node_id,
                        to_osm_node=q.osm_node_id,
                        distance_m=walk_len,
                        walk_seconds=int(walk_time),
                        bearing_deg=bearing,
                    )
                )

        n = len(active)
        avg = len(edges_out) / n if n > 0 else 0.0
        logger.info(
            "GraphBuilder: zone %s — %d edges built, %.1f avg neighbors/point, "
            "%d isolated points",
            zone_id,
            len(edges_out),
            avg,
            len(isolated_nodes),
        )

        return GraphBuildResult(
            zone_id=zone_id,
            edges_built=len(edges_out),
            avg_neighbors_per_point=avg,
            isolated_points=isolated_nodes,
        ), edges_out
