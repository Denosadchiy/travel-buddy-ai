"""
Session Manager — lifecycle orchestration for Live Audio Guide sessions.

Coordinates NavigationEngine (sync, in-memory), SessionState (in-memory cache),
and NavigationRepository (DB).  Each public method maps roughly to one HTTP
endpoint in guide/api/router.py.

Performance targets:
  create_session       < 500 ms   (heavy: loads topology + preload from DB)
  get_navigation_next  < 100 ms   (hot: navigation engine is sync in-memory)
  process_heartbeat    < 200 ms   (DB write fire-and-forget)
  pause / resume / end < 200 ms
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from src.guide.application.gps_processor import compute_speed_mps
from src.guide.application.navigation_engine import NavigationEngine, NavigationState
from src.guide.application.navigation_repository import NavigationRepository
from src.guide.application.session_state import (
    PreloadedContent,
    SessionState,
    ZoneTopology,
    get_session_state,
    put_session_state,
    remove_session_state,
)
from src.guide.domain.schemas import (
    HeartbeatResponse,
    PauseResponse,
    PointContent,
    ResumeResponse,
    SessionCreateResponse,
    SessionSummary,
    TransitionContent,
)

logger = logging.getLogger(__name__)

_HEAD_SENTENCES = 2  # sentences to extract for recap fallback


def _fire_and_forget(coro):
    """
    Schedule a fire-and-forget coroutine. Wraps it with its OWN DB session
    to avoid asyncpg "another operation in progress" when the request's session
    is still active.
    """
    async def _wrapper():
        try:
            await coro
        except Exception as exc:
            logger.debug("Fire-and-forget task error: %s", exc)

    try:
        asyncio.create_task(_wrapper())
    except RuntimeError:
        pass  # no event loop (e.g., during testing)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _head(text: str, sentences: int = 2) -> str:
    """Return the first N sentences of *text*."""
    import re
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return " ".join(parts[:sentences])


def _preloaded_to_schema(pc: PreloadedContent) -> PointContent:
    """Convert in-memory PreloadedContent to the Pydantic schema."""
    return PointContent(
        point_id=pc.point_id,
        main_audio_url=pc.main_audio_url,
        main_duration_s=pc.main_duration_s,
        bonus_audio_url=pc.bonus_audio_url,
        bonus_duration_s=pc.bonus_duration_s,
        transitions=[
            TransitionContent(to_point_id=to_id, audio_url=url)
            for to_id, url in pc.transitions.items()
        ],
    )


class SessionManager:
    """
    One instance per FastAPI app (created in dependencies.py).
    The NavigationEngine is shared (stateless); sessions are stored in the
    module-level _active_sessions dict.
    """

    def __init__(self, settings=None) -> None:
        if settings is None:
            from src.config import settings as app_settings
            settings = app_settings
        self._settings = settings
        self._engine = NavigationEngine(settings=settings)

    # -------------------------------------------------------------------------
    # Session creation
    # -------------------------------------------------------------------------

    async def create_session(
        self,
        repo: NavigationRepository,
        user_id: uuid.UUID,
        zone_id: uuid.UUID,
        voice_id: uuid.UUID,
        language: str,
        detail_level: str,
        initial_lat: float,
        initial_lng: float,
    ) -> SessionCreateResponse:
        """
        Create a new guide session.

        Steps (all within the same DB session):
          1. Billing check — STUB (always passes)
          2. INSERT guide_sessions
          3. Load zone topology into memory
          4. Preload CDN URLs for 8 nearest points
          5. Build SessionState, register in _active_sessions
          6. Fire-and-forget: initial GPS log
        """
        # 1. Balance check — STUB
        _balance = await self._check_and_debit_balance(user_id, seconds_to_debit=0)

        # 2. Create DB session record
        db_session = await repo.create_session(
            user_id=user_id,
            zone_id=zone_id,
            voice_id=voice_id,
            language=language,
            detail_level=detail_level,
        )
        session_id = db_session.id

        # 3. Load zone topology
        topology = await repo.build_zone_topology(zone_id)

        # 4. Preload content for 8 nearest points
        nearest_ids = [pid for pid, _ in topology.find_nearest(initial_lat, initial_lng, limit=self._settings.guide_preload_point_count)]
        preloaded = await repo.load_content_urls(nearest_ids, voice_id, language, detail_level)

        # 5. Build in-memory SessionState
        state = SessionState(
            session_id=session_id,
            zone_topology=topology,
            voice_id=voice_id,
            language=language,
            detail_level=detail_level,
            initial_lat=initial_lat,
            initial_lng=initial_lng,
        )
        state.preloaded = preloaded
        put_session_state(session_id, state)

        # Persist user preferences (non-blocking, own DB session)
        _fire_and_forget(
            self._persist_preferences_bg(user_id, voice_id, language, detail_level)
        )

        # 6. Fire-and-forget: GPS log for initial position (own DB session)
        _fire_and_forget(
            self._log_gps_bg(session_id, initial_lat, initial_lng, None, 0.0, 0.0)
        )

        # Build preload content for response
        preload_content = [
            _preloaded_to_schema(pc)
            for pc in preloaded.values()
        ]

        return SessionCreateResponse(
            session_id=session_id,
            balance_seconds=_balance["seconds_remaining"],
            trial_seconds_remaining=0,   # TODO Step 6: wire trial balance
            preload_content=preload_content,
        )

    # -------------------------------------------------------------------------
    # Navigation (hot path)
    # -------------------------------------------------------------------------

    async def get_navigation_next(
        self,
        repo: NavigationRepository,
        session_id: uuid.UUID,
        lat: float,
        lng: float,
        heading_deg: Optional[float],
        gps_accuracy_m: float,
    ) -> dict:
        """
        < 100 ms target.

        1. Retrieve in-memory state (restore from DB if lost)
        2. Synchronous navigation engine call (< 1 ms)
        3. Fire-and-forget GPS log
        4. Fire-and-forget visit record (if new POI triggered)
        5. Async preload refresh (if moved > 50 m) — background task
        6. Build response from in-memory state
        """
        state = get_session_state(session_id)
        if state is None:
            state = await self._restore_session_state(repo, session_id)

        current_time = time.time()

        # 2. Synchronous engine call
        result = self._engine.process_location(
            state, lat, lng, heading_deg, gps_accuracy_m, current_time
        )

        # 3. Fire-and-forget: GPS log (own DB session)
        speed = compute_speed_mps(state.gps_ring[-3:]) if len(state.gps_ring) >= 2 else 0.0
        _fire_and_forget(
            self._log_gps_bg(session_id, lat, lng, heading_deg, speed, gps_accuracy_m)
        )

        # 4. Fire-and-forget: visit recording (own DB session)
        if result.action == "serve_main" and result.point_id:
            _fire_and_forget(self._record_visit_bg(session_id, result.point_id, "main"))
        elif result.action == "serve_bonus" and result.point_id:
            _fire_and_forget(self._record_visit_bg(session_id, result.point_id, "bonus"))

        # 5. Background preload refresh
        s = self._settings
        if state.needs_preload_refresh(lat, lng, threshold_m=s.guide_preload_refresh_distance_m):
            _fire_and_forget(self._refresh_preload_bg(state, lat, lng))

        # 6. Build response
        return self._build_navigation_response(result, state)

    def _build_navigation_response(self, result, state: SessionState) -> dict:
        """Construct the dict returned from get_navigation_next."""
        nearest = state.find_nearest_points(state.last_lat, state.last_lng, limit=5)
        nearest_points = []
        for pid, dist in nearest:
            pinfo = state.zone.points_by_id.get(pid)
            if pinfo is None:
                continue
            pc = state.preloaded.get(pid)
            from src.guide.domain.schemas import NearestPoint, PointContentDetails
            content_details = PointContentDetails()
            if pc:
                content_details = PointContentDetails(
                    main_audio_url=pc.main_audio_url,
                    main_duration_s=pc.main_duration_s,
                    bonus_audio_url=pc.bonus_audio_url,
                    bonus_duration_s=pc.bonus_duration_s,
                    transitions={str(to_id): url for to_id, url in pc.transitions.items()},
                )
            nearest_points.append(NearestPoint(
                point_id=pid,
                name=pinfo.name,
                dist_m=dist,
                is_in_trigger_radius=dist <= pinfo.trigger_radius_m,
                already_visited=state.is_visited(pid),
                content=content_details,
            ))

        from src.guide.domain.schemas import NavigationNextResponse
        return NavigationNextResponse(
            current_point_id=state.current_point_id,
            nearest_points=nearest_points,
            navigation_state=result.navigation_state.value,
        )

    # -------------------------------------------------------------------------
    # Heartbeat
    # -------------------------------------------------------------------------

    async def process_heartbeat(
        self,
        repo: NavigationRepository,
        session_id: uuid.UUID,
        seconds_active: int,
        lat: float,
        lng: float,
        heading_deg: Optional[float],
    ) -> HeartbeatResponse:
        """
        < 200 ms target.

        1. Load session from DB (status check)
        2. Billing debit — STUB
        3. Fire-and-forget GPS log
        4. Fire-and-forget DB heartbeat update
        5. Preload refresh if needed (synchronous to return nearby_content)
        """
        session = await repo.get_session(session_id)
        if session is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Session not found")

        if session.status == "paused":
            return HeartbeatResponse(
                seconds_remaining=99999,
                continue_session=False,
                stop_reason="paused",
            )

        if session.status == "ended":
            return HeartbeatResponse(
                seconds_remaining=0,
                continue_session=False,
                stop_reason="ended",
            )

        # Cap seconds_active to prevent fraud (max heartbeat interval + 5s grace)
        capped_seconds = min(seconds_active, 35)

        # 2. Billing — STUB
        balance = await self._check_and_debit_balance(session.user_id, capped_seconds)

        # 3. Fire-and-forget: GPS log (own DB session)
        _fire_and_forget(self._log_gps_bg(session_id, lat, lng, heading_deg, None, None))

        # 4. Fire-and-forget: heartbeat update (own DB session)
        _fire_and_forget(self._heartbeat_bg(session_id, lat, lng, capped_seconds))

        # 5. Preload refresh
        state = get_session_state(session_id)
        nearby_content: list[PointContent] = []
        if state and state.needs_preload_refresh(lat, lng, threshold_m=self._settings.guide_preload_refresh_distance_m):
            new_preload = await self._refresh_preload_sync(repo, state, lat, lng)
            nearby_content = [_preloaded_to_schema(pc) for pc in new_preload.values()]

        return HeartbeatResponse(
            seconds_remaining=balance["seconds_remaining"],
            continue_session=balance["continue"],
            stop_reason=balance.get("stop_reason"),
            nearby_content=nearby_content,
        )

    # -------------------------------------------------------------------------
    # Pause / Resume / End
    # -------------------------------------------------------------------------

    async def pause_session(self, repo: NavigationRepository, session_id: uuid.UUID) -> PauseResponse:
        await repo.update_session(session_id, status="paused")
        state = get_session_state(session_id)
        if state:
            state.navigation_state = NavigationState.INIT.value

        session = await repo.get_session(session_id)
        billed = session.total_seconds_billed if session else 0
        return PauseResponse(paused_at=_now(), seconds_billed_total=billed)

    async def resume_session(self, repo: NavigationRepository, session_id: uuid.UUID) -> ResumeResponse:
        await repo.update_session(session_id, status="active", last_heartbeat_at=_now())

        state = get_session_state(session_id)
        if state is None:
            state = await self._restore_session_state(repo, session_id)

        state.navigation_state = NavigationState.RESUMING.value

        # Get recap for the last visited point
        recap_content: Optional[PointContent] = None
        last_visit = await repo.get_last_visited_point(session_id)
        if last_visit:
            recap_pc = await repo.load_recap_content(
                last_visit.point_id, state.voice_id, state.language
            )
            if recap_pc:
                recap_content = _preloaded_to_schema(recap_pc)
            else:
                # Fallback: first 2 sentences of main
                main_text = await repo.get_main_text(
                    last_visit.point_id, state.voice_id, state.language, state.detail_level
                )
                if main_text:
                    snippet = _head(main_text, _HEAD_SENTENCES)
                    recap_content = PointContent(
                        point_id=last_visit.point_id,
                        main_audio_url=None,
                    )

        session = await repo.get_session(session_id)
        balance = await self._check_and_debit_balance(session.user_id if session else uuid.uuid4(), 0)

        return ResumeResponse(
            resumed_at=_now(),
            seconds_remaining=balance["seconds_remaining"],
        )

    async def end_session(
        self,
        repo: NavigationRepository,
        session_id: uuid.UUID,
        exit_reason: str,
    ) -> SessionSummary:
        await repo.update_session(
            session_id,
            status="ended",
            exit_reason=exit_reason,
            ended_at=_now(),
        )
        remove_session_state(session_id)

        return await self._build_summary(repo, session_id)

    async def rate_session(
        self,
        repo: NavigationRepository,
        session_id: uuid.UUID,
        rating: int,
        review_text: Optional[str],
    ) -> None:
        await repo.update_session(session_id, rating=rating, review_text=review_text)

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------

    async def _build_summary(
        self, repo: NavigationRepository, session_id: uuid.UUID
    ) -> SessionSummary:
        session = await repo.get_session(session_id)
        if session is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Session not found")

        zone = await repo.get_zone(session.zone_id)
        zone_name = zone.name if zone else "Unknown"

        visits = await repo.get_session_visits(session_id)
        qa_count = await repo.count_session_qa(session_id)
        gps_track = await repo.get_session_gps_track(session_id)

        started_at = session.started_at
        ended_at = session.ended_at or _now()
        # Normalise both to naive UTC to handle mixed aware/naive datetimes from mocks
        def _to_naive(dt):
            if hasattr(dt, "tzinfo") and dt.tzinfo is not None:
                from datetime import timezone as _tz
                return dt.astimezone(_tz.utc).replace(tzinfo=None)
            return dt
        duration = int((_to_naive(ended_at) - _to_naive(started_at)).total_seconds())

        # Build GeoJSON LineString path
        path_geojson = None
        if len(gps_track) >= 2:
            coords = [[p.lng, p.lat] for p in gps_track]
            path_geojson = {"type": "LineString", "coordinates": coords}

        balance = await repo.get_balance(session.user_id)
        balance_remaining = balance.seconds_remaining if balance else 0

        return SessionSummary(
            session_id=session_id,
            zone_name=zone_name,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration,
            minutes_used=round(session.total_seconds_billed / 60, 2),
            points_visited=len(visits),
            path_geojson=path_geojson,
            questions_asked=qa_count,
            balance_remaining_seconds=balance_remaining,
        )

    # -------------------------------------------------------------------------
    # Billing stub
    # -------------------------------------------------------------------------

    async def _check_and_debit_balance(
        self, user_id: uuid.UUID, seconds_to_debit: int
    ) -> dict:
        """
        STUB — billing is implemented in Step 6.

        TODO Step 6: replace with atomic
          UPDATE guide_minute_balances
          SET seconds_remaining = seconds_remaining - $debit
          WHERE user_id = $user_id AND seconds_remaining >= $debit
          RETURNING seconds_remaining
        and log a guide_minute_transactions row.
        """
        return {
            "continue": True,
            "seconds_remaining": 99999,
            "stop_reason": None,
        }

    # -------------------------------------------------------------------------
    # Preload refresh helpers
    # -------------------------------------------------------------------------

    async def _refresh_preload(
        self,
        repo: NavigationRepository,
        state: SessionState,
        lat: float,
        lng: float,
    ) -> None:
        """Background task: refresh preloaded content when user moves 50+ m."""
        try:
            await self._refresh_preload_sync(repo, state, lat, lng)
        except Exception as exc:
            logger.warning("Preload refresh failed: %s", exc)

    async def _refresh_preload_sync(
        self,
        repo: NavigationRepository,
        state: SessionState,
        lat: float,
        lng: float,
    ) -> dict:
        """Reload preloaded CDN URLs for 8 nearest points and update state."""
        nearest_ids = [
            pid for pid, _ in state.zone.find_nearest(
                lat, lng, limit=self._settings.guide_preload_point_count
            )
        ]
        new_preload = await repo.load_content_urls(
            nearest_ids, state.voice_id, state.language, state.detail_level
        )
        state.preloaded.update(new_preload)
        state.mark_preload_refreshed(lat, lng)
        return new_preload

    # -------------------------------------------------------------------------
    # State restoration after server restart
    # -------------------------------------------------------------------------

    async def _restore_session_state(
        self, repo: NavigationRepository, session_id: uuid.UUID
    ) -> SessionState:
        """
        Reconstruct SessionState from DB after a server restart.
        Called transparently from get_navigation_next when state is missing.
        """
        session = await repo.get_session(session_id)
        if session is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Session not found")

        topology = await repo.build_zone_topology(session.zone_id)
        state = SessionState(
            session_id=session_id,
            zone_topology=topology,
            voice_id=session.voice_id,
            language=session.language,
            detail_level=session.detail_level,
            initial_lat=0.0,
            initial_lng=0.0,
        )

        # Restore visited points
        visits = await repo.get_session_visits(session_id)
        state.visited_point_ids = {v.point_id for v in visits}

        # Restore GPS ring
        gps_points = await repo.get_recent_gps_points(session_id, limit=10)
        for gp in gps_points:
            state.add_gps_point(
                gp.lat, gp.lng, gp.heading_deg, gp.recorded_at.timestamp()
            )

        # Preload content for current position (or last known)
        lat = state.last_lat or 0.0
        lng = state.last_lng or 0.0
        await self._refresh_preload_sync(repo, state, lat, lng)

        put_session_state(session_id, state)
        logger.info("Restored session state for %s from DB", session_id)
        return state

    # -------------------------------------------------------------------------
    # Per-user preferences persistence (fire-and-forget)
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # Background helpers (own DB session to avoid pool conflicts)
    # -------------------------------------------------------------------------

    async def _log_gps_bg(self, session_id, lat, lng, heading, speed, accuracy):
        from src.infrastructure.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            repo = NavigationRepository(db)
            await repo.log_gps_point(session_id, lat, lng, heading, speed, accuracy)
            await db.commit()

    async def _record_visit_bg(self, session_id, point_id, content_type):
        from src.infrastructure.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            repo = NavigationRepository(db)
            await repo.record_visit(session_id, point_id, content_type)
            await db.commit()

    async def _persist_preferences_bg(self, user_id, voice_id, language, detail_level):
        from src.infrastructure.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            repo = NavigationRepository(db)
            await repo.upsert_user_preferences(
                user_id, voice_id=voice_id, language=language, detail_level=detail_level
            )
            await db.commit()

    async def _heartbeat_bg(self, session_id, lat, lng, seconds):
        from src.infrastructure.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            repo = NavigationRepository(db)
            await repo.update_session_heartbeat(session_id, lat, lng, seconds)
            await db.commit()

    async def _refresh_preload_bg(self, state, lat, lng):
        from src.infrastructure.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            repo = NavigationRepository(db)
            await self._refresh_preload_sync(repo, state, lat, lng)

    async def _persist_preferences(
        self,
        repo: NavigationRepository,
        user_id: uuid.UUID,
        voice_id: uuid.UUID,
        language: str,
        detail_level: str,
    ) -> None:
        try:
            await repo.upsert_user_preferences(
                user_id, voice_id=voice_id, language=language, detail_level=detail_level
            )
        except Exception as exc:
            logger.debug("Could not persist preferences: %s", exc)
