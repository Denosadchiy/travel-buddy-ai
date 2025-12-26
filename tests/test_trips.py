"""
Tests for trip creation and update endpoints.
"""
import pytest
from datetime import date
from httpx import AsyncClient
from sqlalchemy import select

from src.main import app
from src.infrastructure.database import AsyncSessionLocal
from src.infrastructure.models import TripModel


@pytest.fixture
async def test_db():
    """Provide a database session for tests."""
    async with AsyncSessionLocal() as session:
        yield session


@pytest.mark.asyncio
async def test_create_trip_minimal():
    """Test creating a trip with minimal required fields."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/trips",
            json={
                "city": "Paris",
                "start_date": "2024-06-15",
                "end_date": "2024-06-20",
            }
        )

    assert response.status_code == 201
    data = response.json()

    # Verify response structure
    assert "id" in data
    assert data["city"] == "Paris"
    assert data["start_date"] == "2024-06-15"
    assert data["end_date"] == "2024-06-20"
    assert data["num_travelers"] == 1  # default
    assert data["pace"] == "medium"  # default
    assert data["budget"] == "medium"  # default
    assert data["interests"] == []  # default
    assert data["hotel_location"] is None
    assert data["additional_preferences"] == {}

    # Verify daily routine defaults
    assert "daily_routine" in data
    assert data["daily_routine"]["wake_time"] == "08:00:00"
    assert data["daily_routine"]["sleep_time"] == "23:00:00"

    # Verify timestamps
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_create_trip_full():
    """Test creating a trip with all fields specified."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/trips",
            json={
                "city": "Tokyo",
                "start_date": "2024-07-01",
                "end_date": "2024-07-10",
                "num_travelers": 3,
                "pace": "fast",
                "budget": "high",
                "interests": ["food", "culture", "nightlife"],
                "daily_routine": {
                    "wake_time": "07:00:00",
                    "sleep_time": "22:00:00",
                    "breakfast_window": ["07:30:00", "09:00:00"],
                    "lunch_window": ["12:00:00", "13:30:00"],
                    "dinner_window": ["18:30:00", "20:30:00"]
                },
                "hotel_location": "Shibuya district, Tokyo"
            }
        )

    assert response.status_code == 201
    data = response.json()

    assert data["city"] == "Tokyo"
    assert data["num_travelers"] == 3
    assert data["pace"] == "fast"
    assert data["budget"] == "high"
    assert data["interests"] == ["food", "culture", "nightlife"]
    assert data["hotel_location"] == "Shibuya district, Tokyo"

    # Verify custom daily routine
    assert data["daily_routine"]["wake_time"] == "07:00:00"
    assert data["daily_routine"]["sleep_time"] == "22:00:00"
    assert data["daily_routine"]["breakfast_window"] == ["07:30:00", "09:00:00"]


@pytest.mark.asyncio
async def test_get_trip():
    """Test retrieving a trip by ID."""
    # First create a trip
    async with AsyncClient(app=app, base_url="http://test") as client:
        create_response = await client.post(
            "/api/trips",
            json={
                "city": "Barcelona",
                "start_date": "2024-08-01",
                "end_date": "2024-08-05",
            }
        )
        assert create_response.status_code == 201
        trip_id = create_response.json()["id"]

        # Now fetch it
        get_response = await client.get(f"/api/trips/{trip_id}")

    assert get_response.status_code == 200
    data = get_response.json()
    assert data["id"] == trip_id
    assert data["city"] == "Barcelona"


@pytest.mark.asyncio
async def test_get_trip_not_found():
    """Test retrieving a non-existent trip returns 404."""
    fake_id = "550e8400-e29b-41d4-a716-446655440000"

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(f"/api/trips/{fake_id}")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_trip_partial():
    """Test updating a trip with partial data."""
    # Create a trip
    async with AsyncClient(app=app, base_url="http://test") as client:
        create_response = await client.post(
            "/api/trips",
            json={
                "city": "Paris",
                "start_date": "2024-06-15",
                "end_date": "2024-06-20",
                "pace": "slow",
                "budget": "low",
            }
        )
        trip_id = create_response.json()["id"]

        # Update only some fields
        update_response = await client.patch(
            f"/api/trips/{trip_id}",
            json={
                "pace": "fast",
                "interests": ["food", "nightlife", "techno parties"],
            }
        )

    assert update_response.status_code == 200
    data = update_response.json()

    # Updated fields
    assert data["pace"] == "fast"
    assert data["interests"] == ["food", "nightlife", "techno parties"]

    # Unchanged fields
    assert data["city"] == "Paris"
    assert data["budget"] == "low"
    assert data["start_date"] == "2024-06-15"


@pytest.mark.asyncio
async def test_update_trip_with_preferences():
    """Test updating a trip with additional preferences (from chat)."""
    # Create a trip
    async with AsyncClient(app=app, base_url="http://test") as client:
        create_response = await client.post(
            "/api/trips",
            json={
                "city": "Berlin",
                "start_date": "2024-09-01",
                "end_date": "2024-09-05",
            }
        )
        trip_id = create_response.json()["id"]

        # Update with additional preferences (simulating chat context)
        update_response = await client.patch(
            f"/api/trips/{trip_id}",
            json={
                "additional_preferences": {
                    "note": "We hate museums",
                    "music_preference": "techno",
                    "dietary_restrictions": ["vegetarian"]
                }
            }
        )

    assert update_response.status_code == 200
    data = update_response.json()

    assert data["additional_preferences"]["note"] == "We hate museums"
    assert data["additional_preferences"]["music_preference"] == "techno"
    assert "vegetarian" in data["additional_preferences"]["dietary_restrictions"]


@pytest.mark.asyncio
async def test_update_trip_daily_routine():
    """Test updating daily routine preferences."""
    # Create a trip
    async with AsyncClient(app=app, base_url="http://test") as client:
        create_response = await client.post(
            "/api/trips",
            json={
                "city": "Rome",
                "start_date": "2024-10-01",
                "end_date": "2024-10-07",
            }
        )
        trip_id = create_response.json()["id"]

        # Update daily routine
        update_response = await client.patch(
            f"/api/trips/{trip_id}",
            json={
                "daily_routine": {
                    "wake_time": "06:00:00",
                    "dinner_window": ["20:00:00", "22:30:00"]
                }
            }
        )

    assert update_response.status_code == 200
    data = update_response.json()

    # Updated fields
    assert data["daily_routine"]["wake_time"] == "06:00:00"
    assert data["daily_routine"]["dinner_window"] == ["20:00:00", "22:30:00"]

    # Unchanged fields (preserved from defaults)
    assert data["daily_routine"]["sleep_time"] == "23:00:00"
    assert data["daily_routine"]["breakfast_window"] == ["08:00:00", "10:00:00"]


@pytest.mark.asyncio
async def test_update_trip_not_found():
    """Test updating a non-existent trip returns 404."""
    fake_id = "550e8400-e29b-41d4-a716-446655440000"

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.patch(
            f"/api/trips/{fake_id}",
            json={"pace": "fast"}
        )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_trip_persists_in_database():
    """Test that created trip is actually stored in the database."""
    # Create a trip via API
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/trips",
            json={
                "city": "Amsterdam",
                "start_date": "2024-11-01",
                "end_date": "2024-11-05",
                "interests": ["art", "cycling"]
            }
        )
        trip_id = response.json()["id"]

    # Verify it's in the database
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TripModel).where(TripModel.city == "Amsterdam")
        )
        trip_model = result.scalars().first()

    assert trip_model is not None
    assert str(trip_model.id) == trip_id
    assert trip_model.city == "Amsterdam"
    assert trip_model.interests == ["art", "cycling"]
