"""
TripSpec Collector service.
Handles creation and updating of TripSpec from form inputs.
"""
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models import TripSpec, DailyRoutine
from src.domain.schemas import TripCreateRequest, TripUpdateRequest, TripResponse, DailyRoutineResponse
from src.infrastructure.models import TripModel
from src.infrastructure.geocoding import get_geocoding_service

logger = logging.getLogger(__name__)


# Category translation mapping: Russian → English
# This ensures the LLM (trained primarily on English) understands user interests
CATEGORY_TRANSLATION_MAP = {
    "Гастрономия": "gastronomy",
    "История и музеи": "history and museums",
    "Ночная жизнь": "nightlife",
    "Природа и виды": "nature and views",
    "Шопинг": "shopping",
    "Кофейни и десерты": "cafes and desserts",
    "Современное искусство": "modern art",
    "Архитектура и районы": "architecture and districts",
    "Архитектура": "architecture",  # Short version without "и районы"
    "Пляж / вода": "beach and water",
    "Пляж/вода": "beach and water",  # Variant without spaces
    "Активности и спорт": "activities and sports",
}


class TripSpecCollector:
    """
    Service for creating and updating trip specifications from form inputs.
    This collector manages TripSpec data and persists it to the database.
    """

    @staticmethod
    def _translate_interests(interests: list[str]) -> list[str]:
        """
        Translate interest categories from Russian to English.

        This ensures the LLM (trained primarily on English) can properly
        understand and use the user's selected interests when generating
        itineraries and selecting POIs.

        Args:
            interests: List of interest categories (may be in Russian or English)

        Returns:
            List of translated interest categories in English
        """
        translated = []
        for interest in interests:
            # If already in English (not in map), keep as is
            # Otherwise, translate from Russian to English
            translated_interest = CATEGORY_TRANSLATION_MAP.get(interest, interest)
            translated.append(translated_interest)

            if interest in CATEGORY_TRANSLATION_MAP:
                logger.info(f"Translated interest '{interest}' → '{translated_interest}'")

        return translated

    @staticmethod
    def _daily_routine_to_dict(routine: DailyRoutine) -> dict:
        """Convert DailyRoutine domain model to JSON-serializable dict."""
        return {
            "wake_time": routine.wake_time.isoformat(),
            "sleep_time": routine.sleep_time.isoformat(),
            "breakfast_window": [t.isoformat() for t in routine.breakfast_window],
            "lunch_window": [t.isoformat() for t in routine.lunch_window],
            "dinner_window": [t.isoformat() for t in routine.dinner_window],
        }

    @staticmethod
    def _dict_to_daily_routine(data: dict) -> DailyRoutine:
        """Convert dict from database to DailyRoutine domain model."""
        from datetime import time as dt_time

        def parse_time(t):
            if isinstance(t, str):
                return dt_time.fromisoformat(t)
            return t

        return DailyRoutine(
            wake_time=parse_time(data["wake_time"]),
            sleep_time=parse_time(data["sleep_time"]),
            breakfast_window=tuple(parse_time(t) for t in data["breakfast_window"]),
            lunch_window=tuple(parse_time(t) for t in data["lunch_window"]),
            dinner_window=tuple(parse_time(t) for t in data["dinner_window"]),
        )

    @staticmethod
    def _trip_model_to_response(trip_model: TripModel) -> TripResponse:
        """Convert TripModel (ORM) to TripResponse (API response)."""
        daily_routine = TripSpecCollector._dict_to_daily_routine(trip_model.daily_routine)

        return TripResponse(
            id=trip_model.id,
            city=trip_model.city,
            city_center_lat=trip_model.city_center_lat,
            city_center_lon=trip_model.city_center_lon,
            start_date=trip_model.start_date,
            end_date=trip_model.end_date,
            num_travelers=trip_model.num_travelers,
            pace=trip_model.pace,
            budget=trip_model.budget,
            interests=trip_model.interests,
            daily_routine=DailyRoutineResponse(
                wake_time=daily_routine.wake_time,
                sleep_time=daily_routine.sleep_time,
                breakfast_window=daily_routine.breakfast_window,
                lunch_window=daily_routine.lunch_window,
                dinner_window=daily_routine.dinner_window,
            ),
            hotel_location=trip_model.hotel_location,
            hotel_lat=trip_model.hotel_lat,
            hotel_lon=trip_model.hotel_lon,
            additional_preferences=trip_model.additional_preferences,
            created_at=trip_model.created_at.isoformat() + "Z",
            updated_at=trip_model.updated_at.isoformat() + "Z",
        )

    async def create_trip(
        self,
        request: TripCreateRequest,
        db: AsyncSession,
    ) -> TripResponse:
        """
        Create a new trip from form inputs.

        Args:
            request: Trip creation request with form data
            db: Database session

        Returns:
            TripResponse with the created trip data including trip_id
        """
        # Build daily routine (use defaults if not provided)
        if request.daily_routine:
            daily_routine = DailyRoutine(
                wake_time=request.daily_routine.wake_time or DailyRoutine().wake_time,
                sleep_time=request.daily_routine.sleep_time or DailyRoutine().sleep_time,
                breakfast_window=request.daily_routine.breakfast_window or DailyRoutine().breakfast_window,
                lunch_window=request.daily_routine.lunch_window or DailyRoutine().lunch_window,
                dinner_window=request.daily_routine.dinner_window or DailyRoutine().dinner_window,
            )
        else:
            daily_routine = DailyRoutine()

        # Geocode city to get coordinates
        city_center_lat = None
        city_center_lon = None
        geocoding_service = get_geocoding_service()
        try:
            geocoding_result = await geocoding_service.geocode_city(request.city)
            if geocoding_result:
                city_center_lat = geocoding_result.lat
                city_center_lon = geocoding_result.lon
                logger.info(f"Geocoded city '{request.city}' to ({city_center_lat}, {city_center_lon})")
            else:
                logger.warning(f"Could not geocode city '{request.city}', proceeding without coordinates")
        except Exception as e:
            logger.error(f"Error geocoding city '{request.city}': {e}")

        # Geocode hotel location to get coordinates
        hotel_lat = None
        hotel_lon = None
        if request.hotel_location:
            try:
                # Geocode hotel with city context for better accuracy
                hotel_query = f"{request.hotel_location}, {request.city}"
                hotel_result = await geocoding_service.geocode_city(hotel_query)
                if hotel_result:
                    hotel_lat = hotel_result.lat
                    hotel_lon = hotel_result.lon
                    logger.info(f"Geocoded hotel '{request.hotel_location}' to ({hotel_lat}, {hotel_lon})")
                else:
                    logger.warning(f"Could not geocode hotel '{request.hotel_location}'")
            except Exception as e:
                logger.error(f"Error geocoding hotel '{request.hotel_location}': {e}")

        # Translate interests from Russian to English for LLM understanding
        translated_interests = self._translate_interests(request.interests) if request.interests else []

        # Create TripModel (ORM)
        trip_model = TripModel(
            city=request.city,
            city_center_lat=city_center_lat,
            city_center_lon=city_center_lon,
            start_date=request.start_date,
            end_date=request.end_date,
            num_travelers=request.num_travelers,
            pace=request.pace,
            budget=request.budget,
            interests=translated_interests,
            daily_routine=self._daily_routine_to_dict(daily_routine),
            hotel_location=request.hotel_location,
            hotel_lat=hotel_lat,
            hotel_lon=hotel_lon,
            additional_preferences={},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db.add(trip_model)
        await db.commit()
        await db.refresh(trip_model)

        return self._trip_model_to_response(trip_model)

    async def get_trip(
        self,
        trip_id: UUID,
        db: AsyncSession,
    ) -> Optional[TripResponse]:
        """
        Get an existing trip by ID.

        Args:
            trip_id: Trip UUID
            db: Database session

        Returns:
            TripResponse if found, None otherwise
        """
        result = await db.execute(
            select(TripModel).where(TripModel.id == trip_id)
        )
        trip_model = result.scalars().first()

        if not trip_model:
            return None

        return self._trip_model_to_response(trip_model)

    async def update_trip(
        self,
        trip_id: UUID,
        request: TripUpdateRequest,
        db: AsyncSession,
    ) -> Optional[TripResponse]:
        """
        Update an existing trip with new form data (partial updates).

        Args:
            trip_id: Trip UUID
            request: Trip update request with partial data
            db: Database session

        Returns:
            Updated TripResponse if trip found, None otherwise
        """
        # Fetch existing trip
        result = await db.execute(
            select(TripModel).where(TripModel.id == trip_id)
        )
        trip_model = result.scalars().first()

        if not trip_model:
            return None

        # Update fields if provided
        if request.city is not None and request.city != trip_model.city:
            trip_model.city = request.city
            # Re-geocode when city changes
            try:
                geocoding_service = get_geocoding_service()
                geocoding_result = await geocoding_service.geocode_city(request.city)
                if geocoding_result:
                    trip_model.city_center_lat = geocoding_result.lat
                    trip_model.city_center_lon = geocoding_result.lon
                    logger.info(f"Re-geocoded city '{request.city}' to ({geocoding_result.lat}, {geocoding_result.lon})")
                else:
                    trip_model.city_center_lat = None
                    trip_model.city_center_lon = None
                    logger.warning(f"Could not re-geocode city '{request.city}'")
            except Exception as e:
                logger.error(f"Error re-geocoding city '{request.city}': {e}")
        if request.start_date is not None:
            trip_model.start_date = request.start_date
        if request.end_date is not None:
            trip_model.end_date = request.end_date
        if request.num_travelers is not None:
            trip_model.num_travelers = request.num_travelers
        if request.pace is not None:
            trip_model.pace = request.pace
        if request.budget is not None:
            trip_model.budget = request.budget
        if request.interests is not None:
            # Translate interests from Russian to English for LLM understanding
            trip_model.interests = self._translate_interests(request.interests)
        if request.hotel_location is not None:
            trip_model.hotel_location = request.hotel_location
            # Re-geocode hotel when it changes
            if request.hotel_location:
                try:
                    geocoding_service = get_geocoding_service()
                    hotel_query = f"{request.hotel_location}, {trip_model.city}"
                    hotel_result = await geocoding_service.geocode_city(hotel_query)
                    if hotel_result:
                        trip_model.hotel_lat = hotel_result.lat
                        trip_model.hotel_lon = hotel_result.lon
                        logger.info(f"Re-geocoded hotel '{request.hotel_location}' to ({hotel_result.lat}, {hotel_result.lon})")
                    else:
                        trip_model.hotel_lat = None
                        trip_model.hotel_lon = None
                        logger.warning(f"Could not re-geocode hotel '{request.hotel_location}'")
                except Exception as e:
                    logger.error(f"Error re-geocoding hotel '{request.hotel_location}': {e}")
            else:
                # Hotel location cleared
                trip_model.hotel_lat = None
                trip_model.hotel_lon = None
        if request.additional_preferences is not None:
            trip_model.additional_preferences = request.additional_preferences

        # Update daily routine if provided
        if request.daily_routine is not None:
            current_routine = self._dict_to_daily_routine(trip_model.daily_routine)
            updated_routine = DailyRoutine(
                wake_time=request.daily_routine.wake_time or current_routine.wake_time,
                sleep_time=request.daily_routine.sleep_time or current_routine.sleep_time,
                breakfast_window=request.daily_routine.breakfast_window or current_routine.breakfast_window,
                lunch_window=request.daily_routine.lunch_window or current_routine.lunch_window,
                dinner_window=request.daily_routine.dinner_window or current_routine.dinner_window,
            )
            trip_model.daily_routine = self._daily_routine_to_dict(updated_routine)

        trip_model.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(trip_model)

        return self._trip_model_to_response(trip_model)
