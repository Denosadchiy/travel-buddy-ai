"""
SQLAlchemy ORM models for database tables.
These are separate from domain models to maintain clean architecture.
"""
from sqlalchemy import Column, String, Integer, DateTime, JSON, Date, Float, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
from src.infrastructure.database import Base
from src.domain.models import PaceLevel, BudgetLevel


class TripModel(Base):
    """Database model for Trip (stores TripSpec)."""
    __tablename__ = "trips"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    city = Column(String, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    num_travelers = Column(Integer, nullable=False, default=1)

    pace = Column(SQLEnum(PaceLevel), nullable=False, default=PaceLevel.MEDIUM)
    budget = Column(SQLEnum(BudgetLevel), nullable=False, default=BudgetLevel.MEDIUM)
    interests = Column(JSON, nullable=False, default=list)

    daily_routine = Column(JSON, nullable=False)
    hotel_location = Column(String, nullable=True)
    additional_preferences = Column(JSON, nullable=False, default=dict)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class POIModel(Base):
    """Database model for Points of Interest."""
    __tablename__ = "pois"

    # Unique constraint on external_source + external_id to prevent duplicates
    __table_args__ = (
        UniqueConstraint('external_source', 'external_id', name='uq_pois_external_source_id'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    city = Column(String, nullable=False)
    category = Column(String, nullable=False)
    tags = Column(JSON, nullable=False, default=list)
    rating = Column(Float, nullable=True)
    location = Column(String, nullable=False)
    opening_hours = Column(JSON, nullable=True)  # Store as JSON for flexibility
    description = Column(String, nullable=True)

    # External source tracking (e.g., "google_places")
    external_source = Column(String, nullable=True, index=True)
    external_id = Column(String, nullable=True, index=True)  # e.g., Google place_id

    # Geolocation
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)

    # Price level (0-4, Google Places format)
    price_level = Column(Integer, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)


class ItineraryModel(Base):
    """Database model for storing generated itineraries."""
    __tablename__ = "itineraries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id = Column(UUID(as_uuid=True), nullable=False, index=True, unique=True)

    # Macro plan skeleton (list of DaySkeleton) - stored as JSON
    macro_plan = Column(JSON, nullable=True)
    macro_plan_created_at = Column(DateTime, nullable=True)

    # POI plan (list of POIPlanBlock) - stored as JSON
    poi_plan = Column(JSON, nullable=True)
    poi_plan_created_at = Column(DateTime, nullable=True)

    # Store the full itinerary as JSON (list of ItineraryDay)
    days = Column(JSON, nullable=True)
    itinerary_created_at = Column(DateTime, nullable=True)

    # Store critique issues as JSON (list of CritiqueIssue)
    critique_issues = Column(JSON, nullable=False, default=list)
    critique_created_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
