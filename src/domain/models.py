"""
Core domain models for the Trip Planning backend.
All models use Pydantic v2 for type safety and validation.
"""
import datetime as dt
from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field
from uuid import UUID, uuid4


# Enums for constrained values
class PaceLevel(str, Enum):
    """Trip pace: how packed the schedule should be."""
    SLOW = "slow"
    MEDIUM = "medium"
    FAST = "fast"


class BudgetLevel(str, Enum):
    """Budget level for the trip."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class BlockType(str, Enum):
    """Type of time block in the itinerary."""
    ACTIVITY = "activity"
    MEAL = "meal"
    NIGHTLIFE = "nightlife"
    REST = "rest"
    TRAVEL = "travel"


class CritiqueIssueSeverity(str, Enum):
    """Severity level for validation issues."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


# Domain Models

class DailyRoutine(BaseModel):
    """User's daily routine preferences."""
    wake_time: dt.time = Field(default=dt.time(8, 0), description="Wake up time")
    sleep_time: dt.time = Field(default=dt.time(23, 0), description="Sleep time")
    breakfast_window: tuple[dt.time, dt.time] = Field(
        default=(dt.time(8, 0), dt.time(10, 0)),
        description="Preferred breakfast time window"
    )
    lunch_window: tuple[dt.time, dt.time] = Field(
        default=(dt.time(12, 0), dt.time(14, 0)),
        description="Preferred lunch time window"
    )
    dinner_window: tuple[dt.time, dt.time] = Field(
        default=(dt.time(18, 0), dt.time(21, 0)),
        description="Preferred dinner time window"
    )


class TripSpec(BaseModel):
    """
    Consolidated trip specification combining form inputs and chat context.
    This is the normalized trip description used throughout the planning pipeline.
    """
    id: UUID = Field(default_factory=uuid4, description="Unique trip ID")
    city: str = Field(description="Destination city")
    start_date: dt.date = Field(description="Trip start date")
    end_date: dt.date = Field(description="Trip end date")
    num_travelers: int = Field(default=1, ge=1, description="Number of travelers")

    pace: PaceLevel = Field(default=PaceLevel.MEDIUM, description="Trip pace")
    budget: BudgetLevel = Field(default=BudgetLevel.MEDIUM, description="Budget level")
    interests: list[str] = Field(default_factory=list, description="User interests (e.g., food, culture, nightlife)")

    daily_routine: DailyRoutine = Field(default_factory=DailyRoutine, description="Daily routine preferences")
    hotel_location: Optional[str] = Field(default=None, description="Hotel location or address")

    additional_preferences: dict = Field(default_factory=dict, description="Additional preferences from chat")

    created_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)
    updated_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)


class SkeletonBlock(BaseModel):
    """A time block within a day skeleton (high-level planning)."""
    block_type: BlockType = Field(description="Type of activity block")
    start_time: dt.time = Field(description="Block start time")
    end_time: dt.time = Field(description="Block end time")
    theme: Optional[str] = Field(default=None, description="Theme or category for this block")
    desired_categories: list[str] = Field(default_factory=list, description="Desired POI categories")


class DaySkeleton(BaseModel):
    """High-level skeleton for one day of the trip."""
    day_number: int = Field(ge=1, description="Day number in the trip")
    date: dt.date = Field(description="Date of this day")
    theme: str = Field(description="Overall theme for the day")
    blocks: list[SkeletonBlock] = Field(description="Time blocks for the day")


class POICandidate(BaseModel):
    """A candidate place of interest for a time block."""
    poi_id: UUID = Field(description="POI database ID")
    name: str = Field(description="POI name")
    category: str = Field(description="POI category")
    tags: list[str] = Field(default_factory=list, description="POI tags")
    rating: Optional[float] = Field(default=None, ge=0, le=5, description="Rating (0-5)")
    location: str = Field(description="Address or location")
    lat: Optional[float] = Field(default=None, description="Latitude coordinate")
    lon: Optional[float] = Field(default=None, description="Longitude coordinate")
    rank_score: float = Field(default=0.0, description="Ranking score for this candidate")


class ItineraryBlock(BaseModel):
    """A final itinerary block with selected POI and timing."""
    block_type: BlockType = Field(description="Type of activity block")
    start_time: dt.time = Field(description="Block start time")
    end_time: dt.time = Field(description="Block end time")
    poi: Optional[POICandidate] = Field(default=None, description="Selected POI")
    travel_time_from_prev: int = Field(default=0, description="Travel time from previous block in minutes")
    travel_distance_meters: Optional[int] = Field(default=None, description="Travel distance from previous block in meters")
    travel_polyline: Optional[str] = Field(default=None, description="Encoded polyline for route visualization")
    notes: Optional[str] = Field(default=None, description="Additional notes")


class ItineraryDay(BaseModel):
    """One day in the final itinerary."""
    day_number: int = Field(ge=1, description="Day number in the trip")
    date: dt.date = Field(description="Date of this day")
    theme: str = Field(description="Overall theme for the day")
    blocks: list[ItineraryBlock] = Field(description="Ordered blocks for the day")


class CritiqueIssue(BaseModel):
    """A validation issue found by the Trip Critic."""
    code: str = Field(description="Issue code for programmatic handling")
    severity: CritiqueIssueSeverity = Field(description="Issue severity")
    message: str = Field(description="Human-readable issue description")
    day_number: Optional[int] = Field(default=None, description="Day number if day-specific")
    block_index: Optional[int] = Field(default=None, description="Block index if block-specific")
    details: dict = Field(default_factory=dict, description="Additional issue-specific data")
