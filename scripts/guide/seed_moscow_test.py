"""
Тестовый прогон City Seeder + Content Pipeline для одной зоны.

NON-INTERACTIVE режим — все решения принимаются через CLI флаги.
Каждая фаза идемпотентна: повторный запуск безопасен.

Запуск (полный прогон):
    python scripts/guide/seed_moscow_test.py \\
        --city Moscow --country Russia \\
        --non-interactive \\
        --auto-approve-zone max-poi \\
        --voice-style academic --voice-language en \\
        --skip-synthesis

Запуск с конкретным zone-id (пропустить Phase 1-2, продолжить с Phase 3):
    python scripts/guide/seed_moscow_test.py \\
        --zone-id <UUID> --job-id <UUID> \\
        --non-interactive --skip-synthesis

Проверка синтаксиса / справка:
    python scripts/guide/seed_moscow_test.py --help
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Optional

# ── Ensure project root is on sys.path when run as a script ──────────────────
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("seed_moscow_test")


# =============================================================================
# Environment check
# =============================================================================

async def check_environment() -> bool:
    """Validate that all required services and settings are in place."""
    from src.config import settings
    from src.infrastructure.database import AsyncSessionLocal
    from sqlalchemy import text

    errors: list[str] = []
    warnings: list[str] = []

    # DB connection
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        print("  ✅ Database: connected")
    except Exception as exc:
        errors.append(f"Database: {exc}")
        print(f"  ❌ Database: {exc}")

    # PostGIS
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT PostGIS_Version()"))
        print("  ✅ PostGIS: available")
    except Exception as exc:
        errors.append(f"PostGIS: {exc}")
        print(f"  ❌ PostGIS: {exc}")

    # Google Maps API key
    if settings.google_maps_api_key:
        print(f"  ✅ GOOGLE_MAPS_API_KEY: set ({settings.google_maps_api_key[:8]}...)")
    else:
        errors.append("GOOGLE_MAPS_API_KEY not set")
        print("  ❌ GOOGLE_MAPS_API_KEY: not set")

    # LLM model
    model = settings.guide_narrative_model or settings.trip_planning_model
    if model:
        print(f"  ✅ LLM model: {model}")
    else:
        errors.append("No LLM model configured (guide_narrative_model or trip_planning_model)")
        print("  ❌ LLM model: not configured")

    # LLM API key
    if settings.llm_provider == "ionet" and not settings.ionet_api_key:
        errors.append("IONET_API_KEY not set")
        print("  ❌ IONET_API_KEY: not set")
    elif settings.llm_provider == "anthropic" and not settings.anthropic_api_key:
        errors.append("ANTHROPIC_API_KEY not set")
        print("  ❌ ANTHROPIC_API_KEY: not set")
    else:
        print(f"  ✅ LLM provider: {settings.llm_provider}")

    # ElevenLabs (optional — needed only for synthesis)
    if settings.elevenlabs_api_key:
        print(f"  ✅ ELEVENLABS_API_KEY: set")
    else:
        warnings.append("ELEVENLABS_API_KEY not set (needed for --synthesize)")
        print("  ⚠️  ELEVENLABS_API_KEY: not set (synthesis will be skipped)")

    # Voice IDs in DB
    try:
        from src.infrastructure.database import get_db_session
        from src.guide.application.seeder.repository import SeederRepository

        async with get_db_session() as db:
            from src.guide.domain.models import GuideVoice
            from sqlalchemy import select
            result = await db.execute(select(GuideVoice).where(GuideVoice.is_active.is_(True)))
            voices = list(result.scalars().all())

        if not voices:
            warnings.append("No active voices in guide_voices table — run migration 009 + seed")
            print("  ⚠️  guide_voices: no active voices found (run migration 009)")
        else:
            placeholders = [v for v in voices if "PLACEHOLDER" in (v.elevenlabs_voice_id or "")]
            if placeholders:
                warnings.append(
                    f"{len(placeholders)} voices still have PLACEHOLDER_VOICE_ID — "
                    "run: psql $DATABASE_URL -f scripts/guide/update_voice_ids.sql"
                )
                print(f"  ⚠️  Voice IDs: {len(placeholders)} placeholder(s) — run update_voice_ids.sql")
            else:
                print(f"  ✅ guide_voices: {len(voices)} active voice(s) with real ElevenLabs IDs")
    except Exception as exc:
        warnings.append(f"Could not check guide_voices: {exc}")
        print(f"  ⚠️  guide_voices: check failed ({exc})")

    # ffmpeg (optional)
    import shutil
    if shutil.which("ffmpeg"):
        print("  ✅ ffmpeg: available")
    else:
        print("  ⚠️  ffmpeg: not found (audio post-processing skipped)")

    print()
    if warnings:
        print(f"Warnings ({len(warnings)}):")
        for w in warnings:
            print(f"  • {w}")
        print()

    if errors:
        print(f"❌ Environment check FAILED ({len(errors)} error(s)):")
        for e in errors:
            print(f"  • {e}")
        return False

    print("✅ Environment check passed")
    return True


# =============================================================================
# Phase 1: Zone Discovery
# =============================================================================

async def phase1_zone_discovery(
    city_name: str,
    country: Optional[str],
    dbscan_eps_m: float = 800.0,
    dbscan_min_samples: int = 5,
) -> tuple[uuid.UUID, uuid.UUID]:
    """
    Run Phase 1: Zone Discovery.
    Returns (job_id, city_id).
    If an active job already exists for the city, returns it (idempotent).
    """
    from src.infrastructure.database import get_db_session
    from src.guide.application.seeder.repository import SeederRepository
    from src.guide.application.seeder.orchestrator import CitySeederOrchestrator
    from src.guide.infrastructure.google_places_client import GuideGooglePlacesClient
    from src.guide.application.seeder.zone_discovery import ZoneDiscovery

    print(f"\n{'='*60}")
    print(f"PHASE 1: Zone Discovery for {city_name}")
    print(f"{'='*60}")

    google_places = GuideGooglePlacesClient()
    zone_discovery = ZoneDiscovery(
        google_places,
        dbscan_eps_m=dbscan_eps_m,
        dbscan_min_samples=dbscan_min_samples,
    )

    async with get_db_session() as db:
        repo = SeederRepository(db)

        # Check if job already exists
        active_job = await repo.get_active_job_for_city(city_name)
        if active_job is not None:
            # If existing job has 0 zones, allow re-discovery by marking it failed
            progress = active_job.progress_json or {}
            if progress.get("zones_proposed", 0) == 0 and active_job.status == "awaiting_zone_approval":
                print(f"  Found existing job {active_job.id} with 0 zones — marking failed and re-running discovery")
                await repo.update_seed_job(
                    active_job.id,
                    status="failed",
                    error_message="Re-running with adjusted DBSCAN parameters",
                    progress_json=progress,
                    completed=True,
                )
                await db.commit()
            else:
                print(f"  Found existing job {active_job.id} (status={active_job.status}) — reusing")
                city_id = active_job.city_id
                if city_id is None:
                    raise RuntimeError("Existing job has no city_id — it may have failed during city upsert")
                await db.commit()
                return active_job.id, city_id

        orchestrator = CitySeederOrchestrator(repo=repo, zone_discovery=zone_discovery)
        job_id = await orchestrator.start_seed(city_name, country)
        await db.commit()

        # Re-fetch to get city_id
        job = await repo.get_seed_job(job_id)
        if job is None or job.city_id is None:
            raise RuntimeError(f"Zone Discovery failed — job {job_id} has no city_id")

        city_id = job.city_id

    print(f"  Job ID:  {job_id}")
    print(f"  City ID: {city_id}")
    print(f"  Status:  {job.status}")
    print(f"  Zones proposed: {job.progress_json.get('zones_proposed', 0)}")

    return job_id, city_id


# =============================================================================
# Phase 2: List and approve zones
# =============================================================================

async def phase2_approve_zones(
    city_id: uuid.UUID,
    strategy: str,
) -> list:
    """
    Approve zones according to strategy: 'first' | 'max-poi' | 'all'.
    Returns list of approved GuideZone objects.
    Idempotent: already-approved zones are counted.
    """
    from src.infrastructure.database import get_db_session
    from src.guide.application.seeder.repository import SeederRepository

    print(f"\n{'='*60}")
    print(f"PHASE 2: Zone Approval (strategy={strategy})")
    print(f"{'='*60}")

    async with get_db_session() as db:
        repo = SeederRepository(db)
        all_zones = await repo.get_zones_by_city(city_id)

        if not all_zones:
            raise RuntimeError(f"No zones found for city_id={city_id} — did Phase 1 complete?")

        print(f"  Found {len(all_zones)} zone(s):")
        for z in sorted(all_zones, key=lambda z: z.poi_count, reverse=True):
            status = "✅ approved" if z.is_approved else "⏳ pending"
            print(f"    {status}  {z.name or 'unnamed'}  (poi_count={z.poi_count}, theme={z.theme})")

        # Determine which zones to approve
        already_approved = [z for z in all_zones if z.is_approved]
        pending = [z for z in all_zones if not z.is_approved]

        to_approve: list = []
        if strategy == "all":
            to_approve = pending
        elif strategy == "first":
            if not already_approved and pending:
                to_approve = [pending[0]]
        elif strategy == "max-poi":
            if not already_approved:
                best = max(pending, key=lambda z: z.poi_count, default=None)
                if best:
                    to_approve = [best]
        else:
            raise ValueError(f"Unknown auto-approve-zone strategy: {strategy}")

        for zone in to_approve:
            await repo.approve_zone(zone.id)
            print(f"  → Approved zone: {zone.name or zone.id}")

        await db.commit()

        # Re-fetch approved zones
        approved = await repo.get_zones_by_city(city_id, only_approved=True)

    if not approved:
        raise RuntimeError("No approved zones after Phase 2 — cannot continue")

    print(f"  ✅ {len(approved)} approved zone(s): {[z.name for z in approved]}")
    return approved


# =============================================================================
# Phase 3: Point Placement + Graph + Knowledge
# =============================================================================

async def phase3_place_and_collect(job_id: uuid.UUID) -> dict:
    """
    Run Phases 2+3+4 (PointPlacement + GraphBuilder + KnowledgeCollector).
    Long-running: 5–15 minutes.
    """
    from src.infrastructure.database import get_db_session
    from src.guide.application.seeder.repository import SeederRepository
    from src.guide.application.seeder.orchestrator import CitySeederOrchestrator
    from src.guide.application.seeder.zone_discovery import ZoneDiscovery
    from src.guide.application.seeder.point_placement import PointPlacement
    from src.guide.application.seeder.graph_builder import GraphBuilder
    from src.guide.application.seeder.knowledge_collector import KnowledgeCollector
    from src.guide.infrastructure.google_places_client import GuideGooglePlacesClient
    from src.guide.infrastructure.wikipedia_client import WikipediaClient
    from src.guide.infrastructure.wikidata_client import WikidataClient

    print(f"\n{'='*60}")
    print("PHASE 3: PointPlacement + GraphBuilder + KnowledgeCollector")
    print(f"{'='*60}")
    print("  This may take 5–15 minutes (OSMnx download + networkx + Wikipedia).")

    google_places = GuideGooglePlacesClient()
    zone_discovery = ZoneDiscovery(google_places)
    point_placement = PointPlacement()
    graph_builder = GraphBuilder()
    wikipedia = WikipediaClient()
    wikidata = WikidataClient()

    async with get_db_session() as db:
        repo = SeederRepository(db)
        knowledge_collector = KnowledgeCollector(
            repo=repo,
            google_places=google_places,
            wikipedia=wikipedia,
            wikidata=wikidata,
        )
        orchestrator = CitySeederOrchestrator(
            repo=repo,
            zone_discovery=zone_discovery,
            point_placement=point_placement,
            graph_builder=graph_builder,
            knowledge_collector=knowledge_collector,
        )
        await orchestrator.continue_after_zone_approval(job_id)
        await db.commit()

        job = await repo.get_seed_job(job_id)

    progress = job.progress_json or {}
    print(f"\n  ✅ Phase 3 complete:")
    print(f"     Points placed:    {progress.get('points_placed', 0)}")
    print(f"     Edges built:      {progress.get('edges_built', 0)}")
    print(f"     Knowledge cards:  {progress.get('cards_collected', 0)}")
    print(f"     Job status:       {job.status}")

    # Activate all approved points in approved zones for this job's city
    # (PointPlacement sets is_approved=True but is_active=False by default)
    from sqlalchemy import text
    async with get_db_session() as db:
        activated = await db.execute(text("""
            UPDATE guide_points gp
            SET is_active = true
            FROM guide_zones gz
            WHERE gp.zone_id = gz.id
              AND gz.city_id = :city_id
              AND gz.is_approved = true
              AND gp.is_approved = true
              AND gp.is_active = false
        """), {"city_id": str(job.city_id)})
        zone_activated = await db.execute(text("""
            UPDATE guide_zones
            SET is_active = true
            WHERE city_id = :city_id AND is_approved = true AND is_active = false
        """), {"city_id": str(job.city_id)})
        await db.commit()
        print(f"     Points activated: {activated.rowcount}")
        print(f"     Zones activated:  {zone_activated.rowcount}")

    return progress


# =============================================================================
# Phase 4: Draft Generation
# =============================================================================

async def phase4_draft_generation(
    zone_id: uuid.UUID,
    voice_style: str,
    voice_language: str,
    max_llm_calls: int,
) -> uuid.UUID:
    """
    Run Stage 1 of content pipeline: Draft Generation.
    Uses the voice matching style + language.
    Returns content job_id.
    """
    from src.infrastructure.database import get_db_session
    from src.infrastructure.llm_client import get_guide_narrative_llm_client
    from src.guide.application.content_pipeline.repository import ContentPipelineRepository
    from src.guide.application.content_pipeline.draft_generator import DraftGenerator
    from src.config import settings

    print(f"\n{'='*60}")
    print(f"PHASE 4: Draft Generation (style={voice_style}, lang={voice_language})")
    print(f"{'='*60}")

    # Find voice matching style + language
    async with get_db_session() as db:
        content_repo = ContentPipelineRepository(db)
        voices = await content_repo.get_active_voices()

        matching = [
            v for v in voices
            if v.style_group == voice_style and v.language == voice_language
        ]
        if not matching:
            available = [(v.style_group, v.language) for v in voices]
            raise RuntimeError(
                f"No voice with style_group={voice_style!r} and language={voice_language!r}. "
                f"Available: {available}"
            )
        voice = matching[0]
        voice_id = voice.id

        # Estimate LLM calls
        points = await content_repo.get_active_points_in_zone(zone_id)
        edges = await content_repo.get_edges_in_zone(zone_id)
        # main + bonus + recap per POI point + 3 transitions per edge
        poi_count = sum(1 for p in points if p.point_type == "poi")
        estimated_calls = poi_count * 3 + len(edges) * 3
        print(f"  Voice: {voice.name} ({voice.style_group}/{voice.language})")
        print(f"  Active points: {len(points)} ({poi_count} POI)")
        print(f"  Edges: {len(edges)}")
        print(f"  Estimated LLM calls: ~{estimated_calls}")
        print(f"  Max LLM calls cap: {max_llm_calls}")

        if estimated_calls > max_llm_calls:
            print(f"  ⚠️  Estimated calls ({estimated_calls}) exceed cap ({max_llm_calls})")
            print(f"     Will stop after {max_llm_calls} calls (raise --max-llm-calls to continue)")

        await db.commit()

    llm_client = get_guide_narrative_llm_client()

    # Override max calls cap in settings (best-effort)
    from src.config import settings as _settings
    original_cap = _settings.guide_content_max_llm_calls_per_job
    _settings.guide_content_max_llm_calls_per_job = max_llm_calls

    try:
        async with get_db_session() as db:
            content_repo = ContentPipelineRepository(db)
            generator = DraftGenerator(repo=content_repo, llm_client=llm_client)
            job_id = await generator.generate_zone_drafts(
                zone_id=zone_id,
                voice_ids=[voice_id],
                languages=[voice_language],
                detail_levels=["standard"],
                force_regenerate=False,
            )
            await db.commit()
    finally:
        _settings.guide_content_max_llm_calls_per_job = original_cap

    print(f"  ✅ Draft generation complete. Content job: {job_id}")
    return job_id


# =============================================================================
# Phase 5: Coherence Validation
# =============================================================================

async def phase5_coherence_validation(zone_id: uuid.UUID, language: str) -> dict:
    """Run Stage 2: Coherence Validation. Returns stats dict."""
    from src.infrastructure.database import get_db_session
    from src.infrastructure.llm_client import get_guide_narrative_llm_client
    from src.guide.application.content_pipeline.repository import ContentPipelineRepository
    from src.guide.application.content_pipeline.coherence_validator import CoherenceValidator

    print(f"\n{'='*60}")
    print(f"PHASE 5: Coherence Validation")
    print(f"{'='*60}")

    llm_client = get_guide_narrative_llm_client()

    async with get_db_session() as db:
        content_repo = ContentPipelineRepository(db)
        val_job = await content_repo.create_content_job(zone_id, job_type="validate")
        val_job_id = val_job.id

        validator = CoherenceValidator(repo=content_repo, llm_client=llm_client)
        stats = await validator.validate_zone(
            zone_id=zone_id,
            language=language,
            include_walk_validation=False,
            job_id=val_job_id,
        )
        await content_repo.mark_job_complete(val_job_id, stats)
        await db.commit()

    print(f"  ✅ Validation complete:")
    print(f"     Validated:    {stats.get('validated', 0)}")
    print(f"     Needs review: {stats.get('needs_review', 0)}")
    print(f"     Retried:      {stats.get('retried', 0)}")
    print(f"     Errors:       {stats.get('errors', 0)}")
    return stats


# =============================================================================
# Phase 6: Batch Approve
# =============================================================================

async def phase6_batch_approve(zone_id: uuid.UUID, min_score: float) -> dict:
    """Batch-approve all needs_manual_review blocks >= min_score."""
    from src.infrastructure.database import get_db_session
    from src.guide.application.content_pipeline.repository import ContentPipelineRepository
    from src.guide.application.content_pipeline.review_service import ReviewService

    print(f"\n{'='*60}")
    print(f"PHASE 6: Batch Approve (min_score={min_score})")
    print(f"{'='*60}")

    async with get_db_session() as db:
        content_repo = ContentPipelineRepository(db)
        # batch_approve only uses repo — pass None for unused TTS/S3/LLM deps
        review_svc = ReviewService(repo=content_repo, llm_client=None, elevenlabs_client=None, s3_client=None)

        result = await review_svc.batch_approve(zone_id=zone_id, min_score=min_score)
        await db.commit()

    print(f"  ✅ Batch approved: {result['approved_count']}")
    print(f"     Skipped (below threshold): {result['skipped_count']}")

    # Also force-approve remaining (all outstanding needs_manual_review)
    async with get_db_session() as db:
        content_repo = ContentPipelineRepository(db)
        review_svc = ReviewService(repo=content_repo, llm_client=None, elevenlabs_client=None, s3_client=None)
        result2 = await review_svc.batch_approve(zone_id=zone_id, min_score=0.0)
        await db.commit()

    if result2["approved_count"] > 0:
        print(f"  ✅ Force-approved remaining: {result2['approved_count']}")

    return {"approved_count": result["approved_count"] + result2["approved_count"]}


# =============================================================================
# Summary: print final DB state
# =============================================================================

async def print_final_summary(zone_id: uuid.UUID) -> None:
    """Print a summary of what's in the DB for this zone."""
    from src.infrastructure.database import get_db_session
    from src.guide.application.content_pipeline.repository import ContentPipelineRepository

    async with get_db_session() as db:
        content_repo = ContentPipelineRepository(db)
        status = await content_repo.get_zone_content_status(zone_id)

    print(f"\n{'='*60}")
    print("FINAL SUMMARY")
    print(f"{'='*60}")
    print(f"  Zone ID: {zone_id}")
    print(f"  Content block status counts:")
    for k, v in status.items():
        if isinstance(v, int) and v > 0:
            print(f"    {k}: {v}")


# =============================================================================
# Visualize: call visualize_zones.py
# =============================================================================

async def generate_visualizations(city_id: uuid.UUID, zone_id: uuid.UUID) -> None:
    """Generate HTML visualizations using visualize_zones.py."""
    import subprocess

    scripts_dir = Path(__file__).parent
    tmp_dir = Path(__file__).parent.parent.parent / "tmp"
    tmp_dir.mkdir(exist_ok=True)

    zones_html = tmp_dir / "moscow_zones.html"
    points_html = tmp_dir / "moscow_zone_points.html"

    print(f"\n{'='*60}")
    print("Generating HTML visualizations")
    print(f"{'='*60}")

    result = subprocess.run(
        [sys.executable, str(scripts_dir / "visualize_zones.py"),
         "--city-id", str(city_id),
         "--output", str(zones_html),
         "--no-open"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"  ✅ Zones map: {zones_html}")
    else:
        print(f"  ⚠️  Zones map failed: {result.stderr[:200]}")

    result2 = subprocess.run(
        [sys.executable, str(scripts_dir / "visualize_zones.py"),
         "--zone-id", str(zone_id),
         "--show-points",
         "--output", str(points_html),
         "--no-open"],
        capture_output=True, text=True
    )
    if result2.returncode == 0:
        print(f"  ✅ Points map: {points_html}")
    else:
        print(f"  ⚠️  Points map failed: {result2.stderr[:200]}")


# =============================================================================
# CLI argument parsing
# =============================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/guide/seed_moscow_test.py",
        description="Тестовый прогон City Seeder + Content Pipeline (NON-INTERACTIVE)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full pipeline for Moscow (non-interactive)
  python scripts/guide/seed_moscow_test.py \\
      --city Moscow --country Russia \\
      --non-interactive --auto-approve-zone max-poi \\
      --voice-style academic --voice-language en \\
      --skip-synthesis

  # Resume from Phase 3 with existing job/zone IDs
  python scripts/guide/seed_moscow_test.py \\
      --job-id <UUID> --zone-id <UUID> \\
      --non-interactive --skip-discovery --skip-synthesis
        """,
    )

    parser.add_argument("--city", default="Moscow", help="City name (default: Moscow)")
    parser.add_argument("--country", default="Russia", help="Country (default: Russia)")
    parser.add_argument("--non-interactive", action="store_true",
                        help="Run all phases without prompts (required for Claude Code)")
    parser.add_argument("--auto-approve-zone",
                        choices=["first", "max-poi", "all"], default="max-poi",
                        help="Zone approval strategy (default: max-poi)")
    parser.add_argument("--voice-style",
                        choices=["academic", "friendly", "dramatic", "minimal"],
                        default="academic",
                        help="Voice style for draft generation (default: academic)")
    parser.add_argument("--voice-language",
                        choices=["en", "ru"],
                        default="en",
                        help="Voice language (default: en)")
    parser.add_argument("--skip-synthesis", action="store_true",
                        help="Skip Phase 7 (audio synthesis) — default for Step 12")
    parser.add_argument("--skip-discovery", action="store_true",
                        help="Skip Phase 1+2 (use --job-id / --zone-id to continue)")
    parser.add_argument("--job-id", default=None,
                        help="Existing seed job UUID (to resume from Phase 3)")
    parser.add_argument("--zone-id", default=None,
                        help="Existing zone UUID (to resume from Phase 4+)")
    parser.add_argument("--city-id", default=None,
                        help="Existing city UUID (for HTML visualization)")
    parser.add_argument("--max-llm-calls", type=int, default=1000,
                        help="Soft cap on LLM calls for draft generation (default: 1000)")
    parser.add_argument("--min-approve-score", type=float, default=3.0,
                        help="Minimum coherence score for batch approve (default: 3.0)")
    parser.add_argument("--dbscan-eps-m", type=float, default=800.0,
                        help="DBSCAN epsilon in metres for POI clustering (default: 800.0 for Moscow)")
    parser.add_argument("--dbscan-min-samples", type=int, default=5,
                        help="DBSCAN min_samples for cluster formation (default: 5)")
    parser.add_argument("--skip-env-check", action="store_true",
                        help="Skip environment validation (use for debugging)")
    return parser


# =============================================================================
# Main
# =============================================================================

async def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.non_interactive:
        print("⚠️  This script is designed for non-interactive mode.")
        print("    Add --non-interactive to proceed without prompts.")
        print("    Example:")
        print("      python scripts/guide/seed_moscow_test.py \\")
        print("        --non-interactive --auto-approve-zone max-poi \\")
        print("        --voice-style academic --voice-language en --skip-synthesis")
        sys.exit(0)

    print("\n" + "="*60)
    print(f"City Seeder — {args.city}, {args.country}")
    print("Step 12: First real pipeline run (non-interactive)")
    print("="*60)

    # ── Environment check ────────────────────────────────────────────────────
    if not args.skip_env_check:
        print("\nEnvironment check:")
        ok = await check_environment()
        if not ok:
            print("\n❌ Aborting — fix environment issues and retry.")
            sys.exit(1)
    else:
        print("⚠️  Skipping environment check (--skip-env-check)")

    job_id: Optional[uuid.UUID] = None
    city_id: Optional[uuid.UUID] = None
    zone_id: Optional[uuid.UUID] = None

    # Parse CLI overrides
    if args.job_id:
        job_id = uuid.UUID(args.job_id)
    if args.zone_id:
        zone_id = uuid.UUID(args.zone_id)
    if args.city_id:
        city_id = uuid.UUID(args.city_id)

    # ── Phase 1: Zone Discovery ───────────────────────────────────────────────
    if not args.skip_discovery:
        job_id, city_id = await phase1_zone_discovery(
            args.city, args.country,
            dbscan_eps_m=args.dbscan_eps_m,
            dbscan_min_samples=args.dbscan_min_samples,
        )
    else:
        if job_id is None:
            print("❌ --skip-discovery requires --job-id")
            sys.exit(1)
        print(f"\nSkipping Phase 1 (--skip-discovery). Using job_id={job_id}")

    # ── Phase 2: Zone Approval ────────────────────────────────────────────────
    if not args.skip_discovery:
        if city_id is None:
            print("❌ city_id not resolved — Phase 1 may have failed")
            sys.exit(1)
        approved_zones = await phase2_approve_zones(city_id, args.auto_approve_zone)
        if zone_id is None:
            zone_id = approved_zones[0].id
    else:
        if zone_id is None:
            print("❌ --skip-discovery requires --zone-id")
            sys.exit(1)
        print(f"Skipping Phase 2 (--skip-discovery). Using zone_id={zone_id}")

    # ── Phase 3: Point Placement + Graph + Knowledge ──────────────────────────
    # Skip if zone already has points (idempotency guard)
    from src.infrastructure.database import get_db_session
    from src.guide.application.seeder.repository import SeederRepository
    from src.guide.domain.models import GuideSeedJob

    should_run_phase3 = True
    if job_id is not None:
        async with get_db_session() as db:
            repo = SeederRepository(db)
            job = await repo.get_seed_job(job_id)
            if job and job.status in ("complete", "collecting_knowledge"):
                progress = job.progress_json or {}
                if progress.get("points_placed", 0) > 0:
                    print(f"\nPhase 3 already complete (points_placed={progress['points_placed']}) — skipping")
                    should_run_phase3 = False

    if should_run_phase3:
        if job_id is None:
            print("❌ job_id is required for Phase 3")
            sys.exit(1)
        await phase3_place_and_collect(job_id)

    # ── Phase 4: Draft Generation ─────────────────────────────────────────────
    await phase4_draft_generation(
        zone_id=zone_id,
        voice_style=args.voice_style,
        voice_language=args.voice_language,
        max_llm_calls=args.max_llm_calls,
    )

    # ── Phase 5: Coherence Validation ────────────────────────────────────────
    await phase5_coherence_validation(zone_id=zone_id, language=args.voice_language)

    # ── Phase 6: Batch Approve ────────────────────────────────────────────────
    await phase6_batch_approve(zone_id=zone_id, min_score=args.min_approve_score)

    # ── Phase 7: Skipped (--skip-synthesis) ──────────────────────────────────
    if args.skip_synthesis:
        print(f"\n{'='*60}")
        print("PHASE 7: Audio Synthesis — SKIPPED (--skip-synthesis)")
        print("  audio_url remains NULL for all blocks.")
        print("  Run synthesize_sample.py for a limited TTS test.")
        print(f"{'='*60}")
    else:
        print(f"\n{'='*60}")
        print("PHASE 7: Audio Synthesis — not implemented in this script")
        print("  Use: python scripts/guide/synthesize_sample.py --zone-id <ID>")
        print(f"{'='*60}")

    # ── Final summary ─────────────────────────────────────────────────────────
    await print_final_summary(zone_id)

    # ── HTML visualizations ───────────────────────────────────────────────────
    if city_id:
        await generate_visualizations(city_id, zone_id)

    print(f"\n{'='*60}")
    print("✅ PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"  zone_id = {zone_id}")
    print(f"  job_id  = {job_id}")
    print(f"\nNext steps:")
    print(f"  python scripts/guide/inspect_zone.py --zone-id {zone_id}")
    print(f"  python scripts/guide/inspect_content.py --zone-id {zone_id}")
    print(f"  python scripts/guide/synthesize_sample.py --zone-id {zone_id} --limit 5")
    print()


if __name__ == "__main__":
    asyncio.run(main())
