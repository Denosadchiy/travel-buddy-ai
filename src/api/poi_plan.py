"""
POI Planning API endpoints for selecting venue candidates.
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database import get_db
from src.application.poi_planner import POIPlanner
from src.domain.schemas import POIPlanResponse


router = APIRouter(prefix="/trips", tags=["poi-planning"])


@router.post(
    "/{trip_id}/poi-plan",
    response_model=POIPlanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate POI plan for trip",
    description="Select candidate POIs for each block in the macro plan."
)
async def create_poi_plan(
    trip_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> POIPlanResponse:
    """
    Generate POI plan (venue candidates) for a trip.

    This step:
    1. Loads the trip's macro plan (day skeletons)
    2. For each block that needs venues (meals, activities, nightlife):
       - Searches internal POI database
       - Optionally queries external APIs for more options
       - Ranks candidates by relevance
    3. Stores candidate list per block
    4. Returns structured plan for route optimization

    Args:
        trip_id: UUID of the trip to plan

    Returns:
        POIPlanResponse with candidate POIs per block

    Raises:
        HTTPException 404 if trip not found or macro plan missing
        HTTPException 500 if planning fails
    """
    planner = POIPlanner()

    try:
        poi_plan = await planner.generate_poi_plan(trip_id, db)
        return poi_plan

    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower() or "no macro plan" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate POI plan: {error_msg}"
            )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during POI planning: {str(e)}"
        )


@router.get(
    "/{trip_id}/poi-plan",
    response_model=POIPlanResponse,
    summary="Get POI plan for trip",
    description="Fetch the stored POI plan (venue candidates) for a trip."
)
async def get_poi_plan(
    trip_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> POIPlanResponse:
    """
    Get stored POI plan for a trip.

    Returns the previously generated venue candidates if they exist.

    Args:
        trip_id: UUID of the trip

    Returns:
        POIPlanResponse with candidate POIs per block

    Raises:
        HTTPException 404 if trip or POI plan not found
    """
    planner = POIPlanner()
    poi_plan = await planner.get_poi_plan(trip_id, db)

    if not poi_plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No POI plan found for trip {trip_id}"
        )

    return poi_plan
