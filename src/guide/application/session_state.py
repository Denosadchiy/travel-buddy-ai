"""
In-memory session state for the Live Audio Guide.

SessionState is loaded once when a session is created and kept in a
module-level dict (_active_sessions). All hot-path operations (navigation,
GPS tracking) read/write this in-memory object — never the database.

The database is only consulted:
  - On session create (heavy load once, < 500ms budget)
  - Periodically for preload refresh (async, on 50m movement)
  - Fire-and-forget for GPS logging and visit recording

On server restart SessionState is lost; _restore_session_state() in
session_manager.py reconstructs it from the DB.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from src.guide.application.gps_processor import haversine_m


# ---------------------------------------------------------------------------
# Immutable topology types (loaded once per session)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PointInfo:
    """Lightweight in-memory representation of a guide_point row."""
    id: uuid.UUID
    lat: float
    lng: float
    trigger_radius_m: int
    point_type: str       # 'poi' | 'connector'
    name: Optional[str]


@dataclass(frozen=True)
class EdgeInfo:
    """Lightweight in-memory representation of a guide_edge row."""
    id: uuid.UUID
    from_point_id: uuid.UUID
    to_point_id: uuid.UUID
    distance_m: float
    walk_seconds: int
    bearing_deg: float    # 0-360, North = 0


@dataclass
class ZoneTopology:
    """
    Complete zone graph loaded into memory.

    Immutable after __post_init__; all navigation runs against these lists.
    Memory footprint: ~80 points × ~320 edges ≈ a few KB per session.
    """
    points: list[PointInfo]
    edges: list[EdgeInfo]

    # Built in __post_init__
    points_by_id: dict[uuid.UUID, PointInfo] = field(default_factory=dict, init=False)
    adj: dict[uuid.UUID, list[EdgeInfo]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.points_by_id = {p.id: p for p in self.points}
        self.adj = {p.id: [] for p in self.points}
        for e in self.edges:
            self.adj[e.from_point_id].append(e)

    def find_nearest(
        self,
        lat: float,
        lng: float,
        limit: int = 10,
    ) -> list[tuple[uuid.UUID, float]]:
        """
        In-memory nearest-point search. O(n) over all points.
        For 80 points this runs in < 1 ms.
        Returns list of (point_id, distance_m) sorted by distance ascending.
        """
        results = [(p.id, haversine_m(lat, lng, p.lat, p.lng)) for p in self.points]
        results.sort(key=lambda x: x[1])
        return results[:limit]


# ---------------------------------------------------------------------------
# Preloaded content (CDN URLs per point)
# ---------------------------------------------------------------------------

@dataclass
class PreloadedContent:
    """
    CDN audio URLs and text fallbacks for one guide_point.
    Loaded for the 8 nearest points on session create and on preload refresh.
    """
    point_id: uuid.UUID
    main_audio_url: Optional[str] = None
    main_text: Optional[str] = None          # text fallback if audio not ready
    main_duration_s: Optional[float] = None
    bonus_audio_url: Optional[str] = None
    bonus_duration_s: Optional[float] = None
    recap_audio_url: Optional[str] = None
    commentary_audio_url: Optional[str] = None   # walking_commentary for connectors
    commentary_text: Optional[str] = None
    commentary_block_id: Optional[uuid.UUID] = None
    # key: to_point_id, value: audio URL for the transition phrase
    transitions: dict[uuid.UUID, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Session state (mutable, in-memory)
# ---------------------------------------------------------------------------

# GPS ring buffer item: (lat, lng, heading_deg_or_None, unix_timestamp)
_GpsEntry = tuple[float, float, Optional[float], float]
_GPS_RING_MAX = 10


class SessionState:
    """
    Mutable in-memory state for one active guide session.

    Created by SessionManager.create_session(), stored in _active_sessions,
    updated on every navigation/heartbeat request.  Never persisted directly —
    the DB is the source of truth; this is a performance cache.
    """

    def __init__(
        self,
        session_id: uuid.UUID,
        zone_topology: ZoneTopology,
        voice_id: uuid.UUID,
        language: str,
        detail_level: str,
        initial_lat: float,
        initial_lng: float,
    ) -> None:
        self.session_id = session_id
        self.zone = zone_topology
        self.voice_id = voice_id
        self.language = language
        self.detail_level = detail_level

        # --- Mutable navigation state ---
        self.visited_point_ids: set[uuid.UUID] = set()
        self.current_point_id: Optional[uuid.UUID] = None
        self.navigation_state: str = "INIT"   # NavigationState enum value

        # --- Position tracking ---
        self.last_lat: float = initial_lat
        self.last_lng: float = initial_lng
        self.last_preload_lat: float = initial_lat
        self.last_preload_lng: float = initial_lng

        # --- GPS ring buffer (last 10 samples) ---
        self._gps_ring: list[_GpsEntry] = []

        # --- Bonus idle tracking ---
        self.idle_at_point_since: Optional[float] = None   # unix timestamp

        # --- Preloaded CDN content for nearest 8 points ---
        self.preloaded: dict[uuid.UUID, PreloadedContent] = {}

        # --- Walking commentary tracking (played once per session) ---
        self.played_commentaries: set[uuid.UUID] = set()

    # -------------------------------------------------------------------------
    # Nearest-point lookup (delegates to ZoneTopology)
    # -------------------------------------------------------------------------

    def find_nearest_points(
        self, lat: float, lng: float, limit: int = 10
    ) -> list[tuple[uuid.UUID, float]]:
        """In-memory nearest-point lookup. See ZoneTopology.find_nearest()."""
        return self.zone.find_nearest(lat, lng, limit)

    # -------------------------------------------------------------------------
    # Visited-point tracking
    # -------------------------------------------------------------------------

    def is_visited(self, point_id: uuid.UUID) -> bool:
        return point_id in self.visited_point_ids

    def mark_visited(self, point_id: uuid.UUID) -> None:
        self.visited_point_ids.add(point_id)

    # -------------------------------------------------------------------------
    # GPS ring buffer
    # -------------------------------------------------------------------------

    @property
    def gps_ring(self) -> list[_GpsEntry]:
        """Read-only view of the GPS ring buffer."""
        return list(self._gps_ring)

    def add_gps_point(
        self,
        lat: float,
        lng: float,
        heading: Optional[float],
        timestamp: float,
    ) -> None:
        """Append a GPS sample; evict oldest if buffer is full."""
        self._gps_ring.append((lat, lng, heading, timestamp))
        if len(self._gps_ring) > _GPS_RING_MAX:
            self._gps_ring.pop(0)
        self.last_lat = lat
        self.last_lng = lng

    # -------------------------------------------------------------------------
    # Preload refresh decision
    # -------------------------------------------------------------------------

    def needs_preload_refresh(
        self, lat: float, lng: float, threshold_m: float = 50.0
    ) -> bool:
        """
        True if the user has moved more than threshold_m from the last
        preload position. Used to avoid redundant CDN URL fetches.
        """
        return (
            haversine_m(lat, lng, self.last_preload_lat, self.last_preload_lng)
            > threshold_m
        )

    def mark_preload_refreshed(self, lat: float, lng: float) -> None:
        self.last_preload_lat = lat
        self.last_preload_lng = lng

    # -------------------------------------------------------------------------
    # Dynamic detail-level based on walking speed
    # -------------------------------------------------------------------------

    def get_effective_detail_level(self) -> str:
        """
        Auto-switch to 'brief' when the user is moving fast (> 2 m/s).
        Falls back to the session's configured detail_level otherwise.
        """
        from src.guide.application.gps_processor import compute_speed_mps
        if len(self._gps_ring) >= 3:
            speed = compute_speed_mps(self._gps_ring[-3:])
            if speed > 2.0:
                return "brief"
        return self.detail_level


# ---------------------------------------------------------------------------
# Module-level in-memory store
# ---------------------------------------------------------------------------

_active_sessions: dict[uuid.UUID, SessionState] = {}


def get_session_state(session_id: uuid.UUID) -> Optional[SessionState]:
    """Return the in-memory state for an active session, or None."""
    return _active_sessions.get(session_id)


def put_session_state(session_id: uuid.UUID, state: SessionState) -> None:
    """Register a new or restored session state."""
    _active_sessions[session_id] = state


def remove_session_state(session_id: uuid.UUID) -> None:
    """Remove session from in-memory store (call on session end)."""
    _active_sessions.pop(session_id, None)
