"""
Macro Planner service.
Generates high-level trip skeleton using LLM.
"""
from uuid import UUID
from typing import Optional
from datetime import datetime, timedelta
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models import DaySkeleton, SkeletonBlock
from src.domain.schemas import MacroPlanResponse
from src.application.trip_spec import TripSpecCollector
from src.infrastructure.llm_client import LLMClient, get_macro_planning_llm_client
from src.infrastructure.models import ItineraryModel


class MacroPlanner:
    """
    Service for generating macro-level trip skeletons.
    Uses LLM to create day-by-day structure with themed blocks.
    """

    # System prompt for Macro Planning Mode
    SYSTEM_PROMPT = """You are an expert travel planner. Your job is to create a high-level skeleton for a multi-day trip.

Given trip details (dates, city, preferences, daily routine), you must:
1. Split the trip into days
2. For each day, assign an overall theme
3. Create time blocks for each day with:
   - Type (meal, activity, nightlife, rest, travel)
   - Time windows respecting the user's daily routine
   - Desired categories for POI selection later

CRITICAL: You MUST respond with valid JSON only, matching this exact structure:
{
  "days": [
    {
      "day_number": 1,
      "date": "YYYY-MM-DD",
      "theme": "Day theme description",
      "blocks": [
        {
          "block_type": "meal|activity|nightlife|rest|travel",
          "start_time": "HH:MM:SS",
          "end_time": "HH:MM:SS",
          "theme": "Block theme",
          "desired_categories": ["category1", "category2"]
        }
      ]
    }
  ]
}

Guidelines:
- Respect wake/sleep times and meal windows from daily routine
- Match pace level (slow=fewer activities, fast=packed schedule)
- Include interests in desired_categories
- Budget affects venue types (low=casual, high=fine dining)
- Add nightlife blocks only if relevant to interests
- Include rest blocks for slow/medium pace
- Each day should have 3 meals + 2-4 activity blocks
- NO explanations, NO markdown, ONLY valid JSON"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        """
        Initialize Macro Planner.

        Args:
            llm_client: LLM client (defaults to macro planning client)
        """
        self.llm_client = llm_client or get_macro_planning_llm_client()
        self.trip_spec_collector = TripSpecCollector()

    def _build_planning_prompt(self, trip_context: str) -> str:
        """Build the user prompt for macro planning."""
        return f"""{trip_context}

Generate a complete day-by-day skeleton for this trip.
Respond with JSON only."""

    def _build_trip_context(self, trip_spec) -> str:
        """Build trip context string for LLM."""
        # Calculate number of days
        num_days = (trip_spec.end_date - trip_spec.start_date).days + 1

        context = f"""Trip Details:
- City: {trip_spec.city}
- Dates: {trip_spec.start_date} to {trip_spec.end_date} ({num_days} days)
- Travelers: {trip_spec.num_travelers}
- Pace: {trip_spec.pace} (slow=relaxed, medium=balanced, fast=packed)
- Budget: {trip_spec.budget}
- Interests: {', '.join(trip_spec.interests) if trip_spec.interests else 'general sightseeing'}

Daily Routine:
- Wake time: {trip_spec.daily_routine.wake_time}
- Sleep time: {trip_spec.daily_routine.sleep_time}
- Breakfast: {trip_spec.daily_routine.breakfast_window[0]} - {trip_spec.daily_routine.breakfast_window[1]}
- Lunch: {trip_spec.daily_routine.lunch_window[0]} - {trip_spec.daily_routine.lunch_window[1]}
- Dinner: {trip_spec.daily_routine.dinner_window[0]} - {trip_spec.daily_routine.dinner_window[1]}"""

        if trip_spec.hotel_location:
            context += f"\n- Hotel: {trip_spec.hotel_location}"

        if trip_spec.additional_preferences:
            context += f"\n- Additional preferences: {json.dumps(trip_spec.additional_preferences)}"

        return context

    def _normalize_time_string(self, time_str: str) -> str:
        """
        Normalize time string to HH:MM:SS format.
        Handles malformed LLM outputs like ':00:00' or '9:00:00'.
        """
        if not time_str:
            return "00:00:00"

        time_str = time_str.strip()

        # Handle case where LLM returns ':MM:SS' (missing hour)
        if time_str.startswith(':'):
            time_str = '00' + time_str

        # Split into parts
        parts = time_str.split(':')
        if len(parts) != 3:
            # Invalid format, return default
            return "00:00:00"

        # Pad hour with leading zero if needed
        hour = parts[0].zfill(2) if parts[0] else '00'
        minute = parts[1].zfill(2) if parts[1] else '00'
        second = parts[2].zfill(2) if parts[2] else '00'

        return f"{hour}:{minute}:{second}"

    def _normalize_block_data(self, block_data: dict) -> dict:
        """Normalize block data before parsing into SkeletonBlock."""
        normalized = block_data.copy()

        # Normalize time fields
        if 'start_time' in normalized:
            normalized['start_time'] = self._normalize_time_string(normalized['start_time'])
        if 'end_time' in normalized:
            normalized['end_time'] = self._normalize_time_string(normalized['end_time'])

        return normalized

    def _parse_skeleton_response(self, llm_response: dict) -> list[DaySkeleton]:
        """Parse LLM JSON response into DaySkeleton objects."""
        days_data = llm_response.get("days", [])
        skeletons = []

        for day_data in days_data:
            # Normalize and parse blocks
            normalized_blocks = [self._normalize_block_data(block_data) for block_data in day_data.get("blocks", [])]
            blocks = [SkeletonBlock(**block_data) for block_data in normalized_blocks]

            skeleton = DaySkeleton(
                day_number=day_data["day_number"],
                date=day_data["date"],
                theme=day_data["theme"],
                blocks=blocks
            )
            skeletons.append(skeleton)

        return skeletons

    def _skeletons_to_json(self, skeletons: list[DaySkeleton]) -> list[dict]:
        """Convert DaySkeleton objects to JSON-serializable dicts."""
        return [skeleton.model_dump(mode='json') for skeleton in skeletons]

    async def generate_macro_plan(
        self,
        trip_id: UUID,
        db: AsyncSession,
    ) -> MacroPlanResponse:
        """
        Generate macro plan for a trip.

        Args:
            trip_id: Trip UUID
            db: Database session

        Returns:
            MacroPlanResponse with day skeletons

        Raises:
            ValueError: If trip not found or LLM response invalid
        """
        # 1. Load trip spec
        trip_spec = await self.trip_spec_collector.get_trip(trip_id, db)
        if not trip_spec:
            raise ValueError(f"Trip {trip_id} not found")

        # 2. Build trip context for LLM
        trip_context = self._build_trip_context(trip_spec)
        user_prompt = self._build_planning_prompt(trip_context)

        # 3. Call LLM for macro planning
        try:
            llm_response = await self.llm_client.generate_structured(
                prompt=user_prompt,
                system_prompt=self.SYSTEM_PROMPT,
                max_tokens=4096,  # Increased limit for multi-day trips with detailed blocks
            )
        except Exception as e:
            raise ValueError(f"LLM failed to generate macro plan: {e}")

        # 4. Parse into DaySkeleton objects
        try:
            skeletons = self._parse_skeleton_response(llm_response)
        except Exception as e:
            raise ValueError(f"Failed to parse LLM response into skeletons: {e}")

        if not skeletons:
            raise ValueError("LLM returned empty skeleton list")

        # 5. Store in database
        created_at = datetime.utcnow()

        # Check if itinerary record exists for this trip
        result = await db.execute(
            select(ItineraryModel).where(ItineraryModel.trip_id == trip_id)
        )
        itinerary_model = result.scalars().first()

        if itinerary_model:
            # Update existing record
            itinerary_model.macro_plan = self._skeletons_to_json(skeletons)
            itinerary_model.macro_plan_created_at = created_at
            itinerary_model.updated_at = created_at
        else:
            # Create new record
            itinerary_model = ItineraryModel(
                trip_id=trip_id,
                macro_plan=self._skeletons_to_json(skeletons),
                macro_plan_created_at=created_at,
                created_at=created_at,
                updated_at=created_at,
            )
            db.add(itinerary_model)

        await db.commit()
        await db.refresh(itinerary_model)

        # 6. Return response
        return MacroPlanResponse(
            trip_id=trip_id,
            days=skeletons,
            created_at=created_at.isoformat() + "Z",
        )

    async def get_macro_plan(
        self,
        trip_id: UUID,
        db: AsyncSession,
    ) -> Optional[MacroPlanResponse]:
        """
        Get stored macro plan for a trip.

        Args:
            trip_id: Trip UUID
            db: Database session

        Returns:
            MacroPlanResponse if plan exists, None otherwise
        """
        result = await db.execute(
            select(ItineraryModel).where(ItineraryModel.trip_id == trip_id)
        )
        itinerary_model = result.scalars().first()

        if not itinerary_model or not itinerary_model.macro_plan:
            return None

        # Parse stored JSON back into DaySkeleton objects
        skeletons = [DaySkeleton(**day_data) for day_data in itinerary_model.macro_plan]

        return MacroPlanResponse(
            trip_id=trip_id,
            days=skeletons,
            created_at=itinerary_model.macro_plan_created_at.isoformat() + "Z"
            if itinerary_model.macro_plan_created_at else datetime.utcnow().isoformat() + "Z",
        )
