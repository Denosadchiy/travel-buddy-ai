"""
SQLAlchemy ORM models for database tables.
These are separate from domain models to maintain clean architecture.
"""
from sqlalchemy import (
    String,
    Integer,
    DateTime,
    JSON,
    Date,
    Float,
    Text,
    Enum as SQLEnum,
    UniqueConstraint,
    Boolean,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, date
import uuid
from typing import Optional, Any

from src.infrastructure.database import Base
from src.infrastructure.db_types import GUID, StringList
from src.domain.models import PaceLevel, BudgetLevel


class TripModel(Base):
    """Database model for Trip (stores TripSpec)."""
    __tablename__ = "trips"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    city: Mapped[str] = mapped_column(String, nullable=False)
    city_geoname_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    city_center_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    city_center_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    num_travelers: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Ownership - a trip belongs to either a user or a guest device
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True, index=True)
    device_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    is_legacy_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    pace: Mapped[PaceLevel] = mapped_column(SQLEnum(PaceLevel), nullable=False, default=PaceLevel.MEDIUM)
    budget: Mapped[BudgetLevel] = mapped_column(SQLEnum(BudgetLevel), nullable=False, default=BudgetLevel.MEDIUM)
    interests: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    daily_routine: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    hotel_location: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    hotel_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hotel_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    additional_preferences: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    structured_preferences: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, nullable=True, default=[])

    city_photo_reference: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class CityModel(Base):
    """Database model for canonical world cities (GeoNames)."""
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    geoname_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_ascii: Mapped[str] = mapped_column(Text, nullable=False)
    alternate_names: Mapped[list[str]] = mapped_column(StringList(), nullable=False, default=list)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    country_name: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    population: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timezone: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class POIModel(Base):
    """Database model for Points of Interest."""
    __tablename__ = "pois"

    # Unique constraint on external_source + external_id to prevent duplicates
    __table_args__ = (
        UniqueConstraint('external_source', 'external_id', name='uq_pois_external_source_id'),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    city: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    user_ratings_total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    location: Mapped[str] = mapped_column(String, nullable=False)
    opening_hours: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    reviews: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True, default=[])
    business_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # External source tracking (e.g., "google_places")
    external_source: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

    # Geolocation
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Price level (0-4, Google Places format)
    price_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, onupdate=datetime.utcnow)


class ItineraryModel(Base):
    """Database model for storing generated itineraries."""
    __tablename__ = "itineraries"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True, unique=True)

    # Macro plan skeleton (list of DaySkeleton) - stored as JSON
    macro_plan: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    macro_plan_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # POI plan (list of POIPlanBlock) - stored as JSON
    poi_plan: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    poi_plan_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Store the full itinerary as JSON (list of ItineraryDay)
    days: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    itinerary_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Store critique issues as JSON (list of CritiqueIssue)
    critique_issues: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    critique_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class DayStudioSettingsModel(Base):
    """Database model for day-level studio settings and state."""
    __tablename__ = "day_studio_settings"

    __table_args__ = (
        UniqueConstraint('trip_id', 'day_number', name='uq_day_studio_trip_day'),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Settings
    tempo: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # low, medium, high
    start_time: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # HH:MM
    end_time: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # HH:MM
    budget: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # low, medium, high
    preset: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Revision for optimistic locking
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class DayWishMessageModel(Base):
    """Database model for wish messages in day studio chat."""
    __tablename__ = "day_wish_messages"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)

    role: Mapped[str] = mapped_column(String, nullable=False)  # "user" or "assistant"
    text: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class DayAISummaryModel(Base):
    """Database model for cached AI summaries."""
    __tablename__ = "day_ai_summaries"

    __table_args__ = (
        UniqueConstraint('trip_id', 'day_number', 'input_hash', name='uq_day_summary_hash'),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Hash of input parameters for cache lookup
    input_hash: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # Generated summary
    summary_text: Mapped[str] = mapped_column(String, nullable=False)

    # Revision when this summary was generated
    revision: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SavedTripModel(Base):
    """Database model for user-saved trips (bookmarks)."""
    __tablename__ = "saved_trips"

    __table_args__ = (
        UniqueConstraint('user_id', 'trip_id', name='uq_saved_trips_user_trip'),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    trip_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    city_name: Mapped[str] = mapped_column(String, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    hero_image_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    route_snapshot: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class LocalizationEntryModel(Base):
    """
    Persistent localization store for translated key/value pairs.

    One row per (translation_key, locale), with status and source hash metadata
    to support machine-translation + human-review workflows.
    """

    __tablename__ = "localization_entries"

    __table_args__ = (
        UniqueConstraint(
            "translation_key",
            "locale",
            name="uq_localization_entries_key_locale",
        ),
        Index("ix_localization_entries_translation_key", "translation_key"),
        Index("ix_localization_entries_locale", "locale"),
        Index("ix_localization_entries_status", "status"),
        Index("ix_localization_entries_source_hash", "source_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    translation_key: Mapped[str] = mapped_column(String, nullable=False)
    locale: Mapped[str] = mapped_column(String(32), nullable=False)
    source_language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    source_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class LocalizationJobModel(Base):
    """
    Persistent translation queue for asynchronous machine-translation jobs.

    One row per (translation_key, target_locale, source_hash).
    """

    __tablename__ = "localization_jobs"

    __table_args__ = (
        UniqueConstraint(
            "translation_key",
            "target_locale",
            "source_hash",
            name="uq_localization_jobs_key_locale_hash",
        ),
        Index("ix_localization_jobs_status", "status"),
        Index("ix_localization_jobs_next_attempt_at", "next_attempt_at"),
        Index("ix_localization_jobs_target_locale", "target_locale"),
        Index("ix_localization_jobs_translation_key", "translation_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    translation_key: Mapped[str] = mapped_column(String, nullable=False)
    target_locale: Mapped[str] = mapped_column(String(32), nullable=False)
    source_locale: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
