"""
Shared data types for the City Seeder pipeline.

These are internal transport objects — not ORM models, not API schemas.
They flow between ZoneDiscovery → SeederRepository → CitySeederOrchestrator.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


# ============================================================================
# Hardcoded city centres — MVP fallback when Google Geocoding is unavailable
# ============================================================================

MVP_CITY_CENTERS: dict[str, tuple[float, float]] = {
    "moscow":    (55.7558, 37.6173),
    "paris":     (48.8566,  2.3522),
    "barcelona": (41.3851,  2.1734),
    "istanbul":  (41.0082, 28.9784),
    "shanghai":  (31.2304, 121.4737),
}


# ============================================================================
# POICandidate — raw POI returned by Google Places during discovery
# ============================================================================

@dataclass
class POICandidate:
    """
    POI returned by Google Places Nearby Search during the Zone Discovery phase.

    Note: This is the *guide seeder* POICandidate — unrelated to
    src.domain.models.POICandidate which is used by the trip-planning pipeline.
    Field names mirror Google Places API keys for easy mapping.
    """
    google_place_id: str
    name: str
    lat: float
    lng: float
    rating: float | None
    user_ratings_total: int | None
    types: list[str]                        # Google Place types list
    place_detail_raw: dict[str, Any] | None = None  # Reserved for Step 5 enrichment


# ============================================================================
# ProposedZone — clustered zone candidate, not yet persisted in DB
# ============================================================================

@dataclass
class ProposedZone:
    """
    Zone proposed by ZoneDiscovery after DBSCAN clustering.

    Not yet saved to guide_zones. Stored in guide_zones with is_approved=FALSE
    by SeederRepository.bulk_insert_zones() — awaiting admin review.

    The boundary is a convex hull of the cluster's POI coordinates.
    Actual point placement on the pedestrian network happens in Step 5
    (PointPlacement + GraphBuilder).
    """
    name: str                   # Auto-generated from highest-scored POI
    boundary_wkt: str           # WKT Polygon for PostGIS ST_GeomFromText()
    boundary_geojson: dict      # GeoJSON Polygon for admin API responses
    poi_count: int
    top_poi_names: list[str]    # Top-5 POIs by score (for admin review display)
    theme_hint: str | None      # Heuristic theme: "cultural" | "religious" | "nature" | "historic"
    centroid_lat: float
    centroid_lng: float


# ============================================================================
# SeedJobProgress — serialised into guide_seed_jobs.progress_json
# ============================================================================

@dataclass
class SeedJobProgress:
    """
    Mutable progress snapshot for a City Seeder job.

    Serialised to/from guide_seed_jobs.progress_json via .to_dict() / from_dict().
    Updated at each phase boundary so the admin dashboard can show live progress.

    Phases (in order):
      zone_discovery → awaiting_approval → point_placement (Step 5)
      → building_graph (Step 5) → collecting_knowledge (Step 5)
      → generating_content → complete
    """
    phase: str
    pois_fetched: int = 0
    zones_proposed: int = 0
    zones_approved: int = 0
    points_placed: int = 0
    edges_built: int = 0
    cards_collected: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "pois_fetched": self.pois_fetched,
            "zones_proposed": self.zones_proposed,
            "zones_approved": self.zones_approved,
            "points_placed": self.points_placed,
            "edges_built": self.edges_built,
            "cards_collected": self.cards_collected,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SeedJobProgress":
        return cls(
            phase=data.get("phase", "unknown"),
            pois_fetched=data.get("pois_fetched", 0),
            zones_proposed=data.get("zones_proposed", 0),
            zones_approved=data.get("zones_approved", 0),
            points_placed=data.get("points_placed", 0),
            edges_built=data.get("edges_built", 0),
            cards_collected=data.get("cards_collected", 0),
            error=data.get("error"),
        )


# ============================================================================
# PlacedPoint — a POI or connector snapped to the OSM pedestrian graph
# ============================================================================

@dataclass
class PlacedPoint:
    """
    A POI or connector point projected onto the OSMnx pedestrian graph.

    Produced by PointPlacement and stored in guide_points (is_active=FALSE
    until manual or automated approval).

    snap_distance_m measures how far the original POI coordinates were from
    the nearest OSM pedestrian node.  Values exceeding seeder_max_snap_distance_m
    indicate the POI may be inside a building courtyard, on an island, or
    otherwise hard to reach on foot — is_approved is set to False for manual review.
    """
    point_type: str                       # 'poi' | 'connector'
    lat: float
    lng: float
    osm_node_id: int                      # Nearest OSM pedestrian node id
    name: str | None = None               # POI display name (None for connectors)
    google_place_id: str | None = None    # None for connectors
    source_poi: POICandidate | None = None  # Original POI (reserved for Step 5b KnowledgeCollector)
    snap_distance_m: float = 0.0          # Distance from original POI coords to snapped OSM node
    is_approved: bool = True              # False if snap_distance_m > threshold


# ============================================================================
# BuiltEdge — a directed pedestrian-graph edge computed by GraphBuilder
# ============================================================================

@dataclass
class BuiltEdge:
    """
    A directed pedestrian edge A→B computed via networkx shortest_path.

    distance_m and walk_seconds reflect the real pedestrian network path
    (NOT straight-line distance).  bearing_deg is the compass heading A→B.
    """
    from_osm_node: int
    to_osm_node: int
    distance_m: float              # Pedestrian walking distance (not straight-line)
    walk_seconds: int              # Estimated walking time
    bearing_deg: float             # Heading A→B in degrees (0=north, 90=east, …)


# ============================================================================
# PointPlacementResult — summary of Phase 2 for one zone
# ============================================================================

@dataclass
class PointPlacementResult:
    """
    Output of PointPlacement.place_points_in_zone() for one zone.

    placed_points contains both POI and connector points, all snapped to the
    OSM pedestrian network.  rejected_pois are POIs that nearest_node() could
    not project (e.g. outside the OSM graph coverage area).
    """
    zone_id: UUID
    placed_points: list[PlacedPoint]
    poi_count: int
    connector_count: int
    rejected_pois: list[tuple[POICandidate, str]]  # (poi, reason)
    graph_nodes_count: int         # Size of the OSMnx graph loaded for this zone
    graph_edges_count: int


# ============================================================================
# GraphBuildResult — summary of Phase 3 for one zone
# ============================================================================

@dataclass
class GraphBuildResult:
    """
    Output of GraphBuilder.build_graph_for_zone() for one zone.

    isolated_points contains OSM node IDs of points that had no reachable
    neighbors within seeder_max_neighbor_distance_m — these warrant manual
    inspection (the point may be on a disconnected graph component).
    """
    zone_id: UUID
    edges_built: int
    avg_neighbors_per_point: float
    isolated_points: list[int]     # OSM node IDs of points without reachable neighbors


# ============================================================================
# CollectedKnowledge — knowledge gathered for one guide_point
# ============================================================================

@dataclass
class CollectedKnowledge:
    """
    Knowledge gathered for a single guide_point by KnowledgeCollector.

    For POI points (card_type='poi'):
      - google_place_data, wikipedia_summary, wikidata_facts may all be None
        (e.g. a local café with no Wikipedia article — totally normal).
    For connector points (card_type='street_context'):
      - Only street_name is populated (from Google Reverse Geocoding).

    has_any_data=False means all sources returned empty — the card is still
    created in guide_knowledge_cards so Step 7 (ContentPipeline) can skip it.
    collection_errors records non-fatal per-source failures for observability.
    """
    point_id: UUID
    card_type: str                          # 'poi' | 'street_context'
    google_place_data: dict | None = None
    wikipedia_summary: str | None = None    # First paragraph of Wikipedia article
    wikipedia_url: str | None = None
    wikidata_entity_id: str | None = None   # Q-ID (e.g. "Q243") for cross-reference
    wikidata_facts: dict | None = None      # {property_name: value_or_list}
    street_name: str | None = None          # Populated for connector cards
    collection_errors: list = field(default_factory=list)  # Non-fatal error strings
    has_any_data: bool = False              # True if at least one source returned data


# ============================================================================
# KnowledgeCollectResult — summary of Phase 4 for one zone
# ============================================================================

@dataclass
class KnowledgeCollectResult:
    """
    Output of KnowledgeCollector.collect_for_zone() for one zone.

    failed_points contains (point_id, error_message) tuples for points that
    suffered a fatal crash (all sources failed or an unexpected exception).
    source_stats tracks how many points got data from each provider — useful
    for monitoring API health and coverage quality.
    """
    zone_id: UUID
    total_points: int
    cards_collected: int
    empty_cards: int                            # Cards where has_any_data=False
    failed_points: list = field(default_factory=list)    # [(UUID, str)] fatal crashes
    source_stats: dict = field(default_factory=dict)     # {'google_details': N, ...}
