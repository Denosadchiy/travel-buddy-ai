"""
Tests for trip chat functionality.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from httpx import AsyncClient

from src.main import app
from src.application.trip_chat import TripChatAssistant
from src.infrastructure.database import AsyncSessionLocal
from src.infrastructure.cache import InMemoryChatCache


class MockLLMClient:
    """Mock LLM client for testing."""

    def __init__(self, response: dict):
        self.response = response

    async def generate_structured(self, prompt: str, system_prompt: str = None, max_tokens: int = 512):
        """Return mocked structured response."""
        return self.response


@pytest.fixture
def mock_llm_response_basic():
    """Basic mock LLM response."""
    return {
        "assistant_message": "Got it! I'll focus on techno clubs and vegetarian food.",
        "trip_updates": {
            "interests": ["techno", "nightlife", "food"],
            "additional_preferences": {
                "avoid": ["museums"],
                "dietary": ["vegetarian"],
                "music": "techno"
            }
        }
    }


@pytest.fixture
def mock_llm_response_no_updates():
    """Mock LLM response with no trip updates."""
    return {
        "assistant_message": "I understand. I'll keep that in mind!",
        "trip_updates": {}
    }


@pytest.mark.asyncio
async def test_trip_chat_assistant_with_updates(mock_llm_response_basic):
    """Test TripChatAssistant with trip updates from LLM."""
    # Create a trip first
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

    # Test chat assistant directly
    async with AsyncSessionLocal() as db:
        mock_llm = MockLLMClient(mock_llm_response_basic)
        mock_cache = InMemoryChatCache()

        assistant = TripChatAssistant(llm_client=mock_llm, cache=mock_cache)

        response = await assistant.handle_chat_message(
            trip_id=trip_id,
            user_message="We hate museums and love techno nightlife",
            db=db,
            use_cache=False,
        )

    # Verify response
    assert response.assistant_message == "Got it! I'll focus on techno clubs and vegetarian food."
    assert "techno" in response.trip.interests
    assert "nightlife" in response.trip.interests
    assert response.trip.additional_preferences["avoid"] == ["museums"]
    assert response.trip.additional_preferences["music"] == "techno"


@pytest.mark.asyncio
async def test_trip_chat_assistant_no_updates(mock_llm_response_no_updates):
    """Test TripChatAssistant with no trip updates."""
    # Create a trip
    async with AsyncClient(app=app, base_url="http://test") as client:
        create_response = await client.post(
            "/api/trips",
            json={
                "city": "Tokyo",
                "start_date": "2024-10-01",
                "end_date": "2024-10-05",
                "interests": ["food", "culture"]
            }
        )
        trip_id = create_response.json()["id"]

    # Test chat with no updates
    async with AsyncSessionLocal() as db:
        mock_llm = MockLLMClient(mock_llm_response_no_updates)
        assistant = TripChatAssistant(llm_client=mock_llm, cache=InMemoryChatCache())

        response = await assistant.handle_chat_message(
            trip_id=trip_id,
            user_message="Thank you!",
            db=db,
            use_cache=False,
        )

    # Trip should remain unchanged
    assert response.assistant_message == "I understand. I'll keep that in mind!"
    assert response.trip.interests == ["food", "culture"]


@pytest.mark.asyncio
async def test_trip_chat_endpoint_success():
    """Test POST /api/trips/{trip_id}/chat endpoint."""
    # Create a trip
    async with AsyncClient(app=app, base_url="http://test") as client:
        create_response = await client.post(
            "/api/trips",
            json={
                "city": "Paris",
                "start_date": "2024-06-15",
                "end_date": "2024-06-20",
            }
        )
        trip_id = create_response.json()["id"]

        # Mock the LLM client at the module level
        from src.application import trip_chat
        original_factory = trip_chat.get_trip_chat_llm_client

        mock_response = {
            "assistant_message": "Perfect! I'll plan around vegetarian options.",
            "trip_updates": {
                "interests": ["food"],
                "additional_preferences": {
                    "dietary": ["vegetarian"]
                }
            }
        }

        trip_chat.get_trip_chat_llm_client = lambda: MockLLMClient(mock_response)

        try:
            # Send chat message
            chat_response = await client.post(
                f"/api/trips/{trip_id}/chat",
                json={
                    "message": "We prefer vegetarian food"
                }
            )

            assert chat_response.status_code == 200
            data = chat_response.json()

            assert "assistant_message" in data
            assert "trip" in data
            assert data["trip"]["id"] == trip_id
            assert "food" in data["trip"]["interests"]
            assert data["trip"]["additional_preferences"]["dietary"] == ["vegetarian"]

        finally:
            # Restore original factory
            trip_chat.get_trip_chat_llm_client = original_factory


@pytest.mark.asyncio
async def test_trip_chat_endpoint_trip_not_found():
    """Test chat endpoint with non-existent trip."""
    fake_trip_id = str(uuid4())

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            f"/api/trips/{fake_trip_id}/chat",
            json={
                "message": "Hello"
            }
        )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_trip_chat_cache():
    """Test that chat responses are cached."""
    # Create a trip
    async with AsyncClient(app=app, base_url="http://test") as client:
        create_response = await client.post(
            "/api/trips",
            json={
                "city": "Barcelona",
                "start_date": "2024-08-01",
                "end_date": "2024-08-05",
            }
        )
        trip_id = create_response.json()["id"]

    mock_response = {
        "assistant_message": "Understood!",
        "trip_updates": {}
    }

    async with AsyncSessionLocal() as db:
        mock_llm = MockLLMClient(mock_response)
        cache = InMemoryChatCache()
        assistant = TripChatAssistant(llm_client=mock_llm, cache=cache)

        # First call - should call LLM
        response1 = await assistant.handle_chat_message(
            trip_id=trip_id,
            user_message="We love food",
            db=db,
            use_cache=True,
        )

        # Second call with same message - should hit cache
        response2 = await assistant.handle_chat_message(
            trip_id=trip_id,
            user_message="We love food",  # Exact same message
            db=db,
            use_cache=True,
        )

        # Both should return same assistant message
        assert response1.assistant_message == response2.assistant_message

        # Cache should have one entry
        cache_key = cache.generate_cache_key(str(trip_id), "We love food")
        cached_value = cache.get(cache_key)
        assert cached_value is not None
        assert cached_value["assistant_message"] == "Understood!"


@pytest.mark.asyncio
async def test_trip_chat_merges_additional_preferences():
    """Test that additional_preferences are merged, not replaced."""
    # Create a trip with existing preferences
    async with AsyncClient(app=app, base_url="http://test") as client:
        create_response = await client.post(
            "/api/trips",
            json={
                "city": "Amsterdam",
                "start_date": "2024-07-01",
                "end_date": "2024-07-05",
            }
        )
        trip_id = create_response.json()["id"]

        # First update: add dietary preference
        update_response = await client.patch(
            f"/api/trips/{trip_id}",
            json={
                "additional_preferences": {
                    "dietary": ["vegan"]
                }
            }
        )
        assert update_response.status_code == 200

    # Now chat to add music preference
    mock_response = {
        "assistant_message": "Got it, techno it is!",
        "trip_updates": {
            "additional_preferences": {
                "music": "techno"
            }
        }
    }

    async with AsyncSessionLocal() as db:
        mock_llm = MockLLMClient(mock_response)
        assistant = TripChatAssistant(llm_client=mock_llm, cache=InMemoryChatCache())

        response = await assistant.handle_chat_message(
            trip_id=trip_id,
            user_message="We love techno music",
            db=db,
            use_cache=False,
        )

    # Both preferences should be present (merged)
    assert response.trip.additional_preferences["dietary"] == ["vegan"]
    assert response.trip.additional_preferences["music"] == "techno"


@pytest.mark.asyncio
async def test_chat_request_validation():
    """Test chat request validation (empty message, too long, etc.)."""
    # Create a trip
    async with AsyncClient(app=app, base_url="http://test") as client:
        create_response = await client.post(
            "/api/trips",
            json={
                "city": "Rome",
                "start_date": "2024-09-01",
                "end_date": "2024-09-05",
            }
        )
        trip_id = create_response.json()["id"]

        # Empty message should fail validation
        response = await client.post(
            f"/api/trips/{trip_id}/chat",
            json={
                "message": ""
            }
        )
        assert response.status_code == 422

        # Message too long should fail
        long_message = "a" * 1001
        response = await client.post(
            f"/api/trips/{trip_id}/chat",
            json={
                "message": long_message
            }
        )
        assert response.status_code == 422
