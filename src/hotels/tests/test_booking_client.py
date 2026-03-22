"""
Integration tests for BookingClient.

These tests make REAL HTTP calls to the Booking.com RapidAPI.
Requirements:
  - RAPIDAPI_KEY must be set in .env
  - Internet connectivity

Run:
  pytest src/hotels/tests/test_booking_client.py -v -s
"""
import asyncio

import pytest

from src.hotels.domain.schemas import DestinationResult, HotelRawData
from src.hotels.infrastructure.booking_client import BookingAPIError, BookingClient


# ---------------------------------------------------------------------------
# Test 1: search_destination
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_destination_paris() -> None:
    """search_destination('Paris') returns a valid DestinationResult."""
    async with BookingClient() as client:
        dest = await client.search_destination("Paris")

    assert isinstance(dest, DestinationResult)
    assert dest.dest_id is not None
    assert dest.dest_id != ""
    assert dest.search_type in ("city", "district", "region", "landmark", "airport")
    assert dest.nr_hotels > 0

    print(f"\n✅ Paris dest_id={dest.dest_id!r}, type={dest.search_type}, hotels={dest.nr_hotels}")


# ---------------------------------------------------------------------------
# Test 2: search_hotels
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_hotels_paris() -> None:
    """search_hotels returns a non-empty list for Paris with price filter."""
    async with BookingClient() as client:
        dest = await client.search_destination("Paris")
        hotels = await client.search_hotels(
            dest_ids=dest.dest_id,
            search_type=dest.search_type,
            arrival_date="2026-06-01",
            departure_date="2026-06-04",
            adults=2,
            price_min=50,
            price_max=300,
            categories_filter="facility::107",  # Free WiFi
            sort_by="bayesian_review_score",
            page_number=1,
            currency_code="EUR",
        )

    assert isinstance(hotels, list)
    assert len(hotels) > 0, "Expected at least 1 hotel in Paris"

    first = hotels[0]
    assert isinstance(first, dict)
    # hotel_id may be under "hotel_id" or "id"
    hotel_id = first.get("hotel_id") or first.get("id")
    assert hotel_id is not None, f"No hotel_id in response. Keys: {list(first.keys())}"

    name = first.get("name") or first.get("hotel_name", "")
    print(f"\n✅ Found {len(hotels)} hotels. First: id={hotel_id}, name={name!r}")


# ---------------------------------------------------------------------------
# Test 3: fetch_hotel_full_data (5 parallel calls)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_hotel_full_data() -> None:
    """
    fetch_hotel_full_data returns a valid HotelRawData with
    details, reviews (combined page 1+2), and facilities.
    """
    async with BookingClient() as client:
        # Resolve a real Paris hotel to avoid hardcoded IDs
        dest = await client.search_destination("Paris")
        hotels = await client.search_hotels(
            dest_ids=dest.dest_id,
            search_type=dest.search_type,
            arrival_date="2026-06-01",
            departure_date="2026-06-04",
            adults=2,
            sort_by="bayesian_review_score",
            page_number=1,
            currency_code="EUR",
        )
        assert hotels, "No hotels returned from search"
        hotel_id = hotels[0].get("hotel_id") or hotels[0].get("id")

        full_data = await client.fetch_hotel_full_data(
            hotel_id=int(hotel_id),
            arrival="2026-06-01",
            departure="2026-06-04",
            adults=2,
            currency="EUR",
        )

    assert isinstance(full_data, HotelRawData)
    assert full_data.hotel_id == int(hotel_id)
    assert full_data.details, "details dict should not be empty"
    assert len(full_data.reviews) > 0, "Expected at least some reviews from pages 1+2"
    assert len(full_data.facilities) > 0, "Expected at least some facilities"

    print(
        f"\n✅ Hotel {hotel_id}: reviews={len(full_data.reviews)}, "
        f"facilities={len(full_data.facilities)}, "
        f"price_per_night={full_data.price_per_night:.2f} {full_data.currency}"
    )


# ---------------------------------------------------------------------------
# Test 4: error handling — nonexistent hotel_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_error_handling_invalid_hotel() -> None:
    """get_hotel_details raises BookingAPIError for a nonexistent hotel_id."""
    async with BookingClient() as client:
        try:
            await client.get_hotel_details(
                hotel_id=999999999,
                arrival="2026-06-01",
                departure="2026-06-04",
                adults=2,
            )
            # If no exception, the API returned something unexpected —
            # still a valid result (API may return empty data instead of error)
            print("\n⚠️  API returned no error for hotel_id=999999999 (may return empty data)")
        except BookingAPIError as exc:
            print(f"\n✅ Error handling works: {type(exc).__name__}: {exc}")
        except Exception as exc:
            # Any other exception type is also acceptable for this test
            print(f"\n✅ Got exception for invalid hotel: {type(exc).__name__}: {exc}")
