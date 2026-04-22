"""
Universal audio synthesis for any Live Guide zone.

Synthesizes reviewed content blocks via ElevenLabs TTS.
Saves audio locally to data/audio/<zone_id>/<block_id>.mp3.

IMPORTANT: No FFmpeg postprocessing — ElevenLabs outputs well-normalized audio.

Usage:
    python scripts/guide/synthesize_audio.py --zone-id <UUID> --language en --non-interactive
    python scripts/guide/synthesize_audio.py --zone-id <UUID> --language en --dry-run --non-interactive
    python scripts/guide/synthesize_audio.py --zone-id <UUID> --language ru --content-types main,bonus --non-interactive
"""
from __future__ import annotations

import argparse
import asyncio
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
logger = logging.getLogger("synthesize_audio")


async def check_quota() -> tuple[int, str]:
    """Check ElevenLabs subscription quota. Returns (remaining_chars, tier)."""
    import httpx
    from src.config import settings

    if not settings.elevenlabs_api_key:
        raise RuntimeError("ELEVENLABS_API_KEY not set")

    r = httpx.get(
        "https://api.elevenlabs.io/v1/user",
        headers={"xi-api-key": settings.elevenlabs_api_key},
        timeout=10,
    )
    r.raise_for_status()
    sub = r.json()["subscription"]
    remaining = sub["character_limit"] - sub["character_count"]
    tier = sub["tier"]
    print(f"  ElevenLabs plan: {tier}")
    print(f"  Used: {sub['character_count']:,} / {sub['character_limit']:,}")
    print(f"  Remaining: {remaining:,} chars")
    return remaining, tier


async def load_blocks_for_synthesis(
    zone_id: UUID,
    language: str,
    voice_style: str,
    content_types: list[str] | None = None,
) -> list[dict]:
    """Load reviewed blocks without audio_url."""
    from src.infrastructure.database import get_db_session
    from sqlalchemy import text

    ct_filter = ""
    params: dict = {"zid": str(zone_id), "lang": language, "style": voice_style}
    if content_types:
        ct_filter = "AND cb.content_type = ANY(:cts)"
        params["cts"] = content_types

    async with get_db_session() as db:
        r = await db.execute(text(f"""
            SELECT cb.id, cb.point_id, cb.content_type, cb.text_script,
                   p.name as point_name
            FROM guide_content_blocks cb
            JOIN guide_points p ON p.id = cb.point_id
            WHERE cb.zone_id = :zid AND cb.language = :lang
              AND cb.voice_id = (SELECT id FROM guide_voices WHERE style_group = :style AND language = :lang)
              AND cb.generation_status = 'reviewed'
              AND cb.audio_url IS NULL
              {ct_filter}
            ORDER BY cb.content_type, p.name
        """), params)
        return [dict(row._mapping) for row in r.fetchall()]


async def synthesize_blocks(
    zone_id: UUID,
    blocks: list[dict],
    language: str,
    voice_style: str,
    concurrency: int = 3,
) -> int:
    """Synthesize audio for all blocks. Returns count of successful syntheses."""
    from src.infrastructure.database import get_db_session
    from src.guide.infrastructure.elevenlabs_client import ElevenLabsClient
    from sqlalchemy import text

    # Get ElevenLabs voice ID
    async with get_db_session() as db:
        r = await db.execute(text(
            "SELECT elevenlabs_voice_id FROM guide_voices WHERE style_group = :style AND language = :lang"
        ), {"style": voice_style, "lang": language})
        el_voice_id = r.scalar()

    if not el_voice_id or "PLACEHOLDER" in el_voice_id:
        raise RuntimeError(f"No valid ElevenLabs voice_id for {voice_style}/{language}")

    audio_dir = _ROOT / "data" / "audio" / str(zone_id)
    audio_dir.mkdir(parents=True, exist_ok=True)

    client = ElevenLabsClient()
    sem = asyncio.Semaphore(concurrency)
    synthesized = 0

    async def _synth(b: dict, idx: int) -> None:
        nonlocal synthesized
        async with sem:
            try:
                audio_bytes = await client.synthesize_batch(
                    text=b["text_script"],
                    voice_id=el_voice_id,
                )

                # Skip suspiciously small files (< 1KB = likely empty/error)
                if len(audio_bytes) < 1000:
                    print(f"  [{idx+1}/{len(blocks)}] SKIP {b['content_type']} — too small ({len(audio_bytes)} bytes)")
                    return

                # Save locally (NO FFmpeg postprocessing — ElevenLabs already well-normalized)
                mp3_path = audio_dir / f"{b['id']}.mp3"
                mp3_path.write_bytes(audio_bytes)
                audio_url = f"/audio/{zone_id}/{b['id']}.mp3"

                # Duration
                try:
                    import io
                    from mutagen.mp3 import MP3
                    duration = float(MP3(io.BytesIO(audio_bytes)).info.length)
                except Exception:
                    duration = len(audio_bytes) / 16000

                # Update DB
                async with get_db_session() as db:
                    await db.execute(text("""
                        UPDATE guide_content_blocks
                        SET audio_url = :url, audio_duration_seconds = :dur,
                            generation_status = 'synthesized', synthesized_at = NOW()
                        WHERE id = :bid
                    """), {"url": audio_url, "dur": duration, "bid": str(b["id"])})
                    await db.commit()

                synthesized += 1
                ct = b["content_type"][:8]
                name = (b["point_name"] or "connector")[:25]
                print(f"  [{idx+1}/{len(blocks)}] {ct} {name}: {len(b['text_script'])} chars, {duration:.1f}s")

            except Exception as exc:
                print(f"  [{idx+1}/{len(blocks)}] ERROR {b['content_type']}: {exc}")

    await asyncio.gather(*[_synth(b, i) for i, b in enumerate(blocks)])
    return synthesized


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/guide/synthesize_audio.py",
        description="Universal audio synthesis for any Live Guide zone",
    )
    parser.add_argument("--zone-id", required=True, help="UUID of the zone")
    parser.add_argument("--language", required=True, choices=["en", "ru"])
    parser.add_argument("--voice-style", default="academic",
                        choices=["academic", "friendly", "dramatic", "minimal"])
    parser.add_argument("--dry-run", action="store_true",
                        help="Count chars and estimate cost, don't synthesize")
    parser.add_argument("--parallel-concurrency", type=int, default=3)
    parser.add_argument("--content-types", default=None,
                        help="Comma-separated: main,bonus,recap,transition,walking_commentary")
    parser.add_argument("--non-interactive", action="store_true", required=True)
    return parser


async def main() -> None:
    args = build_parser().parse_args()
    zone_id = UUID(args.zone_id)
    content_types = args.content_types.split(",") if args.content_types else None

    print(f"\n{'='*60}")
    print(f"Audio Synthesis — zone {zone_id}")
    print(f"Language: {args.language}, Voice: {args.voice_style}")
    print(f"{'='*60}")

    # Load blocks
    blocks = await load_blocks_for_synthesis(zone_id, args.language, args.voice_style, content_types)
    total_chars = sum(len(b["text_script"]) for b in blocks)

    print(f"\n  Blocks to synthesize: {len(blocks)}")
    print(f"  Total characters: {total_chars:,}")
    print(f"  Estimated cost: ~${total_chars * 0.00015:.2f}")

    if not blocks:
        print("  Nothing to synthesize")
        return

    # Content type breakdown
    from collections import Counter
    ct_counts = Counter(b["content_type"] for b in blocks)
    for ct, cnt in sorted(ct_counts.items()):
        print(f"    {ct}: {cnt}")

    if args.dry_run:
        print("\n  [DRY RUN] — no audio synthesized")
        return

    # Check quota
    print(f"\n  Checking ElevenLabs quota...")
    remaining, tier = await check_quota()
    if total_chars > remaining:
        print(f"  NOT ENOUGH QUOTA: need {total_chars:,}, have {remaining:,}")
        return

    # Synthesize
    print(f"\n  Synthesizing {len(blocks)} blocks...")
    synthesized = await synthesize_blocks(
        zone_id, blocks, args.language, args.voice_style, args.parallel_concurrency,
    )

    print(f"\n{'='*60}")
    print(f"DONE: {synthesized}/{len(blocks)} blocks synthesized")
    print(f"Audio directory: {_ROOT / 'data' / 'audio' / str(zone_id)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
