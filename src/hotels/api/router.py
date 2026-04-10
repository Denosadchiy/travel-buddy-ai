"""
FastAPI router for AI Hotel Picker endpoints.

  GET  /api/hotels/health                  — liveness check
  GET  /api/hotels/price-hints             — percentile-based budget presets for a city
  POST /api/hotels/search                  — full 7-phase pipeline (≤62s)
  POST /api/hotels/search/more             — pagination with session_id
  POST /api/hotels/search/stream           — SSE: progress + result_ready signal
  GET  /api/hotels/session/{id}/result     — fetch cached result by session_id
  POST /api/hotels/find                    — direct search by hotel name
  POST /api/hotels/explain                 — why NOT this hotel?
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from src.hotels.application.orchestrator import HotelSearchOrchestrator
from src.hotels.domain.schemas import (
    BudgetRange,
    HotelExplainRequest,
    HotelExplanationResponse,
    HotelFindRequest,
    HotelSearchRequest,
    HotelSearchResponse,
    PriceHintsResponse,
    SearchMoreRequest,
)
from src.hotels.infrastructure.booking_client import (
    BookingAPIError,
    BookingClient,
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
# Price hints — lightweight endpoint for dynamic budget presets
# ---------------------------------------------------------------------------

# In-memory cache: key = "city|currency" → (timestamp, PriceHintsResponse)
_price_hints_cache: dict[str, tuple[float, PriceHintsResponse]] = {}
_PRICE_HINTS_TTL = 86400  # 24 hours


def _compute_percentiles(prices: list[float]) -> PriceHintsResponse | None:
    """Compute economy/comfort/luxury percentile ranges from a list of prices."""
    if len(prices) < 3:
        return None
    prices.sort()
    n = len(prices)

    def _percentile(p: float) -> float:
        idx = p * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        frac = idx - lo
        return round(prices[lo] + frac * (prices[hi] - prices[lo]), 2)

    p10 = _percentile(0.10)
    p35 = _percentile(0.35)
    p65 = _percentile(0.65)
    p95 = _percentile(0.95)

    # Snap to nice round numbers (nearest 5)
    def _snap(v: float) -> float:
        return round(v / 5) * 5 or 5

    return [
        BudgetRange(label="Эконом", min=_snap(p10), max=_snap(p35)),
        BudgetRange(label="Комфорт", min=_snap(p35), max=_snap(p65)),
        BudgetRange(label="Люкс", min=_snap(p65), max=_snap(p95)),
    ]


@router.get("/price-hints", response_model=PriceHintsResponse)
async def price_hints(
    city: str = Query(..., min_length=1, description="City name, e.g. 'Paris'"),
    currency: str = Query("EUR", description="Currency code"),
    check_in: str = Query(..., description="YYYY-MM-DD"),
    check_out: str = Query(..., description="YYYY-MM-DD"),
) -> PriceHintsResponse:
    """
    Return percentile-based budget presets (economy/comfort/luxury) for a city.

    Fetches ~20 hotels from Booking.com, computes P10/P35/P65/P95 price
    percentiles, and caches the result for 24 hours per city+currency.
    """
    from fastapi import HTTPException

    cache_key = f"{city.lower().strip()}|{currency.upper()}"

    # Check cache
    if cache_key in _price_hints_cache:
        ts, cached_response = _price_hints_cache[cache_key]
        if time.time() - ts < _PRICE_HINTS_TTL:
            return cached_response

    try:
        async with BookingClient() as client:
            dest = await client.search_destination(city)
            hotels = await client.search_hotels(
                dest_ids=dest.dest_id,
                search_type=dest.search_type,
                arrival_date=check_in,
                departure_date=check_out,
                currency_code=currency.upper(),
                page_number=1,
            )
    except DestinationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RateLimitError:
        raise HTTPException(status_code=429, detail="Booking API rate limit exceeded")
    except BookingAPIError as exc:
        raise HTTPException(status_code=502, detail=f"Booking API error: {exc}")
    except Exception as exc:
        logger.error("price_hints unexpected error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

    # Extract per-night prices from search results
    prices: list[float] = []
    for h in hotels:
        price = (
            h.get("price_per_night")
            or h.get("min_total_price")
            or h.get("composite_price_breakdown", {}).get("gross_amount_per_night", {}).get("value")
        )
        if price and float(price) > 0:
            prices.append(float(price))

    if len(prices) < 3:
        raise HTTPException(
            status_code=404,
            detail=f"Not enough hotel prices found for '{city}' to compute hints",
        )

    presets = _compute_percentiles(prices)

    response = PriceHintsResponse(
        city=city,
        currency=currency.upper(),
        presets=presets,
        sample_size=len(prices),
    )

    _price_hints_cache[cache_key] = (time.time(), response)
    return response


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
async def search_hotels_stream(
    request: HotelSearchRequest,
    http_request: Request,
) -> StreamingResponse:
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
            except asyncio.CancelledError:
                logger.info("search_stream: task cancelled (client disconnected)")
            except Exception as exc:
                logger.error("search_stream error: %s", exc, exc_info=True)
                await queue.put({"type": "error", "status": 500, "message": "Internal server error"})
            finally:
                await queue.put(None)  # sentinel

        # Send an immediate keepalive the moment the SSE stream opens.
        # This ensures iOS URLSession receives at least one byte right after
        # the HTTP response headers, which resets its timeoutIntervalForRequest
        # timer. Without this, a Railway cold-start (30-60s) + 20s wait for
        # the first timed keepalive could exceed the 70s timeout on real devices.
        yield ": keep-alive\n\n"

        task = asyncio.create_task(run_search())

        keepalive_ticks = 0  # each tick = 1s; send keepalive every 20s of silence
        try:
            while True:
                # Poll with a short timeout so we can detect client disconnects
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=1.0)
                    keepalive_ticks = 0  # reset on any real event
                except asyncio.TimeoutError:
                    if await http_request.is_disconnected():
                        logger.info("search_stream: client disconnected, cancelling search task")
                        task.cancel()
                        return
                    # Send SSE keepalive comment every 20s of silence so that
                    # iOS URLSession resets its timeoutIntervalForRequest counter
                    # (without this, 70s of silence → connection killed on device).
                    keepalive_ticks += 1
                    if keepalive_ticks >= 20:
                        keepalive_ticks = 0
                        yield ": keep-alive\n\n"
                    continue

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
                    # Cache the full result in session store so the client
                    # can fetch it via GET /session/{id}/result.
                    # SSE only sends a lightweight result_ready signal (~100 bytes)
                    # instead of the full 30KB result JSON. This avoids CDN
                    # buffering issues (Fastly) that blocked large SSE events
                    # on real iOS devices, causing the 97% freeze.
                    result_obj: HotelSearchResponse = item["data"]
                    sid = result_obj.session_id
                    _orchestrator._sessions.update_session(
                        sid, cached_result=result_obj,
                    )
                    ready_data = json.dumps({"session_id": sid})
                    yield f"event: result_ready\ndata: {ready_data}\n\n"
                    yield f"event: done\ndata: {{}}\n\n"
                    break

                elif item["type"] == "error":
                    err = json.dumps({"message": item["message"], "status": item.get("status", 500)})
                    yield f"event: error\ndata: {err}\n\n"
                    yield f"event: done\ndata: {{}}\n\n"
                    break
        finally:
            if not task.done():
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            # Disable proxy/CDN buffering — critical for Railway (Fastly CDN).
            # Without these, the CDN buffers the large result event (~30KB)
            # and iOS URLSession never receives it, causing the app to freeze
            # at 97% progress on real devices.
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Session result endpoint (used by iOS after SSE result_ready signal)
# ---------------------------------------------------------------------------

@router.get("/session/{session_id}/result", response_model=HotelSearchResponse)
async def get_session_result(session_id: str) -> HotelSearchResponse:
    """
    Retrieve cached search result by session_id.

    The SSE stream sends a lightweight `result_ready` event with the session_id.
    The client then fetches the full result (~30KB) via this regular HTTP GET,
    which is reliably delivered through CDN without buffering issues.
    """
    from fastapi import HTTPException

    session = _orchestrator._sessions.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    cached = session.get("cached_result")
    if cached is None:
        raise HTTPException(status_code=404, detail="Result not yet available")

    return cached


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
