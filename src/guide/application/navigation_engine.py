"""
Navigation Engine — synchronous state machine for the Live Audio Guide.

IMPORTANT: process_location() is fully synchronous (no async/await).
All work happens in-memory against SessionState.  Target: < 1 ms per call.

State machine transitions:
  INIT → NARRATING           (first POI triggered)
  NARRATING → TRANSITIONING  (movement bearing matches an outgoing edge)
  NARRATING → AT_BONUS       (user idle > guide_bonus_idle_seconds at current POI)
  TRANSITIONING → NARRATING  (new POI triggered)
  Any → OUT_OF_ZONE          (all points are beyond out_of_zone_threshold_m)
  Any → PAUSED               (managed externally by SessionManager)
  PAUSED → RESUMING          (managed externally)
  RESUMING → NARRATING       (next POI triggered after resume)
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.guide.application.gps_processor import (
    angular_diff,
    compute_bearing_from_track,
    compute_speed_mps,
    is_gps_anomaly,
)
from src.guide.application.session_state import PreloadedContent, SessionState


# ---------------------------------------------------------------------------
# Navigation state enum
# ---------------------------------------------------------------------------

class NavigationState(str, Enum):
    INIT = "INIT"
    RESUMING = "RESUMING"
    NARRATING = "NARRATING"
    TRANSITIONING = "TRANSITIONING"
    AT_BONUS = "AT_BONUS"
    OUT_OF_ZONE = "OUT_OF_ZONE"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class NavigationResult:
    """
    Output of NavigationEngine.process_location().
    Consumed by SessionManager to build the HTTP response.
    """
    action: str                             # 'hold' | 'serve_main' | 'serve_bonus'
                                            # | 'play_transition' | 'out_of_zone'
    navigation_state: NavigationState
    point_id: Optional[uuid.UUID] = None   # for serve_main / serve_bonus
    edge_id: Optional[uuid.UUID] = None    # for play_transition
    to_point_id: Optional[uuid.UUID] = None
    content: Optional[PreloadedContent] = None
    effective_detail_level: str = "standard"
    reason: Optional[str] = None           # human-readable cause (e.g. 'gps_anomaly')


# ---------------------------------------------------------------------------
# Navigation Engine
# ---------------------------------------------------------------------------

class NavigationEngine:
    """
    Pure synchronous navigation logic.

    Instantiate once (shared across all sessions) — the engine itself is
    stateless.  All mutable state lives in SessionState which is passed in.
    """

    def __init__(self, settings=None) -> None:
        if settings is None:
            from src.config import settings as app_settings
            settings = app_settings
        self._settings = settings

    # -------------------------------------------------------------------------
    # Main entry point
    # -------------------------------------------------------------------------

    def process_location(
        self,
        state: SessionState,
        lat: float,
        lng: float,
        heading_deg: Optional[float],
        gps_accuracy_m: float,
        current_time: Optional[float] = None,
    ) -> NavigationResult:
        """
        Synchronous navigation step.  Never calls await, never touches the DB.
        Called on every GET /navigation/next request.

        Steps:
          1. GPS anomaly check
          2. Update GPS ring buffer
          3. Find nearest 10 points (in-memory)
          4. Out-of-zone check
          5. Trigger check (point in radius + unvisited)
          6. Bonus idle check
          7. Direction / transition check
          8. Default hold
        """
        if current_time is None:
            current_time = time.time()

        s = self._settings

        # ── 1. GPS anomaly ────────────────────────────────────────────────────
        if state.last_lat != 0 or state.last_lng != 0:
            prev_entries = state.gps_ring
            if prev_entries:
                _, _, _, prev_ts = prev_entries[-1]
                time_delta = current_time - prev_ts
            else:
                time_delta = 1.0  # assume 1 s for first point

            if is_gps_anomaly(
                state.last_lat, state.last_lng,
                lat, lng,
                time_delta,
                max_speed_mps=s.guide_gps_anomaly_max_speed_mps,
            ):
                return NavigationResult(
                    action="hold",
                    navigation_state=NavigationState(state.navigation_state),
                    reason="gps_anomaly",
                )

        # ── 2. Update GPS ring buffer ─────────────────────────────────────────
        state.add_gps_point(lat, lng, heading_deg, current_time)

        # ── 3. Find 10 nearest points (in-memory, O(n)) ───────────────────────
        nearest = state.find_nearest_points(lat, lng, limit=10)

        # ── 4. Out-of-zone check ──────────────────────────────────────────────
        if not nearest or nearest[0][1] > s.guide_out_of_zone_threshold_m:
            state.navigation_state = NavigationState.OUT_OF_ZONE.value
            return NavigationResult(
                action="out_of_zone",
                navigation_state=NavigationState.OUT_OF_ZONE,
            )

        # ── 5. Trigger check — unvisited point within trigger radius ──────────
        triggered = [
            (pid, dist)
            for pid, dist in nearest
            if dist <= state.zone.points_by_id[pid].trigger_radius_m + gps_accuracy_m
            and not state.is_visited(pid)
        ]

        if triggered:
            point_id, _ = triggered[0]
            point_info = state.zone.points_by_id[point_id]

            # Update in-memory state
            state.mark_visited(point_id)
            state.current_point_id = point_id
            state.navigation_state = NavigationState.NARRATING.value
            state.idle_at_point_since = current_time

            content = state.preloaded.get(point_id)
            return NavigationResult(
                action="serve_main",
                navigation_state=NavigationState.NARRATING,
                point_id=point_id,
                content=content,
                effective_detail_level=state.get_effective_detail_level(),
            )

        # ── 6. Bonus idle check — already at a POI, user lingering ───────────
        if state.current_point_id and state.idle_at_point_since is not None:
            idle_duration = current_time - state.idle_at_point_since
            current_info = state.zone.points_by_id.get(state.current_point_id)
            if current_info and current_info.point_type == "poi":
                from src.guide.application.gps_processor import haversine_m
                dist_to_current = haversine_m(lat, lng, current_info.lat, current_info.lng)
                if idle_duration > s.guide_bonus_idle_seconds and dist_to_current < 30.0:
                    state.navigation_state = NavigationState.AT_BONUS.value
                    content = state.preloaded.get(state.current_point_id)
                    return NavigationResult(
                        action="serve_bonus",
                        navigation_state=NavigationState.AT_BONUS,
                        point_id=state.current_point_id,
                        content=content,
                        effective_detail_level=state.get_effective_detail_level(),
                    )

        # ── 7. Direction / transition ─────────────────────────────────────────
        # Determine movement bearing
        bearing: Optional[float] = heading_deg  # prefer device compass
        if bearing is None:
            gps_ring = state.gps_ring
            if len(gps_ring) >= 2:
                bearing = compute_bearing_from_track(gps_ring[-5:])

        if bearing is not None:
            # Use nearest point as current position reference
            current_point_id = nearest[0][0]
            edges = state.zone.adj.get(current_point_id, [])
            if edges:
                best_edge = min(edges, key=lambda e: angular_diff(e.bearing_deg, bearing))
                if angular_diff(best_edge.bearing_deg, bearing) < s.guide_max_bearing_diff_deg:
                    state.navigation_state = NavigationState.TRANSITIONING.value
                    # Try to get transition audio from preloaded content
                    from_content = state.preloaded.get(current_point_id)
                    transition_audio = None
                    if from_content:
                        transition_audio = from_content.transitions.get(best_edge.to_point_id)
                    # Build a PreloadedContent-like wrapper for the transition
                    transition_content = None
                    if transition_audio:
                        transition_content = PreloadedContent(
                            point_id=current_point_id,
                            main_audio_url=transition_audio,
                        )
                    return NavigationResult(
                        action="play_transition",
                        navigation_state=NavigationState.TRANSITIONING,
                        point_id=current_point_id,
                        edge_id=best_edge.id,
                        to_point_id=best_edge.to_point_id,
                        content=transition_content,
                        effective_detail_level=state.get_effective_detail_level(),
                    )

        # ── 8. Walking commentary — connector with pre-recorded observation ──
        nearest_point_id, nearest_dist = nearest[0]
        nearest_info = state.zone.points_by_id.get(nearest_point_id)
        if (
            nearest_info
            and nearest_info.point_type == "connector"
            and nearest_dist <= nearest_info.trigger_radius_m + gps_accuracy_m
        ):
            pc = state.preloaded.get(nearest_point_id)
            if (
                pc
                and pc.commentary_audio_url
                and pc.commentary_block_id
                and pc.commentary_block_id not in state.played_commentaries
            ):
                state.played_commentaries.add(pc.commentary_block_id)
                commentary_content = PreloadedContent(
                    point_id=nearest_point_id,
                    main_audio_url=pc.commentary_audio_url,
                    main_text=pc.commentary_text,
                )
                return NavigationResult(
                    action="play_commentary",
                    navigation_state=NavigationState(state.navigation_state),
                    point_id=nearest_point_id,
                    content=commentary_content,
                )

        # ── 9. Default: hold ──────────────────────────────────────────────────
        return NavigationResult(
            action="hold",
            navigation_state=NavigationState(state.navigation_state),
            reason="no_direction" if bearing is None else "no_matching_edge",
        )
