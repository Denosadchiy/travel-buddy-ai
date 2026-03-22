"""
Stage 4 — SSE Streaming tests.

Tests the POST /api/hotels/search/stream endpoint.

Run:
  pytest src/hotels/tests/test_streaming.py -v -s --no-cov
"""
import json

import pytest
import httpx
from fastapi.testclient import TestClient

from src.main import app


def _parse_sse_body(body: str) -> list[dict]:
    """Parse SSE response body into list of {event, data} dicts."""
    events = []
    current_event: dict = {}
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("event:"):
            current_event["event"] = line[len("event:"):].strip()
        elif line.startswith("data:"):
            raw = line[len("data:"):].strip()
            try:
                current_event["data"] = json.loads(raw)
            except json.JSONDecodeError:
                current_event["data"] = raw
        elif line == "" and current_event:
            events.append(current_event)
            current_event = {}
    if current_event:
        events.append(current_event)
    return events


def test_sse_stream_returns_events():
    """
    POST /api/hotels/search/stream → SSE with progress + result + done events.

    Uses TestClient with stream=True to collect all SSE output.
    """
    client = TestClient(app, raise_server_exceptions=False)

    with client.stream(
        "POST",
        "/api/hotels/search/stream",
        json={
            "city": "Rome",
            "check_in": "2026-08-01",
            "check_out": "2026-08-04",
            "adults": 2,
            "budget_max": 200.0,
            "currency": "EUR",
        },
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        body = response.read().decode()

    print(f"\nSSE body ({len(body)} chars):")
    # Print first 500 chars for debugging
    print(body[:500])

    events = _parse_sse_body(body)
    event_types = [e.get("event") for e in events]
    print(f"Event types: {event_types}")

    # Must have at least one progress event
    progress_events = [e for e in events if e.get("event") == "progress"]
    assert len(progress_events) >= 1, "No progress events in SSE stream"

    # Must have exactly one result or error event
    result_events = [e for e in events if e.get("event") == "result"]
    error_events = [e for e in events if e.get("event") == "error"]
    assert len(result_events) + len(error_events) == 1, (
        "Expected exactly 1 result or error event"
    )

    # Must end with done
    assert "done" in event_types, "SSE stream missing 'done' event"

    # If result was returned, validate its structure
    if result_events:
        result_data = result_events[0].get("data", {})
        assert "hotels" in result_data, "Result event missing 'hotels' key"
        print(f"Hotels in SSE result: {len(result_data['hotels'])}")

        if result_data["hotels"]:
            first = result_data["hotels"][0]
            assert "booking_url" in first
            assert "ai_score" in first


def test_sse_progress_events_have_required_fields():
    """Each progress event must have phase, message, and progress fields."""
    client = TestClient(app, raise_server_exceptions=False)

    with client.stream(
        "POST",
        "/api/hotels/search/stream",
        json={
            "city": "Paris",
            "check_in": "2026-09-01",
            "check_out": "2026-09-03",
            "adults": 2,
            "budget_max": 150.0,
            "currency": "EUR",
            "user_wishes": "Romantic boutique hotel",
        },
    ) as response:
        body = response.read().decode()

    events = _parse_sse_body(body)
    progress_events = [e for e in events if e.get("event") == "progress"]

    for event in progress_events:
        data = event.get("data", {})
        assert "phase" in data, f"Progress event missing 'phase': {data}"
        assert "message" in data, f"Progress event missing 'message': {data}"
        assert "progress" in data, f"Progress event missing 'progress': {data}"
        assert isinstance(data["phase"], int)
        assert isinstance(data["message"], str) and data["message"]
        assert 0.0 <= data["progress"] <= 1.0
        print(f"  Phase {data['phase']}: {data['message']} ({data['progress']:.0%})")


def test_sse_russian_progress_messages():
    """Russian user_wishes → progress messages in Russian (Cyrillic)."""
    client = TestClient(app, raise_server_exceptions=False)

    with client.stream(
        "POST",
        "/api/hotels/search/stream",
        json={
            "city": "Barcelona",
            "check_in": "2026-09-01",
            "check_out": "2026-09-04",
            "adults": 2,
            "budget_max": 180.0,
            "currency": "EUR",
            "user_wishes": "Тихий бутиковый отель в центре",
        },
    ) as response:
        body = response.read().decode()

    events = _parse_sse_body(body)
    progress_events = [e for e in events if e.get("event") == "progress"]

    if progress_events:
        first_msg = progress_events[0]["data"].get("message", "")
        print(f"\nFirst progress message: {first_msg}")
        # Check for Cyrillic characters in at least one message
        has_cyrillic = any(
            any("\u0400" <= c <= "\u04FF" for c in e["data"].get("message", ""))
            for e in progress_events
        )
        assert has_cyrillic, (
            f"Expected Cyrillic in progress messages for Russian input, "
            f"got: {[e['data'].get('message') for e in progress_events]}"
        )
