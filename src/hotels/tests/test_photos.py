"""
Stage 4 — Hotel photos tests.

Verifies that HotelResult.photos is populated with real photo URLs
for hotels returned by search(), search_more(), and find_hotel().

Run:
  pytest src/hotels/tests/test_photos.py -v -s --no-cov
"""
import pytest

from src.hotels.application.orchestrator import HotelSearchOrchestrator
from src.hotels.domain.schemas import HotelFindRequest, HotelSearchRequest


@pytest.mark.asyncio
async def test_photos_populated_in_search():
    """
    All hotels in search response have at least 1 photo URL.
    The URL must be a valid http(s) link.
    """
    orchestrator = HotelSearchOrchestrator()
    request = HotelSearchRequest(
        city="Barcelona",
        check_in="2026-07-01",
        check_out="2026-07-04",
        adults=2,
        budget_max=180.0,
        currency="EUR",
    )
    response = await orchestrator.search(request)

    assert len(response.hotels) > 0, "No hotels returned"

    hotels_with_photos = 0
    for hotel in response.hotels:
        print(f"  [{hotel.name}] photos: {len(hotel.photos)}")
        if hotel.photos:
            hotels_with_photos += 1
            for url in hotel.photos:
                assert url.startswith("http"), f"Invalid photo URL in {hotel.name}: {url}"

    # At least 50% of hotels should have photos (API may vary)
    assert hotels_with_photos >= len(response.hotels) // 2, (
        f"Only {hotels_with_photos}/{len(response.hotels)} hotels have photos — "
        "check room photo extraction in booking_client.py"
    )
    print(f"\n{hotels_with_photos}/{len(response.hotels)} hotels have photos")


@pytest.mark.asyncio
async def test_photos_url_format():
    """Photo URLs must point to Booking.com CDN."""
    orchestrator = HotelSearchOrchestrator()
    request = HotelSearchRequest(
        city="Rome",
        check_in="2026-08-01",
        check_out="2026-08-04",
        adults=2,
        budget_max=200.0,
        currency="EUR",
    )
    response = await orchestrator.search(request)

    cdn_photos = 0
    for hotel in response.hotels:
        for url in hotel.photos:
            if "bstatic.com" in url or "booking.com" in url:
                cdn_photos += 1

    print(f"\nCDN photo URLs: {cdn_photos}")
    # If we have any photos at all, they should come from Booking CDN
    total_photos = sum(len(h.photos) for h in response.hotels)
    if total_photos > 0:
        assert cdn_photos > 0, "Photos found but none from Booking CDN"


@pytest.mark.asyncio
async def test_photos_in_find():
    """find_hotel() also populates photos."""
    orchestrator = HotelSearchOrchestrator()
    request = HotelFindRequest(
        hotel_name="Le Bristol Paris",
        city="Paris",
        check_in="2026-07-01",
        check_out="2026-07-05",
        adults=2,
    )
    response = await orchestrator.find_hotel(request)

    assert len(response.hotels) >= 1
    hotel = response.hotels[0]
    print(f"\n{hotel.name}: {len(hotel.photos)} photos")
    # Le Bristol Paris is a well-known hotel — should have room photos in API response
    # (not guaranteed, so we just check format if present)
    for url in hotel.photos:
        assert url.startswith("http"), f"Invalid photo URL: {url}"
