"""
Universal content generation for any Live Guide zone.

Phases:
  1. POI content: main + bonus + recap (via DraftGenerator)
  2. Transitions: between POI points (via DraftGenerator)
  3. Walking commentary: for selected connectors (WALKING_COMMENTARY_PROMPT)
  4. Coherence validation (CoherenceValidator)
  5. Batch approve

Usage:
    # Full pipeline
    python scripts/guide/generate_content.py --zone-id <UUID> --language en --non-interactive

    # POI only (no commentary)
    python scripts/guide/generate_content.py --zone-id <UUID> --language en --poi-only --non-interactive

    # Commentary only
    python scripts/guide/generate_content.py --zone-id <UUID> --language en --commentary-only --non-interactive
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import math
import re
import sys
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("generate_content")


def _hav(lat1, lng1, lat2, lng2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# =========================================================================
# Phase 1+2: POI content + transitions (delegates to topup_content logic)
# =========================================================================

async def phase_poi_content(
    zone_id: UUID,
    voice_style: str,
    language: str,
    max_llm_calls: int,
    skip_transitions: bool,
    force_regenerate: bool,
) -> dict:
    """Generate main/bonus/recap + transitions for POI points."""
    from src.infrastructure.database import get_db_session
    from src.infrastructure.llm_client import get_guide_narrative_llm_client
    from src.guide.application.content_pipeline.repository import ContentPipelineRepository
    from src.guide.application.content_pipeline.draft_generator import DraftGenerator
    from src.config import settings

    print(f"\n{'='*60}")
    print("Phase 1: POI content (main/bonus/recap)")
    print(f"{'='*60}")

    llm_client = get_guide_narrative_llm_client()

    async with get_db_session() as db:
        content_repo = ContentPipelineRepository(db)
        voices = await content_repo.get_active_voices()
        target_voice = next(
            (v for v in voices if v.style_group == voice_style and v.language == language),
            None,
        )
        if target_voice is None:
            available = [(v.style_group, v.language) for v in voices]
            raise RuntimeError(
                f"No voice with style_group={voice_style!r} language={language!r}. Available: {available}"
            )
        print(f"  Voice: {target_voice.name} ({target_voice.style_group}/{target_voice.language})")

    # Step 1: main/bonus/recap
    settings.guide_content_max_llm_calls_per_job = max_llm_calls

    async with get_db_session() as db:
        content_repo = ContentPipelineRepository(db)
        generator = DraftGenerator(repo=content_repo, llm_client=llm_client)
        job_id = await generator.generate_zone_drafts(
            zone_id=zone_id,
            voice_ids=[target_voice.id],
            languages=[language],
            detail_levels=["standard"],
            force_regenerate=force_regenerate,
            poi_only=True,
            skip_transitions=True,
        )
        await db.commit()
    print(f"  Draft generation job: {job_id}")

    # Step 2: transitions
    trans_result = {"edges_processed": 0, "blocks_created": 0, "llm_calls": 0}
    if not skip_transitions:
        print(f"\n{'='*60}")
        print("Phase 2: Transitions (POI edges only)")
        print(f"{'='*60}")

        async with get_db_session() as db:
            content_repo = ContentPipelineRepository(db)
            generator = DraftGenerator(repo=content_repo, llm_client=llm_client)
            trans_result = await generator.generate_transitions_only(
                zone_id=zone_id,
                voice_ids=[target_voice.id],
                languages=[language],
                poi_edges_only=True,
                force_regenerate=force_regenerate,
                max_calls=max_llm_calls,
            )
            await db.commit()

        print(f"  Edges processed: {trans_result['edges_processed']}/{trans_result.get('edges_total', '?')}")
        print(f"  Transition blocks: {trans_result['blocks_created']}")
        print(f"  LLM calls: {trans_result['llm_calls']}")

    return {"voice_id": target_voice.id, "transitions": trans_result}


# =========================================================================
# Phase 3: Walking commentary for connectors
# =========================================================================

async def select_connectors_for_commentary(
    zone_id: UUID,
    spacing_m: float = 120.0,
    min_from_poi_m: float = 60.0,
) -> list[dict]:
    """Select connectors at regular intervals for walking commentary."""
    from src.infrastructure.database import get_db_session
    from sqlalchemy import text

    async with get_db_session() as db:
        # All active connectors
        r = await db.execute(text("""
            SELECT p.id, ST_Y(p.location::geometry) as lat, ST_X(p.location::geometry) as lng
            FROM guide_points p
            WHERE p.zone_id = :zid AND p.is_active = true AND p.point_type = 'connector'
        """), {"zid": str(zone_id)})
        connectors = [dict(row._mapping) for row in r.fetchall()]

        # POI positions
        r2 = await db.execute(text("""
            SELECT ST_Y(p.location::geometry) as lat, ST_X(p.location::geometry) as lng
            FROM guide_points p
            WHERE p.zone_id = :zid AND p.is_active = true AND p.point_type = 'poi'
        """), {"zid": str(zone_id)})
        poi_positions = [(row.lat, row.lng) for row in r2.fetchall()]

    # Select with spacing
    selected = []
    for c in connectors:
        if any(_hav(c["lat"], c["lng"], pl, pn) < min_from_poi_m for pl, pn in poi_positions):
            continue
        if any(_hav(c["lat"], c["lng"], s["lat"], s["lng"]) < spacing_m for s in selected):
            continue
        selected.append(c)

    return selected


async def phase_walking_commentary(
    zone_id: UUID,
    voice_style: str,
    language: str,
    spacing_m: float,
    max_llm_calls: int,
) -> dict:
    """Generate walking commentary for selected connectors."""
    from src.infrastructure.database import get_db_session
    from src.infrastructure.llm_client import get_guide_narrative_llm_client
    from src.guide.application.content_pipeline.text_validators import auto_fix, validate_text_quality, has_vague_person_references
    from src.guide.application.content_pipeline.prompt_templates import WALKING_COMMENTARY_PROMPT, LANGUAGE_NAMES
    from src.guide.domain.models import GuideContentBlock
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    print(f"\n{'='*60}")
    print("Phase 3: Walking commentary for connectors")
    print(f"{'='*60}")

    connectors = await select_connectors_for_commentary(zone_id, spacing_m=spacing_m)
    print(f"  Selected {len(connectors)} connectors (spacing={spacing_m}m)")

    if not connectors:
        return {"generated": 0, "total_selected": 0}

    # Check existing
    conn_ids = [str(c["id"]) for c in connectors]
    async with get_db_session() as db:
        r = await db.execute(text("""
            SELECT point_id::text FROM guide_content_blocks
            WHERE content_type = 'walking_commentary' AND language = :lang
              AND point_id::text = ANY(:pids)
        """), {"lang": language, "pids": conn_ids})
        existing = {row[0] for row in r.fetchall()}

    need_gen = [c for c in connectors if str(c["id"]) not in existing]
    print(f"  Already have: {len(existing)}")
    print(f"  Need to generate: {len(need_gen)}")

    if not need_gen:
        return {"generated": 0, "total_selected": len(connectors), "existing": len(existing)}

    # Load zone info for city name
    async with get_db_session() as db:
        r = await db.execute(text("""
            SELECT c.name as city_name FROM guide_zones z
            JOIN guide_cities c ON c.id = z.city_id WHERE z.id = :zid
        """), {"zid": str(zone_id)})
        city_name = r.scalar() or "the city"

        # POI knowledge for neighbor context
        r2 = await db.execute(text("""
            SELECT kc.point_id, p.name, kc.wikipedia_summary, kc.street_name
            FROM guide_knowledge_cards kc
            JOIN guide_points p ON p.id = kc.point_id
            WHERE p.zone_id = :zid AND p.point_type = 'poi'
        """), {"zid": str(zone_id)})
        poi_knowledge = [
            {"name": row.name, "wiki": row.wikipedia_summary, "lat": 0, "lng": 0}
            for row in r2.fetchall()
        ]

        # Voice
        r3 = await db.execute(text(
            "SELECT id FROM guide_voices WHERE style_group = :style AND language = :lang"
        ), {"style": voice_style, "lang": language})
        voice_id = r3.scalar()
        if not voice_id:
            raise RuntimeError(f"No voice for {voice_style}/{language}")

    llm = get_guide_narrative_llm_client()
    lang_name = LANGUAGE_NAMES.get(language, language)
    generated = 0
    previous_texts: list[str] = []
    calls = 0

    for i, conn in enumerate(need_gen):
        if calls >= max_llm_calls:
            print(f"  LLM call cap reached ({max_llm_calls})")
            break

        # Street name
        async with get_db_session() as db:
            r = await db.execute(text(
                "SELECT street_name FROM guide_knowledge_cards WHERE point_id = :pid"
            ), {"pid": str(conn["id"])})
            row = r.fetchone()
            street = row[0] if row else "this street"

        # Nearest POIs for context
        nearest_pois = poi_knowledge[:3] if poi_knowledge else []
        neighbor_ctx = "\n".join(
            f"- {pk['name']}: {(pk['wiki'] or '')[:200]}"
            for pk in nearest_pois if pk.get("wiki")
        ) or "(no nearby POI data)"

        previous_commentaries = "\n".join(f"- {t[:120]}" for t in previous_texts[-3:])

        prompt = WALKING_COMMENTARY_PROMPT.format(
            city_name=city_name,
            street_name=street or "this street",
            from_poi_name=nearest_pois[0]["name"] if nearest_pois else "a nearby attraction",
            to_poi_name=nearest_pois[1]["name"] if len(nearest_pois) > 1 else "the next stop",
            connector_knowledge="",
            neighbor_context=neighbor_ctx,
            previous_commentaries=previous_commentaries or "(nothing said yet)",
            language_name=lang_name,
        )

        try:
            text_result = await llm.generate_text(prompt, max_tokens=400)
            calls += 1
            text_result = auto_fix(text_result.strip().strip('"').strip("«»").strip(), language)

            # Validate
            ok, issues = validate_text_quality(text_result, language)
            vague, vi = has_vague_person_references(text_result, language)
            if not ok or vague:
                fix_prompt = prompt + f"\n\n[FIX: {issues + vi}. Use ONLY {lang_name}, no unnamed people.]"
                text_result = await llm.generate_text(fix_prompt, max_tokens=400)
                calls += 1
                text_result = auto_fix(text_result.strip().strip('"').strip("«»").strip(), language)

            # Save
            async with get_db_session() as db:
                now = datetime.now(timezone.utc)
                block_id = _uuid.uuid4()
                stmt = pg_insert(GuideContentBlock).values(
                    id=block_id, point_id=conn["id"], zone_id=zone_id,
                    voice_id=voice_id, language=language, detail_level="standard",
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
            if (i + 1) % 25 == 0:
                print(f"    [{i+1}/{len(need_gen)}] generated... ({calls} LLM calls)")

        except Exception as exc:
            logger.warning("Commentary gen failed for %s: %s", conn["id"], exc)

    print(f"  Generated: {generated}/{len(need_gen)} walking commentary blocks ({calls} LLM calls)")
    return {"generated": generated, "total_selected": len(connectors), "llm_calls": calls}


# =========================================================================
# Phase 4: Coherence validation
# =========================================================================

async def phase_validate(zone_id: UUID, language: str) -> dict:
    from src.infrastructure.database import get_db_session
    from src.infrastructure.llm_client import get_guide_narrative_llm_client
    from src.guide.application.content_pipeline.repository import ContentPipelineRepository
    from src.guide.application.content_pipeline.coherence_validator import CoherenceValidator

    print(f"\n{'='*60}")
    print("Phase 4: Coherence validation")
    print(f"{'='*60}")

    llm_client = get_guide_narrative_llm_client()

    async with get_db_session() as db:
        content_repo = ContentPipelineRepository(db)
        validator = CoherenceValidator(repo=content_repo, llm_client=llm_client)
        val_job = await content_repo.create_content_job(zone_id, job_type="validate")
        stats = await validator.validate_zone(
            zone_id=zone_id,
            language=language,
            include_walk_validation=False,
            job_id=val_job.id,
        )
        await content_repo.mark_job_complete(val_job.id, stats)
        await db.commit()

    print(f"  Validated:    {stats.get('validated', 0)}")
    print(f"  Needs review: {stats.get('needs_review', 0)}")
    print(f"  Errors:       {stats.get('errors', 0)}")
    return stats


# =========================================================================
# Phase 5: Quality gate + batch approve
# =========================================================================

def _check_quality_en(b: dict) -> list[str]:
    """Quality checks for English content."""
    issues = []
    text = b["text_script"] or ""
    ct = b["content_type"]

    # Arabic digits
    nums = re.findall(r"\b\d+\b", text)
    if nums:
        issues.append(f"Digits: {nums[:3]}")

    # Cyrillic in English
    cyr = re.findall(r"[а-яёА-ЯЁ]+", text)
    if cyr:
        issues.append(f"Cyrillic: {cyr[:3]}")

    # Repeated words
    repeated = re.findall(r"\b(\w{3,})\s+\1\b", text, re.IGNORECASE)
    if repeated:
        issues.append(f"Repeated: {repeated[:2]}")

    # Length
    if ct == "main" and (len(text) < 200 or len(text) > 1200):
        issues.append(f"Length {len(text)} (want 200-1200)")
    if ct == "walking_commentary" and (len(text) < 60 or len(text) > 700):
        issues.append(f"Length {len(text)} (want 60-700)")

    return issues


def _check_quality_ru(b: dict) -> list[str]:
    """Quality checks for Russian content."""
    issues = []
    text = b["text_script"] or ""
    ct = b["content_type"]

    nums = re.findall(r"\b\d+\b", text)
    if nums:
        issues.append(f"Digits: {nums[:3]}")

    _ALLOWED = {"GUM", "WiFi", "GPS"}
    latin = [w for w in re.findall(r"[a-zA-Z]{2,}", text) if w not in _ALLOWED]
    if latin:
        issues.append(f"Latin: {latin[:3]}")

    vague = re.findall(r"(?:известн|знаменит)[а-яё]+\s+(?:художник|архитектор|писател)", text, re.I)
    if vague:
        issues.append(f"Unnamed: {vague[:2]}")

    if ct == "main" and (len(text) < 200 or len(text) > 1200):
        issues.append(f"Length {len(text)} (want 200-1200)")
    if ct == "walking_commentary" and (len(text) < 60 or len(text) > 700):
        issues.append(f"Length {len(text)} (want 60-700)")

    return issues


async def phase_quality_and_approve(zone_id: UUID, language: str) -> dict:
    from src.infrastructure.database import get_db_session
    from sqlalchemy import text

    print(f"\n{'='*60}")
    print("Phase 5: Quality gate + batch approve")
    print(f"{'='*60}")

    check_fn = _check_quality_en if language == "en" else _check_quality_ru

    async with get_db_session() as db:
        r = await db.execute(text("""
            SELECT cb.id, cb.content_type, cb.text_script, cb.generation_status,
                   length(cb.text_script) as chars
            FROM guide_content_blocks cb
            WHERE cb.zone_id = :zid AND cb.language = :lang
        """), {"zid": str(zone_id), "lang": language})
        blocks = [dict(row._mapping) for row in r.fetchall()]

    total = len(blocks)
    passed = 0
    failed_ids = []
    for b in blocks:
        issues = check_fn(b)
        if issues:
            failed_ids.append((b["id"], issues))
        else:
            passed += 1

    print(f"  Total: {total}, Passed: {passed}, Failed: {len(failed_ids)}")
    if failed_ids:
        for bid, iss in failed_ids[:5]:
            print(f"    Failed: {iss}")

    # Batch approve all
    async with get_db_session() as db:
        r = await db.execute(text("""
            UPDATE guide_content_blocks
            SET generation_status = 'reviewed'
            WHERE zone_id = :zid AND language = :lang
              AND generation_status IN ('validated', 'draft', 'needs_manual_review')
        """), {"zid": str(zone_id), "lang": language})
        approved = r.rowcount
        await db.commit()

    print(f"  Approved: {approved} blocks → 'reviewed'")
    return {"total": total, "passed": passed, "failed": len(failed_ids), "approved": approved}


# =========================================================================
# Summary
# =========================================================================

async def print_summary(zone_id: UUID, language: str) -> None:
    from src.infrastructure.database import get_db_session
    from sqlalchemy import text

    async with get_db_session() as db:
        r = await db.execute(text("""
            SELECT c.name as city, z.name as zone_name
            FROM guide_zones z JOIN guide_cities c ON c.id = z.city_id
            WHERE z.id = :zid
        """), {"zid": str(zone_id)})
        row = r.mappings().fetchone()
        city = row["city"] if row else "?"
        zone_name = row["zone_name"] if row else "?"

        r2 = await db.execute(text("""
            SELECT content_type, generation_status, count(*) as cnt
            FROM guide_content_blocks
            WHERE zone_id = :zid AND language = :lang
            GROUP BY content_type, generation_status
            ORDER BY content_type, generation_status
        """), {"zid": str(zone_id), "lang": language})

        print(f"\n{'='*60}")
        print(f"SUMMARY: {city} — {zone_name} ({language})")
        print(f"{'='*60}")
        total = 0
        for row in r2.mappings().fetchall():
            print(f"  {row['content_type']:25s} {row['generation_status']:20s} {row['cnt']:5d}")
            total += row['cnt']
        print(f"  {'TOTAL':25s} {'':20s} {total:5d}")


# =========================================================================
# CLI
# =========================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/guide/generate_content.py",
        description="Universal content generation for any Live Guide zone",
    )
    parser.add_argument("--zone-id", required=True, help="UUID of the zone")
    parser.add_argument("--language", required=True, choices=["en", "ru"])
    parser.add_argument("--voice-style", default="academic",
                        choices=["academic", "friendly", "dramatic", "minimal"])
    parser.add_argument("--poi-only", action="store_true", help="Skip walking commentary")
    parser.add_argument("--commentary-only", action="store_true", help="Only walking commentary")
    parser.add_argument("--skip-transitions", action="store_true")
    parser.add_argument("--commentary-spacing-m", type=float, default=120.0)
    parser.add_argument("--max-llm-calls", type=int, default=5000)
    parser.add_argument("--force-regenerate", action="store_true")
    parser.add_argument("--non-interactive", action="store_true", required=True)
    return parser


async def main() -> None:
    args = build_parser().parse_args()
    zone_id = UUID(args.zone_id)

    print(f"\n{'='*60}")
    print(f"Content Generation — zone {zone_id}")
    print(f"Language: {args.language}, Voice: {args.voice_style}")
    print(f"{'='*60}")

    # Phase 1+2: POI content
    if not args.commentary_only:
        await phase_poi_content(
            zone_id=zone_id,
            voice_style=args.voice_style,
            language=args.language,
            max_llm_calls=args.max_llm_calls,
            skip_transitions=args.skip_transitions,
            force_regenerate=args.force_regenerate,
        )

    # Phase 3: Walking commentary
    if not args.poi_only:
        await phase_walking_commentary(
            zone_id=zone_id,
            voice_style=args.voice_style,
            language=args.language,
            spacing_m=args.commentary_spacing_m,
            max_llm_calls=args.max_llm_calls,
        )

    # Phase 4: Validation
    await phase_validate(zone_id, args.language)

    # Phase 5: Quality gate + approve
    await phase_quality_and_approve(zone_id, args.language)

    # Summary
    await print_summary(zone_id, args.language)

    print(f"\n{'='*60}")
    print("DONE")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
