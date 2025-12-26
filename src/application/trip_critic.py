"""
Trip Critic service.
Validates itineraries and generates issues/warnings.
Purely deterministic - no LLM calls.
"""
from uuid import UUID
from datetime import time, datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models import (
    CritiqueIssue,
    CritiqueIssueSeverity,
    BlockType,
    PaceLevel,
    ItineraryDay,
    ItineraryBlock,
)
from src.application.trip_spec import TripSpecCollector
from src.infrastructure.models import ItineraryModel


class TripCritic:
    """
    Service for validating trip itineraries.
    Generates deterministic critique issues based on rule-based checks.
    """

    # Pace-based active time thresholds (in hours)
    PACE_THRESHOLDS = {
        PaceLevel.SLOW: 7.0,      # Slow pace: warn if > 7 hours active
        PaceLevel.MEDIUM: 9.0,    # Medium pace: warn if > 9 hours active
        PaceLevel.FAST: 12.0,     # Fast pace: warn if > 12 hours active
    }

    # Meal time windows (hour of day)
    BREAKFAST_WINDOW = (6, 11)    # 6 AM - 11 AM
    LUNCH_WINDOW = (11, 16)       # 11 AM - 4 PM
    DINNER_WINDOW = (17, 23)      # 5 PM - 11 PM

    # Travel time threshold (minutes)
    LONG_TRAVEL_THRESHOLD = 45

    # Nightlife end time threshold vs sleep time (hours)
    LATE_NIGHTLIFE_THRESHOLD = 2.0

    # Consecutive intense days threshold
    CONSECUTIVE_INTENSE_DAYS = 3

    def __init__(self):
        """Initialize Trip Critic."""
        self.trip_spec_collector = TripSpecCollector()

    def _time_to_hours(self, t: time) -> float:
        """Convert time to hours as float."""
        return t.hour + t.minute / 60.0

    def _calculate_block_duration(self, block: ItineraryBlock) -> float:
        """Calculate block duration in hours."""
        start_hours = self._time_to_hours(block.start_time)
        end_hours = self._time_to_hours(block.end_time)

        # Handle blocks that cross midnight
        if end_hours < start_hours:
            end_hours += 24

        return end_hours - start_hours

    def _is_active_block(self, block_type: BlockType) -> bool:
        """Check if block type counts as active time."""
        return block_type in {BlockType.ACTIVITY, BlockType.NIGHTLIFE, BlockType.MEAL}

    def _check_daily_load(
        self,
        day: ItineraryDay,
        pace: PaceLevel,
    ) -> list[CritiqueIssue]:
        """Check if day is too busy for the given pace."""
        issues = []

        # Calculate total active time
        active_hours = sum(
            self._calculate_block_duration(block)
            for block in day.blocks
            if self._is_active_block(block.block_type)
        )

        threshold = self.PACE_THRESHOLDS.get(pace, 9.0)

        if active_hours > threshold:
            issues.append(
                CritiqueIssue(
                    code="DAY_TOO_BUSY",
                    severity=CritiqueIssueSeverity.WARNING,
                    message=f"Day {day.day_number} has {active_hours:.1f} hours of activities, which may be too intense for a {pace.value} pace.",
                    day_number=day.day_number,
                    details={
                        "active_hours": round(active_hours, 1),
                        "pace": pace.value,
                        "threshold": threshold,
                    },
                )
            )

        return issues

    def _check_meal_coverage(self, day: ItineraryDay) -> list[CritiqueIssue]:
        """Check if day has proper meal coverage."""
        issues = []

        # Find meal blocks
        meal_blocks = [b for b in day.blocks if b.block_type == BlockType.MEAL]

        has_breakfast = False
        has_lunch = False
        has_dinner = False

        for block in meal_blocks:
            hour = block.start_time.hour

            if self.BREAKFAST_WINDOW[0] <= hour < self.BREAKFAST_WINDOW[1]:
                has_breakfast = True
            elif self.LUNCH_WINDOW[0] <= hour < self.LUNCH_WINDOW[1]:
                has_lunch = True
            elif self.DINNER_WINDOW[0] <= hour < self.DINNER_WINDOW[1]:
                has_dinner = True

        # Generate issues for missing meals
        if not has_breakfast:
            issues.append(
                CritiqueIssue(
                    code="MISSING_BREAKFAST",
                    severity=CritiqueIssueSeverity.WARNING,
                    message=f"Day {day.day_number} is missing a breakfast.",
                    day_number=day.day_number,
                    details={"meal_type": "breakfast"},
                )
            )

        if not has_lunch:
            issues.append(
                CritiqueIssue(
                    code="MISSING_LUNCH",
                    severity=CritiqueIssueSeverity.WARNING,
                    message=f"Day {day.day_number} is missing a lunch.",
                    day_number=day.day_number,
                    details={"meal_type": "lunch"},
                )
            )

        if not has_dinner:
            issues.append(
                CritiqueIssue(
                    code="MISSING_DINNER",
                    severity=CritiqueIssueSeverity.WARNING,
                    message=f"Day {day.day_number} is missing a dinner.",
                    day_number=day.day_number,
                    details={"meal_type": "dinner"},
                )
            )

        return issues

    def _check_time_consistency(self, day: ItineraryDay) -> list[CritiqueIssue]:
        """Check for time overlaps and invalid ranges."""
        issues = []

        for i, block in enumerate(day.blocks):
            # Check for invalid time range
            if block.end_time <= block.start_time:
                # Allow blocks that cross midnight (e.g., nightlife 23:00-02:00)
                is_midnight_crossing = (
                    block.end_time.hour < 6 and block.start_time.hour > 18
                )
                if not is_midnight_crossing:
                    issues.append(
                        CritiqueIssue(
                            code="INVALID_TIME_RANGE",
                            severity=CritiqueIssueSeverity.ERROR,
                            message=f"Day {day.day_number}, block {i}: End time is before start time.",
                            day_number=day.day_number,
                            block_index=i,
                            details={
                                "start_time": block.start_time.isoformat(),
                                "end_time": block.end_time.isoformat(),
                            },
                        )
                    )

            # Check for overlaps with next block
            if i < len(day.blocks) - 1:
                next_block = day.blocks[i + 1]

                # Simple overlap check (doesn't handle midnight crossing perfectly)
                if block.end_time > next_block.start_time:
                    issues.append(
                        CritiqueIssue(
                            code="BLOCK_OVERLAP",
                            severity=CritiqueIssueSeverity.ERROR,
                            message=f"Day {day.day_number}: Block {i} overlaps with block {i+1}.",
                            day_number=day.day_number,
                            block_index=i,
                            details={
                                "current_end": block.end_time.isoformat(),
                                "next_start": next_block.start_time.isoformat(),
                            },
                        )
                    )

        return issues

    def _check_travel_fatigue(self, day: ItineraryDay) -> list[CritiqueIssue]:
        """Check for long travel times between blocks."""
        issues = []

        for i, block in enumerate(day.blocks):
            if block.travel_time_from_prev > self.LONG_TRAVEL_THRESHOLD:
                issues.append(
                    CritiqueIssue(
                        code="LONG_TRAVEL",
                        severity=CritiqueIssueSeverity.WARNING,
                        message=f"Day {day.day_number}, block {i}: Long travel time ({block.travel_time_from_prev} minutes) from previous location.",
                        day_number=day.day_number,
                        block_index=i,
                        details={
                            "travel_time_minutes": block.travel_time_from_prev,
                            "threshold": self.LONG_TRAVEL_THRESHOLD,
                        },
                    )
                )

        return issues

    def _check_nightlife_vs_sleep(
        self,
        day: ItineraryDay,
        sleep_time: Optional[time],
    ) -> list[CritiqueIssue]:
        """Check if nightlife ends too late compared to sleep schedule."""
        issues = []

        if not sleep_time:
            return issues

        nightlife_blocks = [b for b in day.blocks if b.block_type == BlockType.NIGHTLIFE]

        for i, block in enumerate(nightlife_blocks):
            block_index = day.blocks.index(block)

            # Calculate hours difference
            nightlife_end_hours = self._time_to_hours(block.end_time)
            sleep_hours = self._time_to_hours(sleep_time)

            # Handle midnight crossing
            if nightlife_end_hours < 6:  # Assume early morning hours
                nightlife_end_hours += 24

            if sleep_hours < 6:  # Assume early morning hours
                sleep_hours += 24

            hours_past_sleep = nightlife_end_hours - sleep_hours

            if hours_past_sleep > self.LATE_NIGHTLIFE_THRESHOLD:
                issues.append(
                    CritiqueIssue(
                        code="LATE_NIGHTLIFE",
                        severity=CritiqueIssueSeverity.INFO,
                        message=f"Day {day.day_number}: Nightlife ends {hours_past_sleep:.1f} hours after your usual sleep time.",
                        day_number=day.day_number,
                        block_index=block_index,
                        details={
                            "nightlife_end": block.end_time.isoformat(),
                            "sleep_time": sleep_time.isoformat(),
                            "hours_past_sleep": round(hours_past_sleep, 1),
                        },
                    )
                )

        return issues

    def _check_consecutive_intense_days(
        self,
        days: list[ItineraryDay],
        pace: PaceLevel,
    ) -> list[CritiqueIssue]:
        """Check for consecutive intense days."""
        issues = []

        threshold = self.PACE_THRESHOLDS.get(pace, 9.0)
        intense_streak = 0
        streak_start = None

        for day in days:
            active_hours = sum(
                self._calculate_block_duration(block)
                for block in day.blocks
                if self._is_active_block(block.block_type)
            )

            is_intense = active_hours > (threshold * 0.9)  # 90% of threshold

            if is_intense:
                if intense_streak == 0:
                    streak_start = day.day_number
                intense_streak += 1
            else:
                intense_streak = 0
                streak_start = None

            # Flag if we hit the threshold
            if intense_streak >= self.CONSECUTIVE_INTENSE_DAYS:
                issues.append(
                    CritiqueIssue(
                        code="CONSECUTIVE_INTENSE_DAYS",
                        severity=CritiqueIssueSeverity.WARNING,
                        message=f"Days {streak_start}-{day.day_number}: {intense_streak} consecutive intense days. Consider adding a lighter day.",
                        day_number=None,  # Trip-level issue
                        details={
                            "streak_start": streak_start,
                            "streak_end": day.day_number,
                            "streak_length": intense_streak,
                        },
                    )
                )
                # Reset to avoid duplicate warnings
                intense_streak = 0

        return issues

    async def critique_trip(
        self,
        trip_id: UUID,
        db: AsyncSession,
    ) -> list[CritiqueIssue]:
        """
        Generate critique for a trip itinerary.

        Args:
            trip_id: Trip UUID
            db: Database session

        Returns:
            List of CritiqueIssue objects

        Raises:
            ValueError: If trip or itinerary not found
        """
        # 1. Load trip spec
        trip_spec = await self.trip_spec_collector.get_trip(trip_id, db)
        if not trip_spec:
            raise ValueError(f"Trip {trip_id} not found")

        # 2. Load itinerary
        result = await db.execute(
            select(ItineraryModel).where(ItineraryModel.trip_id == trip_id)
        )
        itinerary_model = result.scalars().first()

        if not itinerary_model or not itinerary_model.days:
            raise ValueError(f"No itinerary found for trip {trip_id}")

        # Parse itinerary
        from src.domain.models import ItineraryDay
        days = [ItineraryDay(**day_data) for day_data in itinerary_model.days]

        # 3. Run all validation checks
        all_issues = []

        # Per-day checks
        for day in days:
            # Daily load vs pace
            all_issues.extend(self._check_daily_load(day, trip_spec.pace))

            # Meal coverage
            all_issues.extend(self._check_meal_coverage(day))

            # Time consistency
            all_issues.extend(self._check_time_consistency(day))

            # Travel fatigue
            all_issues.extend(self._check_travel_fatigue(day))

            # Nightlife vs sleep schedule
            all_issues.extend(
                self._check_nightlife_vs_sleep(day, trip_spec.daily_routine.sleep_time)
            )

        # Trip-level checks
        all_issues.extend(self._check_consecutive_intense_days(days, trip_spec.pace))

        return all_issues

    async def store_critique(
        self,
        trip_id: UUID,
        issues: list[CritiqueIssue],
        db: AsyncSession,
    ) -> None:
        """
        Store critique issues in database.

        Args:
            trip_id: Trip UUID
            issues: List of critique issues
            db: Database session
        """
        result = await db.execute(
            select(ItineraryModel).where(ItineraryModel.trip_id == trip_id)
        )
        itinerary_model = result.scalars().first()

        if not itinerary_model:
            raise ValueError(f"No itinerary found for trip {trip_id}")

        # Serialize issues to JSON
        critique_json = [issue.model_dump(mode='json') for issue in issues]

        # Update model
        itinerary_model.critique_issues = critique_json
        itinerary_model.critique_created_at = datetime.utcnow()
        itinerary_model.updated_at = datetime.utcnow()

        await db.commit()

    async def get_critique(
        self,
        trip_id: UUID,
        db: AsyncSession,
    ) -> Optional[list[CritiqueIssue]]:
        """
        Get stored critique for a trip.

        Args:
            trip_id: Trip UUID
            db: Database session

        Returns:
            List of CritiqueIssue objects or None if no critique exists
        """
        result = await db.execute(
            select(ItineraryModel).where(ItineraryModel.trip_id == trip_id)
        )
        itinerary_model = result.scalars().first()

        if not itinerary_model or not itinerary_model.critique_issues:
            return None

        # Parse stored JSON back into CritiqueIssue objects
        issues = [CritiqueIssue(**issue_data) for issue_data in itinerary_model.critique_issues]

        return issues
