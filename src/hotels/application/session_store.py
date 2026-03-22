"""
SearchSessionStore — in-memory session cache for pagination.

Stores per session_id:
  - intent: ParsedIntent (with scoring_weights)
  - all_candidates: list[dict]    — all ~80 raw candidates (after dedup)
  - analyzed_hotels: list[int]    — hotel_ids already deep-analyzed
  - ranked_results: MasterRankingResult | None
  - offset: int                   — pagination cursor into all_candidates
  - fetch_params: dict            — original search params for refetching

TTL: HOTEL_SESSION_TTL_MINUTES (default 30min), checked on each get().
Cleanup: lazy (on get) + explicit cleanup_expired().
session_id: UUID4 string.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from src.config import settings

logger = logging.getLogger(__name__)


class SearchSessionStore:
    """
    In-memory cache for hotel search sessions.

    Thread-safety: single-process asyncio — no locking needed.
    For multi-process/distributed use: replace with Redis.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}

    @property
    def _ttl(self) -> timedelta:
        return timedelta(minutes=settings.hotel_session_ttl_minutes)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_session(
        self,
        intent: Any,
        all_candidates: list[dict],
        fetch_params: dict | None = None,
    ) -> str:
        """
        Create a new search session.

        Args:
            intent: ParsedIntent for this search.
            all_candidates: Full candidate list (~80 hotels after dedup).
            fetch_params: Booking params needed to fetch more pages later.

        Returns:
            New session_id (UUID4 string).
        """
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = {
            "intent": intent,
            "all_candidates": list(all_candidates),
            "analyzed_hotels": [],
            "ranked_results": None,
            "offset": 0,
            "fetch_params": fetch_params or {},
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        logger.info(
            "SessionStore: created session %s with %d candidates",
            session_id[:8], len(all_candidates),
        )
        return session_id

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """
        Retrieve session data.

        Returns None if session not found or expired (and removes it lazily).
        """
        session = self._sessions.get(session_id)
        if session is None:
            return None

        if datetime.utcnow() - session["created_at"] > self._ttl:
            del self._sessions[session_id]
            logger.info("SessionStore: session %s expired and removed", session_id[:8])
            return None

        return session

    def update_session(self, session_id: str, **kwargs: Any) -> bool:
        """
        Update fields on an existing session.

        Args:
            session_id: Target session.
            **kwargs: Fields to update (intent, ranked_results, offset, analyzed_hotels, etc.)

        Returns:
            True if session found and updated, False if session not found/expired.
        """
        session = self.get_session(session_id)
        if session is None:
            return False

        session.update(kwargs)
        session["updated_at"] = datetime.utcnow()
        return True

    def cleanup_expired(self) -> int:
        """
        Remove all expired sessions.

        Returns:
            Number of sessions removed.
        """
        now = datetime.utcnow()
        expired = [
            sid for sid, s in self._sessions.items()
            if now - s["created_at"] > self._ttl
        ]
        for sid in expired:
            del self._sessions[sid]

        if expired:
            logger.info("SessionStore: cleaned up %d expired sessions", len(expired))
        return len(expired)

    def session_count(self) -> int:
        """Return number of active (not yet expired) sessions."""
        return len(self._sessions)

    def delete_session(self, session_id: str) -> bool:
        """Explicitly delete a session."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False
