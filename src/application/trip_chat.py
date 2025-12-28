"""
Trip Chat Assistant service.
Handles natural language chat messages and updates TripSpec via LLM.
"""
from uuid import UUID
from typing import Optional
import json

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.domain.schemas import TripChatLLMResponse, TripChatResponse, TripUpdateRequest
from src.application.trip_spec import TripSpecCollector
from src.infrastructure.llm_client import LLMClient, get_trip_chat_llm_client
from src.infrastructure.cache import ChatCache, get_chat_cache


class TripChatAssistant:
    """
    Service for handling trip-related chat messages.
    Uses LLM to interpret user messages and update TripSpec.
    """

    # System prompt for Trip Chat Mode (Russian language)
    SYSTEM_PROMPT = """Ты — дружелюбный помощник по планированию путешествий. Твоя задача:
1. Понять предпочтения, ограничения и пожелания пользователя о поездке
2. Ответить коротким, дружелюбным сообщением на русском языке (1-2 предложения)
3. Извлечь структурированные обновления для спецификации поездки

Пользователь планирует поездку и может сказать что-то вроде:
- Предпочтения: "Мы любим техно музыку", "Предпочитаем вегетарианскую еду"
- Ограничения: "Мы не любим музеи", "Избегайте туристических мест"
- Изменения расписания: "Хотим поспать подольше", "Предпочитаем поздние ужины"

Ты ДОЛЖЕН отвечать валидным JSON в точно таком формате:
{
  "assistant_message": "Твой дружелюбный ответ на русском языке",
  "trip_updates": {
    "interests": ["список", "интересов"],
    "additional_preferences": {
      "любой_ключ": "любое_значение"
    }
  }
}

Правила для trip_updates:
- Включай только поля, которые нужно обновить на основе сообщения пользователя
- interests: список интересов/предпочтений (еда, культура, ночная жизнь, техно и т.д.)
- additional_preferences: произвольный словарь для других предпочтений
- НЕ включай поля city, dates, num_travelers, если они явно не изменились
- Если сообщение не требует обновлений, установи trip_updates в {}

ВАЖНО: Поле assistant_message ВСЕГДА должно быть на русском языке!
Будь дружелюбным, кратким и подтверждай понимание пожеланий пользователя."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        cache: Optional[ChatCache] = None,
    ):
        """
        Initialize Trip Chat Assistant.

        Args:
            llm_client: LLM client (defaults to factory function)
            cache: Chat cache (defaults to global instance)
        """
        self.llm_client = llm_client or get_trip_chat_llm_client()
        self.cache = cache or get_chat_cache()
        self.trip_spec_collector = TripSpecCollector()

    def _build_user_prompt(self, trip_context: str, user_message: str) -> str:
        """Build the user prompt with trip context."""
        return f"""Текущая поездка:
{trip_context}

Сообщение пользователя: {user_message}

Ответь только JSON."""

    def _safe_apply_trip_updates(self, trip_updates: dict) -> TripUpdateRequest:
        """
        Safely convert LLM trip_updates dict to TripUpdateRequest.
        Only allows updating specific allowed fields.
        """
        allowed_updates = {}

        # Simple field mappings
        if "interests" in trip_updates:
            allowed_updates["interests"] = trip_updates["interests"]

        if "pace" in trip_updates:
            allowed_updates["pace"] = trip_updates["pace"]

        if "budget" in trip_updates:
            allowed_updates["budget"] = trip_updates["budget"]

        # Additional preferences (merge with existing)
        if "additional_preferences" in trip_updates:
            allowed_updates["additional_preferences"] = trip_updates["additional_preferences"]

        # Daily routine updates (if any)
        if "daily_routine" in trip_updates:
            allowed_updates["daily_routine"] = trip_updates["daily_routine"]

        return TripUpdateRequest(**allowed_updates)

    async def handle_chat_message(
        self,
        trip_id: UUID,
        user_message: str,
        db: AsyncSession,
        use_cache: bool = True,
    ) -> TripChatResponse:
        """
        Handle a chat message for a trip.

        Args:
            trip_id: Trip UUID
            user_message: User's natural language message
            db: Database session
            use_cache: Whether to use cache (default True)

        Returns:
            TripChatResponse with assistant message and updated trip

        Raises:
            ValueError: If trip not found or LLM response invalid
        """
        # 1. Load current trip
        current_trip = await self.trip_spec_collector.get_trip(trip_id, db)
        if not current_trip:
            raise ValueError(f"Trip {trip_id} not found")

        # 2. Check cache
        cache_key = None
        if use_cache:
            cache_key = self.cache.generate_cache_key(str(trip_id), user_message)
            cached_response = self.cache.get(cache_key)
            if cached_response:
                # Return cached response with fresh trip data
                return TripChatResponse(
                    assistant_message=cached_response["assistant_message"],
                    trip=current_trip,
                )

        # 3. Build trip context for LLM (Russian)
        trip_context = f"""- Город: {current_trip.city}
- Даты: {current_trip.start_date} — {current_trip.end_date}
- Путешественников: {current_trip.num_travelers}
- Темп: {current_trip.pace}
- Бюджет: {current_trip.budget}
- Интересы: {', '.join(current_trip.interests) if current_trip.interests else 'не указаны'}
- Дополнительные предпочтения: {json.dumps(current_trip.additional_preferences, ensure_ascii=False)}"""

        # 4. Call LLM in Trip Chat Mode (use cheaper model)
        user_prompt = self._build_user_prompt(trip_context, user_message)

        try:
            # Use the dedicated trip_chat_model for cost optimization
            llm_response_raw = await self.llm_client.generate_structured(
                prompt=user_prompt,
                system_prompt=self.SYSTEM_PROMPT,
                max_tokens=512,  # Keep it short for cost savings
            )

            # Parse into TripChatLLMResponse
            llm_response = TripChatLLMResponse(**llm_response_raw)

        except Exception as e:
            raise ValueError(f"Failed to parse LLM response: {e}")

        # 5. Apply trip updates if any
        updated_trip = current_trip
        if llm_response.trip_updates:
            # Merge additional_preferences instead of replacing
            if "additional_preferences" in llm_response.trip_updates:
                merged_prefs = {
                    **current_trip.additional_preferences,
                    **llm_response.trip_updates["additional_preferences"]
                }
                llm_response.trip_updates["additional_preferences"] = merged_prefs

            update_request = self._safe_apply_trip_updates(llm_response.trip_updates)
            updated_trip = await self.trip_spec_collector.update_trip(
                trip_id, update_request, db
            )
            if not updated_trip:
                raise ValueError(f"Failed to update trip {trip_id}")

        # 6. Cache the response
        if use_cache and cache_key:
            self.cache.set(
                cache_key,
                {"assistant_message": llm_response.assistant_message},
                ttl_seconds=3600,  # 1 hour TTL
            )

        # 7. Return response
        return TripChatResponse(
            assistant_message=llm_response.assistant_message,
            trip=updated_trip,
        )
