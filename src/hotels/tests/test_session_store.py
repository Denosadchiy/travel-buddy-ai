"""
Unit tests for SearchSessionStore.

These tests are fast (no network calls) and use synthetic data.

Run:
  pytest src/hotels/tests/test_session_store.py -v -s --no-cov
"""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from src.hotels.application.session_store import SearchSessionStore
from src.hotels.domain.schemas import ParsedIntent, ScoringWeights


def _make_intent() -> ParsedIntent:
    return ParsedIntent(
        user_segment="couple",
        scoring_weights=ScoringWeights(),
        price_max=200.0,
    )


def _make_candidates(n: int = 10) -> list[dict]:
    return [{"hotel_id": i, "name": f"Hotel {i}", "_base_score": 0.5} for i in range(n)]


# ---------------------------------------------------------------------------
# Test 1: create and get session
# ---------------------------------------------------------------------------

def test_create_and_get_session() -> None:
    """create_session returns valid UUID; get_session returns the stored data."""
    store = SearchSessionStore()
    intent = _make_intent()
    candidates = _make_candidates(20)
    params = {"arrival": "2026-07-01", "departure": "2026-07-05", "adults": 2}

    session_id = store.create_session(intent, candidates, fetch_params=params)

    assert isinstance(session_id, str)
    assert len(session_id) == 36  # UUID4

    data = store.get_session(session_id)
    assert data is not None
    assert data["intent"] is intent
    assert len(data["all_candidates"]) == 20
    assert data["offset"] == 0
    assert data["analyzed_hotels"] == []
    assert data["fetch_params"] == params

    print(f"\n✅ Session created: {session_id[:8]}...")
    print(f"   candidates={len(data['all_candidates'])}, offset={data['offset']}")


# ---------------------------------------------------------------------------
# Test 2: update_session
# ---------------------------------------------------------------------------

def test_update_session() -> None:
    """update_session modifies fields on existing session."""
    store = SearchSessionStore()
    session_id = store.create_session(_make_intent(), _make_candidates())

    ok = store.update_session(session_id, offset=10, analyzed_hotels=[1, 2, 3])
    assert ok is True

    data = store.get_session(session_id)
    assert data["offset"] == 10
    assert data["analyzed_hotels"] == [1, 2, 3]

    print(f"\n✅ update_session: offset={data['offset']}, analyzed={data['analyzed_hotels']}")


# ---------------------------------------------------------------------------
# Test 3: session not found / expired
# ---------------------------------------------------------------------------

def test_get_nonexistent_session() -> None:
    """get_session returns None for unknown session_id."""
    store = SearchSessionStore()
    result = store.get_session("non-existent-id")
    assert result is None
    print("\n✅ Non-existent session returns None")


def test_expired_session_returns_none() -> None:
    """get_session returns None for sessions past TTL."""
    store = SearchSessionStore()
    session_id = store.create_session(_make_intent(), _make_candidates())

    # Patch created_at to be 31 minutes ago
    old_time = datetime.utcnow() - timedelta(minutes=31)
    store._sessions[session_id]["created_at"] = old_time

    result = store.get_session(session_id)
    assert result is None, "Expired session should return None"

    # Should also be removed from the store
    assert session_id not in store._sessions

    print("\n✅ Expired session (31min) returns None and is removed")


# ---------------------------------------------------------------------------
# Test 4: cleanup_expired
# ---------------------------------------------------------------------------

def test_cleanup_expired() -> None:
    """cleanup_expired removes expired sessions and returns count."""
    store = SearchSessionStore()

    # Create 3 sessions: 2 expired, 1 fresh
    old_time = datetime.utcnow() - timedelta(minutes=35)

    id1 = store.create_session(_make_intent(), _make_candidates())
    id2 = store.create_session(_make_intent(), _make_candidates())
    id3 = store.create_session(_make_intent(), _make_candidates())

    store._sessions[id1]["created_at"] = old_time
    store._sessions[id2]["created_at"] = old_time
    # id3 is fresh

    removed = store.cleanup_expired()
    assert removed == 2

    assert store.get_session(id1) is None
    assert store.get_session(id2) is None
    assert store.get_session(id3) is not None

    print(f"\n✅ cleanup_expired: removed {removed} expired sessions, 1 fresh remains")


# ---------------------------------------------------------------------------
# Test 5: multiple sessions are isolated
# ---------------------------------------------------------------------------

def test_multiple_sessions_isolated() -> None:
    """Multiple sessions do not interfere with each other."""
    store = SearchSessionStore()

    id_a = store.create_session(_make_intent(), _make_candidates(5))
    id_b = store.create_session(_make_intent(), _make_candidates(10))

    store.update_session(id_a, offset=5)

    data_a = store.get_session(id_a)
    data_b = store.get_session(id_b)

    assert data_a["offset"] == 5
    assert data_b["offset"] == 0  # not affected

    assert len(data_a["all_candidates"]) == 5
    assert len(data_b["all_candidates"]) == 10

    print(f"\n✅ Two isolated sessions: A(offset={data_a['offset']}), B(offset={data_b['offset']})")
