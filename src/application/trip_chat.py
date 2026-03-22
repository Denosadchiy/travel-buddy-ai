"""
Trip Chat Assistant service.
Handles natural language chat messages and updates TripSpec via LLM.
"""
from uuid import UUID
from typing import Optional
import json

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.domain.schemas import TripChatLLMResponse, TripChatResponse, TripUpdateRequest, TripUpdates
from src.application.trip_spec import TripSpecCollector
from src.infrastructure.llm_client import LLMClient, get_trip_chat_llm_client
from src.infrastructure.cache import ChatCache, get_chat_cache
from src.i18n import LocaleContext, SupportedLanguage

class TripChatAssistant:
    """
    Service for handling trip-related chat messages.
    Uses LLM to interpret user messages and update TripSpec.
    """

    # Base system prompt (English) - language instruction will be added dynamically
    BASE_SYSTEM_PROMPT = """You are a knowledgeable and friendly travel assistant called Travel Buddy. You have two roles:

1. **Answer travel questions**: When the user asks questions about destinations, culture, food, weather, visa, safety, what to see, local tips, etc. — give helpful, informative answers. Be a real travel expert! Share interesting facts, practical advice, and insider tips.

2. **Extract trip preferences**: When the user mentions trip details (city, dates, travelers, interests, specific requests), extract them as structured updates.

IMPORTANT BEHAVIOR:
- If the user asks a question (e.g., "What's the capital of Vietnam?", "Is Barcelona safe?", "What's the best time to visit Japan?") — ANSWER the question fully and helpfully in assistant_message. Don't just confirm preferences.
- If the user states preferences (e.g., "I want to visit Venice", "We love museums") — acknowledge AND extract trip_updates.
- If the user does both (e.g., "I want to go to Vietnam, what's the capital?") — answer the question AND extract updates.
- Keep answers concise but informative (2-4 sentences). Be warm and enthusiastic about travel.

You MUST respond with valid JSON in exactly this format:
{
  "assistant_message": "Your helpful response — answer questions, share tips, confirm preferences",
  "trip_updates": {
    "city": "Venice",
    "start_date": "2025-03-15",
    "end_date": "2025-03-20",
    "num_travelers": 3,
    "interests": ["list", "of", "interests"],
    "additional_preferences": {
      "any_key": "any_value"
    },
    "structured_preferences": [
      {
        "keyword": "e.g., 'Georgian'",
        "category": "restaurant",
        "price_level": "expensive",
        "quantity": 2
      }
    ]
  }
}

Rules for trip_updates:
- city: destination city name if the user mentions wanting to visit a specific city. Only set if the user explicitly wants to go there.
- start_date: trip start date in YYYY-MM-DD format, if the user specifies dates or timeframes (e.g., "next week", "March 15-20").
- end_date: trip end date in YYYY-MM-DD format, if the user specifies dates or timeframes.
- num_travelers: number of travelers, if the user mentions how many people are traveling (e.g., "with 3 friends" = 4, "couple" = 2).
- interests: list of GENERAL interests/preferences (food, culture, nightlife).
- additional_preferences: dictionary for OTHER general preferences.
- structured_preferences: list for SPECIFIC, structured requests.
  - "keyword": Search keyword (e.g., "Georgian", "coffee", "modern art").
  - "category": POI category (e.g., "restaurant", "cafe", "museum", "park").
  - "price_level": Price level ("cheap", "moderate", "expensive"). Infer from context.
  - "quantity": Number of such places, if specified.
- Only include fields that the user explicitly mentioned or clearly implied. Do NOT include city/start_date/end_date/num_travelers if the user didn't mention them.
- If the message is just a question with no trip preference updates, leave trip_updates empty ({}).
- If the request lacks specifics, `structured_preferences` should be an empty list `[]`.

Be a great travel companion — helpful, knowledgeable, and enthusiastic!"""

    @staticmethod
    def _get_system_prompt(language: SupportedLanguage) -> str:
        """
        Get the system prompt with language instruction.

        The base prompt is in English (LLMs perform better with English instructions),
        but we add a clear instruction to respond in the user's language.
        """
        lang_instruction = f"""

CRITICAL: The assistant_message field MUST be written in {language.display_name}.
All your responses to the user MUST be in {language.display_name}.
The user's message may be in any language - respond in {language.display_name} regardless."""

        return TripChatAssistant.BASE_SYSTEM_PROMPT + lang_instruction

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
        from datetime import date as date_type
        today = date_type.today().isoformat()
        return f"""Today's date: {today}

Current trip:
{trip_context}

User message: {user_message}

Respond with JSON only."""

    def _safe_apply_trip_updates(self, trip_updates: TripUpdates) -> TripUpdateRequest:
        """
        Safely convert LLM trip_updates model to TripUpdateRequest.
        Only allows updating specific allowed fields.
        """
        allowed_updates = {}

        if trip_updates.city is not None:
            allowed_updates["city"] = trip_updates.city

        if trip_updates.start_date is not None:
            allowed_updates["start_date"] = trip_updates.start_date

        if trip_updates.end_date is not None:
            allowed_updates["end_date"] = trip_updates.end_date

        if trip_updates.num_travelers is not None:
            allowed_updates["num_travelers"] = trip_updates.num_travelers

        if trip_updates.interests is not None:
            allowed_updates["interests"] = trip_updates.interests

        if trip_updates.pace is not None:
            allowed_updates["pace"] = trip_updates.pace

        if trip_updates.budget is not None:
            allowed_updates["budget"] = trip_updates.budget

        if trip_updates.additional_preferences is not None:
            allowed_updates["additional_preferences"] = trip_updates.additional_preferences

        if trip_updates.structured_preferences is not None:
            allowed_updates["structured_preferences"] = trip_updates.structured_preferences

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

        # 3. Get current language from context
        language = LocaleContext.get()

        # 4. Build trip context for LLM (English for better LLM understanding)
        trip_context = f"""- City: {current_trip.city}
- Dates: {current_trip.start_date} — {current_trip.end_date}
- Travelers: {current_trip.num_travelers}
- Pace: {current_trip.pace}
- Budget: {current_trip.budget}
- Interests: {', '.join(current_trip.interests) if current_trip.interests else 'not specified'}
- Additional preferences: {json.dumps(current_trip.additional_preferences, ensure_ascii=False)}"""

        # 5. Call LLM in Trip Chat Mode (use cheaper model)
        user_prompt = self._build_user_prompt(trip_context, user_message)
        system_prompt = self._get_system_prompt(language)

        try:
            # Use the dedicated trip_chat_model for cost optimization
            llm_response_raw = await self.llm_client.generate_structured(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=512,  # Keep it short for cost savings
            )

            # Parse into TripChatLLMResponse
            llm_response = TripChatLLMResponse(**llm_response_raw)

        except Exception as e:
            raise ValueError(f"Failed to parse LLM response: {e}")

        # 6. Apply trip updates if any
        updated_trip = current_trip
        if llm_response.trip_updates:
            # Get the update object from the LLM response
            updates = llm_response.trip_updates

            # Merge interests instead of replacing
            if updates.interests:
                existing_interests = set(current_trip.interests or [])
                new_interests = set(updates.interests)
                merged_interests = list(existing_interests | new_interests)
                updates.interests = merged_interests
                print(f"  🔀 Merged interests: {existing_interests} + {new_interests} → {merged_interests}")

            # Merge additional_preferences instead of replacing
            if updates.additional_preferences:
                merged_prefs = {
                    **current_trip.additional_preferences,
                    **updates.additional_preferences,
                }
                updates.additional_preferences = merged_prefs
                print(f"  🔀 Merged additional_preferences: {len(merged_prefs)} items")

            # Merge structured_preferences instead of replacing
            if updates.structured_preferences:
                # Assuming current_trip has a structured_preferences attribute
                # which we will add to the model
                existing_structured_prefs = getattr(current_trip, 'structured_preferences', []) or []
                merged_structured_prefs = existing_structured_prefs + updates.structured_preferences
                updates.structured_preferences = merged_structured_prefs
                print(f"  🔀 Merged structured_preferences: {len(existing_structured_prefs)} + {len(updates.structured_preferences)} → {len(merged_structured_prefs)}")

            update_request = self._safe_apply_trip_updates(updates)
            
            if update_request.model_dump(exclude_unset=True):
                updated_trip = await self.trip_spec_collector.update_trip(
                    trip_id, update_request, db
                )
                if not updated_trip:
                    raise ValueError(f"Failed to update trip {trip_id}")

        # 7. Cache the response
        if use_cache and cache_key:
            self.cache.set(
                cache_key,
                {"assistant_message": llm_response.assistant_message},
                ttl_seconds=3600,  # 1 hour TTL
            )

        # 8. Return response
        return TripChatResponse(
            assistant_message=llm_response.assistant_message,
            trip=updated_trip,
        )
