"""
Reseed Shanghai with expanded multi-center Google Places search.

The initial discovery only found 15 POI — too few for China's largest city.
This script:
  1. Clears old Shanghai zone data (points, edges, knowledge_cards)
  2. Multi-center Google Places search (5 centers, expanded POI types)
  3. DBSCAN clustering with wider eps
  4. Auto-approve best zone
  5. PointPlacement + GraphBuilder + KnowledgeCollector
  6. Generate updated maps

Usage:
    python3 scripts/guide/reseed_shanghai.py --non-interactive
"""
from __future__ import annotations

import asyncio
import logging
import math
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
logger = logging.getLogger("reseed_shanghai")

# =============================================================================
# Constants
# =============================================================================

SHANGHAI_CITY_ID = UUID("5ced8aaf-b036-4ba0-a7c2-c7b081515007")

# Multiple search centers to cover Shanghai's tourist areas
SEARCH_CENTERS = [
    (31.2304, 121.4737, "Nanjing Road / People's Square"),
    (31.2397, 121.4927, "The Bund"),
    (31.2089, 121.4554, "French Concession"),
    (31.2363, 121.5053, "Lujiazui / Pudong"),
    (31.2272, 121.4735, "Old City / Yu Garden"),
]

# Expanded POI types for China where "tourist_attraction" coverage is sparse
EXPANDED_POI_TYPES = [
    "tourist_attraction",
    "museum",
    "art_gallery",
    "church",
    "hindu_temple",
    "mosque",
    "synagogue",
    "park",
    "amusement_park",
    "zoo",
    "aquarium",
    "library",
    "stadium",
    "university",
    "city_hall",
    # Extra types for Shanghai:
    "shopping_mall",
    "point_of_interest",
]

# Key Shanghai landmarks to search by name if not found via nearby_search
MUST_HAVE_LANDMARKS = [
    "Shanghai Tower",
    "Shanghai World Financial Center",
    "Jade Buddha Temple",
    "Longhua Temple",
    "Shanghai Museum",
    "Power Station of Art",
    "M50 Creative Park",
    "Tianzifang",
    "Xintiandi",
    "Jing'an Temple",
    "People's Park Shanghai",
    "Shanghai Natural History Museum",
    "Oriental Pearl TV Tower",
    "Yu Garden",
    "The Bund Shanghai",
    "Nanjing Road Pedestrian Street",
    "Shanghai Science and Technology Museum",
    "Century Park Shanghai",
    "Zhujiajiao Water Town",
    "Shanghai Ocean Aquarium",
    "Former French Concession Shanghai",
    "Wukang Road Shanghai",
    "Huxinting Tea House",
    "Shanghai Grand Theatre",
    "Shanghai Propaganda Poster Art Centre",
]


# =============================================================================
# Phase 1: Clean old data
# =============================================================================

async def clean_old_shanghai_data() -> None:
    """Delete old Shanghai zone points, edges, knowledge cards."""
    from src.infrastructure.database import get_db_session
    from sqlalchemy import text

    print(f"\n{'='*60}")
    print("Phase 1: Cleaning old Shanghai zone data")
    print(f"{'='*60}")

    async with get_db_session() as db:
        # Get all Shanghai zone IDs
        r = await db.execute(text("""
            SELECT z.id FROM guide_zones z
            JOIN guide_cities c ON c.id = z.city_id
            WHERE c.name = 'Shanghai'
        """))
        zone_ids = [row[0] for row in r.fetchall()]

        if not zone_ids:
            print("  No Shanghai zones found — nothing to clean")
            return

        for zone_id in zone_ids:
            zid = str(zone_id)

            # Delete knowledge cards for points in this zone
            kc = await db.execute(text("""
                DELETE FROM guide_knowledge_cards
                WHERE point_id IN (SELECT id FROM guide_points WHERE zone_id = :zid)
            """), {"zid": zid})
            print(f"  Deleted {kc.rowcount} knowledge cards for zone {zid[:8]}")

            # Delete edges
            edges = await db.execute(text("""
                DELETE FROM guide_edges
                WHERE from_point_id IN (SELECT id FROM guide_points WHERE zone_id = :zid)
                   OR to_point_id IN (SELECT id FROM guide_points WHERE zone_id = :zid)
            """), {"zid": zid})
            print(f"  Deleted {edges.rowcount} edges for zone {zid[:8]}")

            # Delete points
            pts = await db.execute(text("""
                DELETE FROM guide_points WHERE zone_id = :zid
            """), {"zid": zid})
            print(f"  Deleted {pts.rowcount} points for zone {zid[:8]}")

        # Delete zones
        zones = await db.execute(text("""
            DELETE FROM guide_zones
            WHERE city_id = :city_id
        """), {"city_id": str(SHANGHAI_CITY_ID)})
        print(f"  Deleted {zones.rowcount} zones")

        # Mark old seed jobs as failed
        jobs = await db.execute(text("""
            UPDATE guide_seed_jobs
            SET status = 'failed', error_message = 'Superseded by reseed_shanghai.py'
            WHERE city_name = 'Shanghai' AND status NOT IN ('failed')
        """))
        print(f"  Marked {jobs.rowcount} old seed jobs as failed")

        await db.commit()

    print("  Done cleaning")


# =============================================================================
# Phase 2: Multi-center Google Places search
# =============================================================================

async def multi_center_poi_search() -> list:
    """
    Search from multiple centers with expanded POI types.
    Returns deduplicated list of POICandidate objects.
    """
    from src.guide.infrastructure.google_places_client import GuideGooglePlacesClient
    from src.guide.application.seeder.types import POICandidate

    print(f"\n{'='*60}")
    print("Phase 2: Multi-center Google Places search")
    print(f"{'='*60}")

    client = GuideGooglePlacesClient()
    seen_place_ids: set[str] = set()
    all_pois: list[POICandidate] = []

    # Part A: Multi-center nearby_search
    for center_lat, center_lng, center_name in SEARCH_CENTERS:
        center_count = 0
        for poi_type in EXPANDED_POI_TYPES:
            try:
                raw_results = await client.nearby_search(
                    center_lat, center_lng,
                    radius_m=3000,
                    place_type=poi_type,
                    max_results=60,
                )
                for place in raw_results:
                    place_id = place.get("place_id")
                    if not place_id or place_id in seen_place_ids:
                        continue

                    geometry = place.get("geometry", {})
                    location = geometry.get("location", {})
                    lat = location.get("lat")
                    lng = location.get("lng")
                    if lat is None or lng is None:
                        continue

                    rating = place.get("rating")
                    reviews = place.get("user_ratings_total")

                    # Relaxed quality filter for Shanghai
                    if rating is not None and rating < 3.0:
                        continue
                    if reviews is not None and reviews < 10:
                        continue

                    seen_place_ids.add(place_id)
                    all_pois.append(POICandidate(
                        google_place_id=place_id,
                        name=place.get("name", ""),
                        lat=float(lat),
                        lng=float(lng),
                        rating=rating,
                        user_ratings_total=reviews,
                        types=place.get("types", []),
                    ))
                    center_count += 1

            except Exception as exc:
                logger.warning("Search failed for %s/%s: %s", center_name, poi_type, exc)

        print(f"  Center '{center_name}': {center_count} new POIs")

    print(f"  Total from nearby_search: {len(all_pois)} unique POIs")

    # Part B: Text search for must-have landmarks
    text_search_url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    import httpx
    from src.config import settings

    landmarks_found = 0
    async with httpx.AsyncClient(timeout=15) as http_client:
        for landmark_name in MUST_HAVE_LANDMARKS:
            try:
                params = {
                    "query": landmark_name,
                    "key": settings.google_maps_api_key,
                    "location": "31.2304,121.4737",
                    "radius": 20000,
                }
                resp = await http_client.get(text_search_url, params=params)
                data = resp.json()
                results = data.get("results", [])

                if not results:
                    continue

                place = results[0]
                place_id = place.get("place_id")
                if not place_id or place_id in seen_place_ids:
                    continue

                geometry = place.get("geometry", {})
                location = geometry.get("location", {})
                lat = location.get("lat")
                lng = location.get("lng")
                if lat is None or lng is None:
                    continue

                # Verify it's actually in Shanghai (within ~30km)
                dist = _haversine_m(31.2304, 121.4737, float(lat), float(lng))
                if dist > 30000:
                    continue

                seen_place_ids.add(place_id)
                all_pois.append(POICandidate(
                    google_place_id=place_id,
                    name=place.get("name", ""),
                    lat=float(lat),
                    lng=float(lng),
                    rating=place.get("rating"),
                    user_ratings_total=place.get("user_ratings_total"),
                    types=place.get("types", []),
                ))
                landmarks_found += 1
                logger.info("Found landmark: %s (%.4f, %.4f)", place.get("name"), lat, lng)

            except Exception as exc:
                logger.warning("Text search failed for '%s': %s", landmark_name, exc)

    print(f"  Landmarks found via text search: {landmarks_found}")
    print(f"  Total unique POIs: {len(all_pois)}")

    return all_pois


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000.0
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# =============================================================================
# Phase 3: DBSCAN clustering
# =============================================================================

def cluster_and_build_zones(pois: list) -> list:
    """Run DBSCAN on POIs and build ProposedZone objects."""
    import numpy as np
    from sklearn.cluster import DBSCAN
    from shapely.geometry import MultiPoint, mapping
    from src.guide.application.seeder.types import ProposedZone

    print(f"\n{'='*60}")
    print("Phase 3: DBSCAN clustering")
    print(f"{'='*60}")

    if len(pois) < 5:
        print(f"  Only {len(pois)} POIs — cannot cluster")
        return []

    coords_rad = np.radians([[p.lat, p.lng] for p in pois])
    eps_rad = (1200.0 / 1000.0) / 6371.0  # 1200m eps

    db = DBSCAN(
        eps=eps_rad,
        min_samples=5,
        algorithm="ball_tree",
        metric="haversine",
    ).fit(coords_rad)

    labels = db.labels_
    cluster_map: dict[int, list] = {}
    for poi, label in zip(pois, labels):
        if label == -1:
            continue
        cluster_map.setdefault(label, []).append(poi)

    outliers = int(np.sum(labels == -1))
    print(f"  Clusters: {len(cluster_map)}, Outliers: {outliers}")

    zones = []
    for cluster_id, cluster_pois in sorted(cluster_map.items(), key=lambda x: -len(x[1])):
        points = MultiPoint([(p.lng, p.lat) for p in cluster_pois])
        hull = points.convex_hull

        if hull.geom_type == "Point":
            hull = hull.buffer(0.0005)
        elif hull.geom_type == "LineString":
            hull = hull.buffer(0.0002)

        centroid = hull.centroid

        # Best name: highest-scored POI
        def score(poi):
            r = poi.rating or 0.0
            n = poi.user_ratings_total or 0
            return r * math.log10(n + 1)

        ranked = sorted(cluster_pois, key=score, reverse=True)
        zone_name = ranked[0].name if ranked else f"Zone {cluster_id}"

        # Theme heuristic
        all_types = [t for p in cluster_pois for t in p.types]
        theme = "historic"
        type_counts = {}
        for t in all_types:
            type_counts[t] = type_counts.get(t, 0) + 1
        if type_counts.get("museum", 0) + type_counts.get("art_gallery", 0) > len(all_types) * 0.3:
            theme = "cultural"
        elif type_counts.get("park", 0) + type_counts.get("zoo", 0) > len(all_types) * 0.3:
            theme = "nature"

        zone = ProposedZone(
            name=zone_name,
            boundary_wkt=hull.wkt,
            boundary_geojson=mapping(hull),
            poi_count=len(cluster_pois),
            top_poi_names=[p.name for p in ranked[:5]],
            theme_hint=theme,
            centroid_lat=centroid.y,
            centroid_lng=centroid.x,
        )
        zones.append(zone)
        print(f"  Cluster {cluster_id}: '{zone_name}' — {len(cluster_pois)} POIs, theme={theme}")

    return zones


# =============================================================================
# Phase 4: Insert zones and approve best
# =============================================================================

async def insert_and_approve_zones(zones: list) -> tuple[UUID, UUID, str]:
    """Insert zones into DB, approve the best one. Returns (job_id, zone_id, zone_name)."""
    from src.infrastructure.database import get_db_session
    from src.guide.application.seeder.repository import SeederRepository

    print(f"\n{'='*60}")
    print("Phase 4: Insert zones and approve best")
    print(f"{'='*60}")

    async with get_db_session() as db:
        repo = SeederRepository(db)

        # Create new seed job
        job = await repo.create_seed_job("Shanghai")
        job_id = job.id
        await repo.update_seed_job(job_id, city_id=SHANGHAI_CITY_ID)

        # Insert zones
        inserted = await repo.bulk_insert_zones(SHANGHAI_CITY_ID, zones)
        print(f"  Inserted {len(inserted)} zones")

        # Approve the one with most POIs
        best = max(inserted, key=lambda z: z.poi_count)
        await repo.approve_zone(best.id)
        print(f"  Approved: '{best.name}' ({best.poi_count} POIs)")

        # Update job
        await repo.update_seed_job(
            job_id,
            status="awaiting_zone_approval",
            current_phase="awaiting_zone_approval",
            progress_json={"phase": "awaiting_approval", "zones_proposed": len(zones)},
        )

        await db.commit()

    return job_id, best.id, best.name or str(best.id)[:8]


# =============================================================================
# Phase 5: PointPlacement + GraphBuilder + KnowledgeCollector
# =============================================================================

async def run_placement_and_knowledge(job_id: UUID, zone_id: UUID, zone_name: str) -> dict:
    """Run PointPlacement, GraphBuilder, KnowledgeCollector for the approved zone."""
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
    print(f"Phase 5: PointPlacement + GraphBuilder + KnowledgeCollector")
    print(f"  Zone: {zone_name}")
    print(f"{'='*60}")
    print("  This may take 5-15 minutes...")

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

    # Activate points
    from sqlalchemy import text as sa_text
    async with get_db_session() as db:
        activated = await db.execute(sa_text("""
            UPDATE guide_points gp
            SET is_active = true
            FROM guide_zones gz
            WHERE gp.zone_id = gz.id
              AND gz.city_id = :city_id
              AND gz.is_approved = true
              AND gp.is_approved = true
              AND gp.is_active = false
        """), {"city_id": str(SHANGHAI_CITY_ID)})
        zone_activated = await db.execute(sa_text("""
            UPDATE guide_zones
            SET is_active = true
            WHERE city_id = :city_id AND is_approved = true AND is_active = false
        """), {"city_id": str(SHANGHAI_CITY_ID)})
        await db.commit()
        print(f"  Points activated: {activated.rowcount}")
        print(f"  Zones activated:  {zone_activated.rowcount}")

    return progress


# =============================================================================
# Phase 6: Generate maps
# =============================================================================

async def generate_maps(zone_id: UUID) -> None:
    """Generate updated HTML maps."""
    from scripts.guide.visualize_zones import generate_points_map
    from scripts.guide.seed_cities import phase_c_generate_map

    print(f"\n{'='*60}")
    print("Phase 6: Generating maps")
    print(f"{'='*60}")

    # Zones map
    map_path = await phase_c_generate_map(
        SHANGHAI_CITY_ID, "Shanghai", zone_id,
    )
    print(f"  Zones map: {map_path}")

    # Points map
    out_dir = _ROOT / "tmp" / "zone_proposals"
    out_path = out_dir / "shanghai_points.html"
    await generate_points_map(zone_id, out_path)
    print(f"  Points map: {out_path}")


# =============================================================================
# Verification
# =============================================================================

async def verify_results(zone_id: UUID) -> None:
    """Print final statistics and verify other cities unchanged."""
    from src.infrastructure.database import get_db_session
    from sqlalchemy import text

    print(f"\n{'='*60}")
    print("Verification")
    print(f"{'='*60}")

    async with get_db_session() as db:
        # Shanghai zone stats
        r = await db.execute(text("""
            SELECT
                (SELECT count(*) FROM guide_points WHERE zone_id = :zid AND point_type='poi') as poi,
                (SELECT count(*) FROM guide_points WHERE zone_id = :zid AND point_type='connector') as conn,
                (SELECT count(*) FROM guide_edges e JOIN guide_points p ON p.id = e.from_point_id WHERE p.zone_id = :zid) as edges,
                (SELECT count(*) FROM guide_knowledge_cards kc JOIN guide_points p ON p.id = kc.point_id WHERE p.zone_id = :zid) as kc,
                (SELECT count(*) FROM guide_knowledge_cards kc JOIN guide_points p ON p.id = kc.point_id WHERE p.zone_id = :zid AND kc.wikipedia_summary IS NOT NULL) as wiki
        """), {"zid": str(zone_id)})
        row = r.mappings().fetchone()
        print(f"\n  Shanghai zone:")
        print(f"    POI:          {row['poi']} (was 11)")
        print(f"    Connectors:   {row['conn']} (was 62)")
        print(f"    Edges:        {row['edges']} (was 257)")
        print(f"    Knowledge:    {row['kc']} (was 73)")
        print(f"    Wikipedia:    {row['wiki']} (was 11)")

        # Verify other cities unchanged
        r2 = await db.execute(text("""
            SELECT c.name, count(p.id)
            FROM guide_points p
            JOIN guide_zones z ON p.zone_id = z.id
            JOIN guide_cities c ON c.id = z.city_id
            WHERE z.is_approved = TRUE
            GROUP BY c.name ORDER BY c.name
        """))
        print(f"\n  Points per city (all should be unchanged except Shanghai):")
        for row in r2.fetchall():
            marker = " <-- UPDATED" if row[0] == "Shanghai" else ""
            print(f"    {row[0]:12s}: {row[1]:5d}{marker}")


# =============================================================================
# Main
# =============================================================================

async def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--non-interactive", action="store_true", required=True)
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("Reseed Shanghai — Expanded Multi-Center Search")
    print("=" * 60)

    # Phase 1: Clean
    await clean_old_shanghai_data()

    # Phase 2: Multi-center search
    pois = await multi_center_poi_search()

    if not pois:
        print("ERROR: No POIs found. Check Google API key.")
        sys.exit(1)

    # Phase 3: DBSCAN clustering
    zones = cluster_and_build_zones(pois)

    if not zones:
        print("ERROR: No clusters formed. Try lowering DBSCAN min_samples.")
        sys.exit(1)

    # Phase 4: Insert and approve
    job_id, zone_id, zone_name = await insert_and_approve_zones(zones)

    # Phase 5: PointPlacement + GraphBuilder + KnowledgeCollector
    progress = await run_placement_and_knowledge(job_id, zone_id, zone_name)

    # Phase 6: Maps
    await generate_maps(zone_id)

    # Verify
    await verify_results(zone_id)

    print(f"\n{'='*60}")
    print("DONE — Shanghai reseeded successfully")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
