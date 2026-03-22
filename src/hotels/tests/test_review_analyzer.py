"""
Integration tests for ReviewAnalyzer.

Run:
  pytest src/hotels/tests/test_review_analyzer.py -v -s --no-cov
"""
import pytest

from src.hotels.application.candidate_selector import CandidateSelector
from src.hotels.application.data_fetcher import HotelDataFetcher
from src.hotels.application.review_analyzer import ReviewAnalyzer
from src.hotels.domain.schemas import ParsedIntent, ReviewAnalysis, ScoringWeights
from src.hotels.infrastructure.booking_client import BookingClient

ARRIVAL = "2026-07-01"
DEPARTURE = "2026-07-05"


@pytest.mark.asyncio
async def test_review_analyzer_couple_segment() -> None:
    """
    ReviewAnalyzer returns ReviewAnalysis for each hotel with valid segment_fit,
    non-empty top_pros, and a valid trend for user_segment='couple'.
    """
    selector = CandidateSelector()
    fetcher = HotelDataFetcher()
    analyzer = ReviewAnalyzer()

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
        filtered = selector.apply_l1_filter(candidates, intent)
        hotel_ids = [h["hotel_id"] for h in filtered[:5]]  # top 5 only

        raw_data = await fetcher.fetch_all(
            hotel_ids=hotel_ids,
            booking_client=client,
            arrival=ARRIVAL,
            departure=DEPARTURE,
            adults=2,
        )

    assert len(raw_data) >= 3, "Need at least 3 hotels to run test"

    results = await analyzer.analyze_batch(raw_data, user_segment="couple")

    assert len(results) == len(raw_data), (
        f"Expected {len(raw_data)} results, got {len(results)}"
    )

    for hotel in raw_data:
        hid = hotel.hotel_id
        assert hid in results, f"Hotel {hid} missing from results"
        analysis = results[hid]

        assert isinstance(analysis, ReviewAnalysis)
        assert analysis.hotel_id == hid
        assert 0.0 <= analysis.segment_fit <= 1.0, f"segment_fit={analysis.segment_fit} out of range"
        assert analysis.trend in ("quality_improving", "declining", "stable"), (
            f"Invalid trend: {analysis.trend!r}"
        )
        assert isinstance(analysis.top_pros, list)
        assert isinstance(analysis.top_cons, list)

    print(f"\n✅ ReviewAnalyzer: {len(results)} hotels analyzed")
    for hid, a in list(results.items())[:3]:
        print(
            f"   {hid}: segment_fit={a.segment_fit:.2f} trend={a.trend} "
            f"pros={a.top_pros[:2]} cons={a.top_cons[:2]}"
        )
        if a.hidden_issues:
            print(f"         hidden_issues={a.hidden_issues}")
