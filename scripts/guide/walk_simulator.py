"""
Walk Simulator v3 — realistic continuous audio guide walkthrough.

v3 improvements over v2:
  - Compact route (--max-route-distance-m, default 1500m)
  - Walking commentary on connector points (~one per 250-350m)
  - Timeline with silences synchronized to walking pace (1.4 m/s)
  - Real-time mp3 duration matches actual walk duration (15-20 min)
  - HTML: progress bar, status text, timer, smooth marker movement

Usage:
    python scripts/guide/walk_simulator.py \\
        --zone-id 04bb6ef2-3914-4920-b721-432c8502a1c8 \\
        --voice-style academic --voice-language ru \\
        --point-count 5 --max-route-distance-m 1500
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import radians, cos, sin, asin, sqrt, atan2, degrees
from pathlib import Path
from typing import Optional
from uuid import UUID

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("walk_simulator")

_USABLE_STATUSES = ("validated", "reviewed", "synthesized", "draft")
WALKING_SPEED_MPS = 1.4   # 5 km/h average walking pace
MAX_SILENCE_S = 45.0
MIN_SILENCE_S = 2.0

OUTPUT_DIR = _ROOT / "tmp" / "walk_simulator_output"
CACHE_DIR = _ROOT / "tmp" / "synthesized_samples"


# =========================================================================
# Helpers
# =========================================================================

def _haversine_m(lat1, lng1, lat2, lng2):
    r = 6_371_000.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlam = radians(lng2 - lng1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlam / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _bearing_to_direction(deg: float) -> str:
    """Convert bearing degrees to compass direction word."""
    if deg is None:
        return "ahead"
    dirs = ["север", "северо-восток", "восток", "юго-восток",
            "юг", "юго-запад", "запад", "северо-запад"]
    idx = int((deg + 22.5) % 360 / 45)
    return dirs[idx]


def _fmt_duration(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s"


def _fmt_clock(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def _get_mp3_duration(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=10,
        )
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def _segments_dir(style, lang):
    return OUTPUT_DIR / f"segments_{style}_{lang}"


def _file_slug(zone_slug, style, lang):
    return f"walk_{zone_slug}_{style}_{lang}"


def calculate_silence_duration(distance_m: float, prev_audio_s: float = 0.0) -> float:
    """Walking time minus prev audio. Capped at [MIN_SILENCE_S, MAX_SILENCE_S]."""
    walk_time = distance_m / WALKING_SPEED_MPS
    silence = max(MIN_SILENCE_S, walk_time - prev_audio_s)
    return min(silence, MAX_SILENCE_S)


# =========================================================================
# OSRM routing — real pedestrian polyline along streets
# =========================================================================

async def get_osrm_route(waypoints_latlng: list[tuple[float, float]]) -> dict | None:
    """
    Get real pedestrian route geometry + nav steps from OSRM.
    Returns {geometry: [[lat,lng]...], steps: [...], total_distance_m, total_duration_s}
    or None if OSRM is unavailable.
    """
    import httpx
    if not waypoints_latlng or len(waypoints_latlng) < 2:
        return None
    coords = ";".join(f"{lng},{lat}" for lat, lng in waypoints_latlng)
    url = f"https://router.project-osrm.org/route/v1/foot/{coords}"
    params = {
        "overview": "full",
        "geometries": "geojson",
        "steps": "true",
        "continue_straight": "true",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, params=params)
            data = r.json()
        if data.get("code") != "Ok":
            logger.warning("OSRM error: %s", data.get("message", "unknown"))
            return None
        route = data["routes"][0]
        geom_lnglat = route["geometry"]["coordinates"]
        geometry = [[pt[1], pt[0]] for pt in geom_lnglat]  # lat,lng for Leaflet
        steps = []
        for leg in route["legs"]:
            for step in leg["steps"]:
                man = step.get("maneuver", {})
                steps.append({
                    "type": man.get("type", ""),
                    "modifier": man.get("modifier", ""),
                    "distance_m": step.get("distance", 0),
                    "duration_s": step.get("duration", 0),
                    "name": step.get("name", "") or "",
                    "lat": man.get("location", [0, 0])[1] if man.get("location") else 0,
                    "lng": man.get("location", [0, 0])[0] if man.get("location") else 0,
                })
        return {
            "geometry": geometry,
            "steps": steps,
            "total_distance_m": route["distance"],
            "total_duration_s": route["duration"],
        }
    except Exception as exc:
        logger.warning("OSRM call failed: %s", exc)
        return None


def generate_nav_instruction_ru(step: dict) -> str | None:
    """Convert OSRM step to Russian nav phrase, or None if not worth saying."""
    typ = step.get("type", "")
    modifier = step.get("modifier", "")
    name = step.get("name", "")
    distance = step.get("distance_m", 0)

    direction_map = {
        "left": "налево", "right": "направо",
        "slight left": "чуть левее", "slight right": "чуть правее",
        "sharp left": "резко налево", "sharp right": "резко направо",
        "straight": "прямо",
    }

    if typ == "turn":
        d = direction_map.get(modifier, "")
        if d and name:
            return f"Поверните {d} на {name}"
        if d:
            return f"Поверните {d}"
    elif typ == "depart" and name:
        return f"Идём по {name}"
    elif typ == "continue" and distance > 200 and name:
        m = round(distance / 100) * 100
        return f"Продолжайте по {name} примерно {m} метров"
    elif typ == "arrive":
        return None  # handled by main narrative
    elif typ in ("merge", "fork", "end of road") and modifier and name:
        d = direction_map.get(modifier, "")
        if d:
            return f"Держитесь {d}, на {name}"
    return None


# =========================================================================
# Timeline data classes
# =========================================================================

@dataclass
class TimelineSegment:
    """One segment of the walking timeline."""
    type: str  # 'main' | 'transition' | 'walking_commentary' | 'silence'
    duration_s: float
    text: str = ""
    audio_file: str = ""
    waypoints: list = field(default_factory=list)  # [[lat, lng], ...]
    point_id: str = ""
    point_name: str = ""
    coherence_score: float | None = None
    block_id: str = ""
    on_the_fly: bool = False
    distance_m: float = 0.0


# =========================================================================
# Preflight
# =========================================================================

async def preflight_check(zone_id, voice_style, voice_language, dry_run):
    from src.infrastructure.database import get_db_session
    from src.guide.domain.models import GuideVoice
    from sqlalchemy import select, text as sa_text
    from src.config import settings

    errors = []
    async with get_db_session() as db:
        result = await db.execute(
            select(GuideVoice).where(
                GuideVoice.is_active == True,
                GuideVoice.style_group == voice_style,
                GuideVoice.language == voice_language,
            )
        )
        voice = result.scalar_one_or_none()
        if voice is None:
            errors.append(f"No voice with style={voice_style} lang={voice_language}")
        elif "PLACEHOLDER" in (voice.elevenlabs_voice_id or ""):
            errors.append("Voice has PLACEHOLDER ID")

        if voice:
            cnt = await db.execute(sa_text("""
                SELECT count(DISTINCT p.id) FROM guide_points p
                JOIN guide_content_blocks cb ON cb.point_id = p.id
                WHERE p.zone_id = :zone_id AND p.point_type = 'poi'
                  AND cb.content_type = 'main'
                  AND cb.generation_status IN ('validated', 'reviewed', 'synthesized', 'draft')
                  AND cb.voice_id = :voice_id AND cb.language = :lang
            """), {"zone_id": str(zone_id), "voice_id": str(voice.id), "lang": voice_language})
            poi_count = cnt.scalar()
            print(f"  POI with content: {poi_count}")
            if poi_count < 3:
                errors.append(f"Only {poi_count} POI have content. Need >= 3")

    if not dry_run:
        if not settings.elevenlabs_api_key:
            errors.append("ELEVENLABS_API_KEY not set")
        if not shutil.which("ffmpeg"):
            errors.append("ffmpeg not found")

    if errors:
        print("\n❌ Preflight FAILED:")
        for e in errors:
            print(f"  • {e}")
        sys.exit(1)
    print("  ✅ Preflight passed")
    return voice


# =========================================================================
# POI selection with diversity + max-route-distance constraint
# =========================================================================

def _pick_diverse_pois_compact(pois, point_map, target_count, min_distance_m, max_total_distance_m):
    """
    Pick a CLUSTER of POIs around the highest-scored seed.
    Strategy: take seed = top-scored POI, add nearest unfilled candidates that
    satisfy min-distance constraint, ordered by haversine distance from seed.
    The max_total_distance_m caps the cluster radius (~half of route distance).
    """
    if not pois:
        return []

    seed_id = pois[0].id
    seed = point_map.get(seed_id)
    if seed is None:
        return []

    selected = [seed_id]
    cluster_radius = max_total_distance_m / 2  # POIs within this radius from seed

    # Sort other candidates by distance from seed
    candidates_with_dist = []
    for c in pois[1:]:
        cm = point_map.get(c.id)
        if cm is None:
            continue
        d_from_seed = _haversine_m(seed["lat"], seed["lng"], cm["lat"], cm["lng"])
        if d_from_seed > cluster_radius:
            continue
        candidates_with_dist.append((c, cm, d_from_seed))

    candidates_with_dist.sort(key=lambda x: x[2])

    for c, cm, _d in candidates_with_dist:
        if len(selected) >= target_count:
            break
        # Check min distance to all already-selected
        min_dist = min(
            _haversine_m(cm["lat"], cm["lng"], point_map[s]["lat"], point_map[s]["lng"])
            for s in selected
        )
        if min_dist < min_distance_m:
            continue
        selected.append(c.id)

    # Fill remaining if we couldn't get enough — relax constraints
    if len(selected) < target_count:
        for c, cm, _d in candidates_with_dist:
            if len(selected) >= target_count:
                break
            if c.id in selected:
                continue
            selected.append(c.id)

    return selected


# =========================================================================
# Graph route building
# =========================================================================

async def build_walk_route_v3(zone_id, voice_id, language, point_count,
                              min_distance_m, max_route_distance_m,
                              seed_poi_id=None):
    """
    Build a compact graph route.
    Returns (waypoints, poi_indices, ordered_poi_ids, edge_seq, total_dist, point_map).
    """
    import networkx as nx
    from src.infrastructure.database import get_db_session
    from geoalchemy2.shape import to_shape
    from sqlalchemy import text as sa_text, select
    from src.guide.domain.models import GuidePoint, GuideEdge

    async with get_db_session() as db:
        pts_result = await db.execute(
            select(GuidePoint).where(GuidePoint.zone_id == zone_id, GuidePoint.is_active == True)
        )
        all_points = list(pts_result.scalars().all())

        edges_result = await db.execute(
            select(GuideEdge)
            .join(GuidePoint, GuideEdge.from_point_id == GuidePoint.id)
            .where(GuidePoint.zone_id == zone_id, GuideEdge.is_active == True)
        )
        all_edges = list(edges_result.scalars().all())

        pois_result = await db.execute(sa_text("""
            SELECT p.id, cb.coherence_score
            FROM guide_points p
            JOIN guide_content_blocks cb ON cb.point_id = p.id
            WHERE p.zone_id = :zone_id AND p.point_type = 'poi'
              AND cb.content_type = 'main'
              AND cb.generation_status IN ('validated', 'reviewed', 'synthesized', 'draft')
              AND cb.voice_id = :voice_id AND cb.language = :lang
            ORDER BY cb.coherence_score DESC NULLS LAST
        """), {"zone_id": str(zone_id), "voice_id": str(voice_id), "lang": language})
        poi_candidates = pois_result.fetchall()

    G = nx.Graph()
    edge_map = {}
    for e in all_edges:
        G.add_edge(e.from_point_id, e.to_point_id, weight=e.distance_m)
        edge_map[(e.from_point_id, e.to_point_id)] = e
        edge_map[(e.to_point_id, e.from_point_id)] = e

    point_map = {}
    for p in all_points:
        shape = to_shape(p.location)
        point_map[p.id] = {
            "id": p.id, "name": p.name, "lat": shape.y, "lng": shape.x,
            "point_type": p.point_type,
        }

    graph_pois = [row for row in poi_candidates if row.id in G and row.id in point_map]

    # Optionally force a specific POI as route seed (highest priority)
    if seed_poi_id is not None:
        seed_pois = [p for p in graph_pois if p.id == seed_poi_id]
        other_pois = [p for p in graph_pois if p.id != seed_poi_id]
        graph_pois = seed_pois + other_pois

    selected_poi_ids = _pick_diverse_pois_compact(
        graph_pois, point_map, point_count, min_distance_m, max_route_distance_m
    )
    if len(selected_poi_ids) < 2:
        print("ERROR: Not enough POI for route")
        sys.exit(1)

    # Greedy nearest-neighbor through graph
    current_id = selected_poi_ids[0]
    visited = {current_id}
    ordered_pois = [current_id]
    while len(visited) < len(selected_poi_ids):
        unvisited = [pid for pid in selected_poi_ids if pid not in visited]
        best, best_dist = None, float("inf")
        for tgt in unvisited:
            try:
                d = nx.shortest_path_length(G, current_id, tgt, weight="weight")
                if d < best_dist:
                    best_dist = d
                    best = tgt
            except nx.NetworkXNoPath:
                continue
        if best is None:
            break
        visited.add(best)
        ordered_pois.append(best)
        current_id = best

    waypoints = []
    edge_sequence = []
    total_dist = 0.0
    for i in range(len(ordered_pois)):
        if i == 0:
            waypoints.append(point_map[ordered_pois[0]])
            continue
        try:
            path = nx.shortest_path(G, ordered_pois[i - 1], ordered_pois[i], weight="weight")
        except nx.NetworkXNoPath:
            waypoints.append(point_map[ordered_pois[i]])
            continue
        for j in range(1, len(path)):
            wp = point_map.get(path[j])
            if wp:
                waypoints.append(wp)
            edge_obj = edge_map.get((path[j - 1], path[j]))
            if edge_obj:
                edge_sequence.append({
                    "from_id": path[j - 1], "to_id": path[j],
                    "edge_id": edge_obj.id, "distance_m": edge_obj.distance_m,
                })
                total_dist += edge_obj.distance_m

    poi_indices = [i for i, wp in enumerate(waypoints) if wp["id"] in set(ordered_pois) and wp["point_type"] == "poi"]
    return waypoints, poi_indices, ordered_pois, edge_sequence, total_dist, point_map


# =========================================================================
# Walking commentary generation (on-the-fly)
# =========================================================================

def _extract_street_names_from_osrm_leg(osrm_leg_data: dict) -> list[str]:
    """Extract unique street names from an OSRM leg's steps."""
    names = []
    for step in osrm_leg_data.get("steps", []):
        name = step.get("name", "")
        if name and name not in names:
            names.append(name)
    return names


def _get_street_at_pct(osrm_leg_data: dict, pct: float) -> str:
    """Get the street name at a given fraction (0-1) along an OSRM leg."""
    total = osrm_leg_data.get("total_distance_m", 1)
    target = total * pct
    cumulative = 0.0
    for step in osrm_leg_data.get("steps", []):
        cumulative += step.get("distance_m", step.get("distance", 0))
        if cumulative >= target:
            return step.get("name", "")
    return ""


async def generate_walking_commentary(
    street_name: str, from_poi: str, to_poi: str,
    language: str, city_name: str = "Москве",
    connector_knowledge: str = "",
    neighbor_context: str = "",
    previous_commentaries: str = "",
) -> str:
    """Generate one short walking observation via LLM with rich context."""
    try:
        from src.infrastructure.llm_client import get_guide_narrative_llm_client
        from src.guide.application.content_pipeline.text_validators import auto_fix
        llm = get_guide_narrative_llm_client()
        from src.guide.application.content_pipeline.prompt_templates import WALKING_COMMENTARY_PROMPT
        lang_name = "Russian" if language == "ru" else "English"
        prompt = WALKING_COMMENTARY_PROMPT.format(
            city_name=city_name,
            street_name=street_name or "this street",
            from_poi_name=from_poi,
            to_poi_name=to_poi,
            connector_knowledge=connector_knowledge or "No specific information for this exact location.",
            neighbor_context=neighbor_context or "No nearby landmark information.",
            previous_commentaries=previous_commentaries or "(none yet)",
            language_name=lang_name,
        )
        from src.guide.application.content_pipeline.text_validators import (
            validate_text_quality, has_vague_person_references, has_broken_russian,
        )
        text = await llm.generate_text(prompt, max_tokens=400)
        text = text.strip().strip('"').strip("«»").strip()
        text = auto_fix(text, language)

        # Validate: alphabet + vague persons + broken text
        all_issues = []
        ok, issues = validate_text_quality(text, language)
        if not ok:
            all_issues.extend(issues)
        vague, vi = has_vague_person_references(text, language)
        if vague:
            all_issues.append(f"Unnamed famous people: {vi[:3]}")
        broken, bi = has_broken_russian(text)
        if broken:
            all_issues.extend(bi)

        if all_issues:
            fix_prompt = (
                prompt
                + f"\n\n[CRITICAL FIX: Previous response had issues: {all_issues}. "
                f"Rewrite: ONLY {lang_name} alphabet, NO unnamed 'famous' people "
                f"(either give full name or don't mention people), no broken words.]"
            )
            text2 = await llm.generate_text(fix_prompt, max_tokens=400)
            text2 = auto_fix(text2.strip().strip('"').strip("«»").strip(), language)
            ok2, _ = validate_text_quality(text2, language)
            vague2, _ = has_vague_person_references(text2, language)
            if ok2 and not vague2:
                text = text2
        return text
    except Exception as exc:
        logger.warning("Walking commentary generation failed: %s", exc)
        return ""


def _commentary_count_for_leg(walk_time_s: float) -> int:
    """One commentary per ~100s of walking. Min 2, max 6."""
    return max(2, min(int(walk_time_s / 100), 6))


async def select_commentary_waypoints(waypoints, poi_indices, edge_sequence,
                                      max_commentary_count=15):
    """
    Pick connector waypoints for walking commentary.
    Rules: skip if < 80m from prev voiced point, < 50m from next POI.
    Aim for ~1 commentary per 250-350m.
    """
    commentary_indices = []
    last_voiced_idx = poi_indices[0] if poi_indices else 0
    poi_set = set(poi_indices)

    cumulative_dist = [0.0]
    for i in range(1, len(waypoints)):
        d = _haversine_m(waypoints[i - 1]["lat"], waypoints[i - 1]["lng"],
                          waypoints[i]["lat"], waypoints[i]["lng"])
        cumulative_dist.append(cumulative_dist[-1] + d)

    for i, wp in enumerate(waypoints):
        if i in poi_set or wp["point_type"] != "connector":
            if i in poi_set:
                last_voiced_idx = i
            continue

        # Distance from last voiced point
        dist_from_last = cumulative_dist[i] - cumulative_dist[last_voiced_idx]
        if dist_from_last < 150:  # too close to last point (relaxed from 250)
            continue

        # Distance to next POI
        next_poi_idx = next((p for p in poi_indices if p > i), None)
        if next_poi_idx is None:
            continue
        dist_to_next_poi = cumulative_dist[next_poi_idx] - cumulative_dist[i]
        if dist_to_next_poi < 60:  # too close to next POI (relaxed from 80)
            continue

        commentary_indices.append(i)
        last_voiced_idx = i

        if len(commentary_indices) >= max_commentary_count:
            break

    return commentary_indices


# =========================================================================
# Collect content + build timeline
# =========================================================================

async def build_timeline(waypoints, poi_indices, ordered_pois, point_map,
                          voice_id, language, zone_id, osrm_legs=None):
    """
    Build the full timeline of segments (main, transition, commentary, silence).
    Returns list[TimelineSegment].
    """
    from src.infrastructure.database import get_db_session
    from sqlalchemy import text as sa_text

    timeline = []
    cumulative = [0.0]
    for i in range(1, len(waypoints)):
        d = _haversine_m(waypoints[i - 1]["lat"], waypoints[i - 1]["lng"],
                          waypoints[i]["lat"], waypoints[i]["lng"])
        cumulative.append(cumulative[-1] + d)

    poi_set = set(poi_indices)

    # Calculate commentary count per leg based on walk time
    commentary_indices = []
    for leg_i in range(len(poi_indices) - 1):
        start_wi = poi_indices[leg_i]
        end_wi = poi_indices[leg_i + 1]

        # Get walk time from osrm_legs if available
        leg_walk_time = 300  # default 5 min
        if osrm_legs and leg_i < len(osrm_legs):
            leg_walk_time = osrm_legs[leg_i].get("duration_s", 300)

        count = _commentary_count_for_leg(leg_walk_time)

        # Pick connector waypoints evenly within this leg's range
        connectors_in_leg = [i for i in range(start_wi + 1, end_wi)
                            if waypoints[i]["point_type"] == "connector"]

        if connectors_in_leg and count > 0:
            step = max(1, len(connectors_in_leg) // (count + 1))
            for j in range(count):
                idx = min(j * step + step // 2, len(connectors_in_leg) - 1)
                if idx < len(connectors_in_leg):
                    commentary_indices.append(connectors_in_leg[idx])

    # Pre-load knowledge cards for ALL points in the zone (for neighbor_context)
    poi_knowledge = {}  # point_id -> {wikipedia_summary, wikidata_facts, street_name}
    async with get_db_session() as db:
        r = await db.execute(sa_text("""
            SELECT kc.point_id, kc.street_name, kc.wikipedia_summary, kc.wikidata_facts
            FROM guide_knowledge_cards kc
            JOIN guide_points p ON p.id = kc.point_id
            WHERE p.zone_id = :zid
        """), {"zid": str(zone_id)})
        for row in r.fetchall():
            poi_knowledge[str(row[0])] = {
                "street_name": row[1],
                "wiki": row[2],
                "facts": row[3],
            }

    # Generate commentary SEQUENTIALLY (so previous_commentaries can be passed)
    commentary_data = {}
    previous_texts: list[str] = []
    print(f"  Generating walking commentary for {len(commentary_indices)} connectors...")

    for idx in commentary_indices:
        wp = waypoints[idx]
        prev_poi_idx = max([p for p in poi_indices if p < idx], default=poi_indices[0])
        next_poi_idx = min([p for p in poi_indices if p > idx], default=poi_indices[-1])
        from_name = waypoints[prev_poi_idx]["name"] or "the previous stop"
        to_name = waypoints[next_poi_idx]["name"] or "the next stop"

        # Get street name and connector knowledge for THIS point
        kc = poi_knowledge.get(str(wp["id"]), {})

        # Determine which OSRM leg this commentary is on
        leg_idx = 0
        for pi_idx in range(len(poi_indices) - 1):
            if poi_indices[pi_idx] <= idx < poi_indices[pi_idx + 1]:
                leg_idx = pi_idx
                break

        # Get OSRM street name if available
        osrm_street = ""
        if osrm_legs and leg_idx < len(osrm_legs):
            leg_total_wp = poi_indices[leg_idx + 1] - poi_indices[leg_idx]
            wp_pct = (idx - poi_indices[leg_idx]) / max(leg_total_wp, 1)
            osrm_street = _get_street_at_pct(osrm_legs[leg_idx], wp_pct)

        street_name = osrm_street or kc.get("street_name") or ("этой улице" if language == "ru" else "this street")
        connector_knowledge = (kc.get("wiki") or "")[:300]

        # Build neighbor context: 3 nearest POIs with content
        nearest_pois = sorted(
            [waypoints[pi] for pi in poi_indices if pi != idx],
            key=lambda p: _haversine_m(wp["lat"], wp["lng"], p["lat"], p["lng"]),
        )[:3]
        neighbor_parts = []
        for poi_wp in nearest_pois:
            pkc = poi_knowledge.get(str(poi_wp["id"]), {})
            wiki = (pkc.get("wiki") or "")[:200]
            if wiki:
                neighbor_parts.append(f"- {poi_wp['name']}: {wiki}")
        neighbor_context = "\n".join(neighbor_parts) if neighbor_parts else ""

        previous_commentaries = "\n".join(f"- {t[:120]}" for t in previous_texts[-3:])

        text = await generate_walking_commentary(
            street_name=street_name, from_poi=from_name, to_poi=to_name,
            language=language,
            connector_knowledge=connector_knowledge,
            neighbor_context=neighbor_context,
            previous_commentaries=previous_commentaries,
        )
        if text:
            commentary_data[idx] = {"text": text}
            previous_texts.append(text)

    # Walk through waypoints in order, building timeline
    main_count = 0
    trans_count = 0
    comm_count = 0

    for i, wp in enumerate(waypoints):
        if i in poi_set:
            # Main block for POI
            async with get_db_session() as db:
                r = await db.execute(sa_text("""
                    SELECT id, text_script, coherence_score
                    FROM guide_content_blocks
                    WHERE point_id = :pid AND voice_id = :vid AND language = :lang
                      AND content_type = 'main'
                      AND generation_status IN ('validated', 'reviewed', 'synthesized', 'draft')
                    ORDER BY coherence_score DESC NULLS LAST LIMIT 1
                """), {"pid": str(wp["id"]), "vid": str(voice_id), "lang": language})
                row = r.fetchone()
            if row is None:
                continue
            main_count += 1
            timeline.append(TimelineSegment(
                type="main",
                duration_s=0,  # filled after synthesis
                text=row.text_script,
                point_id=str(wp["id"]),
                point_name=wp["name"] or "",
                coherence_score=row.coherence_score,
                block_id=str(row.id),
                waypoints=[[wp["lat"], wp["lng"]]],
            ))

            # Look for transition to next POI
            next_poi_idx = next((p for p in poi_indices if p > i), None)
            if next_poi_idx is not None:
                next_wp = waypoints[next_poi_idx]
                async with get_db_session() as db:
                    r2 = await db.execute(sa_text("""
                        SELECT cb.id, cb.text_script, cb.coherence_score
                        FROM guide_content_blocks cb
                        JOIN guide_edges e ON e.id = cb.edge_id
                        WHERE e.from_point_id = :from_pid AND e.to_point_id = :to_pid
                          AND cb.voice_id = :vid AND cb.language = :lang
                          AND cb.content_type = 'transition'
                          AND cb.generation_status IN ('validated', 'reviewed', 'synthesized', 'draft')
                          AND cb.variant_index = 0
                        ORDER BY cb.coherence_score DESC NULLS LAST LIMIT 1
                    """), {"from_pid": str(wp["id"]), "to_pid": str(next_wp["id"]),
                           "vid": str(voice_id), "lang": language})
                    trans_row = r2.fetchone()
                if trans_row:
                    trans_count += 1
                    timeline.append(TimelineSegment(
                        type="transition",
                        duration_s=0,
                        text=trans_row.text_script,
                        point_name=f"{wp['name']} → {next_wp['name']}",
                        block_id=str(trans_row.id),
                        coherence_score=trans_row.coherence_score,
                        waypoints=[[waypoints[k]["lat"], waypoints[k]["lng"]]
                                    for k in range(i, min(i + 3, len(waypoints)))],
                    ))
                else:
                    # Generate on-the-fly transition
                    from src.infrastructure.llm_client import get_guide_narrative_llm_client
                    try:
                        llm = get_guide_narrative_llm_client()
                        lang_name = "Russian" if language == "ru" else "English"
                        prompt = (f"Write a short (15-20 word) spoken transition phrase "
                                  f"FROM '{wp['name']}' TOWARD '{next_wp['name']}' "
                                  f"in {lang_name}. Sound natural. Respond with ONLY the text, no JSON.")
                        from src.guide.application.content_pipeline.text_validators import (
                            auto_fix as _af, validate_text_quality as _vtq,
                        )
                        otf_text = await llm.generate_text(prompt, max_tokens=150)
                        otf_text = _af(otf_text.strip().strip('"').strip("«»").strip(), language)
                        ok_otf, _issues = _vtq(otf_text, language)
                        if not ok_otf:
                            # Retry once with explicit fix
                            otf2 = await llm.generate_text(
                                prompt + f"\n\n[CRITICAL: use ONLY {lang_name} alphabet, no other letters/scripts]",
                                max_tokens=150,
                            )
                            otf2 = _af(otf2.strip().strip('"').strip("«»").strip(), language)
                            ok2, _ = _vtq(otf2, language)
                            if ok2:
                                otf_text = otf2
                        if otf_text:
                            trans_count += 1
                            timeline.append(TimelineSegment(
                                type="transition",
                                duration_s=0,
                                text=otf_text,
                                point_name=f"{wp['name']} → {next_wp['name']}",
                                block_id=f"otf-{uuid.uuid4().hex[:8]}",
                                on_the_fly=True,
                                waypoints=[[waypoints[k]["lat"], waypoints[k]["lng"]]
                                            for k in range(i, min(i + 3, len(waypoints)))],
                            ))
                    except Exception as exc:
                        logger.warning("OTF transition failed: %s", exc)

        elif i in commentary_data:
            comm_count += 1
            comm_text = commentary_data[i]["text"]
            timeline.append(TimelineSegment(
                type="walking_commentary",
                duration_s=0,
                text=comm_text,
                point_name=wp["name"] or "",
                block_id=f"comm-{i}-{uuid.uuid4().hex[:8]}",
                on_the_fly=True,
                waypoints=[[wp["lat"], wp["lng"]]],
            ))

    return timeline, main_count, trans_count, comm_count


# =========================================================================
# Synthesize audio for timeline segments
# =========================================================================

async def synthesize_timeline(timeline, elevenlabs_voice_id, dry_run, seg_dir, lang):
    from src.guide.infrastructure.elevenlabs_client import ElevenLabsClient

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    seg_dir.mkdir(parents=True, exist_ok=True)

    main_idx = 0
    trans_idx = 0
    comm_idx = 0
    for seg in timeline:
        if seg.type == "main":
            main_idx += 1
            seg.audio_file = f"stop_{main_idx:02d}_main.mp3"
        elif seg.type == "transition":
            trans_idx += 1
            seg.audio_file = f"transition_{trans_idx:02d}.mp3"
        elif seg.type == "walking_commentary":
            comm_idx += 1
            seg.audio_file = f"commentary_{comm_idx:02d}.mp3"

    voiced = [s for s in timeline if s.type in ("main", "transition", "walking_commentary")]
    total_chars = sum(len(s.text) for s in voiced)
    print(f"\n  Total voice segments: {len(voiced)}")
    print(f"  Total characters: {total_chars}")
    print(f"  Estimated cost: ~${total_chars * 0.00015:.2f}")

    if dry_run:
        print("  [DRY RUN] skipping synthesis")
        for seg in voiced:
            seg.duration_s = max(2.0, len(seg.text.split()) / 140 * 60)
        return

    client = ElevenLabsClient()
    sem = asyncio.Semaphore(3)  # Creator plan supports parallel

    async def _synth(seg):
        async with sem:
            cache_path = CACHE_DIR / f"{seg.block_id}.mp3"
            if cache_path.exists():
                shutil.copy2(cache_path, seg_dir / seg.audio_file)
                seg.duration_s = _get_mp3_duration(cache_path)
                print(f"  Cached: {seg.audio_file} ({_fmt_duration(seg.duration_s)})")
                return
            tts_text = seg.text  # LLM writes numbers as words; no post-processing
            try:
                audio = await client.synthesize_batch(text=tts_text, voice_id=elevenlabs_voice_id)
                cache_path.write_bytes(audio)
                shutil.copy2(cache_path, seg_dir / seg.audio_file)
                seg.duration_s = _get_mp3_duration(cache_path)
                print(f"  ✅ {seg.audio_file}: {_fmt_duration(seg.duration_s)}, {len(audio)} bytes")
            except Exception as exc:
                logger.error("Synthesis failed for %s: %s", seg.audio_file, exc)
                seg.duration_s = 5.0

    await asyncio.gather(*[_synth(s) for s in voiced])


# =========================================================================
# Insert silences into timeline based on walking pace
# =========================================================================

def insert_silences(timeline, waypoints, poi_indices):
    """
    Insert silence segments between voiced segments based on walking time
    between their respective waypoints.
    """
    if not timeline:
        return timeline

    # Map each timeline segment back to its waypoint position
    # main → poi_index, commentary → its waypoint, transition → next poi
    poi_seq = list(poi_indices)
    poi_seq_iter = iter(poi_seq)
    next_poi_idx = next(poi_seq_iter, None)

    seg_waypoint_idx = []
    poi_use_iter = iter(poi_seq)
    used_pois = []
    for seg in timeline:
        if seg.type == "main":
            used_pois.append(next(poi_use_iter, poi_seq[-1]))
            seg_waypoint_idx.append(used_pois[-1])
        elif seg.type == "transition":
            # Place transition at start of next POI's waypoint
            seg_waypoint_idx.append(used_pois[-1])  # transition starts at last POI
        elif seg.type == "walking_commentary":
            # Find the waypoint by matching coordinates
            wp_lat, wp_lng = seg.waypoints[0]
            best_idx = 0
            best_dist = float("inf")
            for i, wp in enumerate(waypoints):
                d = abs(wp["lat"] - wp_lat) + abs(wp["lng"] - wp_lng)
                if d < best_dist:
                    best_dist = d
                    best_idx = i
            seg_waypoint_idx.append(best_idx)
        else:
            seg_waypoint_idx.append(0)

    # Compute cumulative distances
    cumulative = [0.0]
    for i in range(1, len(waypoints)):
        d = _haversine_m(waypoints[i - 1]["lat"], waypoints[i - 1]["lng"],
                          waypoints[i]["lat"], waypoints[i]["lng"])
        cumulative.append(cumulative[-1] + d)

    new_timeline = []
    for i, seg in enumerate(timeline):
        new_timeline.append(seg)
        if i + 1 >= len(timeline):
            break

        wp_a = seg_waypoint_idx[i]
        wp_b = seg_waypoint_idx[i + 1]
        if wp_b <= wp_a:
            continue

        distance = cumulative[wp_b] - cumulative[wp_a]
        seg.distance_m = distance

        silence_s = calculate_silence_duration(distance, prev_audio_s=seg.duration_s)
        if silence_s > MIN_SILENCE_S:
            silence_waypoints = [
                [waypoints[k]["lat"], waypoints[k]["lng"]]
                for k in range(wp_a, wp_b + 1)
            ]
            new_timeline.append(TimelineSegment(
                type="silence",
                duration_s=silence_s,
                waypoints=silence_waypoints,
                distance_m=distance,
            ))

    return new_timeline


# =========================================================================
# Assemble final mp3 with silence segments
# =========================================================================

def assemble_final_mp3(timeline, output_path, seg_dir):
    voiced_segs = [s for s in timeline if s.type != "silence" and s.audio_file]
    if not voiced_segs:
        return False

    # Pre-generate silence files of unique durations
    unique_silences = {}
    for seg in timeline:
        if seg.type == "silence":
            key = round(seg.duration_s, 1)
            unique_silences.setdefault(key, None)

    sil_dir = output_path.parent / "_silence_cache"
    sil_dir.mkdir(exist_ok=True)
    for dur in unique_silences:
        sil_path = sil_dir / f"silence_{int(dur*10)}.mp3"
        if not sil_path.exists():
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                 "-t", str(dur), "-c:a", "libmp3lame", "-b:a", "128k", str(sil_path)],
                capture_output=True, timeout=30,
            )
        unique_silences[dur] = sil_path

    concat = output_path.parent / "_concat.txt"
    with open(concat, "w") as f:
        for seg in timeline:
            if seg.type == "silence":
                sil = unique_silences.get(round(seg.duration_s, 1))
                if sil and sil.exists():
                    f.write(f"file '{sil.resolve()}'\n")
            else:
                seg_path = seg_dir / seg.audio_file
                if seg_path.exists():
                    f.write(f"file '{seg_path.resolve()}'\n")

    r = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
         "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
         "-c:a", "libmp3lame", "-b:a", "128k", str(output_path)],
        capture_output=True, text=True, timeout=300,
    )
    concat.unlink(missing_ok=True)
    return r.returncode == 0


# =========================================================================
# Markdown report
# =========================================================================

def generate_markdown(timeline, waypoints, zone_name, voice_name, mp3_path, output_path, seg_dir_name):
    voiced = [s for s in timeline if s.type != "silence"]
    main_count = sum(1 for s in voiced if s.type == "main")
    trans_count = sum(1 for s in voiced if s.type == "transition")
    comm_count = sum(1 for s in voiced if s.type == "walking_commentary")
    total_chars = sum(len(s.text) for s in voiced)
    total_duration = sum(s.duration_s for s in timeline)
    voiced_duration = sum(s.duration_s for s in voiced)
    silence_duration = sum(s.duration_s for s in timeline if s.type == "silence")
    poi_wp = sum(1 for w in waypoints if w["point_type"] == "poi")
    mp3_size = mp3_path.stat().st_size / (1024 * 1024) if mp3_path.exists() else 0

    lines = [
        f"# Walk Route v3: {zone_name}",
        "", f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC",
        f"**Zone:** {zone_name}", f"**Voice:** {voice_name}",
        f"**Route:** {len(waypoints)} waypoints ({poi_wp} POI + {len(waypoints)-poi_wp} connectors)",
        f"**Stops:** {main_count} POI, {trans_count} transitions, {comm_count} walking commentaries",
        f"**Total duration:** {_fmt_duration(total_duration)}",
        f"**Voice duration:** {_fmt_duration(voiced_duration)} ({voiced_duration/total_duration*100:.0f}%)",
        f"**Silence duration:** {_fmt_duration(silence_duration)} ({silence_duration/total_duration*100:.0f}%)",
        f"**Text length:** {total_chars:,} characters",
        f"**MP3 size:** {mp3_size:.1f} MB",
        "", "---", "",
        "## Timeline",
        "",
        "| # | Type | Duration | Content/Distance |",
        "|---|------|----------|------------------|",
    ]
    for i, seg in enumerate(timeline):
        if seg.type == "silence":
            lines.append(f"| {i+1} | 🔇 silence | {_fmt_duration(seg.duration_s)} | walking {seg.distance_m:.0f}m |")
        elif seg.type == "main":
            lines.append(f"| {i+1} | 🎙 main | {_fmt_duration(seg.duration_s)} | {seg.point_name[:50]} |")
        elif seg.type == "transition":
            otf = " (OTF)" if seg.on_the_fly else ""
            lines.append(f"| {i+1} | ➡️ transition{otf} | {_fmt_duration(seg.duration_s)} | {seg.point_name[:50]} |")
        elif seg.type == "walking_commentary":
            lines.append(f"| {i+1} | 💬 commentary | {_fmt_duration(seg.duration_s)} | {seg.text[:50]}... |")

    lines.extend(["", "---", "", "## Stops & narration", ""])

    main_num = trans_num = comm_num = 0
    for seg in voiced:
        if seg.type == "main":
            main_num += 1
            lines.extend([
                f"### Stop {main_num}: {seg.point_name}", "",
                f"- **Audio:** {seg_dir_name}/{seg.audio_file} ({_fmt_duration(seg.duration_s)})",
                f"- **Coherence score:** {seg.coherence_score} / 5.0",
                "", "#### Full text", "", f"> {seg.text}", "", "---", "",
            ])
        elif seg.type == "transition":
            trans_num += 1
            otf = " (on-the-fly)" if seg.on_the_fly else ""
            lines.extend([
                f"### Transition {trans_num}{otf}", "",
                f"- **Route:** {seg.point_name}",
                f"- **Audio:** {seg_dir_name}/{seg.audio_file} ({_fmt_duration(seg.duration_s)})",
                "", "#### Full text", "", f"> {seg.text}", "", "---", "",
            ])
        elif seg.type == "walking_commentary":
            comm_num += 1
            lines.extend([
                f"### Walking commentary {comm_num}", "",
                f"- **Audio:** {seg_dir_name}/{seg.audio_file} ({_fmt_duration(seg.duration_s)})",
                "", "#### Full text", "", f"> {seg.text}", "", "---", "",
            ])

    output_path.write_text("\n".join(lines), encoding="utf-8")


# =========================================================================
# HTML map with realistic playback
# =========================================================================

def generate_html_map(timeline, waypoints, zone_name, voice_name, output_path, seg_dir_name,
                       osrm_polyline=None, nav_steps=None, osrm_legs=None):
    voiced = [s for s in timeline if s.type != "silence"]
    main_segs = [s for s in voiced if s.type == "main"]
    total_duration = sum(s.duration_s for s in timeline)
    # Use OSRM polyline if available (real streets), fallback to graph waypoints
    polyline_points = osrm_polyline if osrm_polyline else [[w["lat"], w["lng"]] for w in waypoints]
    waypoints_json = polyline_points
    nav_steps_json = nav_steps or []

    # Stops for popups
    stops_json = [{
        "name": s.point_name, "lat": s.waypoints[0][0], "lng": s.waypoints[0][1],
        "text_preview": s.text[:250].replace('"', '\\"').replace("\n", " "),
        "audio_file": s.audio_file, "duration": _fmt_duration(s.duration_s),
        "duration_s": s.duration_s,
        "score": s.coherence_score if s.coherence_score is not None else "N/A",
        "chars": len(s.text),
    } for s in main_segs]

    timeline_json = []
    for s in timeline:
        entry = {
            "type": s.type, "duration_s": s.duration_s,
            "audio_file": s.audio_file, "waypoints": s.waypoints,
            "name": s.point_name,
            "text_preview": s.text[:120].replace('"', '\\"').replace("\n", " ") if s.text else "",
            "distance_m": s.distance_m,
        }
        timeline_json.append(entry)

    # Build legs_json: assign audio events (transitions + commentaries) to each leg
    # by walking through the timeline in order.
    legs_json = []
    if osrm_legs:
        # Split voiced timeline into per-leg buckets.
        # Order is: main[0], transition[0], comm..., main[1], transition[1], comm..., ...
        # Each leg corresponds to segments BETWEEN main[i] and main[i+1].
        main_positions = [i for i, t in enumerate(timeline_json) if t["type"] == "main"]

        for leg_i, leg in enumerate(osrm_legs):
            events = []
            # Segments that belong to this leg = everything after main[leg_i] until main[leg_i+1]
            start_ti = main_positions[leg_i] + 1 if leg_i < len(main_positions) else len(timeline_json)
            end_ti = main_positions[leg_i + 1] if leg_i + 1 < len(main_positions) else len(timeline_json)

            leg_voiced = [timeline_json[k] for k in range(start_ti, end_ti)
                          if timeline_json[k]["type"] in ("transition", "walking_commentary")]

            # Distribute evenly along leg geometry
            for vi, v in enumerate(leg_voiced):
                pct = (vi + 0.5) / max(len(leg_voiced), 1)  # 0.5/(n), 1.5/(n), ...
                pct = max(0.05, min(pct, 0.95))
                street = ""
                if leg.get("street_sequence"):
                    si = min(int(pct * len(leg["street_sequence"])), len(leg["street_sequence"]) - 1)
                    street = leg["street_sequence"][si]
                events.append({
                    "type": v["type"],
                    "audio_file": v["audio_file"],
                    "duration_s": v["duration_s"],
                    "geometry_pct": pct,
                    "street_name": street,
                })

            legs_json.append({
                "geometry": leg["geometry"],
                "distance_m": leg["distance_m"],
                "walk_time_s": leg["duration_s"],
                "audio_events": events,
            })

    # full_geometry for polyline = concat of all leg geometries
    fg = []
    for leg in legs_json:
        if fg:
            fg.extend(leg["geometry"][1:])
        else:
            fg.extend(leg["geometry"])
    if not fg:
        fg = waypoints_json  # fallback

    route_data = json.dumps({
        "stops": stops_json, "timeline": timeline_json,
        "waypoints": fg, "total_duration_s": total_duration,
        "seg_dir": seg_dir_name,
        "legs": legs_json,
    }, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Walk Route v3: {zone_name}</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}
    #map{{width:calc(100vw - 340px);height:calc(100vh - 80px);float:left}}
    #sidebar{{width:340px;height:calc(100vh - 80px);float:right;overflow-y:auto;background:#f8fafc;padding:16px;border-left:1px solid #e2e8f0}}
    #sidebar h2{{font-size:18px;margin-bottom:4px;color:#1e293b}}
    #sidebar .meta{{color:#64748b;font-size:13px;margin-bottom:16px}}
    .stop-marker{{background:#3b82f6;color:white;border-radius:50%;width:34px;height:34px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px;border:3px solid white;box-shadow:0 2px 6px rgba(0,0,0,.3)}}
    .sidebar-item{{padding:12px;background:white;margin-bottom:8px;border-radius:8px;cursor:pointer;border:1px solid #e2e8f0}}
    .sidebar-item:hover{{background:#eff6ff;border-color:#93c5fd}}
    .sidebar-item.active{{background:#dbeafe;border-color:#3b82f6}}
    .sidebar-item b{{display:block;font-size:14px;color:#1e293b}}
    .sidebar-item small{{color:#64748b;font-size:12px}}
    #control-bar{{position:fixed;bottom:0;left:0;width:100vw;height:80px;background:#1e293b;color:white;display:flex;align-items:center;padding:0 20px;gap:16px;z-index:1000;box-shadow:0 -2px 10px rgba(0,0,0,.3)}}
    .play-btn{{background:#22c55e;color:white;padding:12px 24px;border:none;border-radius:8px;font-size:15px;font-weight:700;cursor:pointer;flex-shrink:0}}
    .play-btn.playing{{background:#ef4444}}
    #status-text{{font-size:14px;flex:0 0 280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
    #progress-container{{flex:1;height:8px;background:#334155;border-radius:4px;overflow:hidden;position:relative}}
    #progress-bar{{height:100%;background:linear-gradient(90deg,#3b82f6,#22c55e);width:0%;transition:width .3s linear}}
    #timer{{font-family:'SF Mono',monospace;font-size:14px;flex-shrink:0;min-width:90px;text-align:right}}
    @keyframes pulse{{0%{{box-shadow:0 0 0 0 rgba(239,68,68,.7)}}70%{{box-shadow:0 0 0 15px rgba(239,68,68,0)}}100%{{box-shadow:0 0 0 0 rgba(239,68,68,0)}}}}
    .user-marker{{animation:pulse 2s infinite}}
    .leaflet-popup-content-wrapper{{border-radius:10px!important}}
    .stop-popup{{min-width:280px;max-width:340px}}
    .stop-popup h3{{margin:0 0 8px;font-size:15px}}
    .stop-popup audio{{width:100%;margin:8px 0}}
    .stop-popup .ptext{{font-size:13px;line-height:1.5;color:#334155;max-height:120px;overflow-y:auto}}
  </style>
</head>
<body>
  <div id="map"></div>
  <div id="sidebar">
    <h2>{zone_name}</h2>
    <p class="meta"><b>{len(stops_json)}</b> stops | <b>{_fmt_duration(total_duration)}</b> walk | {voice_name}</p>
    <div id="stops-list"></div>
  </div>
  <div id="control-bar">
    <button class="play-btn" id="playAllBtn" onclick="togglePlayAll()">&#9654; Play Walk</button>
    <div id="status-text">⏸ Готов к старту</div>
    <div id="progress-container"><div id="progress-bar"></div></div>
    <div id="timer">0:00 / {_fmt_clock(total_duration)}</div>
  </div>
  <script>
    const ROUTE = {route_data};
    let isPlaying = false, currentAudio = null, elapsedS = 0;
    let progressTimer = null;

    const map = L.map('map');
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
      {{attribution:'&copy; OpenStreetMap'}}).addTo(map);

    if (ROUTE.waypoints.length > 0) {{
      L.polyline(ROUTE.waypoints, {{color:'#3b82f6', weight:4, opacity:.7}}).addTo(map);
      map.fitBounds(L.latLngBounds(ROUTE.waypoints), {{padding:[50, 50]}});
    }}

    // Nav markers disabled until iOS integration (data still emitted in ROUTE.nav_steps).

    const userMarker = L.circleMarker(ROUTE.waypoints[0] || [55.75, 37.61], {{
      radius: 9, color: '#ef4444', fillColor: '#ef4444', fillOpacity: .9,
      weight: 3, className: 'user-marker'
    }}).addTo(map);

    const markers = [];
    ROUTE.stops.forEach((stop, i) => {{
      const icon = L.divIcon({{
        html: '<div class="stop-marker">' + (i+1) + '</div>',
        className: '', iconSize: [34, 34], iconAnchor: [17, 17], popupAnchor: [0, -20]
      }});
      const marker = L.marker([stop.lat, stop.lng], {{icon}}).addTo(map);
      const audioHtml = stop.audio_file ?
        '<audio controls src="./' + ROUTE.seg_dir + '/' + stop.audio_file + '"></audio>' : '';
      marker.bindPopup(
        '<div class="stop-popup"><h3>' + (i+1) + '. ' + stop.name + '</h3>' +
        '<div style="color:#64748b;font-size:12px;margin-bottom:6px">' + stop.duration +
        ' | Score: ' + stop.score + '</div>' + audioHtml +
        '<div class="ptext">' + stop.text_preview + '</div></div>',
        {{maxWidth: 380}}
      );
      markers.push(marker);

      const item = document.createElement('div');
      item.className = 'sidebar-item';
      item.id = 'sidebar-stop-' + i;
      item.innerHTML = '<b>' + (i+1) + '. ' + stop.name + '</b><small>' + stop.duration + '</small>';
      item.onclick = () => {{ map.flyTo([stop.lat, stop.lng], 17, {{duration:1}}); marker.openPopup(); }};
      document.getElementById('stops-list').appendChild(item);
    }});

    function setStatus(text) {{ document.getElementById('status-text').textContent = text; }}
    function updateProgress() {{
      const pct = Math.min(elapsedS / ROUTE.total_duration_s * 100, 100);
      document.getElementById('progress-bar').style.width = pct + '%';
      const m = Math.floor(elapsedS / 60), s = Math.floor(elapsedS % 60);
      document.getElementById('timer').textContent =
        m + ':' + (s < 10 ? '0' : '') + s + ' / ' + '{_fmt_clock(total_duration)}';
    }}

    function animateMarkerAlongWaypoints(marker, wps, durationMs) {{
      if (!wps || wps.length < 2) return new Promise(r => setTimeout(r, durationMs));
      let totalDist = 0;
      const segs = [];
      for (let i = 0; i < wps.length - 1; i++) {{
        const d = Math.sqrt(Math.pow(wps[i+1][0] - wps[i][0], 2) + Math.pow(wps[i+1][1] - wps[i][1], 2));
        segs.push({{from: wps[i], to: wps[i+1], dist: d}});
        totalDist += d;
      }}
      return new Promise(async resolve => {{
        for (const seg of segs) {{
          if (!isPlaying) {{ resolve(); return; }}
          const segDur = totalDist > 0 ? durationMs * (seg.dist / totalDist) : 50;
          await new Promise(r2 => {{
            const start = performance.now();
            function step(now) {{
              const p = Math.min((now - start) / segDur, 1);
              marker.setLatLng([
                seg.from[0] + (seg.to[0] - seg.from[0]) * p,
                seg.from[1] + (seg.to[1] - seg.from[1]) * p
              ]);
              if (p < 1 && isPlaying) requestAnimationFrame(step);
              else r2();
            }}
            requestAnimationFrame(step);
          }});
        }}
        resolve();
      }});
    }}

    function playAudioAndWait(audio) {{
      return new Promise(r => {{
        audio.onended = r; audio.onerror = r;
        audio.play().catch(r);
      }});
    }}

    async function togglePlayAll() {{
      const btn = document.getElementById('playAllBtn');
      if (isPlaying) {{
        isPlaying = false;
        if (currentAudio) {{ currentAudio.pause(); currentAudio = null; }}
        if (progressTimer) {{ clearInterval(progressTimer); progressTimer = null; }}
        btn.textContent = '\\u25B6 Play Walk';
        btn.classList.remove('playing');
        setStatus('⏸ Пауза');
        return;
      }}
      isPlaying = true; elapsedS = 0;
      btn.textContent = '\\u23F9 Stop';
      btn.classList.add('playing');
      progressTimer = setInterval(() => {{
        if (isPlaying) {{ elapsedS += 0.5; updateProgress(); }}
      }}, 500);

      const segDir = ROUTE.seg_dir;
      for (let stopIdx = 0; stopIdx < ROUTE.stops.length && isPlaying; stopIdx++) {{
        const stop = ROUTE.stops[stopIdx];

        // 1. Stand at POI, play main
        userMarker.setLatLng([stop.lat, stop.lng]);
        map.flyTo([stop.lat, stop.lng], 16, {{duration: 1.5}});
        if (markers[stopIdx]) {{
          markers[stopIdx].openPopup();
          document.querySelectorAll('.sidebar-item').forEach(el => el.classList.remove('active'));
          const sItem = document.getElementById('sidebar-stop-' + stopIdx);
          if (sItem) {{ sItem.classList.add('active'); sItem.scrollIntoView({{block:'center'}}); }}
        }}
        setStatus('🎙 ' + stop.name);
        if (stop.audio_file) {{
          currentAudio = new Audio('./' + segDir + '/' + stop.audio_file);
          await playAudioAndWait(currentAudio);
        }}

        // 2. Walk to next POI along OSRM leg geometry
        if (stopIdx < ROUTE.legs.length && isPlaying) {{
          const leg = ROUTE.legs[stopIdx];
          const geom = leg.geometry;
          const walkMs = leg.walk_time_s * 1000;
          const events = (leg.audio_events || []).sort((a,b) => a.geometry_pct - b.geometry_pct);
          let nextEvt = 0;

          setStatus('🚶 Идём... (' + Math.round(leg.distance_m) + 'м)');

          await new Promise(resolve => {{
            const startT = performance.now();
            function step(now) {{
              if (!isPlaying) {{ resolve(); return; }}
              const p = Math.min((now - startT) / walkMs, 1.0);
              // Smooth interpolation between geometry points
              const exactIdx = p * (geom.length - 1);
              const lo = Math.floor(exactIdx);
              const hi = Math.min(lo + 1, geom.length - 1);
              const frac = exactIdx - lo;
              const lat = geom[lo][0] + (geom[hi][0] - geom[lo][0]) * frac;
              const lng = geom[lo][1] + (geom[hi][1] - geom[lo][1]) * frac;
              userMarker.setLatLng([lat, lng]);

              // Throttle map pan to every 2 seconds
              if (!step._lastPan || now - step._lastPan > 2000) {{
                  map.panTo([lat, lng], {{animate: true, duration: 1.5}});
                  step._lastPan = now;
              }}

              // Fire audio events at their geometry_pct
              while (nextEvt < events.length && p >= events[nextEvt].geometry_pct) {{
                const evt = events[nextEvt]; nextEvt++;
                if (evt.audio_file) {{
                  const a = new Audio('./' + segDir + '/' + evt.audio_file);
                  a.play().catch(() => {{}});
                  setStatus(evt.type === 'transition' ? '➡️ Переход' : '💬 ...');
                }}
              }}

              if (p < 1.0) requestAnimationFrame(step);
              else resolve();
            }}
            requestAnimationFrame(step);
          }});
        }}
      }}

      isPlaying = false;
      if (progressTimer) {{ clearInterval(progressTimer); progressTimer = null; }}
      btn.textContent = '\\u25B6 Play Walk';
      btn.classList.remove('playing');
      setStatus('✅ Прогулка завершена');
    }}
  </script>
</body>
</html>"""
    output_path.write_text(html, encoding="utf-8")


# =========================================================================
# Main
# =========================================================================

async def run_simulator(args):
    zone_id = UUID(args.zone_id)
    style = args.voice_style
    lang = args.voice_language
    dry_run = args.dry_run

    print(f"\n{'='*60}")
    print(f"Walk Simulator v3 — realistic continuous walk")
    print(f"{'='*60}")
    print(f"  Zone: {zone_id}")
    print(f"  Voice: {style}/{lang}")
    print(f"  Points: {args.point_count} | Min dist: {args.min_distance_m}m | Max route: {args.max_route_distance_m}m")
    print(f"  Dry run: {dry_run}")

    print(f"\n--- Preflight ---")
    voice = await preflight_check(zone_id, style, lang, dry_run)

    print(f"\n--- Building compact route ---")
    seed_poi_id = UUID(args.seed_poi_id) if args.seed_poi_id else None
    if seed_poi_id:
        print(f"  Using forced seed POI: {seed_poi_id}")
    waypoints, poi_indices, ordered_pois, edge_seq, total_dist, point_map = await build_walk_route_v3(
        zone_id, voice.id, lang, args.point_count,
        args.min_distance_m, args.max_route_distance_m,
        seed_poi_id=seed_poi_id,
    )
    poi_count = len(poi_indices)
    print(f"  Waypoints: {len(waypoints)} ({poi_count} POI + {len(waypoints) - poi_count} connectors)")
    print(f"  Total distance: {total_dist:.0f}m")
    print(f"  POI sequence:")
    for i, pi in enumerate(poi_indices):
        wp = waypoints[pi]
        print(f"    {i+1}. {wp['name'] or '?':<50} ({wp['lat']:.4f}, {wp['lng']:.4f})")

    # Google Maps Directions: per-leg pedestrian geometry (fallback: OSRM)
    print(f"\n--- Getting pedestrian route geometry ---")
    from src.guide.infrastructure.google_places_client import GuideGooglePlacesClient
    gmaps = GuideGooglePlacesClient()

    osrm_legs = []
    full_geometry = []
    total_route_dist = 0.0
    for li in range(len(poi_indices) - 1):
        from_wp = waypoints[poi_indices[li]]
        to_wp = waypoints[poi_indices[li + 1]]
        straight_dist = _haversine_m(from_wp["lat"], from_wp["lng"], to_wp["lat"], to_wp["lng"])

        # Try Google Maps first
        leg_data = await gmaps.get_walking_directions(
            from_wp["lat"], from_wp["lng"], to_wp["lat"], to_wp["lng"],
            language="ru" if lang == "ru" else "en",
        )
        source = "Google"

        # Fallback to OSRM if Google fails
        if leg_data is None:
            raw = await get_osrm_route([(from_wp["lat"], from_wp["lng"]),
                                         (to_wp["lat"], to_wp["lng"])])
            if raw:
                geom = raw["geometry"]
                geom[0] = [from_wp["lat"], from_wp["lng"]]
                geom[-1] = [to_wp["lat"], to_wp["lng"]]
                street_seq = []
                for st in raw.get("steps", []):
                    sn = st.get("name", "").strip()
                    if sn and (not street_seq or street_seq[-1] != sn):
                        street_seq.append(sn)
                leg_data = {
                    "geometry": geom,
                    "street_sequence": street_seq,
                    "total_distance_m": raw["total_distance_m"],
                    "total_duration_s": raw["total_duration_s"],
                }
                source = "OSRM"

        if leg_data:
            geom = leg_data["geometry"]
            dist = leg_data["total_distance_m"]
            ratio = dist / straight_dist if straight_dist > 0 else 1.0
            streets = ", ".join(leg_data.get("street_sequence", [])[:4]) or "—"
            osrm_legs.append({
                "geometry": geom,
                "distance_m": dist,
                "duration_s": leg_data["total_duration_s"],
                "street_sequence": leg_data.get("street_sequence", []),
            })
            if full_geometry:
                full_geometry.extend(geom[1:])
            else:
                full_geometry.extend(geom)
            total_route_dist += dist
            flag = " ⚠️" if ratio > 2.5 else ""
            print(f"  Leg {li+1} ({source}): {len(geom)} pts, {dist:.0f}m "
                  f"(direct {straight_dist:.0f}m, {ratio:.1f}x){flag}")
            print(f"    Streets: {streets}")
        else:
            # Last resort: straight line
            geom = [[from_wp["lat"], from_wp["lng"]], [to_wp["lat"], to_wp["lng"]]]
            osrm_legs.append({"geometry": geom, "distance_m": straight_dist,
                              "duration_s": straight_dist / WALKING_SPEED_MPS,
                              "street_sequence": []})
            full_geometry.extend(geom if not full_geometry else geom[1:])
            total_route_dist += straight_dist
            print(f"  Leg {li+1} (straight): {straight_dist:.0f}m (no routing available)")
    print(f"  Total route: {len(full_geometry)} pts, {total_route_dist:.0f}m")

    print(f"\n--- Building timeline ---")
    timeline, m_count, t_count, c_count = await build_timeline(
        waypoints, poi_indices, ordered_pois, point_map,
        voice.id, lang, zone_id, osrm_legs=osrm_legs,
    )
    print(f"  Voice segments: {m_count} main + {t_count} transitions + {c_count} commentaries")

    zone_slug = "red_square"
    slug = _file_slug(zone_slug, style, lang)
    seg_dir = _segments_dir(style, lang)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    seg_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n--- Synthesizing audio ---")
    await synthesize_timeline(timeline, voice.elevenlabs_voice_id, dry_run, seg_dir, lang)

    print(f"\n--- Inserting silence segments ---")
    timeline = insert_silences(timeline, waypoints, poi_indices)
    silences = sum(1 for s in timeline if s.type == "silence")
    silence_total = sum(s.duration_s for s in timeline if s.type == "silence")
    voiced_total = sum(s.duration_s for s in timeline if s.type != "silence")
    total_timeline = silence_total + voiced_total
    print(f"  Silences inserted: {silences} ({_fmt_duration(silence_total)})")
    print(f"  Voice total: {_fmt_duration(voiced_total)}")
    print(f"  Walk total: {_fmt_duration(total_timeline)}")

    mp3_path = OUTPUT_DIR / f"{slug}.mp3"
    md_path = OUTPUT_DIR / f"{slug}.md"
    html_path = OUTPUT_DIR / f"{slug}.html"
    seg_dir_name = seg_dir.name

    if not dry_run:
        print(f"\n--- Assembling final mp3 (with silences) ---")
        ok = assemble_final_mp3(timeline, mp3_path, seg_dir)
        if ok:
            dur = _get_mp3_duration(mp3_path)
            size_mb = mp3_path.stat().st_size / (1024 * 1024)
            print(f"  ✅ {mp3_path.name}: {_fmt_duration(dur)}, {size_mb:.1f} MB")
        else:
            print("  ⚠️  mp3 assembly failed")
    else:
        mp3_path.touch()

    voice_label = f"{voice.name} ({style}/{lang})"

    print(f"\n--- Generating markdown ---")
    generate_markdown(timeline, waypoints, "Red Square", voice_label, mp3_path, md_path, seg_dir_name)
    print(f"  ✅ {md_path.name}: {md_path.stat().st_size} bytes")

    print(f"\n--- Generating HTML map ---")
    generate_html_map(
        timeline, waypoints, "Red Square", voice_label, html_path, seg_dir_name,
        osrm_polyline=full_geometry if full_geometry else None,
        nav_steps=[],
        osrm_legs=osrm_legs,
    )
    print(f"  ✅ {html_path.name}: {html_path.stat().st_size} bytes")

    print(f"\n{'='*60}")
    print(f"WALK SIMULATOR v3 COMPLETE")
    print(f"{'='*60}")
    print(f"  mp3:  {mp3_path}")
    print(f"  md:   {md_path}")
    print(f"  html: {html_path}")
    print(f"  segs: {seg_dir}")
    print(f"  Walk: {len(waypoints)} waypoints, {poi_count} POI, {total_dist:.0f}m")
    print(f"  Timeline: {len(timeline)} segments ({silences} silences)")
    print(f"  Total: {_fmt_duration(total_timeline)}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Walk Simulator v3 — realistic continuous walk")
    parser.add_argument("--zone-id", required=True)
    parser.add_argument("--voice-style", default="academic", choices=["academic", "friendly", "dramatic", "minimal"])
    parser.add_argument("--voice-language", default="en", choices=["en", "ru"])
    parser.add_argument("--point-count", type=int, default=5)
    parser.add_argument("--min-distance-m", type=int, default=100)
    parser.add_argument("--max-route-distance-m", type=int, default=1500)
    parser.add_argument("--seed-poi-id", default=None,
                        help="Force a specific POI as route seed (UUID)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-synthesis", action="store_true",
                        help="Use cached audio only — no ElevenLabs calls")
    parser.add_argument("--non-interactive", action="store_true")
    args = parser.parse_args()
    asyncio.run(run_simulator(args))


if __name__ == "__main__":
    main()
