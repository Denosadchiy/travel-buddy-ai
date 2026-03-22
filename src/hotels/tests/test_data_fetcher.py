"""
Integration tests for HotelDataFetcher.

Run:
  pytest src/hotels/tests/test_data_fetcher.py -v -s --no-cov
"""
import pytest

from src.hotels.application.candidate_selector import CandidateSelector
from src.hotels.application.data_fetcher import HotelDataFetcher
from src.hotels.domain.schemas import HotelRawData, ParsedIntent, ScoringWeights
from src.hotels.infrastructure.booking_client import BookingClient

ARRIVAL = "2026-07-01"
DEPARTURE = "2026-07-05"


@pytest.mark.asyncio
async def test_fetch_all_returns_hotel_raw_data() -> None:
    """
    fetch_all returns HotelRawData with non-empty details, reviews, facilities
    for at least 4 out of 5 hotels.
    """
    selector = CandidateSelector()
    fetcher = HotelDataFetcher()

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

        # Take top 5 for the test (to keep it fast)
        hotel_ids = [h["hotel_id"] for h in filtered[:5]]
        assert len(hotel_ids) >= 3, f"Need at least 3 hotels, got {len(hotel_ids)}"

        results = await fetcher.fetch_all(
            hotel_ids=hotel_ids,
            booking_client=client,
            arrival=ARRIVAL,
            departure=DEPARTURE,
            adults=2,
            currency="EUR",
        )

    # At least 80% success rate
    assert len(results) >= len(hotel_ids) * 0.8, (
        f"Too many failures: {len(results)}/{len(hotel_ids)} returned"
    )

    for rd in results:
        assert isinstance(rd, HotelRawData), f"Expected HotelRawData, got {type(rd)}"
        assert rd.hotel_id in hotel_ids
        assert rd.details, f"Hotel {rd.hotel_id}: details dict is empty"
        assert len(rd.reviews) > 0, f"Hotel {rd.hotel_id}: no reviews"
        assert len(rd.facilities) > 0, f"Hotel {rd.hotel_id}: no facilities"

    print(f"\n✅ fetch_all: {len(results)}/{len(hotel_ids)} hotels fetched")
    for rd in results:
        print(
            f"   id={rd.hotel_id} name={rd.name!r} "
            f"reviews={len(rd.reviews)} facilities={len(rd.facilities)} "
            f"price={rd.price_per_night:.2f} {rd.currency}"
        )


@pytest.mark.asyncio
async def test_fetch_all_handles_invalid_ids_gracefully() -> None:
    """
    fetch_all must not crash on invalid hotel IDs — failed hotels are skipped.
    """
    fetcher = HotelDataFetcher()

    async with BookingClient() as client:
        # Mix valid and completely invalid hotel IDs
        dest = await client.search_destination("Paris")
        selector = CandidateSelector()
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
        valid_id = filtered[0]["hotel_id"]

        results = await fetcher.fetch_all(
            hotel_ids=[valid_id, 999999999],   # one valid, one invalid
            booking_client=client,
            arrival=ARRIVAL,
            departure=DEPARTURE,
            adults=2,
        )

    # Must not raise, must return at least 1 valid result
    assert any(r.hotel_id == valid_id for r in results), "Valid hotel was not returned"
    print(f"\n✅ Graceful error handling: {len(results)} result(s) from 2 (1 valid, 1 invalid)")
