"""
Place details endpoints backed by Google Places API.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from typing import List, Optional

from pydantic import BaseModel

from src.domain.schemas import PlaceDetailsResponse, PlacePhotoResponse, PlaceReviewResponse
from src.infrastructure.google_place_details import fetch_place_details, fetch_place_photo, search_places
from src.infrastructure.database import get_db
from src.infrastructure.models import POIModel

router = APIRouter()


class PlaceSearchResultResponse(BaseModel):
    place_id: str
    name: str
    address: Optional[str] = None
    rating: Optional[float] = None
    photo_references: List[str] = []


@router.get("/places/search", response_model=List[PlaceSearchResultResponse])
async def search_places_endpoint(
    query: str = Query(..., description="Hotel name + city, e.g. 'Hôtel du Marais Paris'"),
    type: str = Query(default="lodging", description="Google place type"),
):
    try:
        results = await search_places(query=query, place_type=type)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return [
        PlaceSearchResultResponse(
            place_id=r.place_id,
            name=r.name,
            address=r.address,
            rating=r.rating,
            photo_references=r.photo_references,
        )
        for r in results
    ]


@router.get("/places/{place_id}/details", response_model=PlaceDetailsResponse)
async def get_place_details(place_id: str, db: AsyncSession = Depends(get_db)):
    resolved_place_id = place_id
    try:
        poi_uuid = UUID(place_id)
        result = await db.execute(select(POIModel).where(POIModel.id == poi_uuid))
        poi = result.scalars().first()
        if not poi or not poi.external_id:
            raise HTTPException(status_code=404, detail="Place not found for provided POI id.")
        resolved_place_id = poi.external_id
    except ValueError:
        # Not a UUID, treat as Google place_id
        pass

    try:
        details = await fetch_place_details(resolved_place_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return PlaceDetailsResponse(
        place_id=details.place_id,
        name=details.name,
        types=details.types,
        rating=details.rating,
        reviews_count=details.reviews_count,
        price_level=details.price_level,
        is_open_now=details.is_open_now,
        opening_hours=details.opening_hours,
        next_open_time=details.next_open_time,
        next_close_time=details.next_close_time,
        address=details.address,
        latitude=details.latitude,
        longitude=details.longitude,
        website=details.website,
        phone=details.phone,
        google_maps_url=details.google_maps_url,
        editorial_summary=details.editorial_summary,
        photos=[
            PlacePhotoResponse(
                id=photo.photo_reference,
                width=photo.width,
                height=photo.height,
                attribution=photo.html_attributions,
            )
            for photo in details.photos
        ],
        reservable=details.reservable,
        serves_breakfast=details.serves_breakfast,
        serves_lunch=details.serves_lunch,
        serves_dinner=details.serves_dinner,
        serves_beer=details.serves_beer,
        serves_wine=details.serves_wine,
        serves_vegetarian_food=details.serves_vegetarian_food,
        takeout=details.takeout,
        delivery=details.delivery,
        dine_in=details.dine_in,
        curbside_pickup=details.curbside_pickup,
        wheelchair_accessible_entrance=details.wheelchair_accessible_entrance,
        reviews=[
            PlaceReviewResponse(
                author_name=review.author_name,
                rating=review.rating,
                text=review.text,
                relative_time=review.relative_time_description,
            )
            for review in details.reviews
        ],
    )


@router.get("/places/photos/{photo_reference}")
async def get_place_photo(photo_reference: str, max_width: int = Query(default=1200, ge=200, le=2400)):
    try:
        content = await fetch_place_photo(photo_reference, max_width=max_width)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return Response(content=content, media_type="image/jpeg")
