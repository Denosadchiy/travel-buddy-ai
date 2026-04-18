"""
Топап Content Pipeline для существующей зоны.

Идемпотентно дополняет недостающий контент:
  - main / bonus / recap для POI-точек (connector пропускает — экономия LLM)
  - transitions для рёбер, выходящих из POI-точек

НЕ затрагивает:
  - уже существующие validated/reviewed блоки
  - connector-точки (main/bonus)
  - синтез аудио (Phase 7)

Запуск:
    python scripts/guide/topup_content.py \\
        --zone-id 04bb6ef2-3914-4920-b721-432c8502a1c8 \\
        --voice-style academic \\
        --voice-language en \\
        --max-llm-calls 500 \\
        --non-interactive
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from uuid import UUID

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("topup_content")


async def print_zone_status(content_repo, zone_id: UUID, label: str) -> dict:
    """Print current content status for the zone and return raw dict."""
    from src.guide.domain.models import GuideContentBlock
    from sqlalchemy import select, func

    async with content_repo._db.begin_nested() if hasattr(content_repo._db, 'begin_nested') else _noop():
        pass

    stmt = (
        select(
            GuideContentBlock.content_type,
            GuideContentBlock.generation_status,
            func.count().label("cnt"),
        )
        .where(GuideContentBlock.zone_id == zone_id)
        .group_by(GuideContentBlock.content_type, GuideContentBlock.generation_status)
        .order_by(GuideContentBlock.content_type, GuideContentBlock.generation_status)
    )
    result = await content_repo._db.execute(stmt)
    rows = result.all()

    total_stmt = (
        select(GuideContentBlock.generation_status, func.count().label("cnt"))
        .where(GuideContentBlock.zone_id == zone_id)
        .group_by(GuideContentBlock.generation_status)
    )
    total_result = await content_repo._db.execute(total_stmt)
    totals = {row.generation_status: row.cnt for row in total_result}

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  {'TYPE':<20} {'STATUS':<20} {'COUNT':>6}")
    print(f"  {'-'*46}")
    for row in rows:
        print(f"  {row.content_type:<20} {row.generation_status:<20} {row.cnt:>6}")
    print(f"  {'-'*46}")
    print(f"  Total blocks: {sum(totals.values())}")
    for status, cnt in sorted(totals.items()):
        print(f"    {status}: {cnt}")
    return totals


class _noop:
    """No-op async context manager."""
    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass


async def run_topup(
    zone_id: UUID,
    voice_style: str,
    voice_language: str,
    max_llm_calls: int,
    force_regenerate_main: bool = False,
) -> None:
    from src.infrastructure.database import get_db_session
    from src.infrastructure.llm_client import get_guide_narrative_llm_client
    from src.guide.application.content_pipeline.repository import ContentPipelineRepository
    from src.guide.application.content_pipeline.draft_generator import DraftGenerator
    from src.guide.application.content_pipeline.coherence_validator import CoherenceValidator
    from src.guide.application.content_pipeline.review_service import ReviewService
    from src.config import settings

    llm_client = get_guide_narrative_llm_client()

    # ── Step 0: Show current state ────────────────────────────────────────────
    async with get_db_session() as db:
        content_repo = ContentPipelineRepository(db)

        voices = await content_repo.get_active_voices()
        target_voice = next(
            (v for v in voices if v.style_group == voice_style and v.language == voice_language),
            None,
        )
        if target_voice is None:
            available = [(v.style_group, v.language) for v in voices]
            print(f"ERROR: No voice with style_group={voice_style!r} language={voice_language!r}")
            print(f"Available: {available}")
            return

        print(f"\nVoice: {target_voice.name} ({target_voice.style_group}/{target_voice.language})")
        await print_zone_status(content_repo, zone_id, "BEFORE TOPUP")
        await db.commit()

    # ── Step 0.5: Force-regenerate main blocks if requested ─────────────────
    if force_regenerate_main:
        print(f"\n{'='*60}")
        print("STEP 0.5: Reset existing main blocks to pending (force-regenerate-main)")
        print(f"{'='*60}")
        from sqlalchemy import text as sa_text
        async with get_db_session() as db:
            result = await db.execute(sa_text("""
                UPDATE guide_content_blocks
                SET generation_status = 'pending', coherence_score = NULL
                WHERE zone_id = :zone_id
                  AND voice_id = :voice_id
                  AND language = :lang
                  AND content_type = 'main'
                  AND generation_status IN ('draft', 'validated', 'reviewed', 'needs_manual_review')
            """), {"zone_id": str(zone_id), "voice_id": str(target_voice.id), "lang": voice_language})
            reset_count = result.rowcount
            await db.commit()
        print(f"  Reset {reset_count} main blocks to 'pending'")

    # ── Step 1: Fill missing main/bonus/recap for POI only ───────────────────
    print(f"\n{'='*60}")
    print("STEP 1: main/bonus/recap for POI points (skip_transitions=True)")
    print(f"{'='*60}")

    async with get_db_session() as db:
        content_repo = ContentPipelineRepository(db)
        generator = DraftGenerator(repo=content_repo, llm_client=llm_client)

        # Override cap for this step (POI pass is cheap — mostly idempotent)
        settings.guide_content_max_llm_calls_per_job = max_llm_calls

        job_id = await generator.generate_zone_drafts(
            zone_id=zone_id,
            voice_ids=[target_voice.id],
            languages=[voice_language],
            detail_levels=["standard"],
            force_regenerate=False,
            poi_only=True,
            skip_transitions=True,
        )
        await db.commit()
        print(f"  Draft generation job: {job_id}")

    # ── Step 2: Transitions for POI edges only ────────────────────────────────
    print(f"\n{'='*60}")
    print("STEP 2: transitions for POI-edges only")
    print(f"{'='*60}")
    calls_used_step1 = 0  # idempotent step, usually 0

    async with get_db_session() as db:
        content_repo = ContentPipelineRepository(db)
        generator = DraftGenerator(repo=content_repo, llm_client=llm_client)

        trans_result = await generator.generate_transitions_only(
            zone_id=zone_id,
            voice_ids=[target_voice.id],
            languages=[voice_language],
            poi_edges_only=True,
            force_regenerate=False,
            max_calls=max_llm_calls,
        )
        await db.commit()

    print(f"  Edges processed: {trans_result['edges_processed']} / {trans_result['edges_total']}")
    print(f"  Transition blocks created: {trans_result['blocks_created']}")
    print(f"  LLM calls (transitions): {trans_result['llm_calls']}")

    # ── Step 3: Coherence Validation ─────────────────────────────────────────
    print(f"\n{'='*60}")
    print("STEP 3: Coherence Validation (new draft blocks)")
    print(f"{'='*60}")

    async with get_db_session() as db:
        content_repo = ContentPipelineRepository(db)
        validator = CoherenceValidator(repo=content_repo, llm_client=llm_client)
        val_job = await content_repo.create_content_job(zone_id, job_type="validate_topup")
        stats = await validator.validate_zone(
            zone_id=zone_id,
            language=voice_language,
            include_walk_validation=False,
            job_id=val_job.id,
        )
        await content_repo.mark_job_complete(val_job.id, stats)
        await db.commit()

    print(f"  Validated:    {stats.get('validated', 0)}")
    print(f"  Needs review: {stats.get('needs_review', 0)}")
    print(f"  Errors:       {stats.get('errors', 0)}")

    # ── Step 4: Batch Approve ─────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("STEP 4: Batch Approve (score >= 3.0)")
    print(f"{'='*60}")

    async with get_db_session() as db:
        content_repo = ContentPipelineRepository(db)
        review_svc = ReviewService(
            repo=content_repo,
            llm_client=None,
            elevenlabs_client=None,
            s3_client=None,
        )
        result = await review_svc.batch_approve(
            zone_id=zone_id,
            min_score=3.0,
            language=voice_language,
        )
        await db.commit()

    print(f"  Auto-approved: {result['approved_count']}")
    print(f"  Skipped (low score): {result['skipped_count']}")

    # ── Step 5: Final state ───────────────────────────────────────────────────
    async with get_db_session() as db:
        content_repo = ContentPipelineRepository(db)
        final_totals = await print_zone_status(content_repo, zone_id, "AFTER TOPUP")
        await db.commit()

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("TOPUP COMPLETE")
    print(f"{'='*60}")
    print(f"  Zone:           {zone_id}")
    print(f"  Voice:          {voice_style}/{voice_language}")
    print(f"  Transition LLM: {trans_result['llm_calls']} calls")
    print(f"  Validated:      {stats.get('validated', 0)}")
    print(f"  Reviewed total: {final_totals.get('reviewed', 0)}")
    print(f"\n  Ready for Step 12.5 emulator: {'✅ YES' if final_totals.get('reviewed', 0) >= 5 else '⚠️ NOT ENOUGH'}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python scripts/guide/topup_content.py",
        description="Топап Content Pipeline — дополняет недостающие main/recap/transitions для POI",
    )
    parser.add_argument("--zone-id", required=True, help="UUID зоны")
    parser.add_argument("--voice-style", default="academic", choices=["academic", "friendly", "dramatic", "minimal"])
    parser.add_argument("--voice-language", default="en", choices=["en", "ru"])
    parser.add_argument("--max-llm-calls", type=int, default=500, help="Лимит LLM вызовов (hard cap)")
    parser.add_argument("--non-interactive", action="store_true", help="Без интерактивных промптов")
    parser.add_argument("--force-regenerate-main", action="store_true",
                        help="Reset existing main blocks to pending and regenerate with updated prompt")
    parser.add_argument("--parallel-concurrency", type=int, default=1,
                        help="Parallel LLM requests (default: 1 sequential)")
    args = parser.parse_args()

    if not args.non_interactive:
        print("Add --non-interactive to run without prompts")
        sys.exit(0)

    asyncio.run(run_topup(
        zone_id=UUID(args.zone_id),
        voice_style=args.voice_style,
        voice_language=args.voice_language,
        max_llm_calls=args.max_llm_calls,
        force_regenerate_main=args.force_regenerate_main,
    ))


if __name__ == "__main__":
    main()
