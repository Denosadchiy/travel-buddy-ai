"""
Itinerary API endpoints for full trip planning.
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database import get_db
from src.application.trip_planner import TripPlannerOrchestrator
from src.domain.schemas import ItineraryResponse


router = APIRouter(prefix="/trips", tags=["itinerary"])


@router.post(
    "/{trip_id}/plan",
    response_model=ItineraryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate complete trip plan",
    description="Execute full planning pipeline: macro plan → POI selection → route optimization."
)
async def plan_trip(
    trip_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ItineraryResponse:
    """
    Generate complete trip plan.

    This endpoint orchestrates the full planning pipeline:
    1. Verifies trip exists
    2. Generates macro plan if missing (LLM-based day skeletons)
    3. Generates POI plan if missing (deterministic candidate selection)
    4. Generates final itinerary (deterministic POI selection + travel times)

    The endpoint is idempotent - it will reuse existing macro/POI plans
    if they already exist, and only regenerate the final itinerary.

    Args:
        trip_id: UUID of the trip to plan

    Returns:
        ItineraryResponse with complete itinerary

    Raises:
        HTTPException 404 if trip not found
        HTTPException 500 if planning fails
    """
    orchestrator = TripPlannerOrchestrator()

    try:
        itinerary = await orchestrator.plan_trip(trip_id, db)
        return itinerary

    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate trip plan: {error_msg}"
            )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during planning: {str(e)}"
        )


@router.get(
    "/{trip_id}/itinerary",
    response_model=ItineraryResponse,
    summary="Get trip itinerary",
    description="Fetch the stored itinerary for a trip."
)
async def get_itinerary(
    trip_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ItineraryResponse:
    """
    Get stored itinerary for a trip.

    Returns the previously generated complete itinerary if it exists.

    Args:
        trip_id: UUID of the trip

    Returns:
        ItineraryResponse with complete itinerary

    Raises:
        HTTPException 404 if trip or itinerary not found
    """
    orchestrator = TripPlannerOrchestrator()

    try:
        itinerary = await orchestrator.get_itinerary(trip_id, db)
        return itinerary

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )
