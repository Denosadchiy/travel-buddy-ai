"""
Tests for health check endpoint.
"""
import pytest
from httpx import AsyncClient
from src.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    """Test the health check endpoint returns expected response."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert data["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_root_endpoint():
    """Test the root endpoint returns API information."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Trip Planning API"
    assert data["status"] == "running"
    assert "version" in data
