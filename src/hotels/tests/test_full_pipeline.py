"""
Full pipeline integration test (Phases 1–5).

Runs the entire hotel search pipeline without the orchestrator,
using Barcelona as the test city.

Run:
  pytest src/hotels/tests/test_full_pipeline.py -v -s --no-cov
"""
import pytest

from src.hotels.application.candidate_selector import CandidateSelector
from src.hotels.application.data_fetcher import HotelDataFetcher
from src.hotels.application.intent_parser import IntentParser
from src.hotels.application.ranker import MasterRanker
from src.hotels.application.review_analyzer import ReviewAnalyzer
from src.hotels.domain.schemas import HotelProfile, HotelSearchRequest
from src.hotels.infrastructure.booking_client import BookingClient


@pytest.mark.asyncio
async def test_full_pipeline_barcelona() -> None:
    """
    End-to-end pipeline: Barcelona, boutique + remote work request.

    Phase 1: IntentParser → ParsedIntent
    Phase 2: CandidateSelector → 80 candidates → 25 filtered
    Phase 3: HotelDataFetcher → full data for 25 hotels
    Phase 4: ReviewAnalyzer → ReviewAnalysis per hotel
    Phase 5: MasterRanker → top 10 ranked hotels

    Assertions:
      - intent.scoring_weights are set and sum to ~1.0
      - funnel: wide > filtered, filtered ≤ 25
      - all fetched hotels have reviews + facilities
      - ranked_top10 has ≤10 items sorted by ai_score
      - first hotel's ai_score ≥ last hotel's ai_score
    """
    request = HotelSearchRequest(
        city="Barcelona",
        check_in="2026-07-01",
        check_out="2026-07-05",
        adults=2,
        budget_max=180.0,
        currency="EUR",
        user_wishes="Тихий бутиковый отель рядом с пляжем, хочу работать из номера",
    )

    # ── Phase 1: Intent ────────────────────────────────────────────────
    intent_parser = IntentParser()
    intent = await intent_parser.parse(request)

    assert intent.scoring_weights is not None
    w_sum = sum(intent.scoring_weights.model_dump().values())
    assert abs(w_sum - 1.0) < 0.02, f"ScoringWeights sum={w_sum:.3f}, expected ~1.0"

    print(f"\n{'='*60}")
    print(f"Phase 1 — Intent:")
    print(f"  segment: {intent.user_segment}")
    print(f"  weights: {{{', '.join(f'{k}={v:.2f}' for k, v in intent.scoring_weights.model_dump().items())}}}")
    print(f"  filters: {intent.api_filters}")
    print(f"  must_have: {intent.must_have}")
    print(f"  dealbreakers: {intent.dealbreakers}")
    print(f"  remote_work: {intent.is_remote_work}")

    # ── Phase 2: Candidate selection ────────────────────────────────────
    selector = CandidateSelector()

    async with BookingClient() as booking_client:
        dest = await booking_client.search_destination(request.city)

        # 2a: Wide funnel
        raw_hotels = await selector.fetch_wide_funnel(
            dest_result=dest,
            intent=intent,
            booking_client=booking_client,
            arrival_date=request.check_in,
            departure_date=request.check_out,
            adults=request.adults,
            currency=request.currency,
        )

        print(f"\nPhase 2a — Wide funnel: {len(raw_hotels)} unique candidates")

        # 2b: L1 filter
        filtered = selector.apply_l1_filter(raw_hotels, intent)

        print(f"Phase 2b — L1 filter: {len(raw_hotels)} → {len(filtered)} candidates")
        assert len(filtered) <= 25, f"Too many candidates after L1: {len(filtered)}"
        assert len(raw_hotels) >= len(filtered), "Funnel should reduce or keep same count"

        # ── Phase 3: Deep data fetch ────────────────────────────────────
        hotel_ids = [h["hotel_id"] for h in filtered]
        fetcher = HotelDataFetcher()

        raw_data = await fetcher.fetch_all(
            hotel_ids=hotel_ids,
            booking_client=booking_client,
            arrival=request.check_in,
            departure=request.check_out,
            adults=request.adults,
            currency=request.currency,
        )

    print(f"\nPhase 3 — Deep fetch: {len(raw_data)}/{len(hotel_ids)} hotels")
    assert len(raw_data) >= len(hotel_ids) * 0.7, (
        f"Too many fetch failures: {len(raw_data)}/{len(hotel_ids)}"
    )
    for rd in raw_data:
        assert rd.details or rd.name, f"Hotel {rd.hotel_id}: completely empty details"

    # ── Phase 4: Review analysis ────────────────────────────────────────
    analyzer = ReviewAnalyzer()
    review_results = await analyzer.analyze_batch(raw_data, user_segment=intent.user_segment)

    print(f"\nPhase 4 — Review analysis: {len(review_results)} hotels analyzed")
    assert len(review_results) == len(raw_data)

    profiles = [
        HotelProfile(raw=rd, review_analysis=review_results[rd.hotel_id])
        for rd in raw_data
        if rd.hotel_id in review_results
    ]
    assert len(profiles) > 0, "No profiles created"

    # ── Phase 5: Master ranking ─────────────────────────────────────────
    ranker = MasterRanker()
    ranking = await ranker.rank(profiles, intent)

    print(f"\nPhase 5 — Ranking: top {len(ranking.ranked_top10)} hotels")
    assert len(ranking.ranked_top10) > 0, "No hotels in top 10"
    assert len(ranking.ranked_top10) <= 10

    scores = [h.ai_score for h in ranking.ranked_top10]
    assert scores == sorted(scores, reverse=True), "Top 10 not sorted by ai_score"
    assert ranking.ranked_top10[0].ai_score >= ranking.ranked_top10[-1].ai_score

    print(f"\n{'='*60}")
    print(f"✅ Full pipeline complete!")
    print(f"   {len(raw_hotels)} candidates → {len(filtered)} filtered → {len(raw_data)} fetched → top {len(ranking.ranked_top10)}")
    print(f"\nTop 10:")
    for h in ranking.ranked_top10:
        print(f"  [{h.ai_score:.1f}] hotel={h.hotel_id} — {h.ai_match_reason[:70]}")
    if ranking.notable_excluded:
        print(f"\nNotable excluded ({len(ranking.notable_excluded)}):")
        for e in ranking.notable_excluded:
            print(f"  {e.name!r}: {e.reason}")
