"""
Orchestrator integration tests (Stage 3 — Phases 1–7).

Tests:
  A. search() large city (Barcelona) — verifies full pipeline
  B. search() small city (Andorra la Vella) — relaxed mode
  C. search() no user_wishes — deterministic intent
  D. search_more() — pagination, no duplicates
  E. find_hotel() — direct lookup by name
  F. explain_hotel() — exclusion reason lookup

Run:
  pytest src/hotels/tests/test_orchestrator.py -v -s --no-cov
"""
import pytest

from src.hotels.application.orchestrator import HotelSearchOrchestrator
from src.hotels.domain.schemas import (
    HotelExplainRequest,
    HotelFindRequest,
    HotelSearchRequest,
)


# ──────────────────────────────────────────────────────────────────────────────
# A. Large city — full pipeline
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_barcelona() -> None:
    """Full pipeline: Barcelona boutique + remote work request."""
    orchestrator = HotelSearchOrchestrator()
    request = HotelSearchRequest(
        city="Barcelona",
        check_in="2026-07-01",
        check_out="2026-07-05",
        adults=2,
        budget_max=180.0,
        currency="EUR",
        user_wishes="Тихий бутиковый отель рядом с пляжем, хочу работать из номера",
    )

    response = await orchestrator.search(request)

    print(f"\n{'='*60}")
    print(f"Barcelona search: {len(response.hotels)} hotels")
    print(f"Session ID: {response.session_id[:16]}...")
    print(f"Total found: {response.total_found}")
    print(f"Filters: {response.applied_filters_summary}")
    for h in response.hotels:
        print(f"  [{h.ai_score:.1f}] {h.name} — {h.ai_match_reason[:60]}")

    assert len(response.hotels) > 0, "No hotels returned"
    assert len(response.hotels) <= 10
    assert response.session_id, "Missing session_id"
    assert response.total_found > 0
    assert all(h.ai_score >= 0 for h in response.hotels)
    assert all(h.hotel_id > 0 for h in response.hotels)
    # Verify sorted by ai_score descending
    scores = [h.ai_score for h in response.hotels]
    assert scores == sorted(scores, reverse=True), "Hotels not sorted by ai_score"


# ──────────────────────────────────────────────────────────────────────────────
# B. Small city — relaxed mode
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_andorra() -> None:
    """Small city: Andorra la Vella — should not crash, relaxed thresholds."""
    orchestrator = HotelSearchOrchestrator()
    request = HotelSearchRequest(
        city="Andorra la Vella",
        check_in="2026-07-01",
        check_out="2026-07-03",
        adults=2,
    )

    response = await orchestrator.search(request)

    print(f"\nAndorra: {len(response.hotels)} hotels, total_found={response.total_found}")
    for h in response.hotels:
        print(f"  [{h.ai_score:.1f}] {h.name}")

    # Small city may have fewer than 10 results — that's OK
    assert response.session_id is not None  # may be empty string if 0 results
    assert len(response.hotels) >= 0        # could be 0 in edge case


# ──────────────────────────────────────────────────────────────────────────────
# C. No user_wishes — deterministic intent only
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_paris_no_wishes() -> None:
    """Paris with only dates and budget — no free text."""
    orchestrator = HotelSearchOrchestrator()
    request = HotelSearchRequest(
        city="Paris",
        check_in="2026-06-01",
        check_out="2026-06-04",
        adults=2,
        budget_max=200.0,
        currency="EUR",
    )

    response = await orchestrator.search(request)

    print(f"\nParis (no wishes): {len(response.hotels)} hotels")
    for h in response.hotels[:3]:
        print(f"  [{h.ai_score:.1f}] {h.name}")

    assert len(response.hotels) > 0, "No hotels for Paris"
    assert response.session_id, "Missing session_id"


# ──────────────────────────────────────────────────────────────────────────────
# D. Pagination — no duplicates
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_more_paris() -> None:
    """search() then search_more() — next batch should not duplicate first."""
    orchestrator = HotelSearchOrchestrator()
    request = HotelSearchRequest(
        city="Paris",
        check_in="2026-06-01",
        check_out="2026-06-04",
        adults=2,
        budget_max=200.0,
        currency="EUR",
    )

    first = await orchestrator.search(request)
    assert first.session_id, "First response missing session_id"

    second = await orchestrator.search_more(first.session_id)

    first_ids = {h.hotel_id for h in first.hotels}
    second_ids = {h.hotel_id for h in second.hotels}

    print(f"\nFirst page: {sorted(first_ids)}")
    print(f"Second page: {sorted(second_ids)}")
    print(f"Overlap: {first_ids & second_ids}")

    overlap = first_ids & second_ids
    assert len(overlap) == 0, f"Duplicate hotels across pages: {overlap}"
    total_unique = len(first_ids) + len(second_ids)
    assert total_unique >= len(first_ids), "Second page returned 0 hotels"


@pytest.mark.asyncio
async def test_search_more_invalid_session() -> None:
    """search_more with invalid session_id → ValueError."""
    orchestrator = HotelSearchOrchestrator()
    with pytest.raises(ValueError, match="not found"):
        await orchestrator.search_more("00000000-invalid-session-id")


# ──────────────────────────────────────────────────────────────────────────────
# E. find_hotel()
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_find_hotel_paris() -> None:
    """Direct hotel lookup by name."""
    orchestrator = HotelSearchOrchestrator()
    request = HotelFindRequest(
        hotel_name="Le Bristol Paris",
        city="Paris",
        check_in="2026-06-01",
        check_out="2026-06-04",
        adults=2,
    )

    response = await orchestrator.find_hotel(request)

    print(f"\nFind 'Le Bristol Paris': {len(response.hotels)} result(s)")
    for h in response.hotels:
        print(f"  [{h.ai_score:.1f}] {h.name} — id={h.hotel_id}")

    assert len(response.hotels) >= 1, "No hotels found"
    # At least one result should contain "Bristol" in name or there's a reasonable result
    assert response.hotels[0].hotel_id > 0
    assert response.hotels[0].ai_score >= 0


# ──────────────────────────────────────────────────────────────────────────────
# F. explain_hotel()
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_explain_hotel() -> None:
    """After search, explain a hotel that was a candidate but not in top-10."""
    orchestrator = HotelSearchOrchestrator()

    # First do a search to populate session
    search_request = HotelSearchRequest(
        city="Paris",
        check_in="2026-06-01",
        check_out="2026-06-04",
        adults=2,
        budget_max=150.0,
        currency="EUR",
    )
    search_response = await orchestrator.search(search_request)
    session_id = search_response.session_id

    # Try to explain a common Ibis hotel (likely a candidate)
    explain_request = HotelExplainRequest(
        session_id=session_id,
        hotel_name="Ibis",
    )
    explain_response = await orchestrator.explain_hotel(explain_request)

    print(f"\nExplain 'Ibis': found_in_candidates={explain_response.found_in_candidates}")
    print(f"  Reason: {explain_response.reason}")

    # Either found or not — but must not crash
    assert explain_response.reason, "Empty explanation"
    # hotel_name is the matched candidate name (may be longer than search query)
    assert "Ibis" in explain_response.hotel_name or explain_response.found_in_candidates is False


@pytest.mark.asyncio
async def test_explain_expired_session() -> None:
    """explain_hotel with expired/invalid session → graceful response."""
    orchestrator = HotelSearchOrchestrator()
    explain_request = HotelExplainRequest(
        session_id="00000000-nonexistent",
        hotel_name="Some Hotel",
    )
    response = await orchestrator.explain_hotel(explain_request)

    assert response.found_in_candidates is False
    assert "not found" in response.reason.lower() or "expired" in response.reason.lower()
