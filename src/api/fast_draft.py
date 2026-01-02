"""
Fast Draft API endpoint - optimized for p95 latency under 20 seconds.
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database import get_db
from src.application.fast_draft_planner import FastDraftPlanner
from src.domain.schemas import ItineraryResponse


router = APIRouter(prefix="/trips", tags=["fast-draft"])


@router.post(
    "/{trip_id}/fast-draft",
    response_model=ItineraryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate fast draft itinerary",
    description="Generate a draft itinerary with p95 latency under 20 seconds. "
                "Uses LLM with 15s timeout, falls back to template on timeout/error. "
                "Returns draft with placeholder POIs (no route optimization). "
                "Use ?debug=1 for extended trace with full generator params, provider calls, and ranking details."
)
async def generate_fast_draft(
    trip_id: UUID,
    db: AsyncSession = Depends(get_db),
    debug: int = Query(default=0, ge=0, le=1, description="Enable debug trace (0 or 1)"),
) -> ItineraryResponse:
    """
    Generate fast draft itinerary.

    This endpoint is optimized for speed over completeness:
    - 15-second hard timeout on LLM call
    - Template-based fallback if LLM times out or fails
    - Returns placeholder POIs (not verified from database)
    - No travel time calculation or route optimization
    - No critique/validation step

    Use this endpoint for initial loading animation, then optionally
    call /plan for full enrichment in the background.

    Args:
        trip_id: UUID of the trip to plan
        debug: 1 to enable extended trace with generator params, provider calls, ranking details

    Returns:
        ItineraryResponse with draft itinerary (and optional extended trace if debug=1)

    Raises:
        HTTPException 404 if trip not found
        HTTPException 500 if planning fails (should be rare due to fallback)
    """
    planner = FastDraftPlanner()

    try:
        enable_extended_trace = debug == 1
        itinerary = await planner.generate_fast_draft(
            trip_id,
            db,
            include_trace=True,  # always include basic trace
            enable_extended_trace=enable_extended_trace,  # extended trace only if debug=1
        )
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
                detail=f"Failed to generate draft: {error_msg}"
            )

    except Exception as e:
        # This should be rare due to template fallback
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during draft generation: {str(e)}"
        )
