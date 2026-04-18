"""
SeederRepository — thin CRUD layer for guide_cities, guide_zones, guide_seed_jobs.

This class contains NO business logic — only database reads/writes.
All decisions about what to persist and when belong to CitySeederOrchestrator.

PostGIS geometry note
---------------------
guide_cities.center and guide_zones.boundary are GeoAlchemy2 Geometry columns.
We insert them via SQLAlchemy text() with ST_GeomFromText(wkt, 4326) rather
than relying on GeoAlchemy2's WKBElement, which requires a PostGIS connection
to encode.  This keeps the repository compatible with both live and test SQLite
setups (though full ST_* functions require PostgreSQL + PostGIS).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.guide.domain.models import GuideCity, GuideEdge, GuideKnowledgeCard, GuidePoint, GuideZone, GuideSeedJob
from src.guide.application.seeder.types import BuiltEdge, CollectedKnowledge, PlacedPoint, ProposedZone

logger = logging.getLogger(__name__)


class SeederRepository:
    """CRUD for the City Seeder database tables."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # =========================================================================
    # guide_seed_jobs
    # =========================================================================

    async def create_seed_job(self, city_name: str) -> GuideSeedJob:
        """Insert a new seed job record with status='running'."""
        job = GuideSeedJob(
            id=uuid.uuid4(),
            city_name=city_name,
            status="running",
            current_phase="zone_discovery",
            progress_json={"phase": "zone_discovery"},
            created_at=datetime.now(timezone.utc),
        )
        self._db.add(job)
        await self._db.flush()  # assigns id without committing
        logger.debug("SeederRepository: created seed job %s for city=%s", job.id, city_name)
        return job

    async def update_seed_job(
        self,
        job_id: UUID,
        *,
        status: str | None = None,
        current_phase: str | None = None,
        progress_json: dict[str, Any] | None = None,
        error_message: str | None = None,
        city_id: UUID | None = None,
        completed: bool = False,
    ) -> None:
        """
        Partially update a seed job.

        Only non-None kwargs are written to avoid accidental overwrites.
        Pass completed=True to set completed_at = now().
        """
        values: dict[str, Any] = {}
        if status is not None:
            values["status"] = status
        if current_phase is not None:
            values["current_phase"] = current_phase
        if progress_json is not None:
            values["progress_json"] = progress_json
        if error_message is not None:
            values["error_message"] = error_message
        if city_id is not None:
            values["city_id"] = city_id
        if completed:
            values["completed_at"] = datetime.now(timezone.utc)

        if not values:
            return

        stmt = (
            update(GuideSeedJob)
            .where(GuideSeedJob.id == job_id)
            .values(**values)
        )
        await self._db.execute(stmt)
        await self._db.flush()

    async def get_seed_job(self, job_id: UUID) -> GuideSeedJob | None:
        result = await self._db.execute(
            select(GuideSeedJob).where(GuideSeedJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_active_job_for_city(self, city_name: str) -> GuideSeedJob | None:
        """
        Return a job that is still in progress for the given city, if any.

        'Active' means status in ('running', 'awaiting_zone_approval').
        """
        result = await self._db.execute(
            select(GuideSeedJob).where(
                GuideSeedJob.city_name == city_name,
                GuideSeedJob.status.in_(["running", "awaiting_zone_approval"]),
            )
        )
        return result.scalar_one_or_none()

    # =========================================================================
    # guide_cities
    # =========================================================================

    async def upsert_city(
        self,
        name: str,
        country: str | None,
        center_lat: float,
        center_lng: float,
    ) -> GuideCity:
        """
        Insert a new city or return the existing one by name.

        center is stored as PostGIS POINT via ST_GeomFromText.
        If a city with the same name already exists we return it unchanged —
        no merge/update is performed on coordinates (city centres don't move).
        """
        existing = await self.get_city_by_name(name)
        if existing is not None:
            logger.debug("SeederRepository: city '%s' already exists (id=%s)", name, existing.id)
            return existing

        wkt_point = f"POINT({center_lng} {center_lat})"

        # Insert via raw SQL to use ST_GeomFromText for the geometry column
        city_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        await self._db.execute(
            text(
                "INSERT INTO guide_cities "
                "(id, name, country, center, timezone, is_active, created_at) "
                "VALUES (:id, :name, :country, ST_GeomFromText(:wkt, 4326), 'UTC', FALSE, :now)"
            ),
            {
                "id": str(city_id),
                "name": name,
                "country": country or "",
                "wkt": wkt_point,
                "now": now,
            },
        )
        await self._db.flush()

        # Re-fetch to get the ORM instance populated
        city = await self.get_city_by_name(name)
        if city is None:
            raise RuntimeError(f"City insert succeeded but re-fetch returned None for name='{name}'")

        logger.debug("SeederRepository: inserted city '%s' (id=%s)", name, city.id)
        return city

    async def get_city_by_name(self, name: str) -> GuideCity | None:
        result = await self._db.execute(
            select(GuideCity).where(GuideCity.name == name)
        )
        return result.scalar_one_or_none()

    # =========================================================================
    # guide_zones
    # =========================================================================

    async def bulk_insert_zones(
        self,
        city_id: UUID,
        zones: list[ProposedZone],
    ) -> list[GuideZone]:
        """
        Insert all proposed zones with is_approved=FALSE.

        Uses ST_GeomFromText(boundary_wkt, 4326) for PostGIS POLYGON columns.
        Returns the newly created GuideZone ORM instances.
        """
        created: list[GuideZone] = []
        now = datetime.now(timezone.utc)

        for zone in zones:
            zone_id = uuid.uuid4()

            await self._db.execute(
                text(
                    "INSERT INTO guide_zones "
                    "(id, city_id, name, theme, boundary, poi_count, "
                    " point_count, is_approved, is_active, created_at) "
                    "VALUES (:id, :city_id, :name, :theme, "
                    "        ST_GeomFromText(:wkt, 4326), :poi_count, "
                    "        0, FALSE, FALSE, :now)"
                ),
                {
                    "id": str(zone_id),
                    "city_id": str(city_id),
                    "name": zone.name,
                    "theme": zone.theme_hint,
                    "wkt": zone.boundary_wkt,
                    "poi_count": zone.poi_count,
                    "now": now,
                },
            )

        await self._db.flush()

        # Re-fetch all unapproved zones for this city inserted just now
        result = await self._db.execute(
            select(GuideZone).where(
                GuideZone.city_id == city_id,
                GuideZone.is_approved.is_(False),
            )
        )
        created = list(result.scalars().all())
        logger.debug(
            "SeederRepository: inserted %d zones for city_id=%s", len(created), city_id
        )
        return created

    async def get_zones_by_city(
        self,
        city_id: UUID,
        *,
        only_approved: bool = False,
    ) -> list[GuideZone]:
        stmt = select(GuideZone).where(GuideZone.city_id == city_id)
        if only_approved:
            stmt = stmt.where(GuideZone.is_approved.is_(True))
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_approved_zones_with_boundaries(
        self,
        city_id: UUID,
    ) -> list[dict]:
        """
        Return approved zones for a city with PostGIS-derived boundary metadata.

        Returns a list of dicts with keys:
          id (UUID), name, theme, poi_count, boundary_wkt (str),
          centroid_lat (float), centroid_lng (float).

        Used by CitySeederOrchestrator.continue_after_zone_approval() to:
          - Get zone polygons for PointPlacement / OSMnx graph loading
          - Get centroids for re-fetching POIs from Google Places
        """
        result = await self._db.execute(
            text(
                "SELECT id, name, theme, poi_count, "
                "ST_AsText(boundary) AS boundary_wkt, "
                "ST_Y(ST_Centroid(boundary)) AS centroid_lat, "
                "ST_X(ST_Centroid(boundary)) AS centroid_lng "
                "FROM guide_zones "
                "WHERE city_id = :city_id AND is_approved = TRUE"
            ),
            {"city_id": str(city_id)},
        )
        rows = result.mappings().fetchall()
        return [
            {
                "id": UUID(str(row["id"])),
                "name": str(row["name"]),
                "theme": row["theme"],
                "poi_count": int(row["poi_count"]) if row["poi_count"] else 0,
                "boundary_wkt": str(row["boundary_wkt"]),
                "centroid_lat": float(row["centroid_lat"]),
                "centroid_lng": float(row["centroid_lng"]),
            }
            for row in rows
        ]

    async def approve_zone(
        self,
        zone_id: UUID,
        *,
        adjusted_boundary_wkt: str | None = None,
    ) -> GuideZone:
        """
        Mark a zone as approved.

        If adjusted_boundary_wkt is provided the boundary polygon is replaced
        (admin may have adjusted it in the review UI).
        """
        now = datetime.now(timezone.utc)

        if adjusted_boundary_wkt:
            await self._db.execute(
                text(
                    "UPDATE guide_zones "
                    "SET is_approved = TRUE, approved_at = :now, "
                    "    boundary = ST_GeomFromText(:wkt, 4326) "
                    "WHERE id = :id"
                ),
                {"id": str(zone_id), "now": now, "wkt": adjusted_boundary_wkt},
            )
        else:
            stmt = (
                update(GuideZone)
                .where(GuideZone.id == zone_id)
                .values(is_approved=True, approved_at=now)
            )
            await self._db.execute(stmt)

        await self._db.flush()

        result = await self._db.execute(
            select(GuideZone).where(GuideZone.id == zone_id)
        )
        zone = result.scalar_one_or_none()
        if zone is None:
            raise ValueError(f"Zone {zone_id} not found after approval update")
        return zone

    # =========================================================================
    # guide_points  (Phase 2 — PointPlacement)
    # =========================================================================

    async def bulk_insert_points(
        self,
        zone_id: UUID,
        placed_points: list[PlacedPoint],
    ) -> list[GuidePoint]:
        """
        Insert POI and connector points for a zone, ignoring conflicts.

        Uses ON CONFLICT DO NOTHING against the composite unique constraints
        (zone_id, osm_node_id) and (zone_id, google_place_id) — this makes
        the operation fully idempotent for re-runs.

        Returns all GuidePoint rows currently in the zone (including any that
        were already present from a previous run).
        """
        now = datetime.now(timezone.utc)

        for pp in placed_points:
            point_id = uuid.uuid4()
            await self._db.execute(
                text(
                    "INSERT INTO guide_points "
                    "(id, zone_id, location, trigger_radius_m, point_type, name, "
                    " google_place_id, osm_node_id, is_approved, is_active, created_at) "
                    "VALUES (:id, :zone_id, "
                    "        ST_SetSRID(ST_MakePoint(:lng, :lat), 4326), "
                    "        :trigger_radius_m, :point_type, :name, "
                    "        :google_place_id, :osm_node_id, :is_approved, FALSE, :now) "
                    "ON CONFLICT DO NOTHING"
                ),
                {
                    "id": str(point_id),
                    "zone_id": str(zone_id),
                    "lng": pp.lng,
                    "lat": pp.lat,
                    "trigger_radius_m": 25,
                    "point_type": pp.point_type,
                    "name": pp.name,
                    "google_place_id": pp.google_place_id,
                    "osm_node_id": pp.osm_node_id,
                    "is_approved": pp.is_approved,
                    "now": now,
                },
            )

        await self._db.flush()

        # Re-fetch all points for this zone (may include pre-existing rows)
        result = await self._db.execute(
            select(GuidePoint).where(GuidePoint.zone_id == zone_id)
        )
        rows = list(result.scalars().all())
        logger.debug(
            "SeederRepository: %d points in zone %s after bulk insert",
            len(rows),
            zone_id,
        )
        return rows

    async def get_points_by_zone(self, zone_id: UUID) -> list[GuidePoint]:
        """Return all guide_points for a zone."""
        result = await self._db.execute(
            select(GuidePoint).where(GuidePoint.zone_id == zone_id)
        )
        return list(result.scalars().all())

    async def update_zone_point_count(self, zone_id: UUID, count: int) -> None:
        """Update guide_zones.point_count after points are inserted."""
        stmt = (
            update(GuideZone)
            .where(GuideZone.id == zone_id)
            .values(point_count=count)
        )
        await self._db.execute(stmt)
        await self._db.flush()

    # =========================================================================
    # guide_edges  (Phase 3 — GraphBuilder)
    # =========================================================================

    async def bulk_insert_edges(
        self,
        from_point_map: dict[int, UUID],
        built_edges: list[BuiltEdge],
    ) -> int:
        """
        Insert directed pedestrian edges, ignoring conflicts.

        Args:
            from_point_map: mapping from osm_node_id → guide_points.id (UUID).
                            Built by the orchestrator after bulk_insert_points().
            built_edges:    BuiltEdge list from GraphBuilder.build_graph_for_zone().

        Returns:
            Number of INSERT statements executed (including those silently ignored
            due to ON CONFLICT DO NOTHING).

        Idempotent: ON CONFLICT (from_point_id, to_point_id) DO NOTHING ensures
        repeated runs don't create duplicate edges.
        """
        now = datetime.now(timezone.utc)
        attempted = 0

        for edge in built_edges:
            from_id = from_point_map.get(edge.from_osm_node)
            to_id = from_point_map.get(edge.to_osm_node)

            if from_id is None or to_id is None:
                logger.warning(
                    "SeederRepository: edge %d→%d skipped — osm_node not in point map",
                    edge.from_osm_node,
                    edge.to_osm_node,
                )
                continue

            edge_id = uuid.uuid4()
            await self._db.execute(
                text(
                    "INSERT INTO guide_edges "
                    "(id, from_point_id, to_point_id, distance_m, walk_seconds, "
                    " bearing_deg, is_active) "
                    "VALUES (:id, :from_id, :to_id, :distance_m, :walk_seconds, "
                    "        :bearing_deg, TRUE) "
                    "ON CONFLICT (from_point_id, to_point_id) DO NOTHING"
                ),
                {
                    "id": str(edge_id),
                    "from_id": str(from_id),
                    "to_id": str(to_id),
                    "distance_m": edge.distance_m,
                    "walk_seconds": edge.walk_seconds,
                    "bearing_deg": edge.bearing_deg,
                },
            )
            attempted += 1

        await self._db.flush()
        logger.debug(
            "SeederRepository: %d edge inserts attempted (conflicts silently ignored)",
            attempted,
        )
        return attempted

    # =========================================================================
    # guide_knowledge_cards  (Phase 4 — KnowledgeCollector)
    # =========================================================================

    async def bulk_upsert_knowledge_cards(
        self,
        collected: list[CollectedKnowledge],
    ) -> int:
        """
        Upsert knowledge cards for a list of guide_points.

        Uses PostgreSQL INSERT … ON CONFLICT (point_id) DO UPDATE so that:
        - A missing card is created from scratch.
        - An existing card is updated only for fields that are non-None in the
          new CollectedKnowledge — existing data is never overwritten with None.
        - enriched_at is always updated to NOW() so the freshness is trackable.

        UNIQUE constraint on guide_knowledge_cards.point_id is confirmed in
        migration 009 (unique=True on the column).

        Returns:
            Number of rows processed (each row produces one INSERT or UPDATE).
        """
        now = datetime.now(timezone.utc)
        processed = 0

        for item in collected:
            # Columns always written
            insert_values: dict[str, Any] = {
                "id": uuid.uuid4(),
                "point_id": item.point_id,
                "card_type": item.card_type,
                "enriched_at": now,
            }

            # ON CONFLICT update: only columns that are non-None in this batch
            update_values: dict[str, Any] = {"enriched_at": now}

            if item.google_place_data is not None:
                insert_values["google_place_data"] = item.google_place_data
                update_values["google_place_data"] = item.google_place_data

            if item.wikipedia_summary is not None:
                insert_values["wikipedia_summary"] = item.wikipedia_summary
                update_values["wikipedia_summary"] = item.wikipedia_summary

            if item.wikidata_facts is not None:
                insert_values["wikidata_facts"] = item.wikidata_facts
                update_values["wikidata_facts"] = item.wikidata_facts

            if item.street_name is not None:
                insert_values["street_name"] = item.street_name
                update_values["street_name"] = item.street_name

            stmt = pg_insert(GuideKnowledgeCard).values(**insert_values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["point_id"],
                set_=update_values,
            )
            await self._db.execute(stmt)
            processed += 1

        await self._db.flush()
        logger.debug(
            "SeederRepository: bulk_upsert_knowledge_cards: %d rows processed",
            processed,
        )
        return processed
