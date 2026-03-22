"""
Integration tests for MasterRanker.

Run:
  pytest src/hotels/tests/test_ranker.py -v -s --no-cov
"""
import pytest

from src.hotels.application.candidate_selector import CandidateSelector
from src.hotels.application.data_fetcher import HotelDataFetcher
from src.hotels.application.ranker import MasterRanker
from src.hotels.application.review_analyzer import ReviewAnalyzer
from src.hotels.domain.schemas import (
    HotelProfile,
    MasterRankingResult,
    ParsedIntent,
    ReviewAnalysis,
    ScoringWeights,
)
from src.hotels.infrastructure.booking_client import BookingClient

ARRIVAL = "2026-07-01"
DEPARTURE = "2026-07-05"


async def _build_profiles(n: int = 8) -> tuple[list[HotelProfile], ParsedIntent]:
    """Helper: fetch real hotel profiles from Paris."""
    selector = CandidateSelector()
    fetcher = HotelDataFetcher()
    analyzer = ReviewAnalyzer()

    intent = ParsedIntent(
        price_max=300.0,
        min_review_score=7.0,
        user_segment="couple",
        semantic_criteria={"atmosphere": ["romantic", "charming"], "style": ["boutique"]},
        must_have=["Free WiFi"],
        is_boutique_preferred=True,
        scoring_weights=ScoringWeights(
            semantic_match=0.30,
            location=0.25,
            review_quality=0.20,
            facility_match=0.15,
            price_value=0.05,
            segment_fit=0.05,
        ),
    )

    async with BookingClient() as client:
        dest = await client.search_destination("Paris")
        candidates = await selector.fetch_wide_funnel(
            dest_result=dest,
            intent=intent,
            booking_client=client,
            arrival_date=ARRIVAL,
            departure_date=DEPARTURE,
            adults=2,
        )
        filtered = selector.apply_l1_filter(candidates, intent)
        hotel_ids = [h["hotel_id"] for h in filtered[:n]]

        raw_data = await fetcher.fetch_all(
            hotel_ids=hotel_ids,
            booking_client=client,
            arrival=ARRIVAL,
            departure=DEPARTURE,
            adults=2,
        )

    reviews = await analyzer.analyze_batch(raw_data, user_segment="couple")
    profiles = [
        HotelProfile(raw=rd, review_analysis=reviews[rd.hotel_id])
        for rd in raw_data
        if rd.hotel_id in reviews
    ]
    return profiles, intent


@pytest.mark.asyncio
async def test_rank_llm_driven() -> None:
    """LLM-driven ranking returns ≤10 hotels sorted by ai_score descending."""
    profiles, intent = await _build_profiles(n=8)
    assert len(profiles) >= 3, "Need at least 3 profiles"

    ranker = MasterRanker()
    result = await ranker.rank(profiles, intent)

    assert isinstance(result, MasterRankingResult)
    assert len(result.ranked_top10) > 0, "No hotels in top 10"
    assert len(result.ranked_top10) <= 10

    # Scores should be descending
    scores = [h.ai_score for h in result.ranked_top10]
    assert scores == sorted(scores, reverse=True), "Top 10 not sorted by ai_score"

    # ai_match_reason must be non-empty for all top 10
    for h in result.ranked_top10:
        assert h.ai_match_reason, f"Hotel {h.hotel_id} has empty ai_match_reason"
        assert 0 <= h.ai_score <= 10, f"ai_score {h.ai_score} out of range"

    print(f"\n✅ LLM ranking: {len(result.ranked_top10)} hotels")
    print(f"   First: id={result.ranked_top10[0].hotel_id} score={result.ranked_top10[0].ai_score}")
    print(f"   Last:  id={result.ranked_top10[-1].hotel_id} score={result.ranked_top10[-1].ai_score}")
    for h in result.ranked_top10:
        print(f"   [{h.ai_score:.1f}] {h.hotel_id} — {h.ai_match_reason[:80]}")
    if result.notable_excluded:
        print(f"   Notable excluded: {len(result.notable_excluded)}")


@pytest.mark.asyncio
async def test_rank_fallback_deterministic() -> None:
    """Formula fallback must produce results without any LLM call."""
    profiles, intent = await _build_profiles(n=5)
    assert len(profiles) >= 3

    ranker = MasterRanker()
    result = ranker.rank_fallback(profiles, intent)

    assert isinstance(result, MasterRankingResult)
    assert len(result.ranked_top10) == min(10, len(profiles))

    scores = [h.ai_score for h in result.ranked_top10]
    assert scores == sorted(scores, reverse=True), "Fallback not sorted by score"
    assert all(0 <= s <= 10 for s in scores), "Scores out of [0,10] range"

    print(f"\n✅ Formula fallback: {len(result.ranked_top10)} hotels")
    for h in result.ranked_top10:
        print(f"   [{h.ai_score:.1f}] {h.hotel_id}")
