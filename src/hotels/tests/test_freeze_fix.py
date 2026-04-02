"""
Tests proving the hotel search freeze bug is fixed.

Covers:
  - Orchestrator enforces _DEADLINE via asyncio.wait_for
  - SSE endpoint cancels its background task when client disconnects
  - BookingClient honours per-request timeout (15 s)
  - Retry loop does not block indefinitely on repeated timeouts
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.hotels.application.orchestrator import HotelSearchOrchestrator, _DEADLINE
from src.hotels.domain.schemas import HotelSearchRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request() -> HotelSearchRequest:
    return HotelSearchRequest(
        city="Barcelona",
        check_in="2026-06-01",
        check_out="2026-06-04",
        adults=2,
        user_wishes="quiet hotel near beach",
    )


# ---------------------------------------------------------------------------
# Test 1 — Orchestrator deadline is enforced
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_deadline_raises_timeout():
    """_run_pipeline that sleeps forever must be cancelled within _DEADLINE seconds."""
    orchestrator = HotelSearchOrchestrator()

    async def _hang(*args, **kwargs):
        await asyncio.sleep(9999)

    with patch.object(orchestrator, "_run_pipeline", side_effect=_hang):
        with pytest.raises(asyncio.TimeoutError):
            # Use a tiny artificial deadline to keep the test fast
            with patch("src.hotels.application.orchestrator._DEADLINE", 0.1):
                await orchestrator.search(_make_request())


@pytest.mark.asyncio
async def test_orchestrator_deadline_value_is_62():
    """Sanity check: deadline constant must stay at 62 seconds."""
    assert _DEADLINE == 62.0


# ---------------------------------------------------------------------------
# Test 2 — Orchestrator cancel propagates cleanly
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_cancel_propagates():
    """Cancelling the search() coroutine must not leak tasks."""
    orchestrator = HotelSearchOrchestrator()

    async def _hang(*args, **kwargs):
        await asyncio.sleep(9999)

    with patch.object(orchestrator, "_run_pipeline", side_effect=_hang):
        task = asyncio.create_task(orchestrator.search(_make_request()))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


# ---------------------------------------------------------------------------
# Test 3 — SSE endpoint cancels task on disconnect
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sse_task_cancelled_on_client_disconnect():
    """
    When the HTTP client disconnects mid-stream, the background search task
    must be cancelled rather than allowed to run to completion.
    """
    from src.hotels.api.router import search_hotels_stream

    cancelled_events: list[bool] = []

    async def _hang_search(req, progress_callback=None):
        try:
            await asyncio.sleep(9999)
        except asyncio.CancelledError:
            cancelled_events.append(True)
            raise

    # Patch the orchestrator used by the router
    import src.hotels.api.router as router_module
    mock_orch = MagicMock()
    mock_orch.search = AsyncMock(side_effect=_hang_search)

    # Simulate a disconnected HTTP request
    mock_http_request = MagicMock()
    call_count = 0

    async def _is_disconnected():
        nonlocal call_count
        call_count += 1
        # Report disconnected after the first poll
        return call_count > 1

    mock_http_request.is_disconnected = _is_disconnected

    search_req = _make_request()

    with patch.object(router_module, "_orchestrator", mock_orch):
        response = await search_hotels_stream(search_req, mock_http_request)
        # Drain the generator
        async for _ in response.body_iterator:
            pass

    # Task must have been cancelled
    assert cancelled_events, "Background search task was not cancelled on disconnect"


# ---------------------------------------------------------------------------
# Test 4 — BookingClient timeout is 15 seconds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_booking_client_timeout_is_15s():
    """BookingClient must configure httpx timeout to settings value (15 s by default)."""
    from src.hotels.infrastructure.booking_client import _TIMEOUT
    from src.config import settings

    assert _TIMEOUT == settings.hotel_search_timeout_seconds
    # Default must be ≤ 20s so that Phase 3 can't hang for minutes per request
    assert _TIMEOUT <= 20, f"Per-request timeout too high: {_TIMEOUT}s"


# ---------------------------------------------------------------------------
# Test 5 — Retry loop re-raises after 3 attempts, does not hang
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_reraises_after_max_attempts():
    """_with_retry must stop after 3 retries and raise, not loop indefinitely."""
    import httpx
    from src.hotels.infrastructure.booking_client import _with_retry

    call_count = 0

    async def _always_timeout():
        nonlocal call_count
        call_count += 1
        raise httpx.TimeoutException("simulated timeout")

    # Patch sleep so test runs instantly
    with patch("src.hotels.infrastructure.booking_client.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(httpx.TimeoutException):
            await _with_retry(_always_timeout)

    # 1 initial attempt + 3 retries = 4 total
    assert call_count == 4, f"Expected 4 attempts, got {call_count}"


# ---------------------------------------------------------------------------
# Test 6 — search() returns TimeoutError (not hang) when pipeline is slow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_does_not_hang_on_slow_pipeline():
    """
    search() must raise TimeoutError within deadline + small buffer,
    never hang indefinitely.
    """
    orchestrator = HotelSearchOrchestrator()

    async def _slow(*args, **kwargs):
        await asyncio.sleep(5)

    artificial_deadline = 0.2  # 200 ms for fast tests

    with patch.object(orchestrator, "_run_pipeline", side_effect=_slow):
        with patch("src.hotels.application.orchestrator._DEADLINE", artificial_deadline):
            start = asyncio.get_event_loop().time()
            with pytest.raises(asyncio.TimeoutError):
                await orchestrator.search(_make_request())
            elapsed = asyncio.get_event_loop().time() - start

    # Must have timed out well within 1 second
    assert elapsed < 1.0, f"search() took {elapsed:.2f}s — deadline not enforced"
