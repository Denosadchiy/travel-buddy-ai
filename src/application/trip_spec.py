"""
TripSpec Collector service.
Handles creation and updating of TripSpec from form inputs.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models import TripSpec, DailyRoutine
from src.domain.schemas import TripCreateRequest, TripUpdateRequest, TripResponse, DailyRoutineResponse
from src.infrastructure.models import TripModel


class TripSpecCollector:
    """
    Service for creating and updating trip specifications from form inputs.
    This collector manages TripSpec data and persists it to the database.
    """

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

        # Create TripModel (ORM)
        trip_model = TripModel(
            city=request.city,
            start_date=request.start_date,
            end_date=request.end_date,
            num_travelers=request.num_travelers,
            pace=request.pace,
            budget=request.budget,
            interests=request.interests,
            daily_routine=self._daily_routine_to_dict(daily_routine),
            hotel_location=request.hotel_location,
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
        if request.city is not None:
            trip_model.city = request.city
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
            trip_model.interests = request.interests
        if request.hotel_location is not None:
            trip_model.hotel_location = request.hotel_location
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
