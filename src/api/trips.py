"""
Trips API endpoints for creating and managing trip specifications.
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database import get_db
from src.application.trip_spec import TripSpecCollector
from src.domain.schemas import TripCreateRequest, TripUpdateRequest, TripResponse


router = APIRouter(prefix="/trips", tags=["trips"])


@router.post(
    "",
    response_model=TripResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new trip",
    description="Create a new trip from form inputs. Returns the trip with a unique ID."
)
async def create_trip(
    request: TripCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> TripResponse:
    """
    Create a new trip from form data.

    The mobile app sends structured trip parameters (city, dates, travelers, etc.)
    and the backend creates a TripSpec and stores it in the database.

    Returns:
        TripResponse with the created trip data including trip_id
    """
    collector = TripSpecCollector()
    trip_response = await collector.create_trip(request, db)
    return trip_response


@router.get(
    "/{trip_id}",
    response_model=TripResponse,
    summary="Get trip by ID",
    description="Fetch an existing trip's current TripSpec state."
)
async def get_trip(
    trip_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> TripResponse:
    """
    Get an existing trip by ID.

    Args:
        trip_id: UUID of the trip to fetch

    Returns:
        TripResponse with current trip data

    Raises:
        HTTPException 404 if trip not found
    """
    collector = TripSpecCollector()
    trip_response = await collector.get_trip(trip_id, db)

    if not trip_response:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trip with ID {trip_id} not found"
        )

    return trip_response


@router.patch(
    "/{trip_id}",
    response_model=TripResponse,
    summary="Update trip",
    description="Update an existing trip's TripSpec with new form data (partial updates)."
)
async def update_trip(
    trip_id: UUID,
    request: TripUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> TripResponse:
    """
    Update an existing trip with new form data.

    Accepts partial updates - only fields provided in the request will be updated.
    Useful when the user modifies trip parameters via the form or chat.

    Args:
        trip_id: UUID of the trip to update
        request: Partial trip data to update

    Returns:
        Updated TripResponse

    Raises:
        HTTPException 404 if trip not found
    """
    collector = TripSpecCollector()
    trip_response = await collector.update_trip(trip_id, request, db)

    if not trip_response:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trip with ID {trip_id} not found"
        )

    return trip_response
