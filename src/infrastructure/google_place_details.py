"""
Google Places Details API client and helpers.
Uses the existing Google Maps API key and HTTP integration.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

from src.config import settings


@dataclass
class PlaceReview:
    author_name: str
    rating: float
    text: str
    relative_time_description: str


@dataclass
class PlacePhoto:
    photo_reference: str
    width: Optional[int]
    height: Optional[int]
    html_attributions: list[str]


@dataclass
class PlaceDetails:
    place_id: str
    name: str
    types: list[str]
    rating: Optional[float]
    reviews_count: Optional[int]
    price_level: Optional[int]
    is_open_now: Optional[bool]
    opening_hours: Optional[list[str]]
    next_open_time: Optional[str]
    next_close_time: Optional[str]
    address: Optional[str]
    latitude: float
    longitude: float
    website: Optional[str]
    phone: Optional[str]
    google_maps_url: Optional[str]
    editorial_summary: Optional[str]
    photos: list[PlacePhoto]
    reservable: Optional[bool]
    serves_breakfast: Optional[bool]
    serves_lunch: Optional[bool]
    serves_dinner: Optional[bool]
    serves_beer: Optional[bool]
    serves_wine: Optional[bool]
    serves_vegetarian_food: Optional[bool]
    takeout: Optional[bool]
    delivery: Optional[bool]
    dine_in: Optional[bool]
    curbside_pickup: Optional[bool]
    wheelchair_accessible_entrance: Optional[bool]
    reviews: list[PlaceReview]


def _format_time(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if len(value) == 4:
        return f"{value[:2]}:{value[2:]}"
    return value


def _google_day_index(date: datetime) -> int:
    # Google: 0 = Sunday, 1 = Monday, ..., 6 = Saturday
    return (date.weekday() + 1) % 7


def _extract_next_times(opening_hours: Optional[dict], utc_offset_minutes: Optional[int]) -> tuple[Optional[str], Optional[str]]:
    if not opening_hours:
        return None, None

    periods = opening_hours.get("periods")
    if not periods:
        return None, None

    offset = timedelta(minutes=utc_offset_minutes or 0)
    now_local = datetime.utcnow() + offset
    today_idx = _google_day_index(now_local)

    next_open = None
    next_close = None
    for period in periods:
        open_info = period.get("open", {})
        close_info = period.get("close", {})
        if open_info.get("day") == today_idx:
            next_close = _format_time(close_info.get("time"))
            break

    if next_close:
        return None, next_close

    # If closed now, find the next open period
    for period in periods:
        open_info = period.get("open", {})
        day = open_info.get("day")
        if day is None:
            continue
        if day == today_idx or (day - today_idx) % 7 >= 0:
            next_open = _format_time(open_info.get("time"))
            if next_open:
                break

    return next_open, None


def _parse_reviews(reviews: Optional[list[dict]]) -> list[PlaceReview]:
    results = []
    for review in reviews or []:
        text = review.get("text")
        if not text:
            continue
        results.append(
            PlaceReview(
                author_name=review.get("author_name", ""),
                rating=review.get("rating", 0.0),
                text=text,
                relative_time_description=review.get("relative_time_description", ""),
            )
        )
    return results


def _parse_photos(photos: Optional[list[dict]]) -> list[PlacePhoto]:
    results = []
    for photo in photos or []:
        reference = photo.get("photo_reference")
        if not reference:
            continue
        results.append(
            PlacePhoto(
                photo_reference=reference,
                width=photo.get("width"),
                height=photo.get("height"),
                html_attributions=photo.get("html_attributions", []),
            )
        )
    return results


async def fetch_place_details(place_id: str) -> PlaceDetails:
    if not settings.google_maps_api_key:
        raise RuntimeError("Google Maps API key is not configured")

    params = {
        "place_id": place_id,
        "key": settings.google_maps_api_key,
        "language": settings.google_places_default_language,
        "fields": ",".join([
            "place_id",
            "name",
            "types",
            "rating",
            "user_ratings_total",
            "price_level",
            "opening_hours",
            "formatted_address",
            "geometry",
            "photos",
            "website",
            "formatted_phone_number",
            "international_phone_number",
            "url",
            "editorial_summary",
            "reviews",
            "utc_offset",
            "reservable",
            "serves_breakfast",
            "serves_lunch",
            "serves_dinner",
            "serves_beer",
            "serves_wine",
            "serves_vegetarian_food",
            "takeout",
            "delivery",
            "dine_in",
            "curbside_pickup",
            "wheelchair_accessible_entrance",
        ]),
    }

    print(f"🌐 Google Place Details API: Fetching place_id={place_id}")
    async with httpx.AsyncClient(timeout=settings.google_places_timeout_seconds) as client:
        try:
            response = await client.get(settings.google_place_details_base_url, params=params)
            response.raise_for_status()
            payload = response.json()
            print(f"✅ Google Place Details API: Success for place_id={place_id}")
        except httpx.HTTPStatusError as e:
            print(f"❌ Google Place Details API: HTTP {e.response.status_code} for place_id={place_id}")
            raise
        except Exception as e:
            print(f"❌ Google Place Details API: Failed for place_id={place_id} - {type(e).__name__}: {e}")
            raise

    status = payload.get("status")
    if status != "OK":
        print(f"❌ Google Place Details API: Status {status} for place_id={place_id}")
        raise RuntimeError(f"Google Places Details error: {status}")

    result: dict[str, Any] = payload.get("result", {})
    geometry = result.get("geometry", {})
    location = geometry.get("location", {})
    opening_hours = result.get("opening_hours") or {}
    utc_offset = result.get("utc_offset")
    next_open, next_close = _extract_next_times(opening_hours, utc_offset)

    return PlaceDetails(
        place_id=result.get("place_id", place_id),
        name=result.get("name", ""),
        types=result.get("types", []),
        rating=result.get("rating"),
        reviews_count=result.get("user_ratings_total"),
        price_level=result.get("price_level"),
        is_open_now=opening_hours.get("open_now"),
        opening_hours=opening_hours.get("weekday_text"),
        next_open_time=next_open,
        next_close_time=next_close,
        address=result.get("formatted_address"),
        latitude=location.get("lat", 0.0),
        longitude=location.get("lng", 0.0),
        website=result.get("website"),
        phone=result.get("international_phone_number") or result.get("formatted_phone_number"),
        google_maps_url=result.get("url"),
        editorial_summary=(result.get("editorial_summary") or {}).get("overview"),
        photos=_parse_photos(result.get("photos")),
        reservable=result.get("reservable"),
        serves_breakfast=result.get("serves_breakfast"),
        serves_lunch=result.get("serves_lunch"),
        serves_dinner=result.get("serves_dinner"),
        serves_beer=result.get("serves_beer"),
        serves_wine=result.get("serves_wine"),
        serves_vegetarian_food=result.get("serves_vegetarian_food"),
        takeout=result.get("takeout"),
        delivery=result.get("delivery"),
        dine_in=result.get("dine_in"),
        curbside_pickup=result.get("curbside_pickup"),
        wheelchair_accessible_entrance=result.get("wheelchair_accessible_entrance"),
        reviews=_parse_reviews(result.get("reviews")),
    )


async def fetch_place_photo(photo_reference: str, max_width: int = 1200) -> bytes:
    if not settings.google_maps_api_key:
        raise RuntimeError("Google Maps API key is not configured")

    params = {
        "photoreference": photo_reference,
        "maxwidth": max_width,
        "key": settings.google_maps_api_key,
    }

    print(f"🌐 Google Place Photo API: Fetching photo_reference={photo_reference[:20]}...")
    async with httpx.AsyncClient(timeout=settings.google_places_timeout_seconds, follow_redirects=True) as client:
        try:
            response = await client.get(settings.google_place_photo_base_url, params=params)
            response.raise_for_status()
            print(f"✅ Google Place Photo API: Success ({len(response.content)} bytes)")
            return response.content
        except httpx.HTTPStatusError as e:
            print(f"❌ Google Place Photo API: HTTP {e.response.status_code}")
            raise
        except Exception as e:
            print(f"❌ Google Place Photo API: Failed - {type(e).__name__}: {e}")
            raise
