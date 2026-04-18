"""
CitySeederOrchestrator — top-level coordinator for the City Seeder pipeline.

Step 4 implemented Phase 1 (Zone Discovery).
Step 5a implements Phases 2–3 (PointPlacement + GraphBuilder).
Phase 4 (KnowledgeCollector) is a Step 5b stub.

Pipeline overview:
  Phase 1 — Zone Discovery      ← Step 4 (ZoneDiscovery)
  Phase 2 — Point Placement     ← Step 5a (PointPlacement)
  Phase 3 — Graph Building      ← Step 5a (GraphBuilder)
  Phase 4 — Knowledge Collect.  ← Step 5b stub
  Phase 5 — Content Generation  ← Step 6+ (ContentPipeline)

Pedestrian-only principle
--------------------------
Zone Discovery (Phase 1) produces convex-hull polygons — these do NOT
represent walkable areas.  Phases 2–3 enforce pedestrian-only by:
  - Snapping every POI to the nearest OSM pedestrian node (PointPlacement).
  - Building graph edges only along real pedestrian paths (GraphBuilder).
  - Marking POIs with snap_distance_m > seeder_max_snap_distance_m as
    is_approved=False for manual review.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from src.guide.application.seeder.repository import SeederRepository
from src.guide.application.seeder.zone_discovery import ZoneDiscovery
from src.guide.application.seeder.types import MVP_CITY_CENTERS, SeedJobProgress

if TYPE_CHECKING:
    from src.guide.application.seeder.point_placement import PointPlacement
    from src.guide.application.seeder.graph_builder import GraphBuilder
    from src.guide.application.seeder.knowledge_collector import KnowledgeCollector

logger = logging.getLogger(__name__)


class CitySeederOrchestrator:
    """
    Coordinates all phases of the City Seeder for a single city.

    Dependencies are injected so each component can be mocked in tests.

    Args:
        repo:             SeederRepository for all DB reads/writes.
        zone_discovery:   ZoneDiscovery (wraps Google Places + DBSCAN).
        point_placement:  PointPlacement (OSMnx snap + connector generation).
                          Required to call continue_after_zone_approval().
        graph_builder:    GraphBuilder (pedestrian shortest-path edges).
                          Required to call continue_after_zone_approval().
    """

    def __init__(
        self,
        repo: SeederRepository,
        zone_discovery: ZoneDiscovery,
        point_placement: PointPlacement | None = None,
        graph_builder: GraphBuilder | None = None,
        knowledge_collector: KnowledgeCollector | None = None,
    ) -> None:
        self._repo = repo
        self._zone_discovery = zone_discovery
        self._point_placement = point_placement
        self._graph_builder = graph_builder
        self._knowledge_collector = knowledge_collector

    # =========================================================================
    # Phase 1 — Zone Discovery  (Step 4)
    # =========================================================================

    async def start_seed(
        self,
        city_name: str,
        country: str | None = None,
    ) -> UUID:
        """
        Start Zone Discovery for a city and return the job_id.

        Idempotent: if an active job already exists for the city, its job_id is
        returned without creating a new one.

        Workflow:
          1. Guard: return existing active job if present.
          2. Create guide_seed_jobs record (status=running, phase=zone_discovery).
          3. Resolve city centre (Google Geocoding → MVP_CITY_CENTERS fallback).
          4. Upsert guide_cities record.
          5. ZoneDiscovery.discover() → list[ProposedZone].
          6. Basic validity filter (lat/lng range, poi_count >= 1).
          7. SeederRepository.bulk_insert_zones() — is_approved=FALSE.
          8. Update job: status=awaiting_zone_approval.

        Phases 2–4 are triggered by continue_after_zone_approval().

        Returns:
            UUID of the created (or reused) seed job.
        """
        # Guard: reuse active job
        active_job = await self._repo.get_active_job_for_city(city_name)
        if active_job is not None:
            logger.info(
                "Orchestrator: active job %s already exists for city=%s — reusing",
                active_job.id,
                city_name,
            )
            return active_job.id

        # Create job
        job = await self._repo.create_seed_job(city_name)
        job_id = job.id
        logger.info("Orchestrator: created seed job %s for city=%s", job_id, city_name)

        progress = SeedJobProgress(phase="zone_discovery")

        try:
            # Resolve city centre
            center_lat, center_lng = await self._resolve_city_center(city_name, country)

            # Upsert city record
            city = await self._repo.upsert_city(city_name, country, center_lat, center_lng)
            await self._repo.update_seed_job(
                job_id,
                city_id=city.id,
                progress_json=progress.to_dict(),
            )

            # Zone Discovery
            proposed_zones = await self._zone_discovery.discover(
                city_name, center_lat, center_lng
            )
            progress.zones_proposed = len(proposed_zones)
            logger.info(
                "Orchestrator: %d zones proposed for %s", len(proposed_zones), city_name
            )

            # Basic validity filter (full pedestrian-network validation in Phase 2)
            valid_zones = self._filter_obviously_invalid_zones(proposed_zones)
            if len(valid_zones) < len(proposed_zones):
                logger.warning(
                    "Orchestrator: %d zones dropped by basic validity check "
                    "(full pedestrian-network validation happens in Phase 2 PointPlacement)",
                    len(proposed_zones) - len(valid_zones),
                )

            # Persist zones (is_approved=FALSE — awaiting admin review)
            if valid_zones:
                await self._repo.bulk_insert_zones(city.id, valid_zones)

            # Update job to awaiting_zone_approval
            progress.phase = "awaiting_approval"
            await self._repo.update_seed_job(
                job_id,
                status="awaiting_zone_approval",
                current_phase="awaiting_zone_approval",
                progress_json=progress.to_dict(),
            )
            logger.info(
                "Orchestrator: job %s → awaiting_zone_approval (%d zones pending admin review)",
                job_id,
                len(valid_zones),
            )

        except Exception as exc:
            logger.exception("Orchestrator: seed job %s failed: %s", job_id, exc)
            progress.error = str(exc)
            progress.phase = "failed"
            await self._repo.update_seed_job(
                job_id,
                status="failed",
                error_message=str(exc),
                progress_json=progress.to_dict(),
                completed=True,
            )
            raise

        return job_id

    # =========================================================================
    # Phase 2–3 — Point Placement + Graph Building  (Step 5a)
    # =========================================================================

    async def continue_after_zone_approval(self, job_id: UUID) -> None:
        """
        Resume seeding after an admin has approved zones via the admin API.

        Runs Phase 2 (PointPlacement), Phase 3 (GraphBuilder), and — when
        knowledge_collector is injected — Phase 4 (KnowledgeCollector) for
        every approved zone in the job's city.

        Workflow:
          1. Load job → verify city_id is set.
          2. Verify point_placement and graph_builder are injected.
          3. Load all approved zones with their boundary WKT (PostGIS ST_AsText).
          4. Update job phase → 'placing_points'.
          5. For each approved zone:
             a. Re-fetch tourist POIs from Google Places (inside zone polygon).
             b. PointPlacement.place_points_in_zone() → placed_points + OSMnx graph G.
             c. bulk_insert_points() → GuidePoint rows in DB.
             d. Build osm_node_id → UUID map for edge FK resolution.
             e. GraphBuilder.build_graph_for_zone(G) → built_edges.
             f. bulk_insert_edges() → GuideEdge rows in DB.
             g. Update zone.point_count.
             h. [Phase 4] If knowledge_collector injected:
                  update phase → 'collecting_knowledge'
                  KnowledgeCollector.collect_for_zone() → knowledge cards upserted.
                  Errors are logged but DO NOT stop the job.
          6. If knowledge_collector injected → job status='complete'.
             Otherwise → job status='collecting_knowledge' (Step 5b pending).

        Raises:
            RuntimeError: if point_placement or graph_builder not injected, or
                          if job/city not found, or if no approved zones exist.
            Any other exception: job is marked failed and the exception re-raised.
        """
        if self._point_placement is None or self._graph_builder is None:
            raise RuntimeError(
                "PointPlacement and GraphBuilder must be injected to run Phase 2–3. "
                "Instantiate the orchestrator with point_placement= and graph_builder= args."
            )

        # Load job
        job = await self._repo.get_seed_job(job_id)
        if job is None:
            raise RuntimeError(f"Seed job {job_id} not found.")

        if job.city_id is None:
            raise RuntimeError(
                f"Job {job_id} has no city_id — Zone Discovery may not have completed. "
                "Run start_seed() first."
            )

        # Load approved zones with boundary metadata
        zone_data_list = await self._repo.get_approved_zones_with_boundaries(job.city_id)
        if not zone_data_list:
            raise RuntimeError(
                f"No approved zones found for city_id={job.city_id}. "
                "Approve zones via admin API before calling continue_after_zone_approval()."
            )

        progress = SeedJobProgress.from_dict(job.progress_json or {})
        progress.phase = "placing_points"

        try:
            await self._repo.update_seed_job(
                job_id,
                current_phase="placing_points",
                progress_json=progress.to_dict(),
            )

            for zone_data in zone_data_list:
                zone_id: UUID = zone_data["id"]
                zone_name: str = zone_data["name"]
                boundary_wkt: str = zone_data["boundary_wkt"]
                centroid_lat: float = zone_data["centroid_lat"]
                centroid_lng: float = zone_data["centroid_lng"]

                logger.info(
                    "Orchestrator: processing zone '%s' (%s)", zone_name, zone_id
                )

                # Re-fetch POIs within the zone's search radius (Variant A: fresh data)
                radius_m = int(self._zone_radius_from_polygon(boundary_wkt))
                pois_raw = await self._zone_discovery._fetch_tourist_pois(
                    centroid_lat, centroid_lng, radius_m
                )

                # Filter to POIs that fall inside the zone polygon
                from shapely import wkt as shapely_wkt
                from shapely.geometry import Point as ShapelyPoint

                polygon = shapely_wkt.loads(boundary_wkt)
                pois_in_zone = [
                    p for p in pois_raw
                    if polygon.contains(ShapelyPoint(p.lng, p.lat))
                ]
                logger.info(
                    "Orchestrator: zone '%s' — %d POIs in zone (from %d fetched)",
                    zone_name,
                    len(pois_in_zone),
                    len(pois_raw),
                )

                # Phase 2: snap POIs to OSMnx pedestrian graph + generate connectors
                placement_result, G = await self._point_placement.place_points_in_zone(
                    zone_id, boundary_wkt, pois_in_zone
                )

                # Insert points into DB
                inserted_points = await self._repo.bulk_insert_points(
                    zone_id, placement_result.placed_points
                )
                await self._repo.update_zone_point_count(zone_id, len(inserted_points))

                # Build osm_node_id → UUID map for edge FK resolution
                node_to_uuid: dict[int, UUID] = {
                    p.osm_node_id: p.id
                    for p in inserted_points
                    if p.osm_node_id is not None
                }

                # Phase 3: build pedestrian-graph edges via networkx shortest-path
                graph_result, built_edges = await self._graph_builder.build_graph_for_zone(
                    zone_id, placement_result.placed_points, G
                )
                await self._repo.bulk_insert_edges(node_to_uuid, built_edges)

                # Accumulate progress
                progress.points_placed += (
                    placement_result.poi_count + placement_result.connector_count
                )
                progress.edges_built += graph_result.edges_built

                logger.info(
                    "Orchestrator: zone '%s' Phase 2+3 done — %d points, %d edges",
                    zone_name,
                    placement_result.poi_count + placement_result.connector_count,
                    graph_result.edges_built,
                )

                # Phase 4: Knowledge Collection (Step 5b)
                if self._knowledge_collector is not None:
                    await self._repo.update_seed_job(
                        job_id,
                        current_phase="collecting_knowledge",
                        progress_json=progress.to_dict(),
                    )
                    try:
                        knowledge_result = await self._knowledge_collector.collect_for_zone(
                            zone_id, language="en"
                        )
                        progress.cards_collected += knowledge_result.cards_collected
                        if knowledge_result.failed_points:
                            logger.warning(
                                "Orchestrator: zone '%s' — %d points failed knowledge "
                                "collection (continuing with next zone)",
                                zone_name,
                                len(knowledge_result.failed_points),
                            )
                        logger.info(
                            "Orchestrator: zone '%s' Phase 4 done — %d cards collected",
                            zone_name,
                            knowledge_result.cards_collected,
                        )
                    except Exception as exc:
                        logger.warning(
                            "Orchestrator: knowledge collection failed for zone '%s': %s "
                            "— continuing with next zone",
                            zone_name,
                            exc,
                        )

            # All zones processed
            if self._knowledge_collector is not None:
                progress.phase = "complete"
                await self._repo.update_seed_job(
                    job_id,
                    status="complete",
                    current_phase="complete",
                    progress_json=progress.to_dict(),
                    completed=True,
                )
                logger.info(
                    "Orchestrator: job %s → complete "
                    "(%d total points, %d total edges, %d knowledge cards).",
                    job_id,
                    progress.points_placed,
                    progress.edges_built,
                    progress.cards_collected,
                )
            else:
                # KnowledgeCollector not injected — Step 5b stub behaviour preserved
                progress.phase = "collecting_knowledge"
                await self._repo.update_seed_job(
                    job_id,
                    status="collecting_knowledge",
                    current_phase="collecting_knowledge",
                    progress_json=progress.to_dict(),
                )
                logger.info(
                    "Orchestrator: job %s → collecting_knowledge "
                    "(%d total points, %d total edges). "
                    "Inject knowledge_collector= to run Phase 4.",
                    job_id,
                    progress.points_placed,
                    progress.edges_built,
                )

        except Exception as exc:
            logger.exception(
                "Orchestrator: Phase 2–3 failed for job %s: %s", job_id, exc
            )
            progress.error = str(exc)
            progress.phase = "failed"
            await self._repo.update_seed_job(
                job_id,
                status="failed",
                error_message=str(exc),
                progress_json=progress.to_dict(),
                completed=True,
            )
            raise

    # =========================================================================
    # Internal helpers
    # =========================================================================

    async def _resolve_city_center(
        self,
        city_name: str,
        country: str | None,
    ) -> tuple[float, float]:
        """
        Return (lat, lng) for the city centre.

        Strategy:
          1. Try Google Geocoding API (uses existing GeocodingService).
          2. Fall back to MVP_CITY_CENTERS dict.
          3. Raise if neither works.
        """
        query = f"{city_name}, {country}" if country else city_name

        try:
            from src.infrastructure.geocoding import get_geocoding_service
            svc = get_geocoding_service()
            result = await svc.geocode_city(query)
            if result is not None:
                logger.info(
                    "Orchestrator: geocoded '%s' → (%.4f, %.4f)",
                    query,
                    result.lat,
                    result.lon,
                )
                return result.lat, result.lon
        except Exception as exc:
            logger.warning("Orchestrator: geocoding failed for '%s': %s", query, exc)

        # Fallback: MVP_CITY_CENTERS
        key = city_name.lower().strip()
        if key in MVP_CITY_CENTERS:
            lat, lng = MVP_CITY_CENTERS[key]
            logger.warning(
                "Orchestrator: using hardcoded MVP centre for '%s' → (%.4f, %.4f)",
                city_name,
                lat,
                lng,
            )
            return lat, lng

        raise RuntimeError(
            f"Cannot resolve city centre for '{city_name}'. "
            "Configure GOOGLE_MAPS_API_KEY or add to MVP_CITY_CENTERS in types.py."
        )

    @staticmethod
    def _filter_obviously_invalid_zones(zones: list) -> list:
        """
        Basic sanity filter on proposed zones before persisting.

        Current checks (lightweight — no OSM network call):
          - Zone centroid must have realistic lat/lng values.
          - POI count must be >= 1.

        Full pedestrian-network reachability check is enforced in Phase 2
        (PointPlacement marks POIs as is_approved=False when they cannot be
        snapped to any walkable OSM node within seeder_max_snap_distance_m).
        """
        valid = []
        for zone in zones:
            if not (-90.0 <= zone.centroid_lat <= 90.0):
                logger.warning(
                    "Dropped zone '%s': invalid centroid lat=%s", zone.name, zone.centroid_lat
                )
                continue
            if not (-180.0 <= zone.centroid_lng <= 180.0):
                logger.warning(
                    "Dropped zone '%s': invalid centroid lng=%s", zone.name, zone.centroid_lng
                )
                continue
            if zone.poi_count < 1:
                logger.warning("Dropped zone '%s': poi_count=0", zone.name)
                continue
            valid.append(zone)
        return valid

    @staticmethod
    def _zone_radius_from_polygon(boundary_wkt: str) -> float:
        """
        Estimate search radius for POI re-fetch from zone boundary WKT.

        Computes the max degree-distance from the centroid to any boundary
        vertex, converts to metres (~111 km/°), and adds a 50% buffer.

        Used in continue_after_zone_approval() to set the radius for
        ZoneDiscovery._fetch_tourist_pois() when re-fetching POIs inside
        an approved zone.
        """
        from shapely import wkt as shapely_wkt

        polygon = shapely_wkt.loads(boundary_wkt)
        centroid = polygon.centroid
        coords = list(polygon.exterior.coords)
        max_deg = max(
            ((lng - centroid.x) ** 2 + (lat - centroid.y) ** 2) ** 0.5
            for lng, lat in coords
        )
        return max_deg * 111_000 * 1.5  # degrees → metres, +50% buffer
