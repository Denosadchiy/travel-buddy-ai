"""
Content Pipeline CLI — Stage 1 through 4.

Usage:
    # Stage 1: Draft generation
    python -m src.guide.application.content_pipeline.cli generate --zone-id <UUID>
    python -m src.guide.application.content_pipeline.cli generate --zone-id <UUID> --dry-run
    python -m src.guide.application.content_pipeline.cli generate --zone-id <UUID> --voice-id <UUID> --language en
    python -m src.guide.application.content_pipeline.cli generate --zone-id <UUID> --force-regenerate

    # Stage 2: Coherence validation
    python -m src.guide.application.content_pipeline.cli validate --zone-id <UUID>
    python -m src.guide.application.content_pipeline.cli validate --zone-id <UUID> --language en
    python -m src.guide.application.content_pipeline.cli validate --zone-id <UUID> --include-walk-validation

    # Stage 4: Audio synthesis
    python -m src.guide.application.content_pipeline.cli synthesize --zone-id <UUID>
    python -m src.guide.application.content_pipeline.cli synthesize --zone-id <UUID> --force-resynthesize

    # Status
    python -m src.guide.application.content_pipeline.cli status --job-id <UUID>
    python -m src.guide.application.content_pipeline.cli status --zone-id <UUID>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import uuid

logger = logging.getLogger(__name__)


# ============================================================================
# Commands
# ============================================================================

async def cmd_generate(
    zone_id: uuid.UUID,
    voice_ids: list[uuid.UUID] | None,
    languages: list[str] | None,
    detail_levels: list[str] | None,
    force_regenerate: bool,
    dry_run: bool,
) -> None:
    from src.infrastructure.database import get_db_session
    from src.infrastructure.llm_client import get_guide_narrative_llm_client
    from src.guide.application.content_pipeline.repository import ContentPipelineRepository
    from src.guide.application.content_pipeline.draft_generator import DraftGenerator

    if dry_run:
        print(f"[dry-run] Starting content generation for zone {zone_id} — no LLM calls will be made.")

    llm_client = get_guide_narrative_llm_client()

    async with get_db_session() as db:
        repo = ContentPipelineRepository(db)
        generator = DraftGenerator(repo=repo, llm_client=llm_client)

        job_id = await generator.generate_zone_drafts(
            zone_id=zone_id,
            voice_ids=voice_ids,
            languages=languages,
            detail_levels=detail_levels,
            force_regenerate=force_regenerate,
            dry_run=dry_run,
        )
        await db.commit()

    print(f"Content generation job: {job_id}")
    print(f"    Zone: {zone_id}")
    if dry_run:
        print("    Mode: DRY RUN — no content written to DB")
    print(f"    Run 'status --job-id {job_id}' to check progress.")


async def cmd_validate(
    zone_id: uuid.UUID,
    language: str | None,
    include_walk_validation: bool,
) -> None:
    from src.infrastructure.database import get_db_session
    from src.infrastructure.llm_client import get_guide_narrative_llm_client
    from src.guide.application.content_pipeline.repository import ContentPipelineRepository
    from src.guide.application.content_pipeline.coherence_validator import CoherenceValidator

    llm_client = get_guide_narrative_llm_client()

    async with get_db_session() as db:
        repo = ContentPipelineRepository(db)
        job = await repo.create_content_job(zone_id, job_type="validate")
        job_id = job.id

        validator = CoherenceValidator(repo=repo, llm_client=llm_client)
        stats = await validator.validate_zone(
            zone_id=zone_id,
            language=language,
            include_walk_validation=include_walk_validation,
            job_id=job_id,
        )
        await repo.mark_job_complete(job_id, stats)
        await db.commit()

    print(f"Coherence validation complete for zone {zone_id}")
    print(f"    Job: {job_id}")
    print(f"    Validated:     {stats['validated']}")
    print(f"    Needs review:  {stats['needs_review']}")
    print(f"    Retried:       {stats['retried']}")
    print(f"    Errors:        {stats['errors']}")


async def cmd_synthesize(
    zone_id: uuid.UUID,
    voice_ids: list[uuid.UUID] | None,
    force_resynthesize: bool,
) -> None:
    from src.infrastructure.database import get_db_session
    from src.guide.application.content_pipeline.repository import ContentPipelineRepository
    from src.guide.application.content_pipeline.audio_synthesizer import AudioSynthesizer
    from src.guide.infrastructure.elevenlabs_client import ElevenLabsClient
    from src.guide.infrastructure.s3_client import GuideS3Client

    tts = ElevenLabsClient()
    s3 = GuideS3Client()

    async with get_db_session() as db:
        repo = ContentPipelineRepository(db)
        job = await repo.create_content_job(zone_id, job_type="synthesize")
        job_id = job.id

        synthesizer = AudioSynthesizer(repo=repo, elevenlabs_client=tts, s3_client=s3)
        stats = await synthesizer.synthesize_zone(
            zone_id=zone_id,
            voice_ids=voice_ids,
            force_resynthesize=force_resynthesize,
            job_id=job_id,
        )
        await db.commit()

    print(f"Audio synthesis complete for zone {zone_id}")
    print(f"    Job:           {job_id}")
    print(f"    Synthesized:   {stats['synthesized']}")
    print(f"    Failed:        {stats['failed']}")
    print(f"    Total duration: {stats['total_duration_s']:.1f}s ({stats['total_duration_s']/60:.1f}min)")
    if stats.get("spot_check_urls"):
        print("    Spot-check URLs:")
        for url in stats["spot_check_urls"]:
            print(f"      {url}")


async def cmd_status(job_id: uuid.UUID | None, zone_id: uuid.UUID | None) -> None:
    from src.infrastructure.database import get_db_session
    from src.guide.domain.models import GuideContentJob
    from sqlalchemy import select

    async with get_db_session() as db:
        if job_id is not None:
            result = await db.get(GuideContentJob, job_id)
            jobs = [result] if result else []
        elif zone_id is not None:
            stmt = (
                select(GuideContentJob)
                .where(GuideContentJob.zone_id == zone_id)
                .order_by(GuideContentJob.created_at.desc())
                .limit(10)
            )
            res = await db.execute(stmt)
            jobs = list(res.scalars().all())
        else:
            print("Provide --job-id or --zone-id", file=sys.stderr)
            sys.exit(1)

    if not jobs:
        print(f"No jobs found", file=sys.stderr)
        sys.exit(1)

    for job in jobs:
        print(f"\nJob ID:       {job.id}")
        print(f"Zone:         {job.zone_id}")
        print(f"Type:         {job.job_type}")
        print(f"Status:       {job.status}")
        print(f"Created:      {job.created_at}")
        print(f"Completed:    {job.completed_at or '—'}")
        if job.error_message:
            print(f"Error:        {job.error_message}")
        print("Progress:")
        print(json.dumps(job.progress_json or {}, indent=2))


# ============================================================================
# Argument parser
# ============================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.guide.application.content_pipeline.cli",
        description="Content Pipeline — Stages 1–4.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # generate (Stage 1)
    gen_p = sub.add_parser("generate", help="Generate draft content blocks for a zone (Stage 1)")
    gen_p.add_argument("--zone-id", required=True, help="UUID of the guide zone")
    gen_p.add_argument("--voice-id", default=None, help="Limit to a single voice UUID")
    gen_p.add_argument("--language", default=None, help="Language code, e.g. 'en' or 'ru'")
    gen_p.add_argument("--detail-level", default=None, help="'standard' or 'brief'")
    gen_p.add_argument("--force-regenerate", action="store_true",
                       help="Re-generate even blocks with draft/validated status")
    gen_p.add_argument("--dry-run", action="store_true",
                       help="Build prompts and log them but make no LLM calls")

    # validate (Stage 2)
    val_p = sub.add_parser("validate", help="Run coherence validation on draft blocks (Stage 2)")
    val_p.add_argument("--zone-id", required=True, help="UUID of the guide zone")
    val_p.add_argument("--language", default=None, help="Validate only this language (default: all)")
    val_p.add_argument("--include-walk-validation", action="store_true",
                       help="Also run end-to-end walk validation (optional)")

    # synthesize (Stage 4)
    syn_p = sub.add_parser("synthesize", help="Synthesize audio for reviewed blocks (Stage 4)")
    syn_p.add_argument("--zone-id", required=True, help="UUID of the guide zone")
    syn_p.add_argument("--voice-id", default=None, help="Limit to a single voice UUID")
    syn_p.add_argument("--force-resynthesize", action="store_true",
                       help="Re-synthesize blocks that already have audio")

    # status
    status_p = sub.add_parser("status", help="Show content job status")
    status_p.add_argument("--job-id", default=None, help="UUID of a specific content job")
    status_p.add_argument("--zone-id", default=None, help="List recent jobs for a zone")

    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = build_parser()
    args = parser.parse_args()

    def _parse_uuid(val: str, name: str) -> uuid.UUID:
        try:
            return uuid.UUID(val)
        except ValueError:
            print(f"Invalid {name} UUID: {val}", file=sys.stderr)
            sys.exit(1)

    if args.command == "generate":
        zone_id = _parse_uuid(args.zone_id, "zone-id")
        voice_ids = [_parse_uuid(args.voice_id, "voice-id")] if args.voice_id else None
        languages = [args.language] if args.language else None
        detail_levels = [args.detail_level] if args.detail_level else None
        asyncio.run(cmd_generate(
            zone_id=zone_id,
            voice_ids=voice_ids,
            languages=languages,
            detail_levels=detail_levels,
            force_regenerate=args.force_regenerate,
            dry_run=args.dry_run,
        ))

    elif args.command == "validate":
        zone_id = _parse_uuid(args.zone_id, "zone-id")
        asyncio.run(cmd_validate(
            zone_id=zone_id,
            language=args.language,
            include_walk_validation=args.include_walk_validation,
        ))

    elif args.command == "synthesize":
        zone_id = _parse_uuid(args.zone_id, "zone-id")
        voice_ids = [_parse_uuid(args.voice_id, "voice-id")] if args.voice_id else None
        asyncio.run(cmd_synthesize(
            zone_id=zone_id,
            voice_ids=voice_ids,
            force_resynthesize=args.force_resynthesize,
        ))

    elif args.command == "status":
        job_id = _parse_uuid(args.job_id, "job-id") if args.job_id else None
        zone_id = _parse_uuid(args.zone_id, "zone-id") if args.zone_id else None
        asyncio.run(cmd_status(job_id=job_id, zone_id=zone_id))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
