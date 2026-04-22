"""
Seed 4 new cities for Live Guide: Paris, Dubai, Shanghai, Istanbul.

For each city:
  Phase A: Zone Discovery (Google Places + DBSCAN clustering)
  Phase B: Auto-select best zone (highest POI density + quality)
  Phase C: Generate HTML map for CPO review
  Phase D: PointPlacement + GraphBuilder + KnowledgeCollector
  Phase E: Print statistics

Usage:
    # Full pipeline for all 4 cities
    python scripts/guide/seed_cities.py --non-interactive

    # Single city only
    python scripts/guide/seed_cities.py --non-interactive --city Paris

    # Skip to Phase D for a specific city (resume after zone approval)
    python scripts/guide/seed_cities.py --non-interactive --city Paris --skip-discovery

    # Discovery only (Phase A+B+C, no point placement)
    python scripts/guide/seed_cities.py --non-interactive --phase discovery
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

# ── Ensure project root is on sys.path ──
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("seed_cities")


# =============================================================================
# City definitions
# =============================================================================

@dataclass
class CitySpec:
    name: str
    country: str
    lat: float
    lng: float
    search_radius_km: float = 3.0
    dbscan_eps_m: float = 800.0
    dbscan_min_samples: int = 5


CITIES: list[CitySpec] = [
    CitySpec("Paris", "France", 48.8566, 2.3522),
    CitySpec("Dubai", "UAE", 25.2048, 55.2708, search_radius_km=5.0, dbscan_eps_m=1200.0),
    CitySpec("Shanghai", "China", 31.2304, 121.4737),
    CitySpec("Istanbul", "Turkey", 41.0082, 28.9784),
]


# =============================================================================
# City statistics collector
# =============================================================================

@dataclass
class CityResult:
    city_name: str
    country: str
    city_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    zone_id: uuid.UUID | None = None
    zone_name: str = ""
    zones_discovered: int = 0
    poi_in_zone: int = 0
    connectors_in_zone: int = 0
    edges: int = 0
    knowledge_cards: int = 0
    wikipedia_cards: int = 0
    wikidata_cards: int = 0
    google_details_cards: int = 0
    zone_area_km2: float = 0.0
    zone_center_lat: float = 0.0
    zone_center_lng: float = 0.0
    map_path: str = ""
    points_map_path: str = ""


# =============================================================================
# Phase A: Zone Discovery
# =============================================================================

async def phase_a_discovery(spec: CitySpec) -> tuple[uuid.UUID, uuid.UUID, int]:
    """
    Run Zone Discovery for a city.
    Returns (job_id, city_id, zones_count).
    """
    from src.infrastructure.database import get_db_session
    from src.guide.application.seeder.repository import SeederRepository
    from src.guide.application.seeder.orchestrator import CitySeederOrchestrator
    from src.guide.infrastructure.google_places_client import GuideGooglePlacesClient
    from src.guide.application.seeder.zone_discovery import ZoneDiscovery

    print(f"\n{'='*60}")
    print(f"Phase A: Zone Discovery — {spec.name}, {spec.country}")
    print(f"  Center: ({spec.lat}, {spec.lng}), radius: {spec.search_radius_km}km")
    print(f"  DBSCAN: eps={spec.dbscan_eps_m}m, min_samples={spec.dbscan_min_samples}")
    print(f"{'='*60}")

    google_places = GuideGooglePlacesClient()
    zone_discovery = ZoneDiscovery(
        google_places,
        dbscan_eps_m=spec.dbscan_eps_m,
        dbscan_min_samples=spec.dbscan_min_samples,
        min_poi_rating=3.5,      # Lower threshold to get more candidates for intl cities
        min_poi_reviews=30,
    )

    async with get_db_session() as db:
        repo = SeederRepository(db)

        # Check if job already exists
        active_job = await repo.get_active_job_for_city(spec.name)
        if active_job is not None:
            progress = active_job.progress_json or {}
            zones_proposed = progress.get("zones_proposed", 0)

            if zones_proposed == 0 and active_job.status == "awaiting_zone_approval":
                print(f"  Found existing job {active_job.id} with 0 zones — marking failed and re-running")
                await repo.update_seed_job(
                    active_job.id,
                    status="failed",
                    error_message="Re-running with new parameters",
                    progress_json=progress,
                    completed=True,
                )
                await db.commit()
            else:
                city_id = active_job.city_id
                if city_id is None:
                    raise RuntimeError(f"Existing job has no city_id")
                # Count zones
                zones = await repo.get_zones_by_city(city_id)
                print(f"  Reusing existing job {active_job.id} (status={active_job.status}, zones={len(zones)})")
                await db.commit()
                return active_job.id, city_id, len(zones)

        orchestrator = CitySeederOrchestrator(repo=repo, zone_discovery=zone_discovery)
        job_id = await orchestrator.start_seed(spec.name, spec.country)
        await db.commit()

        job = await repo.get_seed_job(job_id)
        if job is None or job.city_id is None:
            raise RuntimeError(f"Zone Discovery failed for {spec.name}")

        city_id = job.city_id
        zones = await repo.get_zones_by_city(city_id)
        zones_count = len(zones)

    print(f"  Job ID:  {job_id}")
    print(f"  City ID: {city_id}")
    print(f"  Zones discovered: {zones_count}")
    for z in sorted(zones, key=lambda z: z.poi_count, reverse=True):
        print(f"    {z.name or 'unnamed'}: {z.poi_count} POIs, theme={z.theme}")

    return job_id, city_id, zones_count


# =============================================================================
# Phase B: Auto-select best zone
# =============================================================================

async def phase_b_select_best_zone(city_id: uuid.UUID) -> tuple[uuid.UUID, str, int]:
    """
    Select and approve the best zone for a city.
    Returns (zone_id, zone_name, poi_count).
    """
    from src.infrastructure.database import get_db_session
    from src.guide.application.seeder.repository import SeederRepository

    print(f"\n  Phase B: Auto-selecting best zone...")

    async with get_db_session() as db:
        repo = SeederRepository(db)
        all_zones = await repo.get_zones_by_city(city_id)

        if not all_zones:
            raise RuntimeError(f"No zones found for city_id={city_id}")

        # Check if any already approved
        approved = [z for z in all_zones if z.is_approved]
        if approved:
            best = max(approved, key=lambda z: z.poi_count)
            print(f"  Already approved: {best.name} ({best.poi_count} POIs)")
            return best.id, best.name or str(best.id)[:8], best.poi_count

        # Score: poi_count as primary, proximity to city center as tiebreak
        # For MVP just pick the one with most POIs
        best = max(all_zones, key=lambda z: z.poi_count)

        await repo.approve_zone(best.id)
        await db.commit()

        print(f"  Approved: {best.name} ({best.poi_count} POIs, theme={best.theme})")
        return best.id, best.name or str(best.id)[:8], best.poi_count


# =============================================================================
# Phase C: Generate HTML map
# =============================================================================

async def phase_c_generate_map(
    city_id: uuid.UUID,
    city_name: str,
    recommended_zone_id: uuid.UUID,
) -> str:
    """Generate enhanced HTML map with all zones + RECOMMENDED badge. Returns path."""
    from src.infrastructure.database import get_db_session
    from sqlalchemy import text
    import json

    print(f"\n  Phase C: Generating HTML map...")

    async with get_db_session() as db:
        # City center
        center_result = await db.execute(
            text("SELECT ST_Y(center) AS lat, ST_X(center) AS lng FROM guide_cities WHERE id = :id"),
            {"id": str(city_id)},
        )
        center_row = center_result.mappings().fetchone()
        center_lat = float(center_row["lat"])
        center_lng = float(center_row["lng"])

        # All zones
        zones_result = await db.execute(
            text(
                "SELECT id, name, theme, poi_count, point_count, is_approved, is_active, "
                "ST_AsGeoJSON(boundary) AS boundary_geojson_str, "
                "ST_Area(boundary::geography) / 1e6 AS area_km2, "
                "ST_Y(ST_Centroid(boundary)) AS centroid_lat, "
                "ST_X(ST_Centroid(boundary)) AS centroid_lng "
                "FROM guide_zones WHERE city_id = :city_id ORDER BY poi_count DESC"
            ),
            {"city_id": str(city_id)},
        )
        rows = zones_result.mappings().fetchall()

        # POIs in recommended zone (if any points placed)
        pois_result = await db.execute(
            text(
                "SELECT id, name, point_type, "
                "ST_Y(location) AS lat, ST_X(location) AS lng "
                "FROM guide_points "
                "WHERE zone_id = :zone_id AND point_type = 'poi' "
                "ORDER BY name"
            ),
            {"zone_id": str(recommended_zone_id)},
        )
        poi_rows = pois_result.mappings().fetchall()

    zones_data = []
    for row in rows:
        try:
            geojson = json.loads(row["boundary_geojson_str"])
        except Exception:
            continue
        is_recommended = str(row["id"]) == str(recommended_zone_id)
        zones_data.append({
            "id": str(row["id"]),
            "name": row["name"] or f"Zone {str(row['id'])[:8]}",
            "theme": row["theme"] or "mixed",
            "poi_count": row["poi_count"] or 0,
            "point_count": row["point_count"] or 0,
            "is_approved": bool(row["is_approved"]),
            "is_recommended": is_recommended,
            "boundary_geojson": geojson,
            "area_km2": round(float(row["area_km2"] or 0), 2),
            "centroid_lat": float(row["centroid_lat"] or 0),
            "centroid_lng": float(row["centroid_lng"] or 0),
        })

    pois_data = [
        {
            "id": str(r["id"]),
            "name": r["name"] or "unnamed",
            "lat": float(r["lat"]),
            "lng": float(r["lng"]),
        }
        for r in poi_rows
    ]

    # Recommended zone info for sidebar
    rec_zone = next((z for z in zones_data if z["is_recommended"]), None)
    poi_count = rec_zone["poi_count"] if rec_zone else 0
    est_connectors = poi_count * 12
    est_llm_calls = poi_count * 4 + est_connectors * 1  # main+bonus+recap+commentary per POI, 1 per connector
    est_transitions = poi_count * 4 * 3  # k_neighbors=4, 3 variants
    est_total_blocks = poi_count * 3 + est_connectors + est_transitions
    est_chars = est_total_blocks * 400  # ~400 chars per block average

    html = _ENHANCED_MAP_TEMPLATE.format(
        city_name=city_name,
        center_lat=center_lat,
        center_lng=center_lng,
        zones_json=json.dumps(zones_data, ensure_ascii=False),
        pois_json=json.dumps(pois_data, ensure_ascii=False),
        zones_count=len(zones_data),
        rec_zone_name=rec_zone["name"] if rec_zone else "N/A",
        rec_zone_poi_count=poi_count,
        rec_zone_area=rec_zone["area_km2"] if rec_zone else 0,
        est_connectors=est_connectors,
        est_llm_calls=est_llm_calls,
        est_transitions=est_transitions,
        est_total_blocks=est_total_blocks,
        est_chars=f"{est_chars:,}",
    )

    out_dir = _ROOT / "tmp" / "zone_proposals"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = city_name.lower().replace(" ", "_")
    out_path = out_dir / f"{safe_name}_zones.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"  Map: {out_path}")
    return str(out_path)


_ENHANCED_MAP_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8" />
    <title>Live Guide — Zone Proposal: {city_name}</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; display: flex; height: 100vh; }}
        #sidebar {{
            width: 340px; min-width: 340px; background: #f8fafc; border-right: 1px solid #e2e8f0;
            overflow-y: auto; padding: 20px; font-size: 13px;
        }}
        #map {{ flex: 1; }}
        h1 {{ font-size: 20px; margin-bottom: 4px; }}
        h2 {{ font-size: 15px; color: #334155; margin: 16px 0 8px 0; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; }}
        .stat {{ display: flex; justify-content: space-between; padding: 3px 0; }}
        .stat .label {{ color: #64748b; }}
        .stat .value {{ font-weight: 600; color: #0f172a; }}
        .badge {{
            display: inline-block; padding: 2px 8px; border-radius: 4px;
            font-size: 11px; font-weight: 600; margin-left: 4px;
        }}
        .badge-rec {{ background: #3b82f6; color: #fff; }}
        .badge-other {{ background: #e2e8f0; color: #64748b; }}
        .zone-item {{ padding: 6px 0; border-bottom: 1px solid #f1f5f9; }}
        .zone-item .name {{ font-weight: 600; }}
        .zone-item .meta {{ color: #94a3b8; font-size: 11px; }}
        .poi-list {{ max-height: 300px; overflow-y: auto; }}
        .poi-item {{ padding: 2px 0; color: #334155; }}
        .cost-section {{ background: #fffbeb; padding: 10px; border-radius: 6px; margin-top: 8px; }}
        .cost-section .label {{ color: #92400e; }}
    </style>
</head>
<body>
<div id="sidebar">
    <h1>{city_name}</h1>
    <p style="color:#64748b">Live Guide Zone Proposal</p>

    <h2>Summary</h2>
    <div class="stat"><span class="label">Zones discovered</span><span class="value">{zones_count}</span></div>
    <div class="stat"><span class="label">Recommended zone</span><span class="value">{rec_zone_name}</span></div>
    <div class="stat"><span class="label">POI in recommended</span><span class="value">{rec_zone_poi_count}</span></div>
    <div class="stat"><span class="label">Zone area</span><span class="value">~{rec_zone_area} km&sup2;</span></div>

    <h2>Content Estimate</h2>
    <div class="stat"><span class="label">Est. connectors</span><span class="value">~{est_connectors}</span></div>
    <div class="stat"><span class="label">Est. transitions</span><span class="value">~{est_transitions}</span></div>
    <div class="stat"><span class="label">Total blocks</span><span class="value">~{est_total_blocks}</span></div>
    <div class="stat"><span class="label">io.net LLM calls</span><span class="value">~{est_llm_calls}</span></div>
    <div class="stat"><span class="label">ElevenLabs chars</span><span class="value">~{est_chars}</span></div>

    <h2>All Zones</h2>
    <div id="zones-list"></div>

    <h2>POI in Recommended Zone</h2>
    <div class="poi-list" id="poi-list"></div>
</div>
<div id="map"></div>
<script>
const ZONES = {zones_json};
const POIS = {pois_json};
const CENTER = [{center_lat}, {center_lng}];

const map = L.map('map').setView(CENTER, 14);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution: '&copy; OpenStreetMap', maxZoom: 19
}}).addTo(map);

const palette = ['#3b82f6','#ef4444','#22c55e','#f59e0b','#8b5cf6','#06b6d4','#ec4899','#14b8a6'];

// Zones sidebar
const zonesList = document.getElementById('zones-list');
ZONES.forEach(function(zone, i) {{
    var color = zone.is_recommended ? '#3b82f6' : palette[(i+1) % palette.length];
    var fillOpacity = zone.is_recommended ? 0.25 : 0.12;
    var weight = zone.is_recommended ? 3 : 1.5;

    var poly = L.geoJSON(zone.boundary_geojson, {{
        style: {{ color: color, fillColor: color, fillOpacity: fillOpacity, weight: weight }}
    }}).addTo(map);

    var badge = zone.is_recommended
        ? '<span class="badge badge-rec">RECOMMENDED</span>'
        : '<span class="badge badge-other">other</span>';

    poly.bindPopup(
        '<b>' + zone.name + '</b> ' + badge + '<br>' +
        'POIs: ' + zone.poi_count + ' | Theme: ' + zone.theme +
        ' | Area: ~' + zone.area_km2 + ' km&sup2;',
        {{ maxWidth: 350 }}
    );

    // Sidebar item
    var div = document.createElement('div');
    div.className = 'zone-item';
    div.innerHTML = '<span class="name">' + zone.name + '</span> ' + badge +
        '<div class="meta">' + zone.poi_count + ' POIs &middot; ' + zone.theme +
        ' &middot; ~' + zone.area_km2 + ' km&sup2;</div>';
    zonesList.appendChild(div);

    // Label on map
    if (zone.is_recommended) {{
        L.marker([zone.centroid_lat, zone.centroid_lng], {{
            icon: L.divIcon({{
                className: '',
                html: '<div style="background:#3b82f6;color:#fff;padding:3px 8px;border-radius:4px;font-size:12px;font-weight:600;white-space:nowrap">\\u2605 ' + zone.name + '</div>',
                iconSize: [0, 0],
                iconAnchor: [-5, 15]
            }})
        }}).addTo(map);
    }}
}});

// POI markers
const poiList = document.getElementById('poi-list');
POIS.forEach(function(poi) {{
    L.circleMarker([poi.lat, poi.lng], {{
        radius: 6, color: '#dc2626', fillColor: '#dc2626', fillOpacity: 0.8, weight: 1
    }}).addTo(map).bindPopup('<b>' + poi.name + '</b>');

    var div = document.createElement('div');
    div.className = 'poi-item';
    div.textContent = poi.name;
    poiList.appendChild(div);
}});

// Fit bounds
var allCoords = ZONES.flatMap(function(z) {{
    return z.boundary_geojson.coordinates[0].map(function(c) {{ return [c[1], c[0]]; }});
}});
if (allCoords.length) map.fitBounds(allCoords, {{ padding: [30, 30] }});
</script>
</body>
</html>"""


# =============================================================================
# Phase D: PointPlacement + GraphBuilder + KnowledgeCollector
# =============================================================================

async def phase_d_place_and_collect(
    job_id: uuid.UUID,
    city_id: uuid.UUID,
    zone_id: uuid.UUID,
    zone_name: str,
) -> dict:
    """
    Run Phases 2+3+4 for the approved zone.
    Returns progress dict with counts.
    """
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
    print(f"Phase D: PointPlacement + GraphBuilder + KnowledgeCollector")
    print(f"  Zone: {zone_name} ({zone_id})")
    print(f"{'='*60}")
    print("  This may take 5-15 minutes (OSMnx download + networkx + Wikipedia)")

    # Check if already done
    async with get_db_session() as db:
        repo = SeederRepository(db)
        job = await repo.get_seed_job(job_id)
        if job and job.status in ("complete", "collecting_knowledge"):
            progress = job.progress_json or {}
            if progress.get("points_placed", 0) > 0:
                print(f"  Already done (points_placed={progress['points_placed']}) — skipping")
                return progress

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
    print(f"\n  Phase D complete:")
    print(f"    Points placed:   {progress.get('points_placed', 0)}")
    print(f"    Edges built:     {progress.get('edges_built', 0)}")
    print(f"    Knowledge cards: {progress.get('cards_collected', 0)}")

    # Activate approved points and zone
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
        """), {"city_id": str(city_id)})
        zone_activated = await db.execute(sa_text("""
            UPDATE guide_zones
            SET is_active = true
            WHERE city_id = :city_id AND is_approved = true AND is_active = false
        """), {"city_id": str(city_id)})
        await db.commit()
        print(f"    Points activated: {activated.rowcount}")
        print(f"    Zones activated:  {zone_activated.rowcount}")

    return progress


# =============================================================================
# Phase E: Collect statistics
# =============================================================================

async def phase_e_statistics(
    city_id: uuid.UUID,
    zone_id: uuid.UUID,
    result: CityResult,
) -> CityResult:
    """Fill CityResult with detailed statistics from DB."""
    from src.infrastructure.database import get_db_session
    from sqlalchemy import text as sa_text

    async with get_db_session() as db:
        # Zone details
        zone_row = await db.execute(
            sa_text(
                "SELECT name, poi_count, point_count, theme, "
                "ST_Area(boundary::geography) / 1e6 AS area_km2, "
                "ST_Y(ST_Centroid(boundary)) AS centroid_lat, "
                "ST_X(ST_Centroid(boundary)) AS centroid_lng "
                "FROM guide_zones WHERE id = :zone_id"
            ),
            {"zone_id": str(zone_id)},
        )
        zr = zone_row.mappings().fetchone()
        if zr:
            result.zone_name = zr["name"] or ""
            result.poi_in_zone = zr["poi_count"] or 0
            result.zone_area_km2 = round(float(zr["area_km2"] or 0), 2)
            result.zone_center_lat = float(zr["centroid_lat"] or 0)
            result.zone_center_lng = float(zr["centroid_lng"] or 0)

        # Points breakdown
        pts = await db.execute(
            sa_text(
                "SELECT point_type, count(*) as cnt "
                "FROM guide_points WHERE zone_id = :zone_id "
                "GROUP BY point_type"
            ),
            {"zone_id": str(zone_id)},
        )
        for row in pts.mappings().fetchall():
            if row["point_type"] == "connector":
                result.connectors_in_zone = row["cnt"]

        # Edges
        edges_row = await db.execute(
            sa_text(
                "SELECT count(*) as cnt FROM guide_edges e "
                "JOIN guide_points p ON p.id = e.from_point_id "
                "WHERE p.zone_id = :zone_id"
            ),
            {"zone_id": str(zone_id)},
        )
        result.edges = edges_row.scalar() or 0

        # Knowledge cards
        kc = await db.execute(
            sa_text(
                "SELECT "
                "  count(*) as total, "
                "  count(wikipedia_summary) as wiki, "
                "  count(wikidata_facts) FILTER (WHERE wikidata_facts IS NOT NULL AND wikidata_facts != 'null') as wikidata, "
                "  count(google_place_data) FILTER (WHERE google_place_data IS NOT NULL AND google_place_data != 'null') as google "
                "FROM guide_knowledge_cards kc "
                "JOIN guide_points p ON p.id = kc.point_id "
                "WHERE p.zone_id = :zone_id"
            ),
            {"zone_id": str(zone_id)},
        )
        kc_row = kc.mappings().fetchone()
        if kc_row:
            result.knowledge_cards = kc_row["total"] or 0
            result.wikipedia_cards = kc_row["wiki"] or 0
            result.wikidata_cards = kc_row["wikidata"] or 0
            result.google_details_cards = kc_row["google"] or 0

    return result


# =============================================================================
# Generate points map for completed zone
# =============================================================================

async def generate_points_map(zone_id: uuid.UUID, city_name: str) -> str:
    """Generate HTML map of points/edges for a zone. Returns path."""
    from scripts.guide.visualize_zones import generate_points_map as _gen

    out_dir = _ROOT / "tmp" / "zone_proposals"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = city_name.lower().replace(" ", "_")
    out_path = out_dir / f"{safe_name}_points.html"
    await _gen(zone_id, out_path)
    return str(out_path)


# =============================================================================
# Print statistics
# =============================================================================

def print_city_stats(r: CityResult) -> None:
    est_main = r.poi_in_zone
    est_bonus = r.poi_in_zone
    est_recap = r.poi_in_zone
    est_transitions = r.edges * 3  # 3 variants per edge
    est_commentary = r.connectors_in_zone
    est_total_blocks = est_main + est_bonus + est_recap + est_transitions + est_commentary
    est_llm_calls = est_total_blocks  # 1 LLM call per block
    est_chars = est_total_blocks * 400  # ~400 chars average
    est_ionet_cost = est_llm_calls * 0.001  # ~$0.001 per call

    print(f"\n{'='*60}")
    print(f"=== {r.city_name.upper()} ===")
    print(f"{'='*60}")
    print(f"  Zones discovered:        {r.zones_discovered}")
    print(f"  Recommended zone:        \"{r.zone_name}\" (center: {r.zone_center_lat:.4f}, {r.zone_center_lng:.4f})")
    print(f"  Zone area:               ~{r.zone_area_km2} km2")
    print(f"  POI in zone:             {r.poi_in_zone}")
    print(f"  Connectors in zone:      {r.connectors_in_zone}")
    print(f"  Edges:                   {r.edges}")
    print(f"  Knowledge cards:         {r.knowledge_cards} (Wikipedia: {r.wikipedia_cards}, Wikidata: {r.wikidata_cards}, Google: {r.google_details_cards})")
    print(f"  Estimated content:")
    print(f"    Main blocks:           {est_main}")
    print(f"    Bonus blocks:          {est_bonus}")
    print(f"    Recap blocks:          {est_recap}")
    print(f"    Transitions:           ~{est_transitions}")
    print(f"    Walking commentary:    ~{est_commentary}")
    print(f"    Total blocks:          ~{est_total_blocks}")
    print(f"    io.net LLM calls:      ~{est_llm_calls}")
    print(f"    io.net cost:           ~${est_ionet_cost:.2f}")
    print(f"    ElevenLabs chars:      ~{est_chars:,}")
    print(f"  Maps:")
    print(f"    Zones: {r.map_path}")
    if r.points_map_path:
        print(f"    Points: {r.points_map_path}")


# =============================================================================
# Process one city end-to-end
# =============================================================================

async def process_city(spec: CitySpec, phase: str) -> CityResult:
    """Process one city through all phases. Returns CityResult."""
    result = CityResult(city_name=spec.name, country=spec.country)

    # Phase A: Zone Discovery
    job_id, city_id, zones_count = await phase_a_discovery(spec)
    result.city_id = city_id
    result.job_id = job_id
    result.zones_discovered = zones_count

    # Phase B: Auto-select best zone
    zone_id, zone_name, poi_count = await phase_b_select_best_zone(city_id)
    result.zone_id = zone_id
    result.zone_name = zone_name
    result.poi_in_zone = poi_count

    # Phase C: Generate map
    map_path = await phase_c_generate_map(city_id, spec.name, zone_id)
    result.map_path = map_path

    if phase == "discovery":
        print(f"\n  Phase D skipped (--phase discovery)")
        return result

    # Phase D: PointPlacement + GraphBuilder + KnowledgeCollector
    progress = await phase_d_place_and_collect(job_id, city_id, zone_id, zone_name)

    # Phase E: Statistics
    result = await phase_e_statistics(city_id, zone_id, result)

    # Generate points map
    try:
        points_map_path = await generate_points_map(zone_id, spec.name)
        result.points_map_path = points_map_path
    except Exception as exc:
        print(f"  Warning: points map generation failed: {exc}")

    # Re-generate zones map with updated POI data
    result.map_path = await phase_c_generate_map(city_id, spec.name, zone_id)

    return result


# =============================================================================
# CLI
# =============================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/guide/seed_cities.py",
        description="Seed 4 cities for Live Guide (Paris, Dubai, Shanghai, Istanbul)",
    )
    parser.add_argument("--non-interactive", action="store_true", required=True,
                        help="Required flag for non-interactive mode")
    parser.add_argument("--city", default=None,
                        help="Process only this city (default: all 4)")
    parser.add_argument("--phase", choices=["discovery", "full"], default="full",
                        help="'discovery' = Phase A+B+C only, 'full' = all phases (default: full)")
    return parser


async def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Filter cities if --city specified
    cities = CITIES
    if args.city:
        cities = [c for c in CITIES if c.name.lower() == args.city.lower()]
        if not cities:
            print(f"Unknown city: {args.city}. Available: {[c.name for c in CITIES]}")
            sys.exit(1)

    print("\n" + "=" * 60)
    print("Live Guide — Seed Cities")
    print(f"Cities: {[c.name for c in cities]}")
    print(f"Phase: {args.phase}")
    print("=" * 60)

    results: list[CityResult] = []
    for spec in cities:
        try:
            result = await process_city(spec, args.phase)
            results.append(result)
            print_city_stats(result)
        except Exception as exc:
            logger.exception(f"Failed to process {spec.name}: {exc}")
            print(f"\n{'='*60}")
            print(f"ERROR processing {spec.name}: {exc}")
            print(f"{'='*60}")

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY — All Cities")
    print(f"{'='*60}")
    total_pois = sum(r.poi_in_zone for r in results)
    total_connectors = sum(r.connectors_in_zone for r in results)
    total_edges = sum(r.edges for r in results)
    total_knowledge = sum(r.knowledge_cards for r in results)
    total_wikipedia = sum(r.wikipedia_cards for r in results)

    for r in results:
        status = "OK" if r.zone_id else "FAILED"
        print(f"  {r.city_name:12s} | {status:6s} | zone: {r.zone_name:30s} | POI: {r.poi_in_zone:3d} | conn: {r.connectors_in_zone:3d} | edges: {r.edges:4d} | kc: {r.knowledge_cards:3d}")

    print(f"\n  Total POI:             {total_pois}")
    print(f"  Total connectors:      {total_connectors}")
    print(f"  Total edges:           {total_edges}")
    print(f"  Total knowledge cards: {total_knowledge} (Wikipedia: {total_wikipedia})")

    est_total_blocks = sum(
        r.poi_in_zone * 3 + r.edges * 3 + r.connectors_in_zone
        for r in results
    )
    print(f"  Est. total blocks:     ~{est_total_blocks}")
    print(f"  Est. io.net LLM calls: ~{est_total_blocks}")
    print(f"  Est. io.net cost:      ~${est_total_blocks * 0.001:.2f}")
    print(f"  Est. ElevenLabs chars: ~{est_total_blocks * 400:,}")

    print(f"\nMaps:")
    for r in results:
        print(f"  {r.city_name}: {r.map_path}")
        if r.points_map_path:
            print(f"  {r.city_name} (points): {r.points_map_path}")

    print(f"\n{'='*60}")
    print("DONE")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
