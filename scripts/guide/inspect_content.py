"""
Inspect content blocks for a guide zone.

Shows: status breakdown, content_type distribution, per-voice counts,
example main/transition blocks, and needs_manual_review samples.

Usage:
    python scripts/guide/inspect_content.py --zone-id <UUID>
    python scripts/guide/inspect_content.py --zone-id <UUID> --show-texts
    python scripts/guide/inspect_content.py --zone-id <UUID> --json

Options:
    --zone-id       UUID of the zone to inspect (required)
    --show-texts    Print full text_script for examples (default: 120 chars)
    --status        Filter by status (e.g. needs_manual_review)
    --json          Output raw JSON
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


async def inspect_content(
    zone_id: UUID,
    show_texts: bool,
    status_filter: str | None,
    as_json: bool,
) -> None:
    from src.infrastructure.database import get_db_session
    from src.guide.domain.models import GuideContentBlock, GuideVoice, GuidePoint, GuideEdge
    from sqlalchemy import select, func, text

    async with get_db_session() as db:

        # ── Status breakdown ─────────────────────────────────────────────────
        status_stmt = (
            select(
                GuideContentBlock.generation_status,
                func.count().label("cnt"),
            )
            .where(GuideContentBlock.zone_id == zone_id)
            .group_by(GuideContentBlock.generation_status)
        )
        status_result = await db.execute(status_stmt)
        status_counts = {row.generation_status: row.cnt for row in status_result}
        total = sum(status_counts.values())

        # ── By content_type ──────────────────────────────────────────────────
        type_stmt = (
            select(
                GuideContentBlock.content_type,
                func.count().label("cnt"),
            )
            .where(GuideContentBlock.zone_id == zone_id)
            .group_by(GuideContentBlock.content_type)
        )
        type_result = await db.execute(type_stmt)
        type_counts = {row.content_type: row.cnt for row in type_result}

        # ── By voice ─────────────────────────────────────────────────────────
        voice_stmt = (
            select(
                GuideVoice.name,
                GuideVoice.style_group,
                GuideVoice.language,
                func.count(GuideContentBlock.id).label("cnt"),
            )
            .join(GuideVoice, GuideContentBlock.voice_id == GuideVoice.id)
            .where(GuideContentBlock.zone_id == zone_id)
            .group_by(GuideVoice.id, GuideVoice.name, GuideVoice.style_group, GuideVoice.language)
        )
        voice_result = await db.execute(voice_stmt)
        voice_counts = [
            {
                "name": row.name,
                "style": row.style_group,
                "language": row.language,
                "count": row.cnt,
            }
            for row in voice_result
        ]

        # ── Sample main blocks ───────────────────────────────────────────────
        main_blocks_stmt = (
            select(GuideContentBlock)
            .where(
                GuideContentBlock.zone_id == zone_id,
                GuideContentBlock.content_type == "main",
            )
            .order_by(GuideContentBlock.coherence_score.desc().nullslast())
            .limit(3)
        )
        main_blocks_result = await db.execute(main_blocks_stmt)
        main_blocks = list(main_blocks_result.scalars().all())

        # Get point names for main blocks
        point_ids = [b.point_id for b in main_blocks if b.point_id]
        point_names: dict[str, str] = {}
        if point_ids:
            pts_result = await db.execute(
                select(GuidePoint.id, GuidePoint.name).where(GuidePoint.id.in_(point_ids))
            )
            point_names = {str(r.id): r.name or "" for r in pts_result}

        # ── Sample transition blocks ─────────────────────────────────────────
        trans_blocks_stmt = (
            select(GuideContentBlock)
            .where(
                GuideContentBlock.zone_id == zone_id,
                GuideContentBlock.content_type == "transition",
            )
            .order_by(GuideContentBlock.coherence_score.desc().nullslast())
            .limit(2)
        )
        trans_blocks_result = await db.execute(trans_blocks_stmt)
        trans_blocks = list(trans_blocks_result.scalars().all())

        # Get point names for edges referenced by transitions
        edge_ids = [b.edge_id for b in trans_blocks if b.edge_id]
        edge_point_names: dict[str, tuple[str, str]] = {}
        if edge_ids:
            edges_result = await db.execute(
                select(GuideEdge, GuidePoint)
                .join(GuidePoint, GuideEdge.from_point_id == GuidePoint.id)
                .where(GuideEdge.id.in_(edge_ids))
            )
            for edge, pt in edges_result:
                edge_point_names[str(edge.id)] = (pt.name or str(edge.from_point_id)[:8], "→ ?")

            # Get to_point names too
            to_ids_result = await db.execute(
                select(GuideEdge.id, GuideEdge.to_point_id).where(GuideEdge.id.in_(edge_ids))
            )
            to_map = {str(r.id): r.to_point_id for r in to_ids_result}
            if to_map:
                to_pts_result = await db.execute(
                    select(GuidePoint.id, GuidePoint.name)
                    .where(GuidePoint.id.in_(list(to_map.values())))
                )
                to_name_map = {str(r.id): r.name or "" for r in to_pts_result}
                for eid, to_id in to_map.items():
                    from_name = edge_point_names.get(eid, ("?", "→ ?"))[0]
                    edge_point_names[eid] = (from_name, to_name_map.get(str(to_id), "?"))

        # ── Needs manual review samples ──────────────────────────────────────
        nmr_stmt = (
            select(GuideContentBlock)
            .where(
                GuideContentBlock.zone_id == zone_id,
                GuideContentBlock.generation_status == "needs_manual_review",
            )
            .order_by(GuideContentBlock.coherence_score.asc().nullslast())
            .limit(3)
        )
        nmr_result = await db.execute(nmr_stmt)
        nmr_blocks = list(nmr_result.scalars().all())

    if as_json:
        output = {
            "zone_id": str(zone_id),
            "total_blocks": total,
            "by_status": status_counts,
            "by_content_type": type_counts,
            "by_voice": voice_counts,
        }
        print(json.dumps(output, indent=2))
        return

    # ── Pretty print ──────────────────────────────────────────────────────────
    w = 60
    print("\n" + "="*w)
    print(f" Content Inspection — Zone {str(zone_id)[:8]}...")
    print("="*w)

    print(f"\nTotal blocks: {total}")

    print(f"\nBy generation_status:")
    for status, cnt in sorted(status_counts.items()):
        bar_len = min(cnt * 30 // max(total, 1), 30)
        bar = "█" * bar_len
        pct = cnt * 100 // max(total, 1)
        print(f"  {status:25s}  {cnt:4d}  {pct:3d}%  {bar}")

    print(f"\nBy content_type:")
    for ctype, cnt in sorted(type_counts.items()):
        print(f"  {ctype:20s}  {cnt:4d}")

    if voice_counts:
        print(f"\nBy voice:")
        for v in voice_counts:
            print(f"  {v['name']:25s}  ({v['style']}/{v['language']})  {v['count']:4d} blocks")

    if main_blocks:
        print(f"\nSample main blocks (top {len(main_blocks)} by coherence score):")
        for b in main_blocks:
            pt_name = point_names.get(str(b.point_id), str(b.point_id)[:8])
            score_str = f"{b.coherence_score:.1f}" if b.coherence_score is not None else "—"
            text = b.text_script or ""
            if not show_texts:
                text = text[:120] + ("..." if len(text) > 120 else "")
            print(f"\n  POI: {pt_name}  |  score: {score_str}  |  status: {b.generation_status}")
            print(f"  Language: {b.language}  |  detail: {b.detail_level}  |  chars: {len(b.text_script or '')}")
            print(f"  Script: {text}")

    if trans_blocks:
        print(f"\nSample transition blocks:")
        for b in trans_blocks:
            edge_id_str = str(b.edge_id) if b.edge_id else "?"
            from_name, to_name = edge_point_names.get(edge_id_str, ("?", "?"))
            score_str = f"{b.coherence_score:.1f}" if b.coherence_score is not None else "—"
            text = b.text_script or ""
            if not show_texts:
                text = text[:120] + ("..." if len(text) > 120 else "")
            print(f"\n  {from_name} → {to_name}  |  score: {score_str}  |  variant: {b.variant_index}")
            print(f"  Script: {text}")

    if nmr_blocks:
        print(f"\nNeeds manual review (lowest {len(nmr_blocks)} scores):")
        for b in nmr_blocks:
            pt_name = point_names.get(str(b.point_id), str(b.point_id)[:8])
            score_str = f"{b.coherence_score:.1f}" if b.coherence_score is not None else "—"
            reason = b.review_notes or "—"
            text = b.text_script or ""
            if not show_texts:
                text = text[:80] + ("..." if len(text) > 80 else "")
            print(f"\n  POI: {pt_name}  |  type: {b.content_type}  |  score: {score_str}")
            print(f"  Reason: {reason}")
            print(f"  Script: {text}")

    print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/guide/inspect_content.py",
        description="Inspect content blocks for a guide zone",
    )
    parser.add_argument("--zone-id", required=True, help="UUID of the zone to inspect")
    parser.add_argument("--show-texts", action="store_true",
                        help="Print full text_script (default: 120 chars)")
    parser.add_argument("--status", default=None,
                        help="Filter output to blocks with this status")
    parser.add_argument("--json", dest="as_json", action="store_true",
                        help="Output raw JSON")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(inspect_content(
        UUID(args.zone_id),
        show_texts=args.show_texts,
        status_filter=args.status,
        as_json=args.as_json,
    ))


if __name__ == "__main__":
    main()
