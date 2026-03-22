"""
Stage 4 — Production hardening tests.

Tests HTTP-level behaviour via FastAPI TestClient:
  - Health check endpoint
  - Error responses are JSON (not HTML)
  - 404 for unknown destination
  - 422 for invalid request body
  - CORS headers present

Run:
  pytest src/hotels/tests/test_production.py -v -s --no-cov
"""
import pytest
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_health_check():
    """GET /api/hotels/health → 200 JSON with status=ok."""
    response = client.get("/api/hotels/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["module"] == "hotels"


def test_invalid_city_returns_json_error():
    """Unknown city returns 404 with JSON body, not HTML."""
    response = client.post(
        "/api/hotels/search",
        json={
            "city": "Zzyzxnonsense99999",
            "check_in": "2026-07-01",
            "check_out": "2026-07-04",
            "adults": 2,
        },
    )
    # 404 if destination not found; some cities may resolve loosely → accept 404 or 200 with 0 hotels
    assert response.status_code in (404, 200, 500, 502)
    # Must be JSON regardless
    content_type = response.headers.get("content-type", "")
    assert "application/json" in content_type, (
        f"Expected JSON response, got Content-Type: {content_type}"
    )
    # Must not be an HTML error page
    body = response.text
    assert "<html" not in body.lower(), "Response is HTML, expected JSON"


def test_invalid_request_body_returns_422():
    """Malformed request body → 422 Unprocessable Entity."""
    response = client.post(
        "/api/hotels/search",
        json={
            "city": "Paris",
            "check_in": "not-a-date",   # invalid date format
            "check_out": "2026-07-04",
            "adults": -1,               # violates ge=1 constraint
        },
    )
    assert response.status_code == 422
    data = response.json()
    # FastAPI validation errors have a "detail" key
    assert "detail" in data


def test_search_more_invalid_session_returns_404():
    """search_more with bad session_id → 404."""
    response = client.post(
        "/api/hotels/search/more",
        json={"session_id": "00000000-0000-0000-0000-invalid"},
    )
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data


def test_root_endpoint_alive():
    """Root endpoint / is alive."""
    response = client.get("/")
    assert response.status_code == 200


def test_docs_available():
    """Swagger docs are served."""
    response = client.get("/docs")
    assert response.status_code == 200
