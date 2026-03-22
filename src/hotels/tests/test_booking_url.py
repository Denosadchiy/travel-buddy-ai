"""
Stage 4 — Booking URL tests.

Verifies that booking_url is present and correctly parameterised in
search(), search_more(), and find_hotel() responses.

Run:
  pytest src/hotels/tests/test_booking_url.py -v -s --no-cov
"""
import pytest

from src.hotels.application.orchestrator import HotelSearchOrchestrator, _build_booking_url
from src.hotels.domain.schemas import HotelFindRequest, HotelSearchRequest


# ──────────────────────────────────────────────────────────────────────────────
# Unit tests — _build_booking_url helper (no network)
# ──────────────────────────────────────────────────────────────────────────────

def test_booking_url_uses_base_url():
    url = _build_booking_url(
        base_url="https://www.booking.com/hotel/fr/le-bristol-paris.html",
        hotel_id=1769895,
        check_in="2026-07-01",
        check_out="2026-07-05",
        adults=2,
        children_ages=[],
        currency="EUR",
    )
    assert "booking.com/hotel/fr/le-bristol-paris.html" in url
    assert "checkin=2026-07-01" in url
    assert "checkout=2026-07-05" in url
    assert "group_adults=2" in url
    assert "group_children=0" in url
    assert "selected_currency=EUR" in url
    # hotel_id should NOT be in URL since we have a hotel path
    assert "hotel_id" not in url


def test_booking_url_fallback_when_no_base_url():
    url = _build_booking_url(
        base_url="",
        hotel_id=99999,
        check_in="2026-08-01",
        check_out="2026-08-04",
        adults=1,
        children_ages=[],
        currency="USD",
    )
    assert "booking.com" in url
    assert "checkin=2026-08-01" in url
    assert "hotel_id=99999" in url


def test_booking_url_children_ages():
    url = _build_booking_url(
        base_url="https://www.booking.com/hotel/es/h10-atlantic-city.html",
        hotel_id=12345,
        check_in="2026-07-01",
        check_out="2026-07-05",
        adults=2,
        children_ages=[5, 8],
        currency="EUR",
    )
    assert "group_children=2" in url
    assert "age=5" in url
    assert "age=8" in url


def test_booking_url_strips_existing_query_params():
    url = _build_booking_url(
        base_url="https://www.booking.com/hotel/fr/paris-hotel.html?lang=fr",
        hotel_id=111,
        check_in="2026-07-01",
        check_out="2026-07-03",
        adults=2,
        children_ages=[],
        currency="EUR",
    )
    # Should not contain duplicate lang param from original URL
    assert url.count("lang=fr") == 0
    assert "checkin=2026-07-01" in url


# ──────────────────────────────────────────────────────────────────────────────
# Integration tests — real API calls
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_booking_url_in_search():
    """All hotels in search response have booking_url with correct params."""
    orchestrator = HotelSearchOrchestrator()
    request = HotelSearchRequest(
        city="Paris",
        check_in="2026-07-01",
        check_out="2026-07-05",
        adults=2,
        children_ages=[5, 8],
        budget_max=200.0,
        currency="EUR",
    )
    response = await orchestrator.search(request)

    assert len(response.hotels) > 0, "No hotels returned"
    for hotel in response.hotels:
        print(f"  [{hotel.name}] booking_url: {hotel.booking_url[:80]}...")
        assert hotel.booking_url != "", f"Hotel {hotel.name} has empty booking_url"
        assert "booking.com" in hotel.booking_url
        assert "checkin=2026-07-01" in hotel.booking_url
        assert "checkout=2026-07-05" in hotel.booking_url
        assert "group_adults=2" in hotel.booking_url
        assert "group_children=2" in hotel.booking_url
        assert "age=5" in hotel.booking_url
        assert "age=8" in hotel.booking_url
        assert "EUR" in hotel.booking_url


@pytest.mark.asyncio
async def test_booking_url_in_search_more():
    """search_more() also populates booking_url with original search params."""
    orchestrator = HotelSearchOrchestrator()
    request = HotelSearchRequest(
        city="Paris",
        check_in="2026-07-01",
        check_out="2026-07-04",
        adults=2,
        budget_max=200.0,
        currency="EUR",
    )
    first = await orchestrator.search(request)
    assert first.session_id, "Missing session_id from first page"

    second = await orchestrator.search_more(first.session_id)
    print(f"\nsearch_more: {len(second.hotels)} hotels")
    for hotel in second.hotels:
        assert hotel.booking_url != "", f"Hotel {hotel.name} missing booking_url in page 2"
        assert "checkin=2026-07-01" in hotel.booking_url
        assert "group_adults=2" in hotel.booking_url


@pytest.mark.asyncio
async def test_booking_url_in_find():
    """find_hotel() populates booking_url."""
    orchestrator = HotelSearchOrchestrator()
    request = HotelFindRequest(
        hotel_name="Le Bristol Paris",
        city="Paris",
        check_in="2026-07-01",
        check_out="2026-07-05",
        adults=2,
    )
    response = await orchestrator.find_hotel(request)

    assert len(response.hotels) >= 1, "No hotels returned by find_hotel"
    hotel = response.hotels[0]
    print(f"\nFind Bristol: booking_url = {hotel.booking_url[:80]}...")
    assert hotel.booking_url != ""
    assert "booking.com" in hotel.booking_url
    assert "checkin=2026-07-01" in hotel.booking_url
    assert "checkout=2026-07-05" in hotel.booking_url
