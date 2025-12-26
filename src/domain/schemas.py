"""
Request/Response schemas for API endpoints.
These schemas define the contract between the mobile app and the backend.
"""
from datetime import date, time
from typing import Optional, Any
from pydantic import BaseModel, Field
from uuid import UUID

from src.domain.models import (
    PaceLevel,
    BudgetLevel,
    DailyRoutine,
    DaySkeleton,
    SkeletonBlock,
    POICandidate,
    BlockType,
    ItineraryDay,
    CritiqueIssue,
    CritiqueIssueSeverity,
)


class DailyRoutineRequest(BaseModel):
    """Request schema for daily routine preferences."""
    wake_time: Optional[time] = Field(default=None, description="Wake up time")
    sleep_time: Optional[time] = Field(default=None, description="Sleep time")
    breakfast_window: Optional[tuple[time, time]] = Field(default=None, description="Breakfast time window")
    lunch_window: Optional[tuple[time, time]] = Field(default=None, description="Lunch time window")
    dinner_window: Optional[tuple[time, time]] = Field(default=None, description="Dinner time window")


class TripCreateRequest(BaseModel):
    """Request schema for creating a new trip (form submission)."""
    city: str = Field(description="Destination city", min_length=1, max_length=100)
    start_date: date = Field(description="Trip start date")
    end_date: date = Field(description="Trip end date")
    num_travelers: int = Field(default=1, ge=1, le=20, description="Number of travelers")

    pace: PaceLevel = Field(default=PaceLevel.MEDIUM, description="Trip pace")
    budget: BudgetLevel = Field(default=BudgetLevel.MEDIUM, description="Budget level")
    interests: list[str] = Field(default_factory=list, description="User interests")

    daily_routine: Optional[DailyRoutineRequest] = Field(default=None, description="Daily routine preferences")
    hotel_location: Optional[str] = Field(default=None, max_length=500, description="Hotel location or address")

    class Config:
        json_schema_extra = {
            "example": {
                "city": "Paris",
                "start_date": "2024-06-15",
                "end_date": "2024-06-20",
                "num_travelers": 2,
                "pace": "medium",
                "budget": "medium",
                "interests": ["food", "culture", "nightlife"],
                "daily_routine": {
                    "wake_time": "08:00:00",
                    "sleep_time": "23:00:00",
                    "breakfast_window": ["08:00:00", "10:00:00"],
                    "lunch_window": ["12:00:00", "14:00:00"],
                    "dinner_window": ["19:00:00", "22:00:00"]
                },
                "hotel_location": "Marais district, Paris"
            }
        }


class TripUpdateRequest(BaseModel):
    """Request schema for updating an existing trip (partial updates)."""
    city: Optional[str] = Field(default=None, min_length=1, max_length=100)
    start_date: Optional[date] = Field(default=None)
    end_date: Optional[date] = Field(default=None)
    num_travelers: Optional[int] = Field(default=None, ge=1, le=20)

    pace: Optional[PaceLevel] = Field(default=None)
    budget: Optional[BudgetLevel] = Field(default=None)
    interests: Optional[list[str]] = Field(default=None)

    daily_routine: Optional[DailyRoutineRequest] = Field(default=None)
    hotel_location: Optional[str] = Field(default=None, max_length=500)

    additional_preferences: Optional[dict] = Field(default=None, description="Additional preferences")

    class Config:
        json_schema_extra = {
            "example": {
                "pace": "fast",
                "interests": ["food", "culture", "nightlife", "techno parties"],
                "additional_preferences": {
                    "note": "We hate museums",
                    "music_preference": "techno"
                }
            }
        }


class DailyRoutineResponse(BaseModel):
    """Response schema for daily routine."""
    wake_time: time
    sleep_time: time
    breakfast_window: tuple[time, time]
    lunch_window: tuple[time, time]
    dinner_window: tuple[time, time]


class TripResponse(BaseModel):
    """Response schema for trip data (TripSpec state)."""
    id: UUID = Field(description="Unique trip ID")
    city: str
    start_date: date
    end_date: date
    num_travelers: int

    pace: PaceLevel
    budget: BudgetLevel
    interests: list[str]

    daily_routine: DailyRoutineResponse
    hotel_location: Optional[str] = None

    additional_preferences: dict

    created_at: str = Field(description="ISO 8601 timestamp")
    updated_at: str = Field(description="ISO 8601 timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "city": "Paris",
                "start_date": "2024-06-15",
                "end_date": "2024-06-20",
                "num_travelers": 2,
                "pace": "medium",
                "budget": "medium",
                "interests": ["food", "culture", "nightlife"],
                "daily_routine": {
                    "wake_time": "08:00:00",
                    "sleep_time": "23:00:00",
                    "breakfast_window": ["08:00:00", "10:00:00"],
                    "lunch_window": ["12:00:00", "14:00:00"],
                    "dinner_window": ["19:00:00", "22:00:00"]
                },
                "hotel_location": "Marais district, Paris",
                "additional_preferences": {},
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:30:00Z"
            }
        }


# Trip Chat Schemas

class TripChatRequest(BaseModel):
    """Request schema for trip chat messages."""
    message: str = Field(description="User's natural language message", min_length=1, max_length=1000)

    class Config:
        json_schema_extra = {
            "example": {
                "message": "We hate museums, we love techno nightlife, and we prefer vegetarian food"
            }
        }


class TripChatLLMResponse(BaseModel):
    """
    Structured response from LLM in Trip Chat Mode.
    The LLM is expected to return JSON matching this schema.
    """
    assistant_message: str = Field(description="Friendly reply to the user")
    trip_updates: dict[str, Any] = Field(
        default_factory=dict,
        description="Fields to update in TripSpec (e.g., interests, additional_preferences)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "assistant_message": "Got it! I'll avoid museums and focus on techno clubs and vegetarian-friendly places.",
                "trip_updates": {
                    "interests": ["techno", "nightlife", "food"],
                    "additional_preferences": {
                        "avoid": ["museums"],
                        "dietary": ["vegetarian"],
                        "music": "techno"
                    }
                }
            }
        }


class TripChatResponse(BaseModel):
    """Response schema for trip chat endpoint."""
    assistant_message: str = Field(description="Assistant's reply to the user")
    trip: TripResponse = Field(description="Updated trip data")

    class Config:
        json_schema_extra = {
            "example": {
                "assistant_message": "Got it! I'll avoid museums and focus on techno clubs and vegetarian-friendly places.",
                "trip": {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "city": "Paris",
                    "start_date": "2024-06-15",
                    "end_date": "2024-06-20",
                    "num_travelers": 2,
                    "pace": "medium",
                    "budget": "medium",
                    "interests": ["techno", "nightlife", "food"],
                    "daily_routine": {
                        "wake_time": "08:00:00",
                        "sleep_time": "23:00:00",
                        "breakfast_window": ["08:00:00", "10:00:00"],
                        "lunch_window": ["12:00:00", "14:00:00"],
                        "dinner_window": ["19:00:00", "22:00:00"]
                    },
                    "hotel_location": "Marais district, Paris",
                    "additional_preferences": {
                        "avoid": ["museums"],
                        "dietary": ["vegetarian"],
                        "music": "techno"
                    },
                    "created_at": "2024-01-15T10:30:00Z",
                    "updated_at": "2024-01-15T11:00:00Z"
                }
            }
        }


# Macro Planning Schemas

class MacroPlanResponse(BaseModel):
    """Response schema for macro plan (trip skeleton)."""
    trip_id: UUID = Field(description="Trip ID this plan belongs to")
    days: list[DaySkeleton] = Field(description="Daily skeletons for the trip")
    created_at: str = Field(description="ISO 8601 timestamp when plan was created")

    class Config:
        json_schema_extra = {
            "example": {
                "trip_id": "550e8400-e29b-41d4-a716-446655440000",
                "days": [
                    {
                        "day_number": 1,
                        "date": "2024-06-15",
                        "theme": "Historic Center & Local Food",
                        "blocks": [
                            {
                                "block_type": "meal",
                                "start_time": "08:30:00",
                                "end_time": "09:30:00",
                                "theme": "Breakfast",
                                "desired_categories": ["cafe", "breakfast", "bakery"]
                            },
                            {
                                "block_type": "activity",
                                "start_time": "10:00:00",
                                "end_time": "13:00:00",
                                "theme": "Historic landmarks",
                                "desired_categories": ["landmark", "architecture", "culture"]
                            },
                            {
                                "block_type": "meal",
                                "start_time": "13:00:00",
                                "end_time": "14:30:00",
                                "theme": "Lunch",
                                "desired_categories": ["restaurant", "local cuisine"]
                            },
                            {
                                "block_type": "activity",
                                "start_time": "15:00:00",
                                "end_time": "18:00:00",
                                "theme": "Shopping and cafes",
                                "desired_categories": ["shopping", "cafe", "local market"]
                            },
                            {
                                "block_type": "meal",
                                "start_time": "19:30:00",
                                "end_time": "21:30:00",
                                "theme": "Dinner",
                                "desired_categories": ["restaurant", "fine dining"]
                            }
                        ]
                    },
                    {
                        "day_number": 2,
                        "date": "2024-06-16",
                        "theme": "Parks & Nightlife",
                        "blocks": [
                            {
                                "block_type": "meal",
                                "start_time": "09:00:00",
                                "end_time": "10:00:00",
                                "theme": "Breakfast",
                                "desired_categories": ["cafe", "breakfast"]
                            },
                            {
                                "block_type": "activity",
                                "start_time": "10:30:00",
                                "end_time": "13:00:00",
                                "theme": "Parks and views",
                                "desired_categories": ["park", "viewpoint", "nature"]
                            },
                            {
                                "block_type": "meal",
                                "start_time": "13:30:00",
                                "end_time": "15:00:00",
                                "theme": "Lunch",
                                "desired_categories": ["restaurant", "outdoor seating"]
                            },
                            {
                                "block_type": "rest",
                                "start_time": "15:00:00",
                                "end_time": "17:00:00",
                                "theme": "Rest at hotel",
                                "desired_categories": []
                            },
                            {
                                "block_type": "meal",
                                "start_time": "20:00:00",
                                "end_time": "22:00:00",
                                "theme": "Dinner",
                                "desired_categories": ["restaurant", "local cuisine"]
                            },
                            {
                                "block_type": "nightlife",
                                "start_time": "23:00:00",
                                "end_time": "02:00:00",
                                "theme": "Techno nightlife",
                                "desired_categories": ["nightlife", "techno", "club"]
                            }
                        ]
                    }
                ],
                "created_at": "2024-01-15T12:00:00Z"
            }
        }


# POI Planning Schemas

class POIPlanBlock(BaseModel):
    """POI candidates for a single block in the itinerary."""
    day_number: int = Field(ge=1, description="Day number in the trip")
    block_index: int = Field(ge=0, description="Index of block within the day")
    block_theme: str = Field(description="Theme or description of this block")
    block_type: BlockType = Field(description="Type of block")
    candidates: list[POICandidate] = Field(description="Candidate POIs for this block")

    class Config:
        json_schema_extra = {
            "example": {
                "day_number": 1,
                "block_index": 1,
                "block_theme": "Historic landmarks",
                "block_type": "activity",
                "candidates": [
                    {
                        "poi_id": "550e8400-e29b-41d4-a716-446655440001",
                        "name": "Eiffel Tower",
                        "category": "attraction",
                        "tags": ["landmark", "culture", "views", "iconic"],
                        "rating": 4.7,
                        "location": "Champ de Mars, 5 Avenue Anatole France, 75007 Paris",
                        "lat": 48.8584,
                        "lon": 2.2945,
                        "rank_score": 18.7
                    },
                    {
                        "poi_id": "550e8400-e29b-41d4-a716-446655440002",
                        "name": "Louvre Museum",
                        "category": "museum",
                        "tags": ["culture", "art", "museum", "history"],
                        "rating": 4.8,
                        "location": "Rue de Rivoli, 75001 Paris",
                        "lat": 48.8606,
                        "lon": 2.3376,
                        "rank_score": 16.8
                    },
                    {
                        "poi_id": "550e8400-e29b-41d4-a716-446655440003",
                        "name": "Sacré-Cœur Basilica",
                        "category": "attraction",
                        "tags": ["culture", "architecture", "views", "religious"],
                        "rating": 4.7,
                        "location": "35 Rue du Chevalier de la Barre, 75018 Paris",
                        "lat": 48.8867,
                        "lon": 2.3431,
                        "rank_score": 16.7
                    }
                ]
            }
        }


class POIPlanResponse(BaseModel):
    """Response schema for POI plan."""
    trip_id: UUID = Field(description="Trip ID this plan belongs to")
    blocks: list[POIPlanBlock] = Field(description="POI candidates for each block")
    created_at: str = Field(description="ISO 8601 timestamp when plan was created")

    class Config:
        json_schema_extra = {
            "example": {
                "trip_id": "550e8400-e29b-41d4-a716-446655440000",
                "blocks": [
                    {
                        "day_number": 1,
                        "block_index": 0,
                        "block_theme": "Breakfast",
                        "block_type": "meal",
                        "candidates": [
                            {
                                "poi_id": "a1b2c3d4-e5f6-4g7h-8i9j-0k1l2m3n4o5p",
                                "name": "Café de Flore",
                                "category": "cafe",
                                "tags": ["cafe", "breakfast", "historic"],
                                "rating": 4.3,
                                "location": "172 Boulevard Saint-Germain, 75006 Paris",
                                "rank_score": 14.3
                            }
                        ]
                    },
                    {
                        "day_number": 1,
                        "block_index": 1,
                        "block_theme": "Historic landmarks",
                        "block_type": "activity",
                        "candidates": [
                            {
                                "poi_id": "550e8400-e29b-41d4-a716-446655440001",
                                "name": "Eiffel Tower",
                                "category": "attraction",
                                "tags": ["landmark", "culture", "views", "iconic"],
                                "rating": 4.7,
                                "location": "Champ de Mars, 5 Avenue Anatole France, 75007 Paris",
                                "rank_score": 18.7
                            },
                            {
                                "poi_id": "550e8400-e29b-41d4-a716-446655440002",
                                "name": "Louvre Museum",
                                "category": "museum",
                                "tags": ["culture", "art", "museum", "history"],
                                "rating": 4.8,
                                "location": "Rue de Rivoli, 75001 Paris",
                                "rank_score": 16.8
                            }
                        ]
                    }
                ],
                "created_at": "2024-01-15T13:00:00Z"
            }
        }


# Final Itinerary Schemas

class ItineraryResponse(BaseModel):
    """Response schema for final trip itinerary."""
    trip_id: UUID = Field(description="Trip ID this itinerary belongs to")
    days: list[ItineraryDay] = Field(description="Complete itinerary days with selected POIs and timing")
    created_at: str = Field(description="ISO 8601 timestamp when itinerary was created")

    class Config:
        json_schema_extra = {
            "example": {
                "trip_id": "550e8400-e29b-41d4-a716-446655440000",
                "days": [
                    {
                        "day_number": 1,
                        "date": "2024-06-15",
                        "theme": "Historic Center & Local Food",
                        "blocks": [
                            {
                                "block_type": "meal",
                                "start_time": "08:30:00",
                                "end_time": "09:30:00",
                                "poi": {
                                    "poi_id": "a1b2c3d4-e5f6-4g7h-8i9j-0k1l2m3n4o5p",
                                    "name": "Café de Flore",
                                    "category": "cafe",
                                    "tags": ["cafe", "breakfast", "historic"],
                                    "rating": 4.3,
                                    "location": "172 Boulevard Saint-Germain, 75006 Paris",
                                    "lat": 48.8540,
                                    "lon": 2.3325,
                                    "rank_score": 14.3
                                },
                                "travel_time_from_prev": 0,
                                "travel_distance_meters": None,
                                "travel_polyline": None,
                                "notes": None
                            },
                            {
                                "block_type": "activity",
                                "start_time": "10:00:00",
                                "end_time": "13:00:00",
                                "poi": {
                                    "poi_id": "550e8400-e29b-41d4-a716-446655440001",
                                    "name": "Eiffel Tower",
                                    "category": "attraction",
                                    "tags": ["landmark", "culture", "views", "iconic"],
                                    "rating": 4.7,
                                    "location": "Champ de Mars, 5 Avenue Anatole France, 75007 Paris",
                                    "lat": 48.8584,
                                    "lon": 2.2945,
                                    "rank_score": 18.7
                                },
                                "travel_time_from_prev": 15,
                                "travel_distance_meters": 3200,
                                "travel_polyline": "a~l~Fjk~uOwHJy@P",
                                "notes": None
                            },
                            {
                                "block_type": "meal",
                                "start_time": "13:00:00",
                                "end_time": "14:30:00",
                                "poi": {
                                    "poi_id": "b2c3d4e5-f6g7-h8i9-j0k1-l2m3n4o5p6q7",
                                    "name": "Le Comptoir du Relais",
                                    "category": "restaurant",
                                    "tags": ["restaurant", "french cuisine", "local"],
                                    "rating": 4.5,
                                    "location": "9 Carrefour de l'Odéon, 75006 Paris",
                                    "lat": 48.8520,
                                    "lon": 2.3390,
                                    "rank_score": 15.5
                                },
                                "travel_time_from_prev": 12,
                                "travel_distance_meters": 2800,
                                "travel_polyline": "g~l~Fhk~uOvHJx@Q",
                                "notes": None
                            },
                            {
                                "block_type": "rest",
                                "start_time": "14:30:00",
                                "end_time": "16:00:00",
                                "poi": None,
                                "travel_time_from_prev": 0,
                                "travel_distance_meters": None,
                                "travel_polyline": None,
                                "notes": "Rest at hotel"
                            },
                            {
                                "block_type": "activity",
                                "start_time": "16:00:00",
                                "end_time": "18:00:00",
                                "poi": {
                                    "poi_id": "c3d4e5f6-g7h8-i9j0-k1l2-m3n4o5p6q7r8",
                                    "name": "Marais Shopping District",
                                    "category": "shopping",
                                    "tags": ["shopping", "local market", "boutiques"],
                                    "rating": 4.6,
                                    "location": "Le Marais, 75004 Paris",
                                    "lat": 48.8566,
                                    "lon": 2.3622,
                                    "rank_score": 14.6
                                },
                                "travel_time_from_prev": 18,
                                "travel_distance_meters": 4100,
                                "travel_polyline": "k~l~Fjk~uOwHJy@P",
                                "notes": None
                            },
                            {
                                "block_type": "meal",
                                "start_time": "19:30:00",
                                "end_time": "21:30:00",
                                "poi": {
                                    "poi_id": "d4e5f6g7-h8i9-j0k1-l2m3-n4o5p6q7r8s9",
                                    "name": "L'Astrance",
                                    "category": "restaurant",
                                    "tags": ["fine dining", "michelin star", "french cuisine"],
                                    "rating": 4.8,
                                    "location": "4 Rue Beethoven, 75016 Paris",
                                    "lat": 48.8599,
                                    "lon": 2.2866,
                                    "rank_score": 19.8
                                },
                                "travel_time_from_prev": 20,
                                "travel_distance_meters": 5200,
                                "travel_polyline": "m~l~Fhk~uOvHJx@Q",
                                "notes": None
                            }
                        ]
                    },
                    {
                        "day_number": 2,
                        "date": "2024-06-16",
                        "theme": "Parks & Nightlife",
                        "blocks": [
                            {
                                "block_type": "meal",
                                "start_time": "09:00:00",
                                "end_time": "10:00:00",
                                "poi": {
                                    "poi_id": "e5f6g7h8-i9j0-k1l2-m3n4-o5p6q7r8s9t0",
                                    "name": "Hollybelly 5",
                                    "category": "cafe",
                                    "tags": ["cafe", "breakfast", "brunch"],
                                    "rating": 4.4,
                                    "location": "5 Rue Lucien Sampaix, 75010 Paris",
                                    "lat": 48.8715,
                                    "lon": 2.3611,
                                    "rank_score": 14.4
                                },
                                "travel_time_from_prev": 0,
                                "travel_distance_meters": None,
                                "travel_polyline": None,
                                "notes": None
                            },
                            {
                                "block_type": "activity",
                                "start_time": "10:30:00",
                                "end_time": "13:00:00",
                                "poi": {
                                    "poi_id": "f6g7h8i9-j0k1-l2m3-n4o5-p6q7r8s9t0u1",
                                    "name": "Luxembourg Gardens",
                                    "category": "park",
                                    "tags": ["park", "nature", "viewpoint", "relaxation"],
                                    "rating": 4.7,
                                    "location": "6th arrondissement, 75006 Paris",
                                    "lat": 48.8462,
                                    "lon": 2.3372,
                                    "rank_score": 17.7
                                },
                                "travel_time_from_prev": 14,
                                "travel_distance_meters": 3100,
                                "travel_polyline": "a~l~Fjk~uOwHJy@P",
                                "notes": None
                            },
                            {
                                "block_type": "meal",
                                "start_time": "13:30:00",
                                "end_time": "15:00:00",
                                "poi": {
                                    "poi_id": "g7h8i9j0-k1l2-m3n4-o5p6-q7r8s9t0u1v2",
                                    "name": "Chez Janou",
                                    "category": "restaurant",
                                    "tags": ["restaurant", "provencal cuisine", "outdoor seating"],
                                    "rating": 4.4,
                                    "location": "2 Rue Roger Verlomme, 75003 Paris",
                                    "lat": 48.8552,
                                    "lon": 2.3650,
                                    "rank_score": 14.4
                                },
                                "travel_time_from_prev": 11,
                                "travel_distance_meters": 2400,
                                "travel_polyline": "g~l~Fhk~uOvHJx@Q",
                                "notes": None
                            },
                            {
                                "block_type": "rest",
                                "start_time": "15:00:00",
                                "end_time": "17:00:00",
                                "poi": None,
                                "travel_time_from_prev": 0,
                                "travel_distance_meters": None,
                                "travel_polyline": None,
                                "notes": "Rest at hotel"
                            },
                            {
                                "block_type": "meal",
                                "start_time": "20:00:00",
                                "end_time": "22:00:00",
                                "poi": {
                                    "poi_id": "h8i9j0k1-l2m3-n4o5-p6q7-r8s9t0u1v2w3",
                                    "name": "Bouillon Chartier",
                                    "category": "restaurant",
                                    "tags": ["restaurant", "traditional", "local cuisine", "historic"],
                                    "rating": 4.2,
                                    "location": "7 Rue du Faubourg Montmartre, 75009 Paris",
                                    "lat": 48.8728,
                                    "lon": 2.3422,
                                    "rank_score": 14.2
                                },
                                "travel_time_from_prev": 16,
                                "travel_distance_meters": 3600,
                                "travel_polyline": "k~l~Fjk~uOwHJy@P",
                                "notes": None
                            },
                            {
                                "block_type": "nightlife",
                                "start_time": "23:00:00",
                                "end_time": "02:00:00",
                                "poi": {
                                    "poi_id": "i9j0k1l2-m3n4-o5p6-q7r8-s9t0u1v2w3x4",
                                    "name": "Concrete Club",
                                    "category": "nightclub",
                                    "tags": ["nightlife", "techno", "club", "electronic music"],
                                    "rating": 4.5,
                                    "location": "69 Rue de la Râpée, 75012 Paris",
                                    "lat": 48.8462,
                                    "lon": 2.3667,
                                    "rank_score": 19.5
                                },
                                "travel_time_from_prev": 19,
                                "travel_distance_meters": 4200,
                                "travel_polyline": "m~l~Fhk~uOvHJx@Q",
                                "notes": None
                            }
                        ]
                    }
                ],
                "created_at": "2024-01-15T14:00:00Z"
            }
        }


# Critique Schemas

class CritiqueIssueSchema(BaseModel):
    """Schema for a single critique issue."""
    code: str = Field(description="Issue code for programmatic handling")
    severity: CritiqueIssueSeverity = Field(description="Issue severity")
    message: str = Field(description="Human-readable issue description")
    day_number: Optional[int] = Field(default=None, description="Day number if day-specific")
    block_index: Optional[int] = Field(default=None, description="Block index if block-specific")
    details: dict = Field(default_factory=dict, description="Additional issue-specific data")

    class Config:
        json_schema_extra = {
            "example": {
                "code": "DAY_TOO_BUSY",
                "severity": "warning",
                "message": "Day 1 has 11.5 hours of activities, which may be too intense for a slow pace.",
                "day_number": 1,
                "block_index": None,
                "details": {
                    "active_hours": 11.5,
                    "pace": "slow",
                    "threshold": 7.0
                }
            }
        }


class CritiqueResponse(BaseModel):
    """Response schema for trip critique."""
    trip_id: UUID = Field(description="Trip ID this critique belongs to")
    issues: list[CritiqueIssueSchema] = Field(description="List of critique issues")
    total_issues: int = Field(description="Total number of issues")
    by_severity: dict[str, int] = Field(description="Count of issues by severity")
    created_at: Optional[str] = Field(default=None, description="ISO 8601 timestamp when critique was created")

    class Config:
        json_schema_extra = {
            "example": {
                "trip_id": "550e8400-e29b-41d4-a716-446655440000",
                "issues": [
                    {
                        "code": "DAY_TOO_BUSY",
                        "severity": "warning",
                        "message": "Day 1 has 11.5 hours of activities, which may be too intense for a slow pace.",
                        "day_number": 1,
                        "block_index": None,
                        "details": {
                            "active_hours": 11.5,
                            "pace": "slow",
                            "threshold": 7.0
                        }
                    },
                    {
                        "code": "MISSING_DINNER",
                        "severity": "warning",
                        "message": "Day 2 is missing a dinner.",
                        "day_number": 2,
                        "block_index": None,
                        "details": {
                            "meal_type": "dinner"
                        }
                    },
                    {
                        "code": "LONG_TRAVEL",
                        "severity": "warning",
                        "message": "Day 1, block 3: Long travel time (60 minutes) from previous location.",
                        "day_number": 1,
                        "block_index": 3,
                        "details": {
                            "travel_time_minutes": 60,
                            "threshold": 45
                        }
                    },
                    {
                        "code": "LATE_NIGHTLIFE",
                        "severity": "info",
                        "message": "Day 2: Nightlife ends 3.0 hours after your usual sleep time.",
                        "day_number": 2,
                        "block_index": 5,
                        "details": {
                            "nightlife_end": "02:00:00",
                            "sleep_time": "23:00:00",
                            "hours_past_sleep": 3.0
                        }
                    }
                ],
                "total_issues": 4,
                "by_severity": {
                    "info": 1,
                    "warning": 3,
                    "error": 0
                },
                "created_at": "2024-01-15T14:30:00Z"
            }
        }
