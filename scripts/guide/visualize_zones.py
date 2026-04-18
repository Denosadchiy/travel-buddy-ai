"""
Генерирует standalone HTML файл с интерактивной картой зон/точек.

Режим 1 — карта зон для оценки и утверждения:
    python scripts/guide/visualize_zones.py --city-id <UUID>
    python scripts/guide/visualize_zones.py --city-id <UUID> --output tmp/moscow_zones.html

Режим 2 — карта точек после PointPlacement:
    python scripts/guide/visualize_zones.py --zone-id <UUID> --show-points
    python scripts/guide/visualize_zones.py --zone-id <UUID> --show-points --output tmp/points.html

Опции:
    --city-id     UUID города (режим 1)
    --city-name   Имя города (альтернатива --city-id)
    --zone-id     UUID зоны (режим 2 или конкретная зона в режиме 1)
    --show-points Показать точки и рёбра графа (режим 2)
    --output      Путь к выходному HTML (default: tmp/<name>.html)
    --no-open     Не открывать в браузере автоматически
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import webbrowser
from pathlib import Path
from typing import Optional
from uuid import UUID

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# =============================================================================
# Geometry helpers
# =============================================================================

def _wkt_polygon_to_geojson(wkt: str) -> Optional[dict]:
    """Convert a WKT POLYGON string to a GeoJSON Polygon dict."""
    import re
    m = re.match(r"POLYGON\s*\(\s*\((.+)\)\s*\)", wkt, re.IGNORECASE)
    if not m:
        return None
    coords_str = m.group(1)
    coords = []
    for pair in coords_str.split(","):
        parts = pair.strip().split()
        if len(parts) >= 2:
            coords.append([float(parts[0]), float(parts[1])])  # [lng, lat]
    if not coords:
        return None
    return {"type": "Polygon", "coordinates": [coords]}


def _zone_area_km2(geojson: dict) -> float:
    """Rough polygon area in km² using shoelace formula on lat/lng."""
    try:
        coords = geojson["coordinates"][0]
        n = len(coords)
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += coords[i][0] * coords[j][1]
            area -= coords[j][0] * coords[i][1]
        # Convert degree² to km²: 1° ≈ 111 km
        return abs(area) / 2 * 111 * 111
    except Exception:
        return 0.0


# =============================================================================
# Data loading
# =============================================================================

async def load_zones_for_city(city_id: UUID) -> tuple[dict, list[dict]]:
    """Load city metadata and all zones. Returns (city_info, zone_list)."""
    from src.infrastructure.database import get_db_session
    from src.guide.domain.models import GuideCity, GuideZone
    from sqlalchemy import select, text

    async with get_db_session() as db:
        city = await db.get(GuideCity, city_id)
        if city is None:
            raise ValueError(f"City {city_id} not found")

        # Get city center coordinates
        center_result = await db.execute(
            text("SELECT ST_Y(center) AS lat, ST_X(center) AS lng FROM guide_cities WHERE id = :id"),
            {"id": str(city_id)},
        )
        center_row = center_result.mappings().fetchone()
        center_lat = float(center_row["lat"]) if center_row else 55.7558
        center_lng = float(center_row["lng"]) if center_row else 37.6173

        # Load zones with boundary WKT
        zones_result = await db.execute(
            text(
                "SELECT id, name, theme, poi_count, point_count, is_approved, is_active, "
                "ST_AsText(boundary) AS boundary_wkt, "
                "ST_AsGeoJSON(boundary) AS boundary_geojson_str "
                "FROM guide_zones WHERE city_id = :city_id ORDER BY poi_count DESC"
            ),
            {"city_id": str(city_id)},
        )
        rows = zones_result.mappings().fetchall()

        zones = []
        for row in rows:
            try:
                geojson = json.loads(row["boundary_geojson_str"])
            except Exception:
                geojson = _wkt_polygon_to_geojson(row["boundary_wkt"] or "")

            if geojson is None:
                continue

            zones.append({
                "id": str(row["id"]),
                "name": row["name"] or f"Zone {str(row['id'])[:8]}",
                "theme": row["theme"] or "mixed",
                "poi_count": row["poi_count"] or 0,
                "point_count": row["point_count"] or 0,
                "is_approved": bool(row["is_approved"]),
                "is_active": bool(row["is_active"]),
                "boundary_geojson": geojson,
                "area_km2": round(_zone_area_km2(geojson), 2),
                "top_poi_names": [],  # Would require extra query; omitted for speed
            })

    city_info = {
        "name": city.name,
        "center_lat": center_lat,
        "center_lng": center_lng,
    }
    return city_info, zones


async def load_points_for_zone(zone_id: UUID) -> tuple[dict, list[dict], list[dict]]:
    """Load zone metadata, points, and edges. Returns (zone_info, points, edges)."""
    from src.infrastructure.database import get_db_session
    from src.guide.domain.models import GuideZone, GuidePoint, GuideEdge
    from sqlalchemy import select, text

    async with get_db_session() as db:
        zone = await db.get(GuideZone, zone_id)
        if zone is None:
            raise ValueError(f"Zone {zone_id} not found")

        # Zone center
        center_result = await db.execute(
            text(
                "SELECT ST_Y(ST_Centroid(boundary)) AS lat, ST_X(ST_Centroid(boundary)) AS lng, "
                "ST_AsGeoJSON(boundary) AS boundary_geojson_str "
                "FROM guide_zones WHERE id = :id"
            ),
            {"id": str(zone_id)},
        )
        center_row = center_result.mappings().fetchone()
        center_lat = float(center_row["lat"]) if center_row else 55.7558
        center_lng = float(center_row["lng"]) if center_row else 37.6173
        try:
            boundary_geojson = json.loads(center_row["boundary_geojson_str"])
        except Exception:
            boundary_geojson = None

        # Points with lat/lng from PostGIS
        pts_result = await db.execute(
            text(
                "SELECT id, name, point_type, is_approved, is_active, "
                "ST_Y(location) AS lat, ST_X(location) AS lng "
                "FROM guide_points WHERE zone_id = :zone_id ORDER BY point_type, name"
            ),
            {"zone_id": str(zone_id)},
        )
        pts_rows = pts_result.mappings().fetchall()
        points = [
            {
                "id": str(r["id"]),
                "name": r["name"] or "",
                "point_type": r["point_type"],
                "is_approved": bool(r["is_approved"]),
                "is_active": bool(r["is_active"]),
                "lat": float(r["lat"]),
                "lng": float(r["lng"]),
            }
            for r in pts_rows
        ]

        # Edges — join to get lat/lng of from and to points
        edges_result = await db.execute(
            text(
                "SELECT e.id, "
                "ST_Y(fp.location) AS from_lat, ST_X(fp.location) AS from_lng, "
                "ST_Y(tp.location) AS to_lat, ST_X(tp.location) AS to_lng "
                "FROM guide_edges e "
                "JOIN guide_points fp ON fp.id = e.from_point_id "
                "JOIN guide_points tp ON tp.id = e.to_point_id "
                "WHERE fp.zone_id = :zone_id"
            ),
            {"zone_id": str(zone_id)},
        )
        edges_rows = edges_result.mappings().fetchall()
        edges = [
            {
                "from_lat": float(r["from_lat"]),
                "from_lng": float(r["from_lng"]),
                "to_lat": float(r["to_lat"]),
                "to_lng": float(r["to_lng"]),
            }
            for r in edges_rows
        ]

    zone_info = {
        "id": str(zone_id),
        "name": zone.name or str(zone_id)[:8],
        "theme": zone.theme or "mixed",
        "poi_count": zone.poi_count or 0,
        "point_count": zone.point_count or 0,
        "center_lat": center_lat,
        "center_lng": center_lng,
        "boundary_geojson": boundary_geojson,
    }
    return zone_info, points, edges


# =============================================================================
# HTML templates
# =============================================================================

_ZONES_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8" />
    <title>Live Guide — Zone Review: {city_name}</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body {{ margin: 0; font-family: sans-serif; }}
        #map {{ width: 100vw; height: 100vh; }}
        .zone-popup {{ min-width: 260px; }}
        .zone-popup h3 {{ margin: 0 0 6px 0; font-size: 15px; }}
        .stats {{ color: #555; font-size: 12px; margin-bottom: 6px; }}
        .approve-btn {{
            background: #22c55e; color: #fff; border: none;
            padding: 7px 14px; border-radius: 4px; cursor: pointer;
            font-size: 13px; width: 100%; margin-top: 6px;
        }}
        .approve-btn:hover {{ background: #16a34a; }}
        .badge-approved {{ background:#22c55e; color:#fff; padding:2px 8px; border-radius:4px; font-size:11px; }}
        .badge-pending  {{ background:#f59e0b; color:#fff; padding:2px 8px; border-radius:4px; font-size:11px; }}
        .sql-hint {{ font-size:10px; color:#888; margin-top:6px; word-break:break-all; }}
    </style>
</head>
<body>
<div id="map"></div>
<script>
const ZONES = {zones_json};
const CENTER = [{center_lat}, {center_lng}];
const API_BASE = 'http://localhost:8000/api/guide/admin';

const map = L.map('map').setView(CENTER, 13);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution: '© OpenStreetMap contributors', maxZoom: 19
}}).addTo(map);

const palette = ['#3b82f6','#ef4444','#22c55e','#f59e0b','#8b5cf6','#06b6d4','#ec4899','#14b8a6'];

ZONES.forEach(function(zone, i) {{
    var color = palette[i % palette.length];
    var poly = L.geoJSON(zone.boundary_geojson, {{
        style: {{ color: color, fillColor: color, fillOpacity: 0.18, weight: 2.5 }}
    }}).addTo(map);

    var badge = zone.is_approved
        ? '<span class="badge-approved">✓ Approved</span>'
        : '<span class="badge-pending">Pending</span>';

    var approveBtn = zone.is_approved ? '' :
        '<button class="approve-btn" onclick="approveZone(\\''+zone.id+'\\', this)">Approve Zone</button>';

    var hint = '<div class="sql-hint">SQL: UPDATE guide_zones SET is_approved=TRUE, approved_at=NOW() WHERE id=\\''+zone.id+'\\' ;</div>';

    poly.bindPopup(
        '<div class="zone-popup">' +
        '<h3>' + zone.name + ' ' + badge + '</h3>' +
        '<div class="stats">POIs: ' + zone.poi_count + ' | Theme: ' + zone.theme +
        ' | Area: ~' + zone.area_km2 + ' km²</div>' +
        approveBtn + hint +
        '</div>',
        {{ maxWidth: 380 }}
    );
}});

// Fit bounds to all zones
var allCoords = ZONES.flatMap(function(z) {{
    return z.boundary_geojson.coordinates[0].map(function(c) {{ return [c[1], c[0]]; }});
}});
if (allCoords.length) map.fitBounds(allCoords, {{ padding: [30, 30] }});

async function approveZone(zoneId, btn) {{
    try {{
        var r = await fetch(API_BASE + '/zones/' + zoneId + '/approve', {{
            method: 'PUT',
            headers: {{ 'Content-Type': 'application/json', 'Authorization': 'Bearer ADMIN_TOKEN' }},
            body: JSON.stringify({{ approved: true }})
        }});
        if (r.ok) {{
            btn.outerHTML = '<span class="badge-approved">✓ Approved</span>';
        }} else {{
            alert('API returned ' + r.status + '. Is FastAPI running? Use SQL fallback instead.');
        }}
    }} catch(e) {{
        alert('API error: ' + e.message + '\\nUse SQL fallback shown in popup.');
    }}
}}
</script>
</body>
</html>"""

_POINTS_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8" />
    <title>Live Guide — Points: {zone_name}</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body {{ margin:0; font-family:sans-serif; }}
        #map {{ width:100vw; height:100vh; }}
        .legend {{ position:absolute; bottom:20px; right:10px; z-index:1000;
                   background:#fff; padding:10px; border-radius:6px; font-size:12px;
                   box-shadow:0 2px 6px rgba(0,0,0,.3); }}
        .legend span {{ display:inline-block; width:12px; height:12px;
                        border-radius:50%; margin-right:5px; vertical-align:middle; }}
    </style>
</head>
<body>
<div id="map"></div>
<div class="legend">
    <b>{zone_name}</b><br>
    <span style="background:#2563eb"></span> POI (approved)<br>
    <span style="background:#ef4444"></span> POI (unapproved)<br>
    <span style="background:#9ca3af"></span> Connector<br>
    <span style="background:#d1d5db; border:1px dashed #888"></span> Edge
</div>
<script>
const POINTS = {points_json};
const EDGES  = {edges_json};
const BOUNDARY = {boundary_json};
const CENTER = [{center_lat}, {center_lng}];

const map = L.map('map').setView(CENTER, 15);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    attribution:'© OpenStreetMap contributors', maxZoom:19
}}).addTo(map);

// Zone boundary
if (BOUNDARY) {{
    L.geoJSON(BOUNDARY, {{ style:{{color:'#f59e0b', fillOpacity:0.08, weight:2}} }}).addTo(map);
}}

// Edges (dashed)
EDGES.forEach(function(e) {{
    L.polyline([[e.from_lat, e.from_lng],[e.to_lat, e.to_lng]], {{
        color:'#9ca3af', weight:1, dashArray:'4 4', opacity:0.6
    }}).addTo(map);
}});

// Points
POINTS.forEach(function(p) {{
    var isConnector = p.point_type === 'connector';
    var color = isConnector ? '#9ca3af' : (p.is_approved ? '#2563eb' : '#ef4444');
    var radius = isConnector ? 4 : 8;

    var marker = L.circleMarker([p.lat, p.lng], {{
        radius: radius, color: color, fillColor: color, fillOpacity: 0.8, weight: 1
    }}).addTo(map);

    if (!isConnector) {{
        marker.bindPopup('<b>' + (p.name || 'unnamed') + '</b><br>'
            + 'type: ' + p.point_type + '<br>'
            + 'approved: ' + p.is_approved + '<br>'
            + 'active: ' + p.is_active + '<br>'
            + '<small>' + p.id + '</small>');
    }}
}});

// Fit to points
var allCoords = POINTS.map(function(p) {{ return [p.lat, p.lng]; }});
if (allCoords.length) map.fitBounds(allCoords, {{ padding:[30,30] }});
</script>
</body>
</html>"""


# =============================================================================
# Main generator
# =============================================================================

async def generate_zones_map(
    city_id: Optional[UUID],
    city_name: Optional[str],
    output_path: Path,
) -> None:
    """Generate HTML map of zones for a city."""
    if city_id is None and city_name is not None:
        from src.infrastructure.database import get_db_session
        from src.guide.application.seeder.repository import SeederRepository
        async with get_db_session() as db:
            repo = SeederRepository(db)
            city = await repo.get_city_by_name(city_name)
            if city is None:
                raise ValueError(f"City '{city_name}' not found in DB")
            city_id = city.id

    if city_id is None:
        raise ValueError("Provide --city-id or --city-name")

    city_info, zones = await load_zones_for_city(city_id)

    html = _ZONES_TEMPLATE.format(
        city_name=city_info["name"],
        center_lat=city_info["center_lat"],
        center_lng=city_info["center_lng"],
        zones_json=json.dumps(zones, ensure_ascii=False),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"Zones map written: {output_path}")
    print(f"  City: {city_info['name']}")
    print(f"  Zones: {len(zones)}")


async def generate_points_map(zone_id: UUID, output_path: Path) -> None:
    """Generate HTML map of points/edges for a zone."""
    zone_info, points, edges = await load_points_for_zone(zone_id)

    poi_count = sum(1 for p in points if p["point_type"] == "poi")
    connector_count = sum(1 for p in points if p["point_type"] == "connector")
    print(f"  Zone: {zone_info['name']}")
    print(f"  POIs: {poi_count}, Connectors: {connector_count}, Edges: {len(edges)}")

    html = _POINTS_TEMPLATE.format(
        zone_name=zone_info["name"],
        center_lat=zone_info["center_lat"],
        center_lng=zone_info["center_lng"],
        points_json=json.dumps(points, ensure_ascii=False),
        edges_json=json.dumps(edges, ensure_ascii=False),
        boundary_json=json.dumps(zone_info["boundary_geojson"] or "null"),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"Points map written: {output_path}")


# =============================================================================
# CLI
# =============================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/guide/visualize_zones.py",
        description="Generate Leaflet HTML map for zone review or point inspection",
    )
    parser.add_argument("--city-id", default=None, help="UUID of the city")
    parser.add_argument("--city-name", default=None, help="City name (alt to --city-id)")
    parser.add_argument("--zone-id", default=None, help="UUID of a specific zone")
    parser.add_argument("--show-points", action="store_true",
                        help="Show point markers and graph edges (requires --zone-id)")
    parser.add_argument("--output", default=None,
                        help="Output HTML path (default: tmp/<name>.html)")
    parser.add_argument("--no-open", action="store_true",
                        help="Do not open the browser after generating")
    return parser


async def main_async(args) -> None:
    tmp_dir = _ROOT / "tmp"
    tmp_dir.mkdir(exist_ok=True)

    if args.show_points:
        if not args.zone_id:
            print("❌ --show-points requires --zone-id", file=sys.stderr)
            sys.exit(1)
        zone_id = UUID(args.zone_id)
        out = Path(args.output) if args.output else tmp_dir / f"zone_{str(zone_id)[:8]}_points.html"
        await generate_points_map(zone_id, out)
    elif args.zone_id and not args.city_id and not args.city_name:
        # Single zone
        zone_id = UUID(args.zone_id)
        out = Path(args.output) if args.output else tmp_dir / f"zone_{str(zone_id)[:8]}.html"
        await generate_points_map(zone_id, out)
    else:
        city_id = UUID(args.city_id) if args.city_id else None
        out = Path(args.output) if args.output else tmp_dir / "zones.html"
        await generate_zones_map(city_id, args.city_name, out)

    if not args.no_open:
        webbrowser.open(f"file://{out.resolve()}")
        print(f"Opened in browser: {out.resolve()}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
