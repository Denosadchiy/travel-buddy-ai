"""
FastAPI router for AI Hotel Picker endpoints.

  GET  /api/hotels/health          — liveness check
  POST /api/hotels/search          — full 7-phase pipeline (≤62s)
  POST /api/hotels/search/more     — pagination with session_id
  POST /api/hotels/search/stream   — SSE: progress events + final result
  POST /api/hotels/find            — direct search by hotel name
  POST /api/hotels/explain         — why NOT this hotel?
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.hotels.application.orchestrator import HotelSearchOrchestrator
from src.hotels.domain.schemas import (
    HotelExplainRequest,
    HotelExplanationResponse,
    HotelFindRequest,
    HotelSearchRequest,
    HotelSearchResponse,
    SearchMoreRequest,
)
from src.hotels.infrastructure.booking_client import (
    BookingAPIError,
    DestinationNotFoundError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hotels", tags=["hotels"])

# Single orchestrator instance — shared session store across all requests
_orchestrator = HotelSearchOrchestrator()


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@router.get("/health")
async def health() -> dict:
    """Liveness check for the hotels module."""
    return {"status": "ok", "module": "hotels"}


# ---------------------------------------------------------------------------
# Main search endpoints
# ---------------------------------------------------------------------------

@router.post("/search", response_model=HotelSearchResponse)
async def search_hotels(request: HotelSearchRequest) -> HotelSearchResponse:
    """
    Full AI hotel search pipeline (≤62s).
    Returns top-10 hotels + notable excluded + session_id for pagination.
    """
    try:
        return await _orchestrator.search(request)
    except DestinationNotFoundError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=str(exc))
    except RateLimitError:
        from fastapi import HTTPException
        raise HTTPException(status_code=429, detail="Booking API rate limit exceeded. Please retry in a moment.")
    except BookingAPIError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail=f"Booking API error: {exc}")
    except asyncio.TimeoutError:
        from fastapi import HTTPException
        raise HTTPException(status_code=504, detail="Search timed out. Please try again.")
    except Exception as exc:
        from fastapi import HTTPException
        logger.error("search_hotels unexpected error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/search/more", response_model=HotelSearchResponse)
async def search_more(request: SearchMoreRequest) -> HotelSearchResponse:
    """
    Pagination: return next batch of hotels from a previous search session.
    Requires session_id from a prior /search response.
    """
    try:
        return await _orchestrator.search_more(request.session_id)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        from fastapi import HTTPException
        logger.error("search_more unexpected error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# SSE streaming endpoint
# ---------------------------------------------------------------------------

@router.post("/search/stream")
async def search_hotels_stream(request: HotelSearchRequest) -> StreamingResponse:
    """
    Full AI hotel search with Server-Sent Events progress updates.

    Events emitted:
      event: progress  data: {"phase": N, "message": "...", "progress": 0.0-1.0}
      event: result    data: {HotelSearchResponse JSON}
      event: error     data: {"message": "...", "status": N}
      event: done      data: {}
    """
    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()

        async def on_progress(phase: int, message: str, progress: float) -> None:
            await queue.put({
                "type": "progress",
                "phase": phase,
                "message": message,
                "progress": progress,
            })

        async def run_search() -> None:
            try:
                result = await _orchestrator.search(request, progress_callback=on_progress)
                await queue.put({"type": "result", "data": result})
            except DestinationNotFoundError as exc:
                await queue.put({"type": "error", "status": 404, "message": str(exc)})
            except RateLimitError:
                await queue.put({"type": "error", "status": 429, "message": "Rate limit exceeded"})
            except Exception as exc:
                logger.error("search_stream error: %s", exc, exc_info=True)
                await queue.put({"type": "error", "status": 500, "message": "Internal server error"})
            finally:
                await queue.put(None)  # sentinel

        task = asyncio.create_task(run_search())

        try:
            while True:
                item = await queue.get()
                if item is None:
                    break

                if item["type"] == "progress":
                    data = json.dumps({
                        "phase": item["phase"],
                        "message": item["message"],
                        "progress": item["progress"],
                    })
                    yield f"event: progress\ndata: {data}\n\n"

                elif item["type"] == "result":
                    yield f"event: result\ndata: {item['data'].model_dump_json()}\n\n"
                    yield f"event: done\ndata: {{}}\n\n"
                    break

                elif item["type"] == "error":
                    err = json.dumps({"message": item["message"], "status": item.get("status", 500)})
                    yield f"event: error\ndata: {err}\n\n"
                    yield f"event: done\ndata: {{}}\n\n"
                    break
        finally:
            await task

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Find + Explain endpoints
# ---------------------------------------------------------------------------

@router.post("/find", response_model=HotelSearchResponse)
async def find_hotel(request: HotelFindRequest) -> HotelSearchResponse:
    """
    Find a specific hotel by name with full AI analysis.
    Returns 1 hotel result with complete review and AI insights.
    """
    try:
        return await _orchestrator.find_hotel(request)
    except DestinationNotFoundError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=str(exc))
    except BookingAPIError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail=f"Booking API error: {exc}")
    except Exception as exc:
        from fastapi import HTTPException
        logger.error("find_hotel unexpected error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/explain", response_model=HotelExplanationResponse)
async def explain_hotel(request: HotelExplainRequest) -> HotelExplanationResponse:
    """
    Explain why a specific hotel did not appear in the top-10.
    Requires session_id from a prior /search response.
    """
    try:
        return await _orchestrator.explain_hotel(request)
    except Exception as exc:
        from fastapi import HTTPException
        logger.error("explain_hotel unexpected error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
