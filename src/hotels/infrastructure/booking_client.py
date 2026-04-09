"""
BookingClient — async HTTP client for Booking.com RapidAPI.

Design:
  - httpx.AsyncClient with timeout=15s, max_connections=20
  - asyncio.Semaphore(15) for rate limiting
  - Retry ×3 with exponential backoff: 0.5s → 1s → 2s
  - All requests use direct HTTP (no MCP dependency)

CRITICAL: searchHotels API parameter is `dest_id` (singular).
The architecture plan note about `dest_ids` (plural) was incorrect — confirmed by direct test.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from src.config import settings
from src.hotels.domain.schemas import (
    DestinationResult,
    FacilityItem,
    HotelRawData,
    ReviewRaw,
    ReviewScores,
)

logger = logging.getLogger(__name__)

_BASE = f"{settings.booking_api_base_url}/api/v1/hotels"
_TIMEOUT = settings.hotel_search_timeout_seconds
_RETRY_DELAYS = [0.5, 1.0, 2.0]


# =============================================================================
# Custom exceptions
# =============================================================================

class BookingAPIError(Exception):
    """Raised when Booking.com API returns an error response."""
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class RateLimitError(BookingAPIError):
    """Raised on HTTP 429 Too Many Requests."""


class DestinationNotFoundError(BookingAPIError):
    """Raised when searchDestination returns no results."""


# =============================================================================
# Helper: retry wrapper
# =============================================================================

async def _with_retry(coro_fn, *args, **kwargs) -> Any:
    """
    Execute an async callable with up to 3 retry attempts.
    Backs off 0.5s → 1s → 2s between attempts.
    Re-raises on the final attempt.
    """
    last_exc: Exception | None = None
    for attempt, delay in enumerate([0, *_RETRY_DELAYS]):
        if attempt > 0:
            logger.warning("Booking API retry %d after %.1fs: %s", attempt, delay, last_exc)
            await asyncio.sleep(delay)
        try:
            return await coro_fn(*args, **kwargs)
        except RateLimitError:
            raise   # 429 — don't retry, propagate immediately
        except (httpx.TimeoutException, httpx.NetworkError, BookingAPIError) as exc:
            last_exc = exc
    raise last_exc  # type: ignore[misc]


# =============================================================================
# BookingClient
# =============================================================================

class BookingClient:
    """
    Async HTTP client for Booking.com RapidAPI.

    Usage (as async context manager):
        async with BookingClient() as client:
            dest = await client.search_destination("Paris")
    """

    def __init__(self) -> None:
        self._semaphore = asyncio.Semaphore(15)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "BookingClient":
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(_TIMEOUT),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            headers={
                "x-rapidapi-host": settings.rapidapi_host,
                "x-rapidapi-key": settings.rapidapi_key,
            },
        )
        return self

    async def __aexit__(self, *_) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Low-level request helper
    # ------------------------------------------------------------------

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a GET request and return the parsed JSON data dict."""
        assert self._client is not None, "BookingClient must be used as async context manager"

        # Strip None values — Booking API rejects unknown/null params
        clean_params = {k: v for k, v in params.items() if v is not None}

        async with self._semaphore:
            try:
                response = await self._client.get(f"{_BASE}/{path}", params=clean_params)
            except httpx.TimeoutException as exc:
                raise BookingAPIError(f"Timeout on {path}") from exc
            except httpx.NetworkError as exc:
                raise BookingAPIError(f"Network error on {path}") from exc

        if response.status_code == 429:
            raise RateLimitError("Rate limit exceeded (HTTP 429)")
        if response.status_code >= 500:
            raise BookingAPIError(
                f"Server error {response.status_code} on {path}",
                status_code=response.status_code,
            )

        try:
            body = response.json()
        except Exception as exc:
            raise BookingAPIError(f"Invalid JSON from {path}") from exc

        # Explicit API-level error (status: false)
        if body.get("status") is False:
            msg = body.get("message", "Unknown API error")
            if isinstance(msg, dict):
                msg = msg.get("message", str(msg))
            raise BookingAPIError(str(msg), status_code=response.status_code)

        # Soft rate-limit / error response without status field
        # e.g. {"message": "Too many requests"} returned as HTTP 200
        if "data" not in body and "status" not in body:
            msg = body.get("message", "Unexpected response (no data)")
            lower = msg.lower()
            if "too many" in lower or "rate limit" in lower or "quota" in lower:
                raise RateLimitError(f"Rate limit (soft): {msg}")
            raise BookingAPIError(msg, status_code=response.status_code)

        return body.get("data", body)

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def search_destination(self, query: str) -> DestinationResult:
        """
        Find the dest_id and search_type for a city/location query.
        Returns the first result of type "city" or the first result overall.
        """
        async def _call() -> DestinationResult:
            results = await self._get("searchDestination", {"query": query})
            if not results:
                raise DestinationNotFoundError(f"No destination found for '{query}'")

            # Prefer city-type result; fall back to first result
            items: list[dict] = results if isinstance(results, list) else [results]
            city_item = next((r for r in items if r.get("dest_type") == "city"), items[0])

            raw_dest_id = city_item.get("dest_id") or city_item.get("id") or city_item.get("dest_id_str", "")
            return DestinationResult(
                dest_id=str(raw_dest_id),
                search_type=city_item.get("search_type", "city"),
                name=city_item.get("name", query),
                country=city_item.get("country", ""),
                label=city_item.get("label", ""),
                latitude=city_item.get("latitude"),
                longitude=city_item.get("longitude"),
                nr_hotels=city_item.get("nr_hotels", 0),
            )

        return await _with_retry(_call)

    async def search_hotels(
        self,
        *,
        dest_ids: str,          # kept as dest_ids for API compat — maps to dest_id in request
        search_type: str,
        arrival_date: str,
        departure_date: str,
        adults: int = 2,
        children_age: str | None = None,   # comma-separated, e.g. "3,7"
        price_min: float | None = None,
        price_max: float | None = None,
        categories_filter: str | None = None,
        sort_by: str = "bayesian_review_score",
        page_number: int = 1,
        currency_code: str = "EUR",
    ) -> list[dict[str, Any]]:
        """
        Search hotels for given destination and dates.

        NOTE: The Booking.com API expects `dest_id` (singular) in the query params.
        Confirmed by direct httpx test — `dest_id=-1456928` returns status:True with hotels.
        """
        async def _call() -> list[dict[str, Any]]:
            params: dict[str, Any] = {
                "dest_id": dest_ids,         # singular — API uses dest_id
                "search_type": search_type,
                "arrival_date": arrival_date,
                "departure_date": departure_date,
                "adults": adults,
                "children_age": children_age,
                "price_min": price_min,
                "price_max": price_max,
                "categories_filter": categories_filter,
                "sort_by": sort_by,
                "page_number": page_number,
                "currency_code": currency_code,
                "room_qty": 1,
                "languagecode": "en-us",
            }
            data = await self._get("searchHotels", params)
            # Response may be a dict with "hotels" key or a list
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("hotels", data.get("result", []))
            return []

        return await _with_retry(_call)

    async def get_hotel_details(
        self,
        hotel_id: int,
        arrival: str,
        departure: str,
        adults: int = 2,
        children_age: str | None = None,
        currency: str = "EUR",
    ) -> dict[str, Any]:
        """Fetch detailed hotel information including price, location, facilities."""
        async def _call() -> dict[str, Any]:
            params: dict[str, Any] = {
                "hotel_id": str(hotel_id),
                "arrival_date": arrival,
                "departure_date": departure,
                "adults": adults,
                "children_age": children_age,
                "currency_code": currency,
                "room_qty": 1,
                "languagecode": "en-us",
            }
            return await self._get("getHotelDetails", params)

        return await _with_retry(_call)

    async def get_hotel_review_scores(self, hotel_id: int) -> dict[str, Any]:
        """
        Fetch category review scores broken down by guest type.
        Returns 7 categories × 9 guest types (solo, couple, family, business, group...).
        """
        async def _call() -> dict[str, Any]:
            return await self._get("getHotelReviewScores", {
                "hotel_id": str(hotel_id),
                "languagecode": "en-us",
            })

        return await _with_retry(_call)

    async def get_hotel_reviews(
        self,
        hotel_id: int,
        page: int = 1,
        sort: str = "sort_most_relevant",
    ) -> dict[str, Any]:
        """
        Fetch hotel reviews with pros/cons fields.
        Call twice (page=1, page=2) for 20 reviews per hotel.
        """
        async def _call() -> dict[str, Any]:
            return await self._get("getHotelReviews", {
                "hotel_id": str(hotel_id),
                "page_number": page,
                "sort_option_id": sort,
                "languagecode": "en-us",
            })

        return await _with_retry(_call)

    async def get_hotel_facilities(self, hotel_id: int) -> dict[str, Any]:
        """
        Fetch full facility list grouped by category with FREE/PAID info.
        Returns 60+ facilities across groups (General, Bathroom, Services, etc.).
        """
        async def _call() -> dict[str, Any]:
            return await self._get("getHotelFacilities", {
                "hotel_id": str(hotel_id),
                "languagecode": "en-us",
            })

        return await _with_retry(_call)

    async def get_hotel_photos(self, hotel_id: int) -> list[dict[str, Any]]:
        """
        Fetch hotel photos in multiple sizes.
        Returns 40+ photos with url_square1024, url_max500, url_max300.
        """
        async def _call() -> list[dict[str, Any]]:
            data = await self._get("getHotelPhotos", {
                "hotel_id": str(hotel_id),
                "languagecode": "en-us",
            })
            return data if isinstance(data, list) else []

        return await _with_retry(_call)

    # ------------------------------------------------------------------
    # High-level: parallel full data fetch for one hotel (Phase 3)
    # ------------------------------------------------------------------

    async def fetch_hotel_full_data(
        self,
        hotel_id: int,
        arrival: str,
        departure: str,
        adults: int = 2,
        children_age: str | None = None,
        currency: str = "EUR",
    ) -> HotelRawData:
        """
        Fetch all data for a single hotel in 5 parallel requests:
          1. getHotelDetails
          2. getHotelReviewScores
          3. getHotelReviews(page=1)
          4. getHotelReviews(page=2)   ← v3 addition
          5. getHotelFacilities

        Total: 5 calls per hotel, run via asyncio.gather.
        Semaphore is held inside each individual _get() call, not here,
        so all 5 can progress concurrently within the per-hotel gather.
        """
        details_task = self.get_hotel_details(
            hotel_id, arrival, departure, adults, children_age, currency
        )
        scores_task = self.get_hotel_review_scores(hotel_id)
        reviews_p1_task = self.get_hotel_reviews(hotel_id, page=1)
        reviews_p2_task = self.get_hotel_reviews(hotel_id, page=2)
        facilities_task = self.get_hotel_facilities(hotel_id)
        photos_task = self.get_hotel_photos(hotel_id)

        details, scores, reviews_p1, reviews_p2, facilities, hotel_photos = await asyncio.gather(
            details_task,
            scores_task,
            reviews_p1_task,
            reviews_p2_task,
            facilities_task,
            photos_task,
            return_exceptions=True,   # don't abort on partial failure
        )

        # --- Parse details ---
        raw_details: dict[str, Any] = details if isinstance(details, dict) else {}
        price_breakdown = raw_details.get("product_price_breakdown", {})
        price_per_night = (
            price_breakdown.get("gross_amount_per_night", {}).get("value", 0.0)
        )
        total_price = price_breakdown.get("gross_amount", {}).get("value", 0.0)
        raw_data_block = raw_details.get("rawData", {})

        # Checkin/checkout from rawData block
        checkin_from = raw_data_block.get("checkin", {}).get("fromTime", "")
        checkout_until = raw_data_block.get("checkout", {}).get("untilTime", "")

        # Property highlights
        highlights = [
            h.get("name", "")
            for h in raw_details.get("property_highlight_strip", [])
            if h.get("name")
        ]
        top_benefits = [
            b.get("translated_name", "")
            for b in raw_details.get("top_ufi_benefits", [])
            if b.get("translated_name")
        ]

        wifi_score_data = raw_details.get("wifi_review_score", {})
        wifi_score = wifi_score_data.get("rating") if isinstance(wifi_score_data, dict) else None

        # Free cancellation: check blocks
        free_cancel = False
        for block in raw_details.get("block", []):
            if block.get("refundable", 0):
                free_cancel = True
                break

        # --- Parse review scores ---
        review_scores_obj = ReviewScores()
        raw_scores = scores if isinstance(scores, dict) else {}
        if raw_scores:
            # Booking returns scores in various nested structures
            # Try common key patterns
            review_scores_obj.cleanliness = _extract_score(raw_scores, "hotel_clean", "cleanliness")
            review_scores_obj.comfort = _extract_score(raw_scores, "hotel_comfort", "comfort")
            review_scores_obj.location = _extract_score(raw_scores, "hotel_location", "location")
            review_scores_obj.staff = _extract_score(raw_scores, "hotel_staff", "staff")
            review_scores_obj.value = _extract_score(raw_scores, "hotel_value", "value")
            review_scores_obj.wifi = _extract_score(raw_scores, "hotel_wifi", "wifi")
            review_scores_obj.facilities = _extract_score(raw_scores, "hotel_facilities", "facilities")

            # Parse by-segment breakdown
            by_segment: dict[str, float] = {}
            for item in raw_scores.get("category_type", []):
                seg_name = item.get("customer_type", item.get("type", ""))
                seg_score = item.get("review_score", item.get("score"))
                if seg_name and seg_score is not None:
                    by_segment[seg_name] = float(seg_score)
            review_scores_obj.by_segment = by_segment

        review_score = float(raw_data_block.get("reviewScore", raw_details.get("review_score", 0.0)))
        review_count = int(raw_details.get("review_nr", raw_data_block.get("reviewCount", 0)))

        # --- Parse reviews (page 1 + page 2 combined) ---
        parsed_reviews: list[ReviewRaw] = []
        for page_data in [reviews_p1, reviews_p2]:
            if isinstance(page_data, Exception) or not isinstance(page_data, dict):
                continue
            result_list = page_data.get("result", [])
            for r in result_list:
                if not isinstance(r, dict):
                    continue
                author = r.get("author", {})
                parsed_reviews.append(ReviewRaw(
                    review_hash=r.get("review_hash", ""),
                    pros=r.get("pros", r.get("pros_translated", "")),
                    cons=r.get("cons", r.get("cons_translated", "")),
                    title=r.get("title", r.get("title_translated", "")),
                    hotelier_response=r.get("hotelier_response", ""),
                    author_type=author.get("type", ""),
                    average_score=r.get("average_score"),
                ))

        # --- Parse facilities ---
        parsed_facilities: list[FacilityItem] = []
        raw_facilities = facilities if isinstance(facilities, dict) else {}
        for fac in raw_facilities.get("facilities", []):
            if not isinstance(fac, dict):
                continue
            for instance in fac.get("instances", []):
                attrs = instance.get("attributes") or {}
                payment = attrs.get("paymentInfo") or {}
                parsed_facilities.append(FacilityItem(
                    id=fac.get("id", 0),
                    group_id=fac.get("groupId", 0),
                    title=instance.get("title", ""),
                    charge_mode=payment.get("chargeMode", "UNKNOWN_CHARGE_MODE"),
                ))

        # --- Extract photos: hotel-level first, room photos last ---
        photo_urls: list[str] = []
        seen_photos: set[str] = set()

        # Collect room photo IDs to sort them after hotel-level photos
        room_photo_ids: set[int] = set()
        rooms_data = raw_details.get("rooms", {})
        if isinstance(rooms_data, dict):
            for room in rooms_data.values():
                if not isinstance(room, dict):
                    continue
                for p in room.get("photos", []):
                    if isinstance(p, dict) and p.get("photo_id"):
                        room_photo_ids.add(int(p["photo_id"]))

        # Priority 1: hotel-level photos from getHotelPhotos
        # API returns {id, url} with "square1024"; convert to "max500"
        # Hotel-level photos (not in room_photo_ids) go first,
        # room photos from the gallery go second as fallback
        hotel_only_urls: list[str] = []
        room_gallery_urls: list[str] = []
        if not isinstance(hotel_photos, Exception) and isinstance(hotel_photos, list):
            for photo in hotel_photos:
                if not isinstance(photo, dict):
                    continue
                raw_url = photo.get("url") or ""
                if not raw_url:
                    continue
                url = raw_url.replace("/square1024/", "/max500/")
                if url in seen_photos:
                    continue
                seen_photos.add(url)
                photo_id = photo.get("id")
                if isinstance(photo_id, int) and photo_id in room_photo_ids:
                    room_gallery_urls.append(url)
                else:
                    hotel_only_urls.append(url)

        # Take hotel photos first, then room gallery photos (no limit)
        photo_urls.extend(hotel_only_urls)
        photo_urls.extend(room_gallery_urls)

        # Priority 2: room photos from getHotelDetails (deduplicated)
        if isinstance(rooms_data, dict):
            for room in rooms_data.values():
                if not isinstance(room, dict):
                    continue
                for photo in room.get("photos", []):
                    if not isinstance(photo, dict):
                        continue
                    url = (
                        photo.get("url_max750")
                        or photo.get("url_max300")
                        or photo.get("url_original")
                    )
                    if url and url not in seen_photos:
                        seen_photos.add(url)
                        photo_urls.append(url)

        return HotelRawData(
            hotel_id=hotel_id,
            details=raw_details,
            name=raw_details.get("hotel_name", raw_data_block.get("name", "")),
            url=raw_details.get("url", ""),
            latitude=raw_details.get("latitude"),
            longitude=raw_details.get("longitude"),
            address=raw_details.get("address", ""),
            city=raw_details.get("city", ""),
            district=raw_details.get("district"),
            distance_to_cc=float(raw_details.get("distance_to_cc", 0.0)),
            accommodation_type=raw_details.get("accommodation_type_name", ""),
            stars=int(raw_data_block.get("accuratePropertyClass", raw_details.get("qualityClass", 0))),
            is_sold_out=bool(raw_details.get("soldout", 0)),
            price_per_night=price_per_night,
            total_price=total_price,
            currency=currency,  # always use requested currency (API field may return local currency)
            breakfast_included=bool(raw_details.get("hotel_include_breakfast", 0)),
            checkin_from=checkin_from,
            checkout_until=checkout_until,
            chaincode=raw_details.get("chaincode"),
            property_highlights=highlights,
            top_benefits=top_benefits,
            wifi_score=wifi_score,
            free_cancellation=free_cancel,
            review_scores=review_scores_obj,
            review_score=review_score,
            review_count=review_count,
            reviews=parsed_reviews,
            facilities=parsed_facilities,
            photo_urls=photo_urls,
        )


# =============================================================================
# Helpers
# =============================================================================

def _extract_score(data: dict, *keys: str) -> float | None:
    """Try multiple key names to extract a numeric score from a dict."""
    for key in keys:
        val = data.get(key)
        if val is not None:
            # May be nested {"score": 8.5} or a flat value
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, dict):
                for sub_key in ("score", "value", "rating"):
                    sub = val.get(sub_key)
                    if sub is not None:
                        return float(sub)
    return None
