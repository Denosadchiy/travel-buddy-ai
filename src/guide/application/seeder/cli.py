"""
City Seeder CLI — runs the seeder from the command line.

Usage:
    python -m src.guide.application.seeder.cli seed --city "Moscow" --country "Russia"
    python -m src.guide.application.seeder.cli seed --city "Paris" --dry-run
    python -m src.guide.application.seeder.cli status --job-id <UUID>
    python -m src.guide.application.seeder.cli continue --job-id <UUID>

Options for 'seed':
    --city      City name (required)
    --country   Country name (optional, improves geocoding accuracy)
    --dry-run   Skip real Google Places calls; use mock data (for local dev)

Options for 'status':
    --job-id    UUID of a seed job to inspect

Options for 'continue':
    --job-id    UUID of the seed job to resume (must be in 'awaiting_zone_approval')

In --dry-run mode ZoneDiscovery returns a fixed set of mock ProposedZones so
you can test the orchestrator ↔ repository flow without hitting any external API.
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
# Dry-run mock discovery
# ============================================================================

def _make_dry_run_zone_discovery():
    """
    Return a ZoneDiscovery-compatible object whose discover() method returns
    two hardcoded ProposedZone objects without any API calls.
    """
    from src.guide.application.seeder.types import ProposedZone

    # Tiny square polygon centred on (0, 0) for testing
    _MOCK_WKT = (
        "POLYGON((0.001 0.001, 0.002 0.001, 0.002 0.002, 0.001 0.002, 0.001 0.001))"
    )
    _MOCK_GEOJSON = {
        "type": "Polygon",
        "coordinates": [[[0.001, 0.001], [0.002, 0.001], [0.002, 0.002],
                          [0.001, 0.002], [0.001, 0.001]]],
    }

    class _MockZoneDiscovery:
        async def discover(self, city_name, center_lat, center_lng, radius_km=15.0):
            print(f"[dry-run] ZoneDiscovery: returning 2 mock zones for '{city_name}'")
            return [
                ProposedZone(
                    name="Mock Historical Centre",
                    boundary_wkt=_MOCK_WKT,
                    boundary_geojson=_MOCK_GEOJSON,
                    poi_count=15,
                    top_poi_names=["Mock Museum", "Mock Cathedral", "Mock Park"],
                    theme_hint="historic",
                    centroid_lat=center_lat,
                    centroid_lng=center_lng,
                ),
                ProposedZone(
                    name="Mock Cultural Quarter",
                    boundary_wkt=_MOCK_WKT,
                    boundary_geojson=_MOCK_GEOJSON,
                    poi_count=10,
                    top_poi_names=["Mock Gallery", "Mock Library"],
                    theme_hint="cultural",
                    centroid_lat=center_lat + 0.01,
                    centroid_lng=center_lng + 0.01,
                ),
            ]

    return _MockZoneDiscovery()


# ============================================================================
# Commands
# ============================================================================

async def cmd_seed(city: str, country: str | None, dry_run: bool) -> None:
    """Run Zone Discovery for a city and persist proposed zones."""
    from src.infrastructure.database import get_db_session
    from src.guide.application.seeder.repository import SeederRepository
    from src.guide.application.seeder.orchestrator import CitySeederOrchestrator

    if dry_run:
        print(f"[dry-run] Starting seeder for '{city}' (no real API calls)")
        zone_discovery = _make_dry_run_zone_discovery()
    else:
        from src.guide.infrastructure.google_places_client import GuideGooglePlacesClient
        from src.guide.application.seeder.zone_discovery import ZoneDiscovery
        zone_discovery = ZoneDiscovery(GuideGooglePlacesClient())

    async with get_db_session() as db:
        repo = SeederRepository(db)
        orchestrator = CitySeederOrchestrator(repo, zone_discovery)

        job_id = await orchestrator.start_seed(city, country)
        await db.commit()

    print(f"✅  Seed job created: {job_id}")
    print(f"    City: {city}")
    print(f"    Next: review and approve zones via admin API, then run Step 5.")


async def cmd_continue(job_id_str: str) -> None:
    """Resume seeding after zones have been approved (Phase 2: PointPlacement + Phase 3: GraphBuilder)."""
    from src.infrastructure.database import get_db_session
    from src.guide.application.seeder.repository import SeederRepository
    from src.guide.application.seeder.orchestrator import CitySeederOrchestrator
    from src.guide.application.seeder.zone_discovery import ZoneDiscovery
    from src.guide.application.seeder.point_placement import PointPlacement
    from src.guide.application.seeder.graph_builder import GraphBuilder
    from src.guide.infrastructure.google_places_client import GuideGooglePlacesClient

    try:
        job_id = uuid.UUID(job_id_str)
    except ValueError:
        print(f"❌  Invalid UUID: {job_id_str}", file=sys.stderr)
        sys.exit(1)

    print(f"▶  Resuming seed job {job_id} (Phase 2: PointPlacement + Phase 3: GraphBuilder)…")
    print("   This requires GOOGLE_MAPS_API_KEY and internet access to OpenStreetMap.")

    async with get_db_session() as db:
        repo = SeederRepository(db)
        zone_discovery = ZoneDiscovery(GuideGooglePlacesClient())
        point_placement = PointPlacement()
        graph_builder = GraphBuilder()

        orchestrator = CitySeederOrchestrator(
            repo=repo,
            zone_discovery=zone_discovery,
            point_placement=point_placement,
            graph_builder=graph_builder,
        )

        await orchestrator.continue_after_zone_approval(job_id)
        await db.commit()

    print(f"✅  Job {job_id} — Phase 2+3 complete.")
    print(f"    Status: collecting_knowledge")
    print(f"    Next: Step 5b (KnowledgeCollector) will populate guide_knowledge_cards.")


async def cmd_status(job_id_str: str) -> None:
    """Print the current status of a seed job."""
    from src.infrastructure.database import get_db_session
    from src.guide.application.seeder.repository import SeederRepository

    try:
        job_id = uuid.UUID(job_id_str)
    except ValueError:
        print(f"❌  Invalid UUID: {job_id_str}", file=sys.stderr)
        sys.exit(1)

    async with get_db_session() as db:
        repo = SeederRepository(db)
        job = await repo.get_seed_job(job_id)

    if job is None:
        print(f"❌  Job {job_id} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Job ID:       {job.id}")
    print(f"City:         {job.city_name}")
    print(f"Status:       {job.status}")
    print(f"Phase:        {job.current_phase}")
    print(f"Created:      {job.created_at}")
    print(f"Completed:    {job.completed_at or '—'}")
    if job.error_message:
        print(f"Error:        {job.error_message}")
    print(f"Progress:")
    progress_data = job.progress_json or {}
    print(json.dumps(progress_data, indent=2))


# ============================================================================
# Argument parser
# ============================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.guide.application.seeder.cli",
        description="City Seeder — discover tourist zones for the Live Audio Guide.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # seed
    seed_p = sub.add_parser("seed", help="Discover zones for a city")
    seed_p.add_argument("--city", required=True, help="City name (e.g. 'Moscow')")
    seed_p.add_argument("--country", default=None, help="Country name (improves geocoding)")
    seed_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip real API calls; use mock zone data (local dev only)",
    )

    # status
    status_p = sub.add_parser("status", help="Show seed job status")
    status_p.add_argument("--job-id", required=True, help="UUID of the seed job")

    # continue
    continue_p = sub.add_parser(
        "continue",
        help=(
            "Resume seeding after zones are approved "
            "(Phase 2: PointPlacement + Phase 3: GraphBuilder)"
        ),
    )
    continue_p.add_argument(
        "--job-id",
        required=True,
        help="UUID of the seed job (must be in 'awaiting_zone_approval' status)",
    )

    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = build_parser()
    args = parser.parse_args()

    if args.command == "seed":
        asyncio.run(cmd_seed(args.city, args.country, args.dry_run))
    elif args.command == "status":
        asyncio.run(cmd_status(args.job_id))
    elif args.command == "continue":
        asyncio.run(cmd_continue(args.job_id))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
