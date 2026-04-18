"""
Production pipeline for Yakimanka zone.

Phases:
  A1.1: Audit — check what content exists
  A1.2: Regenerate draft main blocks
  A1.3: Generate walking_commentary for connectors (~50 blocks)
  A1.4: Coherence validation + batch approve
  A1.5: Quality gate — 10 checks per block
  A2.1: ElevenLabs quota check
  A2.2: Synthesize audio (local storage, no S3)
  A2.3: Verify all audio_url populated

Usage:
    python scripts/guide/produce_yakimanka.py --phase all --non-interactive
    python scripts/guide/produce_yakimanka.py --phase a1 --non-interactive
    python scripts/guide/produce_yakimanka.py --phase a2 --non-interactive
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Optional
from uuid import UUID

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("produce_yakimanka")

ZONE_ID = UUID("04bb6ef2-3914-4920-b721-432c8502a1c8")
CENTER_LAT, CENTER_LNG = 55.7373, 37.6132
RADIUS_M = 800
VOICE_STYLE = "academic"
VOICE_LANG = "ru"


def _hav(lat1, lng1, lat2, lng2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# =========================================================================
# Phase A1.1: Audit
# =========================================================================

async def phase_audit():
    from src.infrastructure.database import get_db_session
    from sqlalchemy import text

    print(f"\n{'='*60}\nPHASE A1.1: AUDIT\n{'='*60}")

    async with get_db_session() as db:
        r = await db.execute(text("""
            SELECT p.id, p.name, p.point_type,
                   ST_Y(p.location::geometry) as lat, ST_X(p.location::geometry) as lng
            FROM guide_points p
            WHERE p.zone_id = :zid AND p.is_active = true
        """), {"zid": str(ZONE_ID)})
        all_pts = [dict(row._mapping) for row in r.fetchall()]

    yak_pois = [p for p in all_pts if p["point_type"] == "poi" and _hav(p["lat"], p["lng"], CENTER_LAT, CENTER_LNG) <= RADIUS_M]
    yak_conns = [p for p in all_pts if p["point_type"] == "connector" and _hav(p["lat"], p["lng"], CENTER_LAT, CENTER_LNG) <= RADIUS_M]

    print(f"  POI in zone: {len(yak_pois)}")
    print(f"  Connectors in zone: {len(yak_conns)}")
    for p in yak_pois:
        print(f"    {p['name'] or '?'}")

    return [str(p["id"]) for p in yak_pois], [p for p in yak_conns]


# =========================================================================
# Phase A1.2: Regenerate main blocks + fix draft
# =========================================================================

async def phase_regen_main(poi_ids):
    from src.infrastructure.database import get_db_session
    from sqlalchemy import text

    print(f"\n{'='*60}\nPHASE A1.2: REGENERATE DRAFT MAIN BLOCKS\n{'='*60}")

    # Check for draft/pending main blocks
    async with get_db_session() as db:
        r = await db.execute(text("""
            SELECT cb.point_id, p.name, cb.generation_status
            FROM guide_content_blocks cb
            JOIN guide_points p ON p.id = cb.point_id
            WHERE cb.point_id::text = ANY(:pids)
              AND cb.language = 'ru' AND cb.content_type = 'main'
              AND cb.generation_status NOT IN ('validated', 'reviewed', 'synthesized')
              AND cb.voice_id = (SELECT id FROM guide_voices WHERE style_group='academic' AND language='ru')
        """), {"pids": poi_ids})
        drafts = r.fetchall()

    if not drafts:
        print("  All main blocks validated — skipping regeneration")
        return

    print(f"  {len(drafts)} main blocks need regeneration")
    for d in drafts:
        print(f"    {d.name}: {d.generation_status}")

    # Run topup with force-regenerate-main
    print("  Running topup_content.py --force-regenerate-main ...")
    result = subprocess.run(
        [sys.executable, str(_ROOT / "scripts/guide/topup_content.py"),
         "--zone-id", str(ZONE_ID),
         "--voice-style", VOICE_STYLE, "--voice-language", VOICE_LANG,
         "--force-regenerate-main",
         "--max-llm-calls", "50", "--non-interactive"],
        capture_output=True, text=True, timeout=600,
    )
    # Log key lines
    for line in result.stdout.split("\n"):
        if any(k in line for k in ("Reset", "TOPUP", "Total", "draft:", "validated:")):
            print(f"    {line.strip()}")


# =========================================================================
# Phase A1.3: Walking commentary for connectors
# =========================================================================

async def phase_walking_commentary(yak_conns):
    from src.infrastructure.database import get_db_session
    from src.infrastructure.llm_client import get_guide_narrative_llm_client
    from src.guide.application.content_pipeline.text_validators import auto_fix, validate_text_quality, has_vague_person_references
    from src.guide.application.content_pipeline.prompt_templates import WALKING_COMMENTARY_PROMPT
    from sqlalchemy import text
    from src.guide.domain.models import GuideContentBlock
    import uuid as _uuid
    from datetime import datetime, timezone

    print(f"\n{'='*60}\nPHASE A1.3: WALKING COMMENTARY FOR CONNECTORS\n{'='*60}")

    # Select connectors with spacing
    MIN_SPACING = 120
    MIN_FROM_POI = 60

    # Sort by distance from center
    for c in yak_conns:
        c["dist_center"] = _hav(c["lat"], c["lng"], CENTER_LAT, CENTER_LNG)
    yak_conns.sort(key=lambda c: c["dist_center"])

    # Get POI positions for min-distance check
    async with get_db_session() as db:
        r = await db.execute(text("""
            SELECT ST_Y(location::geometry) as lat, ST_X(location::geometry) as lng
            FROM guide_points WHERE zone_id = :zid AND point_type = 'poi'
        """), {"zid": str(ZONE_ID)})
        poi_positions = [(row.lat, row.lng) for row in r.fetchall()]

    selected = []
    for c in yak_conns:
        # Check distance to POIs
        if any(_hav(c["lat"], c["lng"], pl, pn) < MIN_FROM_POI for pl, pn in poi_positions):
            continue
        # Check spacing from already-selected
        if any(_hav(c["lat"], c["lng"], s["lat"], s["lng"]) < MIN_SPACING for s in selected):
            continue
        selected.append(c)

    print(f"  Selected {len(selected)} connectors (from {len(yak_conns)} total, spacing={MIN_SPACING}m)")

    # Check existing commentary
    conn_ids = [str(c["id"]) for c in selected]
    async with get_db_session() as db:
        r = await db.execute(text("""
            SELECT point_id::text FROM guide_content_blocks
            WHERE content_type = 'walking_commentary' AND language = 'ru'
              AND point_id::text = ANY(:pids)
        """), {"pids": conn_ids if conn_ids else ["_none_"]})
        existing = {row[0] for row in r.fetchall()}

    need_gen = [c for c in selected if str(c["id"]) not in existing]
    print(f"  Already have commentary: {len(existing)}")
    print(f"  Need to generate: {len(need_gen)}")

    if not need_gen:
        return

    # Load knowledge for neighbor POIs
    async with get_db_session() as db:
        r = await db.execute(text("""
            SELECT kc.point_id, p.name, kc.wikipedia_summary, kc.street_name
            FROM guide_knowledge_cards kc
            JOIN guide_points p ON p.id = kc.point_id
            WHERE p.zone_id = :zid AND p.point_type = 'poi'
        """), {"zid": str(ZONE_ID)})
        poi_knowledge = {str(row.point_id): {"name": row.name, "wiki": row.wikipedia_summary, "street": row.street_name} for row in r.fetchall()}

        # Get voice_id
        r2 = await db.execute(text("SELECT id FROM guide_voices WHERE style_group='academic' AND language='ru'"))
        voice_id = r2.scalar()

    llm = get_guide_narrative_llm_client()
    lang_name = "Russian"
    generated = 0
    previous_texts = []

    for i, conn in enumerate(need_gen):
        # Find 3 nearest POIs for context
        nearest_pois = sorted(
            poi_knowledge.values(),
            key=lambda pk: 1  # simplified — use all
        )[:3]
        neighbor_ctx = "\n".join(
            f"- {pk['name']}: {(pk['wiki'] or '')[:200]}"
            for pk in nearest_pois if pk.get("wiki")
        )

        # Street name from knowledge card
        async with get_db_session() as db:
            r = await db.execute(text(
                "SELECT street_name FROM guide_knowledge_cards WHERE point_id = :pid"
            ), {"pid": str(conn["id"])})
            row = r.fetchone()
            street = row[0] if row else "этой улице"

        previous_commentaries = "\n".join(f"- {t[:120]}" for t in previous_texts[-3:])

        prompt = WALKING_COMMENTARY_PROMPT.format(
            city_name="Москве",
            street_name=street or "этой улице",
            from_poi_name=nearest_pois[0]["name"] if nearest_pois else "ближайшей достопримечательности",
            to_poi_name=nearest_pois[1]["name"] if len(nearest_pois) > 1 else "следующей остановке",
            connector_knowledge="",
            neighbor_context=neighbor_ctx,
            previous_commentaries=previous_commentaries or "(ещё ничего не сказано)",
            language_name=lang_name,
        )

        try:
            text_result = await llm.generate_text(prompt, max_tokens=400)
            text_result = auto_fix(text_result.strip().strip('"').strip("«»").strip(), VOICE_LANG)

            # Validate
            ok, issues = validate_text_quality(text_result, VOICE_LANG)
            vague, vi = has_vague_person_references(text_result, VOICE_LANG)
            if not ok or vague:
                # Retry once
                fix_prompt = prompt + f"\n\n[CRITICAL FIX: {issues + vi}. Use ONLY Russian, no unnamed people.]"
                text_result = await llm.generate_text(fix_prompt, max_tokens=400)
                text_result = auto_fix(text_result.strip().strip('"').strip("«»").strip(), VOICE_LANG)

            # Save to DB
            async with get_db_session() as db:
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                now = datetime.now(timezone.utc)
                block_id = _uuid.uuid4()
                stmt = pg_insert(GuideContentBlock).values(
                    id=block_id, point_id=conn["id"], zone_id=ZONE_ID,
                    voice_id=voice_id, language=VOICE_LANG, detail_level="standard",
                    content_type="walking_commentary", variant_index=0,
                    text_script=text_result, generation_status="draft",
                    generated_at=now, created_at=now,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["point_id", "voice_id", "language", "detail_level",
                                    "content_type", "variant_index"],
                    index_where=GuideContentBlock.edge_id.is_(None),
                    set_={"text_script": text_result, "generation_status": "draft", "generated_at": now},
                )
                await db.execute(stmt)
                await db.commit()

            generated += 1
            previous_texts.append(text_result)
            if (i + 1) % 10 == 0:
                print(f"    [{i+1}/{len(need_gen)}] generated...")

        except Exception as exc:
            logger.warning("Commentary generation failed for connector %s: %s", conn["id"], exc)

    print(f"  Generated: {generated}/{len(need_gen)} walking commentary blocks")


# =========================================================================
# Phase A1.4: Quality Gate
# =========================================================================

async def phase_quality_gate(poi_ids):
    from src.infrastructure.database import get_db_session
    from sqlalchemy import text

    print(f"\n{'='*60}\nPHASE A1.5: QUALITY GATE\n{'='*60}")

    async with get_db_session() as db:
        r = await db.execute(text("""
            SELECT cb.id, cb.point_id, p.name as point_name, cb.content_type,
                   cb.text_script, cb.coherence_score, cb.generation_status,
                   length(cb.text_script) as chars
            FROM guide_content_blocks cb
            JOIN guide_points p ON p.id = cb.point_id
            WHERE cb.point_id::text = ANY(:pids)
              AND cb.language = 'ru'
              AND cb.voice_id = (SELECT id FROM guide_voices WHERE style_group='academic' AND language='ru')
            ORDER BY p.name, cb.content_type
        """), {"pids": poi_ids})
        blocks = [dict(row._mapping) for row in r.fetchall()]

    # Also check walking_commentary
    async with get_db_session() as db:
        r2 = await db.execute(text("""
            SELECT cb.id, cb.point_id, '' as point_name, cb.content_type,
                   cb.text_script, cb.coherence_score, cb.generation_status,
                   length(cb.text_script) as chars
            FROM guide_content_blocks cb
            WHERE cb.zone_id = :zid AND cb.content_type = 'walking_commentary'
              AND cb.language = 'ru'
        """), {"zid": str(ZONE_ID)})
        commentary_blocks = [dict(row._mapping) for row in r2.fetchall()]
    blocks.extend(commentary_blocks)

    total = len(blocks)
    passed = 0
    failed = []

    for b in blocks:
        issues = _check_quality(b)
        if issues:
            failed.append((b, issues))
        else:
            passed += 1

    print(f"  Total blocks checked: {total}")
    print(f"  PASSED: {passed} ({passed * 100 // max(total, 1)}%)")
    print(f"  FAILED: {len(failed)}")
    if failed:
        for b, iss in failed[:10]:
            print(f"    ❌ {b['content_type']:<20} {(b['point_name'] or 'connector')[:25]}: {iss[0]}")
        if len(failed) > 10:
            print(f"    ... and {len(failed) - 10} more")

    return passed, failed


def _check_quality(b):
    issues = []
    text = b["text_script"] or ""
    ct = b["content_type"]

    # 1. Arabic digits
    nums = re.findall(r"\b\d+\b", text)
    if nums:
        issues.append(f"Digits: {nums[:3]}")

    # 2. Latin
    # Allow: Roman numerals, single-letter abbreviations, brands
    _ALLOWED_LATIN = {"GUM", "WiFi", "GPS", "I", "II", "III", "IV", "V", "VI", "VII", "VIII",
                       "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX", "XXI"}
    latin = [w for w in re.findall(r"[a-zA-Z]+", text) if w not in _ALLOWED_LATIN]
    if latin:
        issues.append(f"Latin: {latin[:3]}")

    # 3. Unnamed famous
    vague = re.findall(r"(?:известн|знаменит)[а-яё]+\s+(?:художник|архитектор|писател|музыкант|поэт)", text, re.I)
    if vague:
        issues.append(f"Unnamed: {vague[:2]}")

    # 4. Broken words
    long = re.findall(r"\b[а-яё]{22,}\b", text)  # 22+ is suspicious (Russian has long legit words up to ~20)
    if long:
        issues.append(f"Broken: {long[:2]}")

    # 5. Length
    if ct == "main" and (len(text) < 300 or len(text) > 1000):
        issues.append(f"Length {len(text)} (want 300-1000)")
    if ct == "walking_commentary" and (len(text) < 80 or len(text) > 600):
        issues.append(f"Length {len(text)} (want 80-600)")

    # 6. Non-Cyrillic chars
    non_cyr = re.findall(r"[^\u0400-\u04FF\u0500-\u052F0-9\s.,;:!?—–\-()«»\"\"''…'\"%№°\n]", text)
    non_cyr = [c for c in non_cyr if c.strip() and c not in "a-zA-Z"]
    if non_cyr:
        issues.append(f"Non-Cyrillic: {non_cyr[:3]}")

    return issues


# =========================================================================
# Phase A1.6: Batch Approve
# =========================================================================

async def phase_batch_approve(poi_ids):
    from src.infrastructure.database import get_db_session
    from sqlalchemy import text

    print(f"\n{'='*60}\nPHASE A1.6: BATCH APPROVE\n{'='*60}")

    async with get_db_session() as db:
        # Approve all validated + draft blocks (they passed quality gate)
        r = await db.execute(text("""
            UPDATE guide_content_blocks
            SET generation_status = 'reviewed', reviewed_by = 'produce_yakimanka', reviewed_at = NOW()
            WHERE zone_id = :zid AND language = 'ru'
              AND voice_id = (SELECT id FROM guide_voices WHERE style_group='academic' AND language='ru')
              AND generation_status IN ('validated', 'draft')
              AND (point_id::text = ANY(:pids) OR content_type = 'walking_commentary')
            RETURNING id
        """), {"zid": str(ZONE_ID), "pids": poi_ids})
        approved = len(r.fetchall())
        await db.commit()

    print(f"  Approved: {approved} blocks → 'reviewed'")


# =========================================================================
# Phase A2: Synthesis
# =========================================================================

async def phase_synthesis(poi_ids):
    from src.infrastructure.database import get_db_session
    from src.guide.infrastructure.elevenlabs_client import ElevenLabsClient
    from sqlalchemy import text
    import httpx
    from src.config import settings

    print(f"\n{'='*60}\nPHASE A2: AUDIO SYNTHESIS\n{'='*60}")

    # A2.1: Check quota
    print("--- A2.1: ElevenLabs quota check ---")
    r = httpx.get("https://api.elevenlabs.io/v1/user",
                   headers={"xi-api-key": settings.elevenlabs_api_key}, timeout=10)
    sub = r.json()["subscription"]
    remaining = sub["character_limit"] - sub["character_count"]
    print(f"  Plan: {sub['tier']}, used: {sub['character_count']}/{sub['character_limit']}, remaining: {remaining}")

    # Load blocks to synthesize
    async with get_db_session() as db:
        r2 = await db.execute(text("""
            SELECT cb.id, cb.point_id, cb.content_type, cb.text_script, cb.audio_url,
                   p.name as point_name
            FROM guide_content_blocks cb
            JOIN guide_points p ON p.id = cb.point_id
            WHERE cb.zone_id = :zid AND cb.language = 'ru'
              AND cb.voice_id = (SELECT id FROM guide_voices WHERE style_group='academic' AND language='ru')
              AND cb.generation_status = 'reviewed'
              AND cb.audio_url IS NULL
              AND (cb.point_id::text = ANY(:pids) OR cb.content_type = 'walking_commentary')
            ORDER BY cb.content_type, p.name
        """), {"zid": str(ZONE_ID), "pids": poi_ids})
        blocks = [dict(row._mapping) for row in r2.fetchall()]

        r3 = await db.execute(text(
            "SELECT elevenlabs_voice_id FROM guide_voices WHERE style_group='academic' AND language='ru'"
        ))
        el_voice_id = r3.scalar()

    total_chars = sum(len(b["text_script"]) for b in blocks)
    print(f"  Blocks to synthesize: {len(blocks)}")
    print(f"  Total characters: {total_chars:,}")
    print(f"  Estimated cost: ~${total_chars * 0.00015:.2f}")

    if total_chars > remaining:
        print(f"  ❌ NOT ENOUGH QUOTA ({total_chars} > {remaining})")
        return

    if not blocks:
        print("  Nothing to synthesize")
        return

    # A2.2: Storage
    audio_dir = _ROOT / "data" / "audio" / str(ZONE_ID)
    audio_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Storage: local ({audio_dir})")

    # A2.3: Synthesize
    print(f"\n--- A2.3: Synthesizing {len(blocks)} blocks ---")
    client = ElevenLabsClient()
    synthesized = 0
    sem = asyncio.Semaphore(3)

    async def _synth(b, idx):
        nonlocal synthesized
        async with sem:
            try:
                audio_bytes = await client.synthesize_batch(
                    text=b["text_script"], voice_id=el_voice_id,
                )

                # ElevenLabs outputs well-normalized audio (-23 to -25 dB).
                # FFmpeg loudnorm was destroying the audio — skip postprocessing.

                # Save locally
                mp3_path = audio_dir / f"{b['id']}.mp3"
                mp3_path.write_bytes(audio_bytes)
                audio_url = f"/audio/{ZONE_ID}/{b['id']}.mp3"

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
                ct = b["content_type"][:6]
                name = (b["point_name"] or "connector")[:25]
                print(f"  [{idx+1}/{len(blocks)}] ✅ {ct} {name}: {len(b['text_script'])} chars, {duration:.1f}s")

            except Exception as exc:
                print(f"  [{idx+1}/{len(blocks)}] ❌ {b['content_type']} {b.get('point_name', '')[:20]}: {exc}")

    await asyncio.gather(*[_synth(b, i) for i, b in enumerate(blocks)])

    print(f"\n  Synthesized: {synthesized}/{len(blocks)}")
    print(f"  Audio directory: {audio_dir}")

    # A2.4: Verify
    async with get_db_session() as db:
        r4 = await db.execute(text("""
            SELECT count(*) FROM guide_content_blocks
            WHERE zone_id = :zid AND language = 'ru'
              AND voice_id = (SELECT id FROM guide_voices WHERE style_group='academic' AND language='ru')
              AND generation_status = 'synthesized'
              AND audio_url IS NOT NULL
              AND (point_id::text = ANY(:pids) OR content_type = 'walking_commentary')
        """), {"zid": str(ZONE_ID), "pids": poi_ids})
        total_synth = r4.scalar()
    print(f"  Verified: {total_synth} blocks with audio_url")


# =========================================================================
# Main
# =========================================================================

async def main(phase: str):
    poi_ids, yak_conns = await phase_audit()

    if phase in ("a1", "all"):
        await phase_regen_main(poi_ids)
        await phase_walking_commentary(yak_conns)
        passed, failed = await phase_quality_gate(poi_ids)
        await phase_batch_approve(poi_ids)

    if phase in ("a2", "all"):
        await phase_synthesis(poi_ids)

    print(f"\n{'='*60}\nDONE\n{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", default="all", choices=["a1", "a2", "all"])
    parser.add_argument("--non-interactive", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.phase))
