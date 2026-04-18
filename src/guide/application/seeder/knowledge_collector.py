"""
KnowledgeCollector — Phase 4 of the City Seeder pipeline.

Collects raw knowledge for every guide_point in a zone from up to four sources:
  • Google Place Details    — for POI points (paid, ~1 API call per POI)
  • Wikipedia REST API      — for POI points (free, best-effort)
  • Wikidata SPARQL         — for POI points only if Wikipedia returned a wikibase_item
  • Google Reverse Geocode  — for connector points (paid, ~1 call per connector)

Graceful-degradation principle
--------------------------------
Missing data from any source is NORMAL, not an error. A local café may have
no Wikipedia article; a connector node on a side street may not reverse-geocode
to a named route. Cards are always created — even with all-None fields — so
the Content Pipeline (Step 7) can skip them or handle them appropriately.

The ONLY fatal case is an unexpected Python exception for a point. Those
points are captured in KnowledgeCollectResult.failed_points and the job
continues with the remaining points.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, TYPE_CHECKING
from uuid import UUID

from src.guide.application.seeder.types import (
    CollectedKnowledge,
    KnowledgeCollectResult,
)
from src.config import settings

if TYPE_CHECKING:
    from src.guide.application.seeder.repository import SeederRepository
    from src.guide.domain.models import GuidePoint
    from src.guide.infrastructure.google_places_client import GuideGooglePlacesClient
    from src.guide.infrastructure.wikipedia_client import WikipediaClient, WikipediaSummary
    from src.guide.infrastructure.wikidata_client import WikidataClient

logger = logging.getLogger(__name__)


class KnowledgeCollector:
    """
    Collects guide_knowledge_cards for all guide_points in a zone.

    Dependencies are injected so each component can be mocked in tests.

    Args:
        repo:           SeederRepository for DB reads/writes.
        google_places:  GuideGooglePlacesClient for Place Details + Reverse Geocode.
        wikipedia:      WikipediaClient for article summaries.
        wikidata:       WikidataClient for structured entity facts.
        max_parallel:   Semaphore limit — max concurrent point-level tasks.
    """

    def __init__(
        self,
        repo: SeederRepository,
        google_places: GuideGooglePlacesClient,
        wikipedia: WikipediaClient,
        wikidata: WikidataClient,
        max_parallel: int | None = None,
    ) -> None:
        self._repo = repo
        self._google_places = google_places
        self._wikipedia = wikipedia
        self._wikidata = wikidata
        self._max_parallel = (
            max_parallel
            if max_parallel is not None
            else settings.knowledge_collector_max_parallel
        )

    # =========================================================================
    # Public API
    # =========================================================================

    async def collect_for_zone(
        self,
        zone_id: UUID,
        language: str = "en",
    ) -> KnowledgeCollectResult:
        """
        Collect knowledge for every guide_point in the zone.

        Workflow:
          1. Load all points for the zone via repo.get_points_by_zone().
          2. Process points in parallel (semaphore limits concurrency).
          3. Upsert all collected knowledge cards in one batch call.
          4. Return aggregated KnowledgeCollectResult.

        Per-point errors are non-fatal: failures land in result.failed_points
        and processing continues for the remaining points.
        """
        points: list[GuidePoint] = await self._repo.get_points_by_zone(zone_id)
        logger.info(
            "KnowledgeCollector: processing %d points for zone %s", len(points), zone_id
        )

        semaphore = asyncio.Semaphore(self._max_parallel)
        collected: list[CollectedKnowledge] = []
        failed: list[tuple[UUID, str]] = []

        async def process_point(point: GuidePoint) -> None:
            async with semaphore:
                try:
                    if point.point_type == "poi":
                        knowledge = await self._collect_poi_knowledge(point, language)
                    else:
                        knowledge = await self._collect_connector_knowledge(point)
                    collected.append(knowledge)
                except Exception as exc:
                    logger.exception(
                        "KnowledgeCollector: fatal error for point %s: %s", point.id, exc
                    )
                    failed.append((point.id, str(exc)))

        await asyncio.gather(*[process_point(p) for p in points])

        # Persist all collected knowledge cards in one batch
        if collected:
            upserted = await self._repo.bulk_upsert_knowledge_cards(collected)
            logger.info(
                "KnowledgeCollector: zone %s — %d cards upserted, %d fatal failures",
                zone_id, upserted, len(failed),
            )

        source_stats = {
            "google_details": sum(1 for k in collected if k.google_place_data is not None),
            "wikipedia":      sum(1 for k in collected if k.wikipedia_summary is not None),
            "wikidata":       sum(1 for k in collected if k.wikidata_facts is not None),
            "street_name":    sum(1 for k in collected if k.street_name is not None),
        }
        cards_collected = len(collected)
        empty_cards = sum(1 for k in collected if not k.has_any_data)

        return KnowledgeCollectResult(
            zone_id=zone_id,
            total_points=len(points),
            cards_collected=cards_collected,
            empty_cards=empty_cards,
            failed_points=failed,
            source_stats=source_stats,
        )

    # =========================================================================
    # Per-point collection
    # =========================================================================

    async def _collect_poi_knowledge(
        self,
        point: GuidePoint,
        language: str,
    ) -> CollectedKnowledge:
        """
        Collect from Google Place Details + Wikipedia (parallel),
        then Wikidata (sequential — depends on Wikipedia wikibase_item).
        Each source is wrapped in its own try/except to preserve the others.
        """
        lat, lng = self._extract_coords(point)
        name: str = point.name or ""
        errors: list[str] = []

        # Google Place Details and Wikipedia run in parallel (independent)
        google_task = asyncio.create_task(
            self._safe_google_details(point, errors)
        )
        wiki_task = asyncio.create_task(
            self._safe_wikipedia(name, language, lat, lng, errors)
        )
        google_data, wiki_summary = await asyncio.gather(google_task, wiki_task)

        # Wikidata depends on Wikipedia's wikibase_item — runs sequentially
        wikidata_facts: dict[str, Any] | None = None
        wikidata_entity_id: str | None = None
        if wiki_summary is not None and wiki_summary.wikibase_item:
            wikidata_entity_id = wiki_summary.wikibase_item
            try:
                wikidata_facts = await self._wikidata.fetch_entity_facts(
                    wiki_summary.wikibase_item, language=language
                )
            except Exception as exc:
                msg = f"Wikidata error for {wiki_summary.wikibase_item}: {exc}"
                errors.append(msg)
                logger.warning("KnowledgeCollector: %s", msg)

        has_any_data = (
            google_data is not None
            or wiki_summary is not None
            or wikidata_facts is not None
        )

        return CollectedKnowledge(
            point_id=point.id,
            card_type="poi",
            google_place_data=google_data,
            wikipedia_summary=wiki_summary.extract if wiki_summary else None,
            wikipedia_url=wiki_summary.page_url if wiki_summary else None,
            wikidata_entity_id=wikidata_entity_id,
            wikidata_facts=wikidata_facts,
            collection_errors=errors,
            has_any_data=has_any_data,
        )

    async def _collect_connector_knowledge(
        self,
        point: GuidePoint,
    ) -> CollectedKnowledge:
        """
        For connector nodes: only reverse-geocode to get the street name.
        One API call; failure → empty card (has_any_data=False).
        """
        lat, lng = self._extract_coords(point)
        errors: list[str] = []
        street_name: str | None = None

        try:
            geo_result = await self._google_places.reverse_geocode(lat, lng)
            if geo_result is not None:
                street_name = self._google_places.extract_street_name(geo_result)
        except Exception as exc:
            msg = f"Reverse geocode error for point {point.id}: {exc}"
            errors.append(msg)
            logger.warning("KnowledgeCollector: %s", msg)

        return CollectedKnowledge(
            point_id=point.id,
            card_type="street_context",
            street_name=street_name,
            collection_errors=errors,
            has_any_data=street_name is not None,
        )

    # =========================================================================
    # Guarded source calls (each returns None on any error)
    # =========================================================================

    async def _safe_google_details(
        self,
        point: GuidePoint,
        errors: list[str],
    ) -> dict[str, Any] | None:
        try:
            if not point.google_place_id:
                return None
            return await self._google_places.place_details(point.google_place_id)
        except Exception as exc:
            msg = f"Google Place Details error for place_id={point.google_place_id}: {exc}"
            errors.append(msg)
            logger.warning("KnowledgeCollector: %s", msg)
            return None

    async def _safe_wikipedia(
        self,
        name: str,
        language: str,
        lat: float,
        lng: float,
        errors: list[str],
    ) -> WikipediaSummary | None:
        try:
            if not name:
                return None
            return await self._wikipedia.search_and_get_summary(
                name, language=language, near_lat=lat, near_lng=lng
            )
        except Exception as exc:
            msg = f"Wikipedia error for name={name!r}: {exc}"
            errors.append(msg)
            logger.warning("KnowledgeCollector: %s", msg)
            return None

    # =========================================================================
    # Geometry helper
    # =========================================================================

    def _extract_coords(self, point: GuidePoint) -> tuple[float, float]:
        """
        Extract (lat, lng) from a GuidePoint's PostGIS geometry column.

        Uses geoalchemy2.shape.to_shape() to convert the WKBElement to a
        Shapely Point. Shapely convention: .y = latitude, .x = longitude.
        Returns (0.0, 0.0) and logs a warning on any error.
        """
        try:
            from geoalchemy2.shape import to_shape
            shape = to_shape(point.location)
            return float(shape.y), float(shape.x)
        except Exception:
            logger.warning(
                "KnowledgeCollector: cannot extract coords from point %s "
                "— location may be None or non-PostGIS type",
                point.id,
            )
            return 0.0, 0.0
