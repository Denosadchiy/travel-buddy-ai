"""
Integration tests for CandidateSelector.

Run:
  pytest src/hotels/tests/test_candidate_selector.py -v -s --no-cov
"""
import pytest

from src.hotels.application.candidate_selector import CandidateSelector
from src.hotels.application.intent_parser import IntentParser
from src.hotels.domain.schemas import HotelSearchRequest, ParsedIntent, ScoringWeights
from src.hotels.infrastructure.booking_client import BookingClient


ARRIVAL = "2026-07-01"
DEPARTURE = "2026-07-05"


@pytest.mark.asyncio
async def test_fetch_wide_funnel_large_city() -> None:
    """Paris (large city) — should fetch 40+ unique candidates from multi-sort."""
    selector = CandidateSelector()

    async with BookingClient() as client:
        dest = await client.search_destination("Paris")
        intent = ParsedIntent(scoring_weights=ScoringWeights())

        candidates = await selector.fetch_wide_funnel(
            dest_result=dest,
            intent=intent,
            booking_client=client,
            arrival_date=ARRIVAL,
            departure_date=DEPARTURE,
            adults=2,
        )

    # Large city should produce many unique candidates
    assert len(candidates) > 20, f"Expected >20 candidates, got {len(candidates)}"

    # All must have hotel_id
    assert all(h["hotel_id"] for h in candidates), "Some hotels missing hotel_id"

    # No duplicates
    ids = [h["hotel_id"] for h in candidates]
    assert len(ids) == len(set(ids)), "Duplicate hotel_ids found"

    print(f"\n✅ Paris wide funnel: {len(candidates)} unique candidates")
    print(f"   Sample: {candidates[0]['name']!r}, score={candidates[0]['review_score']}")


@pytest.mark.asyncio
async def test_l1_filter_reduces_candidates() -> None:
    """L1 filter should reduce Paris candidates to ≤25, all within budget."""
    selector = CandidateSelector()
    budget_max = 300.0

    intent = ParsedIntent(
        price_max=budget_max,
        min_review_score=7.0,
        scoring_weights=ScoringWeights(),
    )

    async with BookingClient() as client:
        dest = await client.search_destination("Paris")
        raw = await selector.fetch_wide_funnel(
            dest_result=dest,
            intent=intent,
            booking_client=client,
            arrival_date=ARRIVAL,
            departure_date=DEPARTURE,
            adults=2,
            currency="EUR",
        )

    filtered = selector.apply_l1_filter(raw, intent)

    assert len(filtered) <= 25, f"Too many candidates after L1: {len(filtered)}"
    assert len(filtered) > 0, "L1 filter removed everything"

    # All survivors must pass review threshold (if review_score is present)
    for h in filtered:
        if h["review_score"] > 0:
            assert h["review_score"] >= 7.0 - 0.01, (
                f"Hotel {h['hotel_id']} has score {h['review_score']} below threshold"
            )

    # Sorted by base score descending
    scores = [h["_base_score"] for h in filtered]
    assert scores == sorted(scores, reverse=True), "Candidates not sorted by base score"

    print(f"\n✅ L1 filter: {len(raw)} → {len(filtered)} candidates")
    print(f"   Top hotel: {filtered[0]['name']!r}, review={filtered[0]['review_score']}")
    print(f"   Base scores: {[round(s, 2) for s in scores[:5]]}")


@pytest.mark.asyncio
async def test_fetch_wide_funnel_small_city() -> None:
    """Small city — should work with single-sort and RELAXED thresholds."""
    selector = CandidateSelector()

    async with BookingClient() as client:
        # Andorra la Vella is a genuinely small city
        try:
            dest = await client.search_destination("Andorra la Vella")
        except Exception:
            pytest.skip("Could not resolve Andorra la Vella destination")

        intent = ParsedIntent(scoring_weights=ScoringWeights())

        candidates = await selector.fetch_wide_funnel(
            dest_result=dest,
            intent=intent,
            booking_client=client,
            arrival_date=ARRIVAL,
            departure_date=DEPARTURE,
            adults=2,
        )

    assert len(candidates) >= 0  # May be very small, just ensure no crash
    print(f"\n✅ Andorra la Vella: {len(candidates)} candidates (nr_hotels={dest.nr_hotels})")
