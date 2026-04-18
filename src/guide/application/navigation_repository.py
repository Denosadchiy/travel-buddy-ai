"""
Navigation Repository — database queries for the navigation / session layer.

Used by SessionManager for:
  - Session CRUD (create, read, update)
  - Loading zone topology into memory at session create
  - Preloading CDN audio URLs
  - Fire-and-forget GPS logging and visit recording
  - State restoration after server restart

All methods are async.  Hot-path (navigation/next) only calls synchronous
in-memory code; this repository is only consulted on session create,
periodic preload refresh, and restoration.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from geoalchemy2.shape import to_shape
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.guide.application.session_state import EdgeInfo, PointInfo, PreloadedContent, ZoneTopology
from src.guide.domain.models import (
    GuideContentBlock,
    GuideEdge,
    GuideMinuteBalance,
    GuidePackage,
    GuidePoint,
    GuideSession,
    GuideSessionGpsLog,
    GuideSessionQA,
    GuideSessionVisit,
    GuideUserPreference,
    GuideVoice,
    GuideZone,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class NavigationRepository:
    """DB access layer for session / navigation operations."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # -------------------------------------------------------------------------
    # Zone topology (loaded once per session)
    # -------------------------------------------------------------------------

    async def get_active_points_in_zone(self, zone_id: uuid.UUID) -> list[GuidePoint]:
        """Load all active points in a zone for topology construction."""
        result = await self._db.execute(
            select(GuidePoint)
            .where(GuidePoint.zone_id == zone_id, GuidePoint.is_active == True)
        )
        return list(result.scalars().all())

    async def get_edges_in_zone(self, zone_id: uuid.UUID) -> list[GuideEdge]:
        """Load all active edges for points in a zone."""
        result = await self._db.execute(
            select(GuideEdge)
            .join(GuidePoint, GuideEdge.from_point_id == GuidePoint.id)
            .where(GuidePoint.zone_id == zone_id, GuideEdge.is_active == True)
        )
        return list(result.scalars().all())

    async def build_zone_topology(self, zone_id: uuid.UUID) -> ZoneTopology:
        """
        Load zone points and edges from DB and construct an in-memory ZoneTopology.
        Converts PostGIS geometry to (lat, lng) floats using geoalchemy2.
        """
        db_points = await self.get_active_points_in_zone(zone_id)
        db_edges = await self.get_edges_in_zone(zone_id)

        point_infos: list[PointInfo] = []
        for p in db_points:
            shape = to_shape(p.location)
            point_infos.append(PointInfo(
                id=p.id,
                lat=shape.y,
                lng=shape.x,
                trigger_radius_m=p.trigger_radius_m,
                point_type=p.point_type,
                name=p.name,
            ))

        edge_infos: list[EdgeInfo] = []
        for e in db_edges:
            edge_infos.append(EdgeInfo(
                id=e.id,
                from_point_id=e.from_point_id,
                to_point_id=e.to_point_id,
                distance_m=e.distance_m,
                walk_seconds=e.walk_seconds,
                bearing_deg=e.bearing_deg or 0.0,
            ))

        return ZoneTopology(points=point_infos, edges=edge_infos)

    # -------------------------------------------------------------------------
    # Content URL preloading
    # -------------------------------------------------------------------------

    async def load_content_urls(
        self,
        point_ids: list[uuid.UUID],
        voice_id: uuid.UUID,
        language: str,
        detail_level: str,
    ) -> dict[uuid.UUID, PreloadedContent]:
        """
        Fetch CDN audio URLs for a list of points (preload set).

        Loads main, bonus, recap, and transition blocks in one query per
        content type to avoid N+1 issues.
        """
        if not point_ids:
            return {}

        preloaded: dict[uuid.UUID, PreloadedContent] = {}
        for pid in point_ids:
            preloaded[pid] = PreloadedContent(point_id=pid)

        # Main blocks (one per point × detail_level)
        main_result = await self._db.execute(
            select(GuideContentBlock)
            .where(
                GuideContentBlock.point_id.in_(point_ids),
                GuideContentBlock.voice_id == voice_id,
                GuideContentBlock.language == language,
                GuideContentBlock.detail_level == detail_level,
                GuideContentBlock.content_type == "main",
                GuideContentBlock.edge_id.is_(None),
                GuideContentBlock.generation_status.in_(["synthesized", "reviewed", "validated", "draft"]),
            )
        )
        for block in main_result.scalars().all():
            pc = preloaded.get(block.point_id)
            if pc:
                pc.main_audio_url = block.audio_url
                pc.main_text = block.text_script
                pc.main_duration_s = block.audio_duration_seconds

        # Bonus blocks
        bonus_result = await self._db.execute(
            select(GuideContentBlock)
            .where(
                GuideContentBlock.point_id.in_(point_ids),
                GuideContentBlock.voice_id == voice_id,
                GuideContentBlock.language == language,
                GuideContentBlock.detail_level == detail_level,
                GuideContentBlock.content_type == "bonus",
                GuideContentBlock.edge_id.is_(None),
                GuideContentBlock.generation_status.in_(["synthesized", "reviewed", "validated", "draft"]),
            )
        )
        for block in bonus_result.scalars().all():
            pc = preloaded.get(block.point_id)
            if pc:
                pc.bonus_audio_url = block.audio_url
                pc.bonus_duration_s = block.audio_duration_seconds

        # Recap blocks
        recap_result = await self._db.execute(
            select(GuideContentBlock)
            .where(
                GuideContentBlock.point_id.in_(point_ids),
                GuideContentBlock.voice_id == voice_id,
                GuideContentBlock.language == language,
                GuideContentBlock.content_type == "recap",
                GuideContentBlock.edge_id.is_(None),
                GuideContentBlock.generation_status.in_(["synthesized", "reviewed", "validated", "draft"]),
            )
        )
        for block in recap_result.scalars().all():
            pc = preloaded.get(block.point_id)
            if pc:
                pc.recap_audio_url = block.audio_url

        # Transition blocks: edge.from_point_id in point_ids (variant_index=0)
        trans_result = await self._db.execute(
            select(GuideContentBlock, GuideEdge)
            .join(GuideEdge, GuideContentBlock.edge_id == GuideEdge.id)
            .where(
                GuideEdge.from_point_id.in_(point_ids),
                GuideContentBlock.voice_id == voice_id,
                GuideContentBlock.language == language,
                GuideContentBlock.content_type == "transition",
                GuideContentBlock.variant_index == 0,
                GuideContentBlock.generation_status.in_(["synthesized", "reviewed", "validated", "draft"]),
            )
        )
        for block, edge in trans_result.all():
            pc = preloaded.get(edge.from_point_id)
            if pc and block.audio_url:
                pc.transitions[edge.to_point_id] = block.audio_url

        # Walking commentary blocks for connector points
        commentary_result = await self._db.execute(
            select(GuideContentBlock)
            .where(
                GuideContentBlock.point_id.in_(point_ids),
                GuideContentBlock.voice_id == voice_id,
                GuideContentBlock.language == language,
                GuideContentBlock.content_type == "walking_commentary",
                GuideContentBlock.generation_status.in_(["synthesized", "reviewed", "validated", "draft"]),
            )
        )
        for block in commentary_result.scalars().all():
            pc = preloaded.get(block.point_id)
            if pc:
                pc.commentary_audio_url = block.audio_url
                pc.commentary_text = block.text_script
                pc.commentary_block_id = block.id

        return preloaded

    async def load_recap_content(
        self,
        point_id: uuid.UUID,
        voice_id: uuid.UUID,
        language: str,
    ) -> Optional[PreloadedContent]:
        """Load recap content block for a single point (used on session resume)."""
        result = await self._db.execute(
            select(GuideContentBlock)
            .where(
                GuideContentBlock.point_id == point_id,
                GuideContentBlock.voice_id == voice_id,
                GuideContentBlock.language == language,
                GuideContentBlock.content_type == "recap",
                GuideContentBlock.edge_id.is_(None),
            )
        )
        block = result.scalar_one_or_none()
        if block is None:
            return None
        return PreloadedContent(
            point_id=point_id,
            main_audio_url=block.audio_url,
            main_text=block.text_script,
            main_duration_s=block.audio_duration_seconds,
        )

    async def get_main_text(
        self,
        point_id: uuid.UUID,
        voice_id: uuid.UUID,
        language: str,
        detail_level: str,
    ) -> Optional[str]:
        """Return just the text_script of the main content block (for recap fallback)."""
        result = await self._db.execute(
            select(GuideContentBlock.text_script)
            .where(
                GuideContentBlock.point_id == point_id,
                GuideContentBlock.voice_id == voice_id,
                GuideContentBlock.language == language,
                GuideContentBlock.detail_level == detail_level,
                GuideContentBlock.content_type == "main",
                GuideContentBlock.edge_id.is_(None),
            )
        )
        return result.scalar_one_or_none()

    # -------------------------------------------------------------------------
    # Session CRUD
    # -------------------------------------------------------------------------

    async def create_session(
        self,
        user_id: uuid.UUID,
        zone_id: uuid.UUID,
        voice_id: uuid.UUID,
        language: str,
        detail_level: str,
    ) -> GuideSession:
        session = GuideSession(
            user_id=user_id,
            zone_id=zone_id,
            voice_id=voice_id,
            language=language,
            detail_level=detail_level,
            status="active",
            started_at=_now(),
            last_heartbeat_at=_now(),
        )
        self._db.add(session)
        await self._db.flush()  # get session.id without full commit
        return session

    async def get_session(self, session_id: uuid.UUID) -> Optional[GuideSession]:
        return await self._db.get(GuideSession, session_id)

    async def update_session(self, session_id: uuid.UUID, **kwargs) -> None:
        await self._db.execute(
            update(GuideSession)
            .where(GuideSession.id == session_id)
            .values(**kwargs)
        )

    async def update_session_heartbeat(
        self,
        session_id: uuid.UUID,
        lat: float,
        lng: float,
        seconds_debited: int,
    ) -> None:
        """Batch-update session fields written on every heartbeat."""
        from geoalchemy2.elements import WKTElement
        location_wkt = f"SRID=4326;POINT({lng} {lat})"
        await self._db.execute(
            update(GuideSession)
            .where(GuideSession.id == session_id)
            .values(
                last_heartbeat_at=_now(),
                last_known_location=WKTElement(location_wkt, srid=4326),
                total_seconds_billed=GuideSession.total_seconds_billed + seconds_debited,
            )
        )

    # -------------------------------------------------------------------------
    # GPS logging (fire-and-forget)
    # -------------------------------------------------------------------------

    async def log_gps_point(
        self,
        session_id: uuid.UUID,
        lat: float,
        lng: float,
        heading_deg: Optional[float],
        speed_mps: Optional[float],
        accuracy_m: Optional[float],
    ) -> None:
        """Insert one GPS sample. Always committed by caller or fire-and-forget task."""
        entry = GuideSessionGpsLog(
            session_id=session_id,
            lat=lat,
            lng=lng,
            heading_deg=heading_deg,
            speed_mps=speed_mps,
            accuracy_m=accuracy_m,
            recorded_at=_now(),
        )
        self._db.add(entry)
        await self._db.flush()

    # -------------------------------------------------------------------------
    # Visit recording (fire-and-forget)
    # -------------------------------------------------------------------------

    async def record_visit(
        self,
        session_id: uuid.UUID,
        point_id: uuid.UUID,
        content_type_played: str = "main",
    ) -> None:
        visit = GuideSessionVisit(
            session_id=session_id,
            point_id=point_id,
            content_type_played=content_type_played,
            visited_at=_now(),
        )
        self._db.add(visit)
        await self._db.flush()

    # -------------------------------------------------------------------------
    # State restoration (after server restart)
    # -------------------------------------------------------------------------

    async def get_session_visits(self, session_id: uuid.UUID) -> list[GuideSessionVisit]:
        result = await self._db.execute(
            select(GuideSessionVisit)
            .where(GuideSessionVisit.session_id == session_id)
        )
        return list(result.scalars().all())

    async def get_recent_gps_points(
        self, session_id: uuid.UUID, limit: int = 10
    ) -> list[GuideSessionGpsLog]:
        result = await self._db.execute(
            select(GuideSessionGpsLog)
            .where(GuideSessionGpsLog.session_id == session_id)
            .order_by(GuideSessionGpsLog.recorded_at.desc())
            .limit(limit)
        )
        rows = list(result.scalars().all())
        rows.reverse()  # oldest first (chronological order for ring buffer)
        return rows

    async def get_last_visited_point(self, session_id: uuid.UUID) -> Optional[GuideSessionVisit]:
        result = await self._db.execute(
            select(GuideSessionVisit)
            .where(GuideSessionVisit.session_id == session_id)
            .order_by(GuideSessionVisit.visited_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_session_gps_track(
        self, session_id: uuid.UUID
    ) -> list[GuideSessionGpsLog]:
        """Full GPS track for path_geojson in session summary."""
        result = await self._db.execute(
            select(GuideSessionGpsLog)
            .where(GuideSessionGpsLog.session_id == session_id)
            .order_by(GuideSessionGpsLog.recorded_at)
        )
        return list(result.scalars().all())

    async def count_session_qa(self, session_id: uuid.UUID) -> int:
        result = await self._db.execute(
            select(GuideSessionQA)
            .where(GuideSessionQA.session_id == session_id)
        )
        return len(result.scalars().all())

    async def get_session_qa_history(
        self, session_id: uuid.UUID, limit: int = 5
    ) -> list[GuideSessionQA]:
        """Return last N Q&A pairs for a session (for LLM context)."""
        result = await self._db.execute(
            select(GuideSessionQA)
            .where(GuideSessionQA.session_id == session_id)
            .order_by(GuideSessionQA.created_at.desc())
            .limit(limit)
        )
        rows = list(result.scalars().all())
        rows.reverse()
        return rows

    async def save_qa_entry(
        self,
        session_id: uuid.UUID,
        question_text: str,
        answer_text: str,
        point_id: Optional[uuid.UUID] = None,
        qa_entry_id: Optional[uuid.UUID] = None,
    ) -> uuid.UUID:
        """Insert a Q&A record. Returns the new entry's id."""
        entry = GuideSessionQA(
            id=qa_entry_id or uuid.uuid4(),
            session_id=session_id,
            point_id=point_id,
            question_text=question_text,
            answer_text=answer_text,
        )
        self._db.add(entry)
        await self._db.flush()
        return entry.id

    # -------------------------------------------------------------------------
    # Knowledge for Q&A context
    # -------------------------------------------------------------------------

    async def get_knowledge_card_for_qa(
        self, point_id: uuid.UUID
    ) -> Optional[dict]:
        """Return knowledge card fields needed to build Q&A context."""
        from src.guide.domain.models import GuideKnowledgeCard
        card = await self._db.get(GuideKnowledgeCard, point_id)
        if card is None:
            return None
        return {
            "point_id": card.point_id,
            "card_type": card.card_type,
            "wikipedia_summary": card.wikipedia_summary,
            "street_name": card.street_name,
        }

    # -------------------------------------------------------------------------
    # User preferences
    # -------------------------------------------------------------------------

    async def get_user_preferences(
        self, user_id: uuid.UUID
    ) -> Optional[GuideUserPreference]:
        return await self._db.get(GuideUserPreference, user_id)

    async def upsert_user_preferences(
        self,
        user_id: uuid.UUID,
        voice_id: Optional[uuid.UUID] = None,
        language: Optional[str] = None,
        detail_level: Optional[str] = None,
    ) -> GuideUserPreference:
        prefs = await self._db.get(GuideUserPreference, user_id)
        if prefs is None:
            prefs = GuideUserPreference(
                user_id=user_id,
                preferred_voice_id=voice_id,
                preferred_language=language or "en",
                preferred_detail_level=detail_level or "standard",
                updated_at=_now(),
            )
            self._db.add(prefs)
        else:
            if voice_id is not None:
                prefs.preferred_voice_id = voice_id
            if language is not None:
                prefs.preferred_language = language
            if detail_level is not None:
                prefs.preferred_detail_level = detail_level
            prefs.updated_at = _now()
        await self._db.flush()
        return prefs

    # -------------------------------------------------------------------------
    # Balance (stub)
    # -------------------------------------------------------------------------

    async def get_balance(self, user_id: uuid.UUID) -> Optional[GuideMinuteBalance]:
        return await self._db.get(GuideMinuteBalance, user_id)

    # -------------------------------------------------------------------------
    # Zone / voices helpers for API handlers
    # -------------------------------------------------------------------------

    async def get_zone(self, zone_id: uuid.UUID) -> Optional[GuideZone]:
        return await self._db.get(GuideZone, zone_id)

    async def get_active_voices(self) -> list[GuideVoice]:
        result = await self._db.execute(
            select(GuideVoice).where(GuideVoice.is_active == True)
        )
        return list(result.scalars().all())

    async def get_packages(self) -> list[GuidePackage]:
        result = await self._db.execute(
            select(GuidePackage).where(GuidePackage.is_active == True)
        )
        return list(result.scalars().all())
