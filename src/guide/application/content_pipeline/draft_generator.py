"""
DraftGenerator — Stage 1 of the Content Pipeline.

BFS-based orchestrator that generates all content blocks (main, bonus, recap,
transition) for a guide zone using the existing io.net LLM client.

Safety mechanisms:
  - asyncio.Semaphore limits concurrent LLM calls (guide_content_max_parallel_llm)
  - Hard cap on total LLM calls per job (guide_content_max_llm_calls_per_job)
  - Idempotency: existing draft/validated/reviewed blocks are skipped unless force_regenerate=True
  - Dry-run mode: builds all prompts and logs them but makes zero LLM calls
  - Progress written to guide_content_jobs.progress_json after every BFS group
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from math import radians, cos, sin, asin, sqrt
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from src.config import settings as _default_settings
from src.guide.application.content_pipeline.prompt_builder import (
    build_bonus_prompt,
    build_connector_prompt,
    build_main_prompt,
    build_recap_prompt,
    build_transition_prompt,
)
from src.guide.application.content_pipeline.utils import _head, _tail
from src.guide.application.content_pipeline.text_validators import (
    has_wrong_alphabet, validate_text_quality, auto_fix,
    has_arabic_or_roman_numerals,
)
from src.guide.domain.models import GuideContentBlock

if TYPE_CHECKING:
    from src.guide.application.content_pipeline.repository import ContentPipelineRepository
    from src.infrastructure.llm_client import LLMClient

logger = logging.getLogger(__name__)

# Generation statuses that indicate an existing block should be kept
_SKIP_STATUSES = {"draft", "validated", "needs_manual_review", "reviewed", "synthesized"}


# ============================================================================
# Haversine helper (no PostGIS needed for centroid distance)
# ============================================================================

def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return distance in metres between two WGS-84 coordinates."""
    r = 6_371_000.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlam = radians(lng2 - lng1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlam / 2) ** 2
    return 2 * r * asin(sqrt(a))


# ============================================================================
# BFS helpers
# ============================================================================

def _split_independent(
    point_ids: list[UUID],
    adj: dict[UUID, list[UUID]],
) -> list[list[UUID]]:
    """
    Partition a single BFS level into independent groups — two points are
    "dependent" if one is a graph-neighbour of the other.

    Points in the same group can be processed in parallel because none of them
    reference each other's narrative (which isn't cached yet).
    Greedy colouring approach: O(n²) but n (one BFS level) is small.
    """
    groups: list[list[UUID]] = []
    assigned: set[UUID] = set()

    for pid in point_ids:
        placed = False
        for group in groups:
            group_set = set(group)
            neighbors = set(adj.get(pid, []))
            if not (group_set & neighbors):
                group.append(pid)
                assigned.add(pid)
                placed = True
                break
        if not placed:
            groups.append([pid])
            assigned.add(pid)

    return groups


def _find_central_point(points, zone):
    """Return the point closest to the zone centroid (lat/lng from boundary centroid)."""
    from geoalchemy2.shape import to_shape

    try:
        boundary_shape = to_shape(zone.boundary)
        centroid = boundary_shape.centroid
        centroid_lat, centroid_lng = centroid.y, centroid.x
    except Exception:
        # Fallback: use first point
        return points[0]

    best, best_dist = points[0], float("inf")
    for p in points:
        try:
            loc_shape = to_shape(p.location)
            d = _haversine_m(centroid_lat, centroid_lng, loc_shape.y, loc_shape.x)
            if d < best_dist:
                best, best_dist = p, d
        except Exception:
            continue
    return best


# ============================================================================
# DraftGenerator
# ============================================================================

class DraftGenerator:
    """
    Orchestrates Stage 1 (Draft Generation) for a single zone.

    Usage::

        generator = DraftGenerator(repo=repo, llm_client=llm_client)
        job_id = await generator.generate_zone_drafts(zone_id)
    """

    def __init__(
        self,
        repo: "ContentPipelineRepository",
        llm_client: "LLMClient",
        app_settings=None,
    ) -> None:
        self._repo = repo
        self._llm_client = llm_client
        self._settings = app_settings or _default_settings
        self._llm_semaphore = asyncio.Semaphore(
            self._settings.guide_content_max_parallel_llm
        )
        self._llm_calls_count = 0

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def generate_zone_drafts(
        self,
        zone_id: UUID,
        voice_ids: list[UUID] | None = None,
        languages: list[str] | None = None,
        detail_levels: list[str] | None = None,
        force_regenerate: bool = False,
        dry_run: bool = False,
        poi_only: bool = False,
        skip_transitions: bool = False,
    ) -> UUID:
        """
        Generate all content blocks for a zone.

        Returns the job_id of the created guide_content_jobs record.
        """
        if languages is None:
            languages = list(self._settings.guide_content_default_languages)
        if detail_levels is None:
            detail_levels = list(self._settings.guide_content_default_detail_levels)

        # Create job
        job = await self._repo.create_content_job(zone_id, job_type="generate_drafts")
        job_id = job.id
        logger.info(
            "DraftGenerator: starting job %s for zone %s (dry_run=%s force=%s)",
            job_id, zone_id, dry_run, force_regenerate,
        )

        try:
            # Load data
            zone = await self._repo.get_zone_with_metadata(zone_id)
            points = await self._repo.get_active_points_in_zone(zone_id)
            edges = await self._repo.get_edges_in_zone(zone_id)

            if poi_only:
                points = [p for p in points if p.point_type == "poi"]
                poi_ids = {p.id for p in points}
                edges = [e for e in edges if e.from_point_id in poi_ids]

            if not points:
                logger.warning("Zone %s has no active approved points — nothing to generate", zone_id)
                await self._repo.mark_job_complete(job_id, {"total": 0, "processed": 0, "draft": 0, "failed": 0})
                return job_id

            voices = (
                await self._repo.get_voices_by_ids(voice_ids)
                if voice_ids
                else await self._repo.get_active_voices()
            )
            if not voices:
                raise RuntimeError("No active voices found — cannot generate content")

            # Bulk load knowledge cards (avoid N+1)
            point_ids = [p.id for p in points]
            cards = await self._repo.get_knowledge_cards_for_points(point_ids)

            # Build adjacency map (undirected for BFS — include both directions)
            adj: dict[UUID, list[UUID]] = {p.id: [] for p in points}
            for edge in edges:
                if edge.from_point_id in adj:
                    adj[edge.from_point_id].append(edge.to_point_id)
                if edge.to_point_id in adj and edge.from_point_id not in adj[edge.to_point_id]:
                    adj[edge.to_point_id].append(edge.from_point_id)

            # Lookup maps
            point_map = {p.id: p for p in points}

            # BFS
            narrative_cache: dict[UUID, dict] = {}
            central_point = _find_central_point(points, zone)
            current_level: list[UUID] = [central_point.id]
            visited: set[UUID] = {central_point.id}
            bfs_level_num = 0
            total_processed = 0
            total_failed = 0
            total_draft = 0
            dry_run_prompt_count = 0

            while current_level:
                independent_groups = _split_independent(current_level, adj)

                for group in independent_groups:
                    # Process points sequentially within each group to avoid
                    # concurrent access on the shared SQLAlchemy async session.
                    results = []
                    for pid in group:
                        try:
                            result = await self._generate_point_all_variants(
                                pid,
                                voices=voices,
                                languages=languages,
                                detail_levels=detail_levels,
                                zone=zone,
                                cards=cards,
                                point_map=point_map,
                                adj=adj,
                                narrative_cache=narrative_cache,
                                force_regenerate=force_regenerate,
                                dry_run=dry_run,
                                dry_run_prompt_count_ref=[dry_run_prompt_count],
                                job_id=job_id,
                            )
                        except Exception as exc:
                            result = exc
                        results.append(result)

                    for pid, result in zip(group, results):
                        total_processed += 1
                        if isinstance(result, Exception):
                            logger.error(
                                "Point %s generation failed: %s", pid, result
                            )
                            total_failed += 1
                        else:
                            narrative_cache[pid] = result
                            total_draft += result.get("blocks_generated", 0)

                    # Progress after each group
                    await self._repo.update_job_progress(job_id, {
                        "bfs_level": bfs_level_num,
                        "points_processed": total_processed,
                        "points_total": len(points),
                        "draft": total_draft,
                        "failed": total_failed,
                        "llm_calls": self._llm_calls_count,
                        "dry_run": dry_run,
                    })

                # Next BFS level
                next_level: list[UUID] = []
                for pid in current_level:
                    for neighbor_id in adj.get(pid, []):
                        if neighbor_id not in visited:
                            visited.add(neighbor_id)
                            next_level.append(neighbor_id)

                # Handle disconnected sub-graphs: if BFS is exhausted but some
                # points were never reached, seed the next level from any unvisited point.
                if not next_level:
                    unvisited = [p.id for p in points if p.id not in visited]
                    if unvisited:
                        seed = unvisited[0]
                        visited.add(seed)
                        next_level = [seed]

                current_level = next_level
                bfs_level_num += 1

            # Transitions pass (sequential — shared async session can't be used concurrently)
            if skip_transitions:
                logger.info("DraftGenerator: skipping transitions pass (skip_transitions=True)")
                transition_results = []
            else:
                logger.info("DraftGenerator: starting transitions pass (%d edges)", len(edges))
                transition_results = []
                for edge in edges:
                    try:
                        result = await self._generate_edge_transitions(
                            edge=edge,
                            voices=voices,
                            languages=languages,
                            point_map=point_map,
                            narrative_cache=narrative_cache,
                            zone_id=zone_id,
                            force_regenerate=force_regenerate,
                            dry_run=dry_run,
                            job_id=job_id,
                        )
                    except Exception as exc:
                        result = exc
                    transition_results.append(result)
            transition_failed = sum(1 for r in transition_results if isinstance(r, Exception))
            transition_blocks = sum(r for r in transition_results if isinstance(r, int))

            final_progress = {
                "bfs_levels": bfs_level_num,
                "points_processed": total_processed,
                "points_total": len(points),
                "draft": total_draft + transition_blocks,
                "failed": total_failed + transition_failed,
                "edges_processed": len(edges),
                "llm_calls": self._llm_calls_count,
                "dry_run": dry_run,
            }
            await self._repo.mark_job_complete(job_id, final_progress)
            logger.info(
                "DraftGenerator: job %s complete — %d points, %d edges, %d LLM calls",
                job_id, total_processed, len(edges), self._llm_calls_count,
            )

        except Exception as exc:
            logger.error("DraftGenerator: job %s failed: %s", job_id, exc, exc_info=True)
            await self._repo.mark_job_failed(job_id, str(exc))
            raise

        return job_id

    # ------------------------------------------------------------------
    # Zone transitions (stub — requires inter-zone data)
    # ------------------------------------------------------------------

    async def generate_zone_transitions_for_city(self, city_id: UUID) -> None:
        """
        TODO: generate zone_transition blocks for all zone-pairs in a city.
        This requires knowing which zones are adjacent, which is determined
        only after all zones in the city have been seeded.
        Implement after MVP city seeding is complete.
        """
        raise NotImplementedError(
            "zone_transition generation is deferred — implement after all zones "
            "in the city are seeded and adjacency is mapped."
        )

    # ------------------------------------------------------------------
    # Transitions-only pass (for topup runs)
    # ------------------------------------------------------------------

    async def generate_transitions_only(
        self,
        zone_id: UUID,
        voice_ids: list[UUID] | None = None,
        languages: list[str] | None = None,
        poi_edges_only: bool = True,
        force_regenerate: bool = False,
        max_calls: int = 500,
    ) -> dict:
        """
        Generate transition blocks for edges in a zone.

        When poi_edges_only=True (default), only processes edges where
        from_point is a POI — skipping the 3,000+ connector-only edges.

        Returns {"edges_processed": N, "blocks_created": M, "llm_calls": K}.
        """
        if languages is None:
            languages = list(self._settings.guide_content_default_languages)

        original_cap = self._settings.guide_content_max_llm_calls_per_job
        self._settings.guide_content_max_llm_calls_per_job = max_calls
        self._llm_calls_count = 0

        try:
            job = await self._repo.create_content_job(zone_id, job_type="generate_transitions")
            job_id = job.id

            points = await self._repo.get_active_points_in_zone(zone_id)
            edges = await self._repo.get_edges_in_zone(zone_id)

            voices = (
                await self._repo.get_voices_by_ids(voice_ids)
                if voice_ids
                else await self._repo.get_active_voices()
            )

            point_map = {p.id: p for p in points}

            if poi_edges_only:
                poi_ids = {p.id for p in points if p.point_type == "poi"}
                edges = [e for e in edges if e.from_point_id in poi_ids]
                logger.info(
                    "generate_transitions_only: poi_edges_only=True → %d edges (from %d total)",
                    len(edges), len(await self._repo.get_edges_in_zone(zone_id)),
                )
            else:
                logger.info("generate_transitions_only: processing all %d edges", len(edges))

            # Load narrative cache from existing DB content
            narrative_cache: dict[UUID, dict] = {}
            for p in points:
                for lang in languages:
                    text = await self._repo.get_content_text(
                        p.id, voices[0].id if voices else None, lang, "main", "standard"
                    ) if voices else None
                    if text:
                        narrative_cache.setdefault(p.id, {})
                        narrative_cache[p.id][f"main_{lang}_standard"] = text[:300]

            total_blocks = 0
            edges_processed = 0
            for edge in edges:
                try:
                    n = await self._generate_edge_transitions(
                        edge=edge,
                        voices=voices,
                        languages=languages,
                        point_map=point_map,
                        narrative_cache=narrative_cache,
                        zone_id=zone_id,
                        force_regenerate=force_regenerate,
                        dry_run=False,
                        job_id=job_id,
                    )
                    total_blocks += n
                    edges_processed += 1
                except RuntimeError as exc:
                    if "Hard cap reached" in str(exc):
                        logger.warning("LLM call cap reached after %d edges", edges_processed)
                        break
                    logger.error("Transition edge %s failed: %s", edge.id, exc)
                except Exception as exc:
                    logger.error("Transition edge %s failed: %s", edge.id, exc)

            final = {
                "edges_processed": edges_processed,
                "edges_total": len(edges),
                "blocks_created": total_blocks,
                "llm_calls": self._llm_calls_count,
            }
            await self._repo.mark_job_complete(job_id, final)
            logger.info("generate_transitions_only complete: %s", final)
            return final

        finally:
            self._settings.guide_content_max_llm_calls_per_job = original_cap

    # ------------------------------------------------------------------
    # Per-point generation
    # ------------------------------------------------------------------

    async def _generate_point_all_variants(
        self,
        point_id: UUID,
        voices,
        languages: list[str],
        detail_levels: list[str],
        zone,
        cards: dict,
        point_map: dict,
        adj: dict,
        narrative_cache: dict,
        force_regenerate: bool,
        dry_run: bool,
        dry_run_prompt_count_ref: list,
        job_id: UUID,
    ) -> dict:
        """
        Generate main + bonus (per detail_level × voice × language) and recap (per voice × language)
        for one point.

        Returns a cache dict used by subsequent BFS levels:
        {
          "name": str,
          "main_{lang}_{detail_level}": str (≤300 chars),
          "themes_{voice_id}_{lang}": list[str],
          "blocks_generated": int,
        }
        """
        point = point_map[point_id]
        card = cards.get(point_id)
        is_connector = point.point_type == "connector"

        # Build neighbour narratives from cache
        neighbor_narratives: dict[str, str] = {}
        for nid in adj.get(point_id, []):
            cached = narrative_cache.get(nid)
            if cached:
                for lang in languages:
                    for dl in detail_levels:
                        key = f"main_{lang}_{dl}"
                        if key in cached:
                            nname = cached.get("name") or str(nid)
                            if nname not in neighbor_narratives:
                                neighbor_narratives[nname] = cached[key]

        result_cache: dict = {"name": point.name, "blocks_generated": 0}
        blocks_generated = 0

        for voice in voices:
            for language in languages:
                # ---- main / connector narrative ----
                for detail_level in detail_levels:
                    if is_connector:
                        prompt = build_connector_prompt(
                            point, card, zone, voice, language, detail_level
                        )
                    else:
                        prompt = build_main_prompt(
                            point, card, zone, voice, language, detail_level,
                            neighbor_narratives,
                        )

                    if dry_run:
                        dry_run_prompt_count_ref[0] += 1
                        if dry_run_prompt_count_ref[0] <= 3:
                            logger.info(
                                "[dry-run] PROMPT #%d (%s/%s/%s/%s):\n%s\n---",
                                dry_run_prompt_count_ref[0],
                                point.name or point_id,
                                voice.style_group, language, detail_level,
                                prompt[:500],
                            )
                        main_text = f"[dry-run placeholder for {point.name}]"
                    else:
                        if not force_regenerate:
                            existing = await self._repo.get_existing_block(
                                point_id, voice.id, language, detail_level, "main", None, 0
                            )
                            if existing and existing.generation_status in _SKIP_STATUSES:
                                main_text = existing.text_script
                                # Still cache for neighbours
                                cache_key = f"main_{language}_{detail_level}"
                                result_cache.setdefault(cache_key, main_text[:300])
                                continue

                        raw = await self._llm_generate_with_retry(
                            prompt,
                            expected_keys=["text_script"],
                        )
                        main_text = raw["text_script"]
                        themes = raw.get("themes_covered", [])

                        # 1) Auto-fix simple artifacts (non-Cyrillic chars, mixed words)
                        main_text = auto_fix(main_text, language)

                        # 2) Validate alphabet quality + numerals; if bad, retry
                        is_clean, issues = validate_text_quality(main_text, language)
                        has_nums, num_issues = has_arabic_or_roman_numerals(main_text)
                        all_issues = list(issues) + (list(num_issues) if has_nums else [])
                        if not is_clean or has_nums:
                            for _retry in range(2):
                                fix_prompt = (
                                    prompt
                                    + f"\n\n[CRITICAL FIX: Previous response had issues: "
                                    f"{all_issues}. Rewrite the ENTIRE narrative in {language} only, "
                                    f"with NO foreign characters, NO mixed-alphabet words, "
                                    f"NO Arabic numerals (0-9), NO Roman numerals (I, V, X). "
                                    f"Write ALL numbers as words in correct grammatical form.]"
                                )
                                raw = await self._llm_generate_with_retry(
                                    fix_prompt, expected_keys=["text_script"],
                                )
                                main_text = auto_fix(raw["text_script"], language)
                                themes = raw.get("themes_covered", themes)
                                is_clean, issues = validate_text_quality(main_text, language)
                                has_nums, num_issues = has_arabic_or_roman_numerals(main_text)
                                all_issues = list(issues) + (list(num_issues) if has_nums else [])
                                if is_clean and not has_nums:
                                    break

                        gen_status = "needs_manual_review" if (not is_clean or has_nums) else "draft"

                        block = GuideContentBlock(
                            id=uuid.uuid4(),
                            point_id=point_id,
                            zone_id=zone.id,
                            voice_id=voice.id,
                            language=language,
                            detail_level=detail_level,
                            content_type="main",
                            variant_index=0,
                            text_script=main_text,
                            generation_status=gen_status,
                            generated_at=datetime.now(timezone.utc),
                            created_at=datetime.now(timezone.utc),
                        )
                        await self._repo.upsert_content_block(block)
                        blocks_generated += 1

                        cache_key = f"main_{language}_{detail_level}"
                        result_cache.setdefault(cache_key, main_text[:300])
                        result_cache.setdefault(
                            f"themes_{voice.id}_{language}", themes
                        )

                # ---- bonus ----
                for detail_level in detail_levels:
                    main_text_for_bonus = result_cache.get(
                        f"main_{language}_{detail_level}", ""
                    )
                    if not main_text_for_bonus:
                        # try to load from DB
                        main_text_for_bonus = (
                            await self._repo.get_content_text(
                                point_id, voice.id, language, "main", detail_level
                            )
                        ) or ""

                    bonus_prompt = build_bonus_prompt(
                        point, card, zone, voice, language, detail_level,
                        main_text_for_bonus,
                    )

                    if dry_run:
                        pass  # bonus not logged in dry-run (quota already shown)
                    else:
                        if not force_regenerate:
                            existing = await self._repo.get_existing_block(
                                point_id, voice.id, language, detail_level, "bonus", None, 0
                            )
                            if existing and existing.generation_status in _SKIP_STATUSES:
                                continue

                        raw = await self._llm_generate_with_retry(
                            bonus_prompt,
                            expected_keys=["text_script"],
                        )
                        block = GuideContentBlock(
                            id=uuid.uuid4(),
                            point_id=point_id,
                            zone_id=zone.id,
                            voice_id=voice.id,
                            language=language,
                            detail_level=detail_level,
                            content_type="bonus",
                            variant_index=0,
                            text_script=raw["text_script"],
                            generation_status="draft",
                            generated_at=datetime.now(timezone.utc),
                            created_at=datetime.now(timezone.utc),
                        )
                        await self._repo.upsert_content_block(block)
                        blocks_generated += 1

                # ---- recap (POI only, always standard) ----
                if not is_connector:
                    main_text_std = result_cache.get(f"main_{language}_standard", "")
                    if not main_text_std:
                        main_text_std = (
                            await self._repo.get_content_text(
                                point_id, voice.id, language, "main", "standard"
                            )
                        ) or ""

                    recap_prompt = build_recap_prompt(
                        point, voice, language, main_text_std
                    )

                    if not dry_run:
                        if not force_regenerate:
                            existing = await self._repo.get_existing_block(
                                point_id, voice.id, language, "standard", "recap", None, 0
                            )
                            if existing and existing.generation_status in _SKIP_STATUSES:
                                continue

                        raw = await self._llm_generate_with_retry(
                            recap_prompt,
                            expected_keys=["text_script"],
                        )
                        block = GuideContentBlock(
                            id=uuid.uuid4(),
                            point_id=point_id,
                            zone_id=zone.id,
                            voice_id=voice.id,
                            language=language,
                            detail_level="standard",
                            content_type="recap",
                            variant_index=0,
                            text_script=raw["text_script"],
                            generation_status="draft",
                            generated_at=datetime.now(timezone.utc),
                            created_at=datetime.now(timezone.utc),
                        )
                        await self._repo.upsert_content_block(block)
                        blocks_generated += 1

        result_cache["blocks_generated"] = blocks_generated
        return result_cache

    # ------------------------------------------------------------------
    # Transition generation
    # ------------------------------------------------------------------

    async def _generate_edge_transitions(
        self,
        edge,
        voices,
        languages: list[str],
        point_map: dict,
        narrative_cache: dict,
        zone_id: UUID,
        force_regenerate: bool,
        dry_run: bool,
        job_id: UUID,
    ) -> int:
        """Generate 3 transition variants for one edge × all voices × all languages."""
        async with self._llm_semaphore:
            from_point = point_map.get(edge.from_point_id)
            to_point = point_map.get(edge.to_point_id)
            if from_point is None or to_point is None:
                return 0

            from_cache = narrative_cache.get(edge.from_point_id, {})
            to_cache = narrative_cache.get(edge.to_point_id, {})
            blocks_created = 0

            for voice in voices:
                for language in languages:
                    from_text = from_cache.get(f"main_{language}_standard", "")
                    to_text = to_cache.get(f"main_{language}_standard", "")

                    if not from_text:
                        from_text = (
                            await self._repo.get_content_text(
                                edge.from_point_id, voice.id, language, "main", "standard"
                            )
                        ) or ""
                    if not to_text:
                        to_text = (
                            await self._repo.get_content_text(
                                edge.to_point_id, voice.id, language, "main", "standard"
                            )
                        ) or ""

                    if not from_text and not to_text:
                        logger.warning(
                            "No narrative cache for edge %s→%s (%s/%s) — skipping transition",
                            edge.from_point_id, edge.to_point_id, voice.style_group, language,
                        )

                    if not force_regenerate and not dry_run:
                        # Check if variant 0 already exists
                        existing = await self._repo.get_existing_block(
                            edge.from_point_id, voice.id, language,
                            "standard", "transition", edge.id, 0
                        )
                        if existing and existing.generation_status in _SKIP_STATUSES:
                            continue

                    from_themes = from_cache.get(f"themes_{voice.id}_{language}", [])
                    prompt = build_transition_prompt(
                        from_point=from_point,
                        to_point=to_point,
                        edge=edge,
                        voice=voice,
                        language=language,
                        from_narrative_tail=from_text,
                        to_narrative_head=to_text,
                        from_themes=from_themes,
                    )

                    if dry_run:
                        continue

                    try:
                        raw = await self._llm_generate_with_retry(
                            prompt,
                            expected_keys=["variants"],
                        )
                    except Exception as exc:
                        logger.error(
                            "Transition generation failed for edge %s (%s/%s): %s",
                            edge.id, voice.style_group, language, exc,
                        )
                        continue

                    variants = (raw.get("variants") or [])[:3]
                    for idx, variant in enumerate(variants):
                        variant_text = (variant or {}).get("text_script", "")
                        if not variant_text:
                            continue
                        block = GuideContentBlock(
                            id=uuid.uuid4(),
                            point_id=edge.from_point_id,
                            zone_id=zone_id,
                            voice_id=voice.id,
                            language=language,
                            detail_level="standard",
                            content_type="transition",
                            edge_id=edge.id,
                            variant_index=idx,
                            text_script=variant_text,
                            generation_status="draft",
                            generated_at=datetime.now(timezone.utc),
                            created_at=datetime.now(timezone.utc),
                        )
                        await self._repo.upsert_content_block(block)
                        blocks_created += 1

            return blocks_created

    # ------------------------------------------------------------------
    # LLM call with retry
    # ------------------------------------------------------------------

    async def _llm_generate_with_retry(
        self,
        prompt: str,
        expected_keys: list[str],
    ) -> dict:
        """
        Call generate_structured() with retry on bad JSON / missing keys.
        Enforces the hard cap on total LLM calls per job.
        """
        max_retries = self._settings.guide_content_retry_attempts
        cap = self._settings.guide_content_max_llm_calls_per_job

        if self._llm_calls_count >= cap:
            raise RuntimeError(
                f"Hard cap reached: {cap} LLM calls. "
                "Increase guide_content_max_llm_calls_per_job if intentional."
            )

        last_error: Exception | None = None
        current_prompt = prompt

        for attempt in range(max_retries):
            async with self._llm_semaphore:
                self._llm_calls_count += 1
                try:
                    result = await self._llm_client.generate_structured(current_prompt, max_tokens=800)
                except Exception as exc:
                    last_error = exc
                    logger.warning(
                        "LLM call failed (attempt %d/%d): %s", attempt + 1, max_retries, exc
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.5 * (attempt + 1))
                    continue

            # Validate expected keys
            try:
                for key in expected_keys:
                    if key not in result:
                        raise ValueError(f"Missing key '{key}' in LLM response")
                if "text_script" in result and len(result["text_script"].strip()) < 20:
                    raise ValueError("text_script too short")
                return result
            except (ValueError, KeyError) as exc:
                last_error = exc
                if attempt < max_retries - 1:
                    current_prompt += (
                        f"\n\n[Previous attempt failed: {exc}. "
                        f"Ensure valid JSON with all required keys: {expected_keys}]"
                    )
                    await asyncio.sleep(0.5 * (attempt + 1))

        raise RuntimeError(
            f"LLM generation failed after {max_retries} attempts: {last_error}"
        )
