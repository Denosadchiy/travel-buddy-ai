"""
Saved Trips API endpoints for bookmarking trips.
All endpoints require authentication (Bearer token).
"""
from uuid import UUID
from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, Field

from src.infrastructure.database import get_db
from src.infrastructure.models import SavedTripModel, TripModel, ItineraryModel
from src.auth.dependencies import get_current_user
from src.auth.models import UserModel
from src.domain.schemas import ItineraryDay


router = APIRouter(prefix="/saved_trips", tags=["saved_trips"])


# --- Request/Response DTOs ---

class SaveTripRequest(BaseModel):
    """Request to save a trip."""
    trip_id: str = Field(description="ID of the trip to save (UUID string)")
    city_name: str = Field(min_length=1, max_length=100)
    start_date: str = Field(description="Date in YYYY-MM-DD format")
    end_date: str = Field(description="Date in YYYY-MM-DD format")
    hero_image_url: Optional[str] = Field(default=None, max_length=2000)
    route_snapshot: Optional[dict] = Field(default=None, description="Optional itinerary snapshot")


class SavedTripResponse(BaseModel):
    """Single saved trip card."""
    id: UUID
    trip_id: UUID
    city_name: str
    start_date: date
    end_date: date
    hero_image_url: Optional[str]
    already_saved: bool = Field(default=False, description="True if trip was already saved before")

    class Config:
        from_attributes = True


class SavedTripsListResponse(BaseModel):
    """List of saved trips."""
    trips: list[SavedTripResponse]
    total: int


class SavedTripDetailResponse(BaseModel):
    """Detailed information about a saved trip including itinerary."""
    id: UUID
    trip_id: UUID
    city_name: str
    start_date: date
    end_date: date
    hero_image_url: Optional[str]
    num_travelers: int
    itinerary: Optional[list[ItineraryDay]] = Field(default=None, description="Full itinerary if available")
    saved_at: str = Field(description="When this trip was saved (ISO 8601)")

    class Config:
        from_attributes = True


# --- Endpoints ---

@router.post(
    "",
    response_model=SavedTripResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save a trip",
    description="Save a trip to user's bookmarks. Returns existing record if already saved."
)
async def save_trip(
    request: SaveTripRequest,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_user),
) -> SavedTripResponse:
    """
    Save a trip to user's bookmarks.

    - If trip already saved by this user, returns existing record with already_saved=true
    - Validates date range (end_date >= start_date)
    - Requires authentication
    """
    # Parse and validate UUID
    try:
        trip_uuid = UUID(request.trip_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid trip_id format. Must be a valid UUID."
        )

    # Parse and validate dates
    try:
        start_date_obj = date.fromisoformat(request.start_date)
        end_date_obj = date.fromisoformat(request.end_date)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Use YYYY-MM-DD format."
        )

    # Validate date range
    if end_date_obj < start_date_obj:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be >= start_date"
        )

    # Check if already saved
    result = await db.execute(
        select(SavedTripModel).where(
            and_(
                SavedTripModel.user_id == user.id,
                SavedTripModel.trip_id == trip_uuid,
            )
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        return SavedTripResponse(
            id=existing.id,
            trip_id=existing.trip_id,
            city_name=existing.city_name,
            start_date=existing.start_date,
            end_date=existing.end_date,
            hero_image_url=existing.hero_image_url,
            already_saved=True,
        )

    # Create new saved trip
    saved_trip = SavedTripModel(
        user_id=user.id,
        trip_id=trip_uuid,
        city_name=request.city_name,
        start_date=start_date_obj,
        end_date=end_date_obj,
        hero_image_url=request.hero_image_url,
        route_snapshot=request.route_snapshot,
    )
    db.add(saved_trip)

    try:
        await db.commit()
        await db.refresh(saved_trip)
    except IntegrityError:
        await db.rollback()
        # Race condition: someone else saved it concurrently
        result = await db.execute(
            select(SavedTripModel).where(
                and_(
                    SavedTripModel.user_id == user.id,
                    SavedTripModel.trip_id == trip_uuid,
                )
            )
        )
        existing = result.scalar_one()
        return SavedTripResponse(
            id=existing.id,
            trip_id=existing.trip_id,
            city_name=existing.city_name,
            start_date=existing.start_date,
            end_date=existing.end_date,
            hero_image_url=existing.hero_image_url,
            already_saved=True,
        )

    return SavedTripResponse(
        id=saved_trip.id,
        trip_id=saved_trip.trip_id,
        city_name=saved_trip.city_name,
        start_date=saved_trip.start_date,
        end_date=saved_trip.end_date,
        hero_image_url=saved_trip.hero_image_url,
        already_saved=False,
    )


@router.get(
    "",
    response_model=SavedTripsListResponse,
    summary="Get saved trips",
    description="Get user's saved trips, sorted by start_date ASC (nearest first)."
)
async def get_saved_trips(
    limit: Optional[int] = Query(default=None, ge=1, le=100, description="Max trips to return"),
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_user),
) -> SavedTripsListResponse:
    """
    Get user's saved trips.

    - Sorted by start_date ASC (nearest trip first)
    - Optional limit parameter
    - Requires authentication
    """
    # Build query
    query = (
        select(SavedTripModel)
        .where(SavedTripModel.user_id == user.id)
        .order_by(SavedTripModel.start_date.asc())
    )

    if limit:
        query = query.limit(limit)

    result = await db.execute(query)
    saved_trips = result.scalars().all()

    # Get total count
    count_result = await db.execute(
        select(SavedTripModel).where(SavedTripModel.user_id == user.id)
    )
    total = len(count_result.scalars().all())

    trips = [
        SavedTripResponse(
            id=st.id,
            trip_id=st.trip_id,
            city_name=st.city_name,
            start_date=st.start_date,
            end_date=st.end_date,
            hero_image_url=st.hero_image_url,
            already_saved=False,
        )
        for st in saved_trips
    ]

    return SavedTripsListResponse(trips=trips, total=total)


@router.get(
    "/{saved_trip_id}",
    response_model=SavedTripResponse,
    summary="Get saved trip by ID",
    description="Get a specific saved trip by its ID."
)
async def get_saved_trip(
    saved_trip_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_user),
) -> SavedTripResponse:
    """Get a specific saved trip by ID."""
    result = await db.execute(
        select(SavedTripModel).where(
            and_(
                SavedTripModel.id == saved_trip_id,
                SavedTripModel.user_id == user.id,
            )
        )
    )
    saved_trip = result.scalar_one_or_none()

    if not saved_trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved trip not found"
        )

    return SavedTripResponse(
        id=saved_trip.id,
        trip_id=saved_trip.trip_id,
        city_name=saved_trip.city_name,
        start_date=saved_trip.start_date,
        end_date=saved_trip.end_date,
        hero_image_url=saved_trip.hero_image_url,
        already_saved=False,
    )


@router.get(
    "/{saved_trip_id}/detail",
    response_model=SavedTripDetailResponse,
    summary="Get saved trip with full itinerary",
    description="Get complete details of a saved trip including the full day-by-day itinerary."
)
async def get_saved_trip_detail(
    saved_trip_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_user),
) -> SavedTripDetailResponse:
    """
    Get detailed information about a saved trip including full itinerary.

    This endpoint returns:
    - Basic trip information (city, dates, hero image)
    - Number of travelers
    - Complete day-by-day itinerary with POIs and timing
    - When the trip was saved

    Returns 404 if:
    - Saved trip not found
    - Trip not owned by current user
    - Original trip was deleted
    """
    # Get saved trip
    result = await db.execute(
        select(SavedTripModel).where(
            and_(
                SavedTripModel.id == saved_trip_id,
                SavedTripModel.user_id == user.id,
            )
        )
    )
    saved_trip = result.scalar_one_or_none()

    if not saved_trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved trip not found"
        )

    # Get original trip details
    trip_result = await db.execute(
        select(TripModel).where(TripModel.id == saved_trip.trip_id)
    )
    trip = trip_result.scalar_one_or_none()

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Original trip not found. It may have been deleted."
        )

    # Get itinerary
    itinerary_result = await db.execute(
        select(ItineraryModel).where(ItineraryModel.trip_id == saved_trip.trip_id)
    )
    itinerary_model = itinerary_result.scalar_one_or_none()

    # Parse itinerary days if available
    itinerary_days = None
    if itinerary_model and itinerary_model.days:
        try:
            itinerary_days = [ItineraryDay(**day) for day in itinerary_model.days]
        except Exception as e:
            print(f"⚠️ Failed to parse itinerary: {e}")
            # If parsing fails, we still return the trip but without itinerary

    return SavedTripDetailResponse(
        id=saved_trip.id,
        trip_id=saved_trip.trip_id,
        city_name=saved_trip.city_name,
        start_date=saved_trip.start_date,
        end_date=saved_trip.end_date,
        hero_image_url=saved_trip.hero_image_url,
        num_travelers=trip.num_travelers,
        itinerary=itinerary_days,
        saved_at=saved_trip.created_at.isoformat(),
    )


@router.delete(
    "/{saved_trip_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete saved trip",
    description="Remove a trip from user's bookmarks."
)
async def delete_saved_trip(
    saved_trip_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_user),
) -> None:
    """Delete a saved trip."""
    result = await db.execute(
        select(SavedTripModel).where(
            and_(
                SavedTripModel.id == saved_trip_id,
                SavedTripModel.user_id == user.id,
            )
        )
    )
    saved_trip = result.scalar_one_or_none()

    if not saved_trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved trip not found"
        )

    await db.delete(saved_trip)
    await db.commit()


@router.get(
    "/check/{trip_id}",
    response_model=SavedTripResponse,
    summary="Check if trip is saved",
    description="Check if a specific trip is already saved by the user."
)
async def check_trip_saved(
    trip_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: UserModel = Depends(get_current_user),
) -> SavedTripResponse:
    """Check if a trip is saved and return its info."""
    result = await db.execute(
        select(SavedTripModel).where(
            and_(
                SavedTripModel.trip_id == trip_id,
                SavedTripModel.user_id == user.id,
            )
        )
    )
    saved_trip = result.scalar_one_or_none()

    if not saved_trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not saved"
        )

    return SavedTripResponse(
        id=saved_trip.id,
        trip_id=saved_trip.trip_id,
        city_name=saved_trip.city_name,
        start_date=saved_trip.start_date,
        end_date=saved_trip.end_date,
        hero_image_url=saved_trip.hero_image_url,
        already_saved=True,
    )
