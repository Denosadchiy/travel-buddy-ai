"""
Inspect the result of City Seeder for a zone.

Shows: zone metadata, points table, edge stats, knowledge card coverage,
and 3 best POI examples with Wikipedia summaries.

Usage:
    python scripts/guide/inspect_zone.py --zone-id <UUID>
    python scripts/guide/inspect_zone.py --zone-id <UUID> --verbose

Options:
    --zone-id    UUID of the guide_zone to inspect (required)
    --verbose    Print full Wikipedia summaries (default: 200 chars)
    --json       Output raw JSON instead of pretty-print
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


async def inspect_zone(zone_id: UUID, verbose: bool, as_json: bool) -> None:
    from src.infrastructure.database import get_db_session
    from src.guide.domain.models import (
        GuideZone, GuidePoint, GuideEdge, GuideKnowledgeCard
    )
    from sqlalchemy import select, func, text

    async with get_db_session() as db:

        # ── Zone ────────────────────────────────────────────────────────────
        zone = await db.get(GuideZone, zone_id)
        if zone is None:
            print(f"❌ Zone {zone_id} not found", file=sys.stderr)
            sys.exit(1)

        # City name
        city_result = await db.execute(
            text("SELECT name FROM guide_cities WHERE id = :id"),
            {"id": str(zone.city_id)},
        )
        city_row = city_result.fetchone()
        city_name = city_row[0] if city_row else "unknown"

        # ── Points ───────────────────────────────────────────────────────────
        pts_result = await db.execute(
            text(
                "SELECT id, name, point_type, is_approved, is_active, "
                "ST_Y(location) AS lat, ST_X(location) AS lng "
                "FROM guide_points WHERE zone_id = :zid ORDER BY point_type, name"
            ),
            {"zid": str(zone_id)},
        )
        pts_rows = pts_result.mappings().fetchall()

        poi_points = [r for r in pts_rows if r["point_type"] == "poi"]
        connector_points = [r for r in pts_rows if r["point_type"] == "connector"]
        approved_pts = [r for r in pts_rows if r["is_approved"]]
        active_pts = [r for r in pts_rows if r["is_active"]]

        # ── Edges ────────────────────────────────────────────────────────────
        edges_result = await db.execute(
            text(
                "SELECT e.id, e.distance_m, e.walk_seconds, e.bearing_deg "
                "FROM guide_edges e "
                "JOIN guide_points p ON p.id = e.from_point_id "
                "WHERE p.zone_id = :zid"
            ),
            {"zid": str(zone_id)},
        )
        edges_rows = edges_result.mappings().fetchall()

        avg_neighbors: float = 0.0
        if pts_rows and edges_rows:
            avg_neighbors = len(edges_rows) / len(pts_rows)

        # ── Knowledge cards ──────────────────────────────────────────────────
        cards_result = await db.execute(
            text(
                "SELECT kc.point_id, kc.card_type, kc.wikipedia_summary, "
                "kc.wikidata_facts, kc.google_place_data, kc.street_name "
                "FROM guide_knowledge_cards kc "
                "JOIN guide_points p ON p.id = kc.point_id "
                "WHERE p.zone_id = :zid"
            ),
            {"zid": str(zone_id)},
        )
        cards_rows = cards_result.mappings().fetchall()

        cards_with_wiki = sum(1 for r in cards_rows if r["wikipedia_summary"])
        cards_with_wikidata = sum(1 for r in cards_rows if r["wikidata_facts"])
        cards_with_google = sum(1 for r in cards_rows if r["google_place_data"])
        cards_empty = sum(
            1 for r in cards_rows
            if not r["wikipedia_summary"]
            and not r["wikidata_facts"]
            and not r["google_place_data"]
            and not r["street_name"]
        )

        # Best 3 POI examples (those with wikipedia_summary)
        poi_examples = [r for r in cards_rows if r["wikipedia_summary"] and r["card_type"] == "poi"][:3]
        poi_id_to_name = {str(r["id"]): r["name"] for r in pts_rows}

    if as_json:
        output = {
            "zone_id": str(zone_id),
            "zone_name": zone.name,
            "city": city_name,
            "theme": zone.theme,
            "poi_count": zone.poi_count,
            "point_count": zone.point_count,
            "is_approved": zone.is_approved,
            "is_active": zone.is_active,
            "points": {
                "total": len(pts_rows),
                "poi": len(poi_points),
                "connector": len(connector_points),
                "approved": len(approved_pts),
                "active": len(active_pts),
            },
            "edges": {
                "total": len(edges_rows),
                "avg_neighbors_per_point": round(avg_neighbors, 2),
            },
            "knowledge_cards": {
                "total": len(cards_rows),
                "with_wikipedia": cards_with_wiki,
                "with_wikidata": cards_with_wikidata,
                "with_google_details": cards_with_google,
                "empty": cards_empty,
            },
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return

    # ── Pretty print ─────────────────────────────────────────────────────────
    w = 60
    print("\n" + "="*w)
    print(f" Zone Inspection: {zone.name}")
    print("="*w)

    print(f"\n{'Zone metadata':}")
    print(f"  ID:          {zone_id}")
    print(f"  City:        {city_name}")
    print(f"  Theme:       {zone.theme or '—'}")
    print(f"  POI count:   {zone.poi_count}")
    print(f"  Point count: {zone.point_count}")
    print(f"  Approved:    {zone.is_approved}")
    print(f"  Active:      {zone.is_active}")

    print(f"\nPoints ({len(pts_rows)} total)")
    print(f"  POI:              {len(poi_points)}")
    print(f"  Connector:        {len(connector_points)}")
    print(f"  Approved:         {len(approved_pts)}")
    print(f"  Active:           {len(active_pts)}")

    if poi_points:
        print(f"\n  Top POIs:")
        for p in sorted(poi_points, key=lambda r: r["name"] or "")[:10]:
            approved_flag = "✅" if p["is_approved"] else "❌"
            active_flag = "▶" if p["is_active"] else "—"
            print(f"    {approved_flag} {active_flag}  {p['name'] or '(unnamed)':35s}  "
                  f"({p['lat']:.5f}, {p['lng']:.5f})")

    print(f"\nGraph edges")
    print(f"  Total edges:         {len(edges_rows)}")
    print(f"  Avg neighbors/point: {avg_neighbors:.2f}")
    if edges_rows:
        avg_dist = sum(r["distance_m"] for r in edges_rows) / len(edges_rows)
        avg_walk = sum(r["walk_seconds"] for r in edges_rows) / len(edges_rows)
        print(f"  Avg edge distance:   {avg_dist:.0f} m")
        print(f"  Avg walk time:       {avg_walk:.0f} s")

    print(f"\nKnowledge cards ({len(cards_rows)} total)")
    print(f"  With Wikipedia:     {cards_with_wiki}")
    print(f"  With Wikidata:      {cards_with_wikidata}")
    print(f"  With Google Details:{cards_with_google}")
    print(f"  Empty cards:        {cards_empty}")

    if poi_examples:
        print(f"\nExample POI summaries (best {len(poi_examples)}):")
        for row in poi_examples:
            name = poi_id_to_name.get(str(row["point_id"]), str(row["point_id"])[:8])
            summary = row["wikipedia_summary"] or ""
            if not verbose:
                summary = summary[:200] + ("..." if len(summary) > 200 else "")
            print(f"\n  [{name}]")
            print(f"  {summary}")

    print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/guide/inspect_zone.py",
        description="Inspect City Seeder results for a guide zone",
    )
    parser.add_argument("--zone-id", required=True, help="UUID of the zone to inspect")
    parser.add_argument("--verbose", action="store_true",
                        help="Print full Wikipedia summaries")
    parser.add_argument("--json", dest="as_json", action="store_true",
                        help="Output raw JSON")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(inspect_zone(UUID(args.zone_id), args.verbose, args.as_json))


if __name__ == "__main__":
    main()
