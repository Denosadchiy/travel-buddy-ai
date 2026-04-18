"""
Sample audio synthesis — synthesize a limited number of content blocks for testing.

Picks the highest-priority reviewed blocks (main POI first), synthesizes each
via ElevenLabs, uploads to S3, and saves locally to tmp/synthesized_samples/.

Usage:
    python scripts/guide/synthesize_sample.py --zone-id <UUID> --limit 5
    python scripts/guide/synthesize_sample.py --zone-id <UUID> --limit 5 --dry-run

Options:
    --zone-id    UUID of the zone (required)
    --limit      Max blocks to synthesize (default: 5)
    --dry-run    List blocks without synthesizing (no API calls)
    --local-only Save audio locally only, skip S3 upload
    --voice-id   Override voice UUID (default: first active voice in zone)
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import sys
from pathlib import Path
from uuid import UUID

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# =============================================================================
# Block selection
# =============================================================================

async def select_blocks_for_synthesis(
    zone_id: UUID,
    limit: int,
    voice_id: UUID | None,
) -> list:
    """
    Select up to `limit` reviewed blocks for synthesis.

    Priority order:
      1. main POI blocks
      2. bonus POI blocks
      3. recap blocks
      4. transition blocks
    """
    from src.infrastructure.database import get_db_session
    from src.guide.domain.models import GuideContentBlock, GuidePoint, GuideVoice
    from sqlalchemy import select, case

    async with get_db_session() as db:

        # Find voice to use
        if voice_id is None:
            voices_result = await db.execute(
                select(GuideVoice).where(GuideVoice.is_active.is_(True)).limit(1)
            )
            voice = voices_result.scalar_one_or_none()
            if voice is None:
                raise RuntimeError("No active voices found in guide_voices table")
            voice_id = voice.id
            voice_name = voice.name
            elevenlabs_voice_id = voice.elevenlabs_voice_id
        else:
            voice = await db.get(GuideVoice, voice_id)
            if voice is None:
                raise RuntimeError(f"Voice {voice_id} not found")
            voice_name = voice.name
            elevenlabs_voice_id = voice.elevenlabs_voice_id

        # Priority ordering
        priority = case(
            (GuideContentBlock.content_type == "main", 1),
            (GuideContentBlock.content_type == "bonus", 2),
            (GuideContentBlock.content_type == "recap", 3),
            (GuideContentBlock.content_type == "transition", 4),
            else_=5,
        )

        blocks_stmt = (
            select(GuideContentBlock)
            .where(
                GuideContentBlock.zone_id == zone_id,
                GuideContentBlock.voice_id == voice_id,
                GuideContentBlock.generation_status == "reviewed",
                GuideContentBlock.audio_url.is_(None),
            )
            .order_by(priority, GuideContentBlock.coherence_score.desc().nullslast())
            .limit(limit)
        )
        blocks_result = await db.execute(blocks_stmt)
        blocks = list(blocks_result.scalars().all())

        if not blocks:
            # Fall back to 'validated' status if no reviewed blocks
            blocks_stmt2 = (
                select(GuideContentBlock)
                .where(
                    GuideContentBlock.zone_id == zone_id,
                    GuideContentBlock.voice_id == voice_id,
                    GuideContentBlock.generation_status.in_(["validated", "draft"]),
                    GuideContentBlock.audio_url.is_(None),
                )
                .order_by(priority, GuideContentBlock.coherence_score.desc().nullslast())
                .limit(limit)
            )
            blocks_result2 = await db.execute(blocks_stmt2)
            blocks = list(blocks_result2.scalars().all())

        # Get point names for display
        point_ids = list({b.point_id for b in blocks if b.point_id})
        point_names: dict[str, str] = {}
        if point_ids:
            pts_result = await db.execute(
                select(GuidePoint.id, GuidePoint.name).where(GuidePoint.id.in_(point_ids))
            )
            point_names = {str(r.id): r.name or "" for r in pts_result}

    return blocks, voice_id, voice_name, elevenlabs_voice_id, point_names


# =============================================================================
# Synthesis
# =============================================================================

async def synthesize_blocks(
    zone_id: UUID,
    blocks: list,
    voice_id: UUID,
    elevenlabs_voice_id: str,
    point_names: dict,
    local_only: bool,
    dry_run: bool,
) -> list[dict]:
    """Synthesize blocks and return results list."""
    from src.guide.infrastructure.elevenlabs_client import ElevenLabsClient
    from src.guide.infrastructure.s3_client import GuideS3Client
    from src.infrastructure.database import get_db_session
    from src.guide.application.content_pipeline.repository import ContentPipelineRepository

    samples_dir = _ROOT / "tmp" / "synthesized_samples"
    samples_dir.mkdir(parents=True, exist_ok=True)

    tts = ElevenLabsClient()
    s3 = GuideS3Client() if not local_only else None

    results = []

    for i, block in enumerate(blocks):
        pt_name = point_names.get(str(block.point_id), str(block.point_id)[:8])
        char_count = len(block.text_script or "")
        print(f"\n  [{i+1}/{len(blocks)}] {pt_name} — {block.content_type}")
        print(f"          status: {block.generation_status}  |  chars: {char_count}")
        print(f"          script: {(block.text_script or '')[:80]}...")

        if dry_run:
            results.append({
                "block_id": str(block.id),
                "point_name": pt_name,
                "content_type": block.content_type,
                "char_count": char_count,
                "status": "dry_run",
            })
            continue

        try:
            audio_bytes = await tts.synthesize_batch(
                text=block.text_script or "",
                voice_id=elevenlabs_voice_id,
            )
        except Exception as exc:
            print(f"          ❌ TTS failed: {exc}")
            results.append({
                "block_id": str(block.id),
                "point_name": pt_name,
                "content_type": block.content_type,
                "error": str(exc),
            })
            continue

        # Save locally
        safe_name = (pt_name or str(block.id)[:8]).replace("/", "_").replace(" ", "_")
        local_path = samples_dir / f"{i+1:02d}_{block.content_type}_{safe_name}.mp3"
        local_path.write_bytes(audio_bytes)
        print(f"          💾 Saved: {local_path}")

        # Estimate duration (rough: 140 wpm)
        word_count = len((block.text_script or "").split())
        duration_s = round(word_count / 140 * 60, 1)

        cdn_url = None
        if s3 is not None:
            try:
                key = f"guide/samples/{zone_id}/{voice_id}/{block.id}.mp3"
                cdn_url = await s3.upload_audio(key, audio_bytes)
                print(f"          ☁️  CDN: {cdn_url}")
            except Exception as exc:
                print(f"          ⚠️  S3 upload failed: {exc} (local copy saved)")

        # Update DB
        try:
            async with get_db_session() as db:
                content_repo = ContentPipelineRepository(db)
                await content_repo.update_block_audio(
                    block_id=block.id,
                    audio_url=cdn_url or f"file://{local_path}",
                    duration_s=duration_s,
                )
                await db.commit()
        except Exception as exc:
            print(f"          ⚠️  DB update failed: {exc}")

        results.append({
            "block_id": str(block.id),
            "point_name": pt_name,
            "content_type": block.content_type,
            "char_count": char_count,
            "audio_bytes": len(audio_bytes),
            "duration_s": duration_s,
            "local_path": str(local_path),
            "cdn_url": cdn_url,
        })

    return results


# =============================================================================
# Main
# =============================================================================

async def main_async(args) -> None:
    zone_id = UUID(args.zone_id)
    voice_id = UUID(args.voice_id) if args.voice_id else None

    print(f"\n{'='*60}")
    print(f"Sample Audio Synthesis — Zone {str(zone_id)[:8]}...")
    print(f"{'='*60}")

    # Select blocks
    blocks, voice_id, voice_name, elevenlabs_voice_id, point_names = \
        await select_blocks_for_synthesis(zone_id, args.limit, voice_id)

    if not blocks:
        print("  ❌ No synthesizable blocks found for this zone/voice.")
        print("     Run Phase 4–6 of seed_moscow_test.py first.")
        sys.exit(0)

    print(f"\n  Voice: {voice_name} (ElevenLabs: {elevenlabs_voice_id})")
    print(f"  Blocks selected: {len(blocks)}")

    total_chars = sum(len(b.text_script or "") for b in blocks)
    print(f"  Total characters: {total_chars}")
    print(f"  ElevenLabs free tier: ~10,000 chars/month")
    print(f"  Remaining budget after this: ~{10000 - total_chars} chars")

    if total_chars > 10000:
        print(f"  ⚠️  This exceeds free tier! {total_chars} chars > 10,000 limit")
        print(f"     Reduce --limit or use paid tier.")

    if args.dry_run:
        print("\n  DRY RUN — no API calls will be made.\n")
    elif total_chars > 0:
        print(f"\n  Proceeding with synthesis ({total_chars} chars via ElevenLabs)...")

    results = await synthesize_blocks(
        zone_id=zone_id,
        blocks=blocks,
        voice_id=voice_id,
        elevenlabs_voice_id=elevenlabs_voice_id,
        point_names=point_names,
        local_only=args.local_only,
        dry_run=args.dry_run,
    )

    # Summary
    successful = [r for r in results if "error" not in r and r.get("status") != "dry_run"]
    failed = [r for r in results if "error" in r]
    dry = [r for r in results if r.get("status") == "dry_run"]

    print(f"\n{'='*60}")
    print("SYNTHESIS SUMMARY")
    print(f"{'='*60}")
    if args.dry_run:
        print(f"  Blocks listed (dry run): {len(dry)}")
        print(f"  Total chars:             {total_chars}")
    else:
        print(f"  Synthesized: {len(successful)}")
        print(f"  Failed:      {len(failed)}")
        if successful:
            total_dur = sum(r.get("duration_s", 0) for r in successful)
            total_bytes = sum(r.get("audio_bytes", 0) for r in successful)
            print(f"  Total duration: ~{total_dur:.0f}s ({total_dur/60:.1f}min)")
            print(f"  Total audio:    {total_bytes/1024:.0f} KB")
            print(f"  Local files:    {_ROOT}/tmp/synthesized_samples/")
        if failed:
            print(f"\n  Failures:")
            for r in failed:
                print(f"    {r['point_name']} ({r['content_type']}): {r['error']}")

    print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/guide/synthesize_sample.py",
        description="Synthesize a limited number of content blocks via ElevenLabs",
    )
    parser.add_argument("--zone-id", required=True, help="UUID of the zone")
    parser.add_argument("--limit", type=int, default=5,
                        help="Max blocks to synthesize (default: 5)")
    parser.add_argument("--dry-run", action="store_true",
                        help="List blocks without synthesizing (no API calls)")
    parser.add_argument("--local-only", action="store_true",
                        help="Save locally, skip S3 upload")
    parser.add_argument("--voice-id", default=None,
                        help="Override voice UUID (default: first active voice)")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
