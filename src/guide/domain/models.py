"""
SQLAlchemy ORM models for all guide_* tables (Live Audio Guide module).

All 19 models mirror alembic/versions/009_add_live_guide.py exactly.
PostGIS geometry columns use GeoAlchemy2 (Geometry type).
Do NOT add business logic here — columns and relationships only.

Partial UNIQUE indexes on guide_content_blocks are managed by migration only
(not reflected in ORM __table_args__). Names for upsert ON CONFLICT clauses:
  - idx_guide_content_uq_no_edge   (edge_id IS NULL)
  - idx_guide_content_uq_with_edge (edge_id IS NOT NULL)
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database import Base
from src.infrastructure.db_types import GUID


# ============================================================================
# 1. GuideCity
# ============================================================================

class GuideCity(Base):
    """Cities index — root of the guide geography hierarchy."""

    __tablename__ = "guide_cities"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    name_local: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    country: Mapped[str] = mapped_column(String, nullable=False)
    center: Mapped[Any] = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    timezone: Mapped[str] = mapped_column(String, nullable=False, default="UTC")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    zones: Mapped[list[GuideZone]] = relationship("GuideZone", back_populates="city")
    seed_jobs: Mapped[list[GuideSeedJob]] = relationship("GuideSeedJob", back_populates="city")


# ============================================================================
# 2. GuideZone
# ============================================================================

class GuideZone(Base):
    """Coverage polygons — walkable tourist zones within a city."""

    __tablename__ = "guide_zones"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    city_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("guide_cities.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    theme: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    boundary: Mapped[Any] = mapped_column(Geometry("POLYGON", srid=4326), nullable=False)
    poi_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    point_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    city: Mapped[GuideCity] = relationship("GuideCity", back_populates="zones")
    points: Mapped[list[GuidePoint]] = relationship("GuidePoint", back_populates="zone")
    content_blocks: Mapped[list[GuideContentBlock]] = relationship("GuideContentBlock", back_populates="zone")
    content_jobs: Mapped[list[GuideContentJob]] = relationship("GuideContentJob", back_populates="zone")
    sessions: Mapped[list[GuideSession]] = relationship("GuideSession", back_populates="zone")


# ============================================================================
# 3. GuidePoint
# ============================================================================

class GuidePoint(Base):
    """Graph nodes — POI landmarks and connector path nodes within a zone."""

    __tablename__ = "guide_points"

    __table_args__ = (
        UniqueConstraint("zone_id", "google_place_id", name="uq_guide_points_zone_google"),
        UniqueConstraint("zone_id", "osm_node_id", name="uq_guide_points_zone_osm"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    zone_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("guide_zones.id", ondelete="CASCADE"), nullable=False)
    location: Mapped[Any] = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    trigger_radius_m: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    # point_type: 'poi' | 'connector'
    point_type: Mapped[str] = mapped_column(String, nullable=False, default="poi")
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    google_place_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    osm_node_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    is_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    zone: Mapped[GuideZone] = relationship("GuideZone", back_populates="points")
    knowledge_card: Mapped[Optional[GuideKnowledgeCard]] = relationship(
        "GuideKnowledgeCard", back_populates="point", uselist=False
    )
    content_blocks: Mapped[list[GuideContentBlock]] = relationship(
        "GuideContentBlock", back_populates="point", foreign_keys="[GuideContentBlock.point_id]"
    )
    outgoing_edges: Mapped[list[GuideEdge]] = relationship(
        "GuideEdge", back_populates="from_point", foreign_keys="[GuideEdge.from_point_id]"
    )
    incoming_edges: Mapped[list[GuideEdge]] = relationship(
        "GuideEdge", back_populates="to_point", foreign_keys="[GuideEdge.to_point_id]"
    )
    visits: Mapped[list[GuideSessionVisit]] = relationship("GuideSessionVisit", back_populates="point")
    qa_entries: Mapped[list[GuideSessionQA]] = relationship("GuideSessionQA", back_populates="point")


# ============================================================================
# 4. GuideEdge
# ============================================================================

class GuideEdge(Base):
    """Directed pedestrian-graph edges connecting guide_points within a zone."""

    __tablename__ = "guide_edges"

    __table_args__ = (
        UniqueConstraint("from_point_id", "to_point_id", name="uq_guide_edges_from_to"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    from_point_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("guide_points.id", ondelete="CASCADE"), nullable=False
    )
    to_point_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("guide_points.id", ondelete="CASCADE"), nullable=False
    )
    distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    walk_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    bearing_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    from_point: Mapped[GuidePoint] = relationship(
        "GuidePoint", back_populates="outgoing_edges", foreign_keys=[from_point_id]
    )
    to_point: Mapped[GuidePoint] = relationship(
        "GuidePoint", back_populates="incoming_edges", foreign_keys=[to_point_id]
    )
    content_blocks: Mapped[list[GuideContentBlock]] = relationship("GuideContentBlock", back_populates="edge")


# ============================================================================
# 5. GuideKnowledgeCard
# ============================================================================

class GuideKnowledgeCard(Base):
    """Raw knowledge collected by City Seeder — inputs for LLM narrative generation."""

    __tablename__ = "guide_knowledge_cards"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    point_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("guide_points.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    # card_type: 'poi' | 'street_context'
    card_type: Mapped[str] = mapped_column(String, nullable=False, default="poi")
    google_place_data: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    # street_name populated for connector/street_context cards
    street_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    wikipedia_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    wikidata_facts: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    enriched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    point: Mapped[GuidePoint] = relationship("GuidePoint", back_populates="knowledge_card")


# ============================================================================
# 6. GuideVoice
# ============================================================================

class GuideVoice(Base):
    """Narrator personas — 4 styles × 2 languages = 8 seeded rows."""

    __tablename__ = "guide_voices"

    __table_args__ = (
        UniqueConstraint("style_group", "language", name="uq_guide_voices_style_group_lang"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # style_group: 'academic' | 'friendly' | 'dramatic' | 'minimal'
    # Named style_group (not style) from the start to avoid a rename migration.
    style_group: Mapped[str] = mapped_column(String, nullable=False)
    language: Mapped[str] = mapped_column(String, nullable=False, default="en")
    elevenlabs_voice_id: Mapped[str] = mapped_column(String, nullable=False)
    preview_audio_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    content_blocks: Mapped[list[GuideContentBlock]] = relationship("GuideContentBlock", back_populates="voice")
    content_jobs: Mapped[list[GuideContentJob]] = relationship("GuideContentJob", back_populates="voice")
    sessions: Mapped[list[GuideSession]] = relationship("GuideSession", back_populates="voice")
    user_preferences: Mapped[list[GuideUserPreference]] = relationship("GuideUserPreference", back_populates="preferred_voice")


# ============================================================================
# 7. GuideContentBlock
# ============================================================================

class GuideContentBlock(Base):
    """Text + audio per (point × voice × language × detail_level × content_type × variant).

    zone_id is denormalized from guide_points.zone_id at insert time.
    Partial UNIQUE indexes managed by migration (not ORM __table_args__):
      - idx_guide_content_uq_no_edge   WHERE edge_id IS NULL
      - idx_guide_content_uq_with_edge WHERE edge_id IS NOT NULL
    Pass the correct index name to ON CONFLICT clauses in upsert calls.
    """

    __tablename__ = "guide_content_blocks"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    point_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("guide_points.id", ondelete="CASCADE"), nullable=False
    )
    # Denormalized — copied from guide_points.zone_id at insert time
    zone_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("guide_zones.id"), nullable=False)
    voice_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("guide_voices.id"), nullable=False)
    language: Mapped[str] = mapped_column(String, nullable=False, default="en")
    # detail_level: 'brief' | 'standard'
    detail_level: Mapped[str] = mapped_column(String, nullable=False, default="standard")
    # content_type: 'main' | 'bonus' | 'transition' | 'zone_transition' | 'recap'
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    # edge_id is set only for transition/zone_transition blocks
    edge_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), ForeignKey("guide_edges.id"), nullable=True)
    variant_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text_script: Mapped[str] = mapped_column(Text, nullable=False)
    audio_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    audio_duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # generation_status pipeline: pending → draft → validated → needs_manual_review
    #   → reviewed → synthesizing → synthesized → failed
    generation_status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    # coherence_score: 1–5 from LLM validator (transitions ≥ 4.0; others ≥ 3.5)
    coherence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    synthesized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    point: Mapped[GuidePoint] = relationship(
        "GuidePoint", back_populates="content_blocks", foreign_keys=[point_id]
    )
    zone: Mapped[GuideZone] = relationship("GuideZone", back_populates="content_blocks")
    voice: Mapped[GuideVoice] = relationship("GuideVoice", back_populates="content_blocks")
    edge: Mapped[Optional[GuideEdge]] = relationship("GuideEdge", back_populates="content_blocks")


# ============================================================================
# 8. GuideContentJob
# ============================================================================

class GuideContentJob(Base):
    """Batch content pipeline job tracking per zone (generate | validate | synthesize)."""

    __tablename__ = "guide_content_jobs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    zone_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("guide_zones.id"), nullable=False)
    # job_type: 'generate_drafts' | 'validate' | 'synthesize'
    job_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    voice_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), ForeignKey("guide_voices.id"), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    progress_json: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    zone: Mapped[GuideZone] = relationship("GuideZone", back_populates="content_jobs")
    voice: Mapped[Optional[GuideVoice]] = relationship("GuideVoice", back_populates="content_jobs")


# ============================================================================
# 9. GuideSession
# ============================================================================

class GuideSession(Base):
    """Active/ended guide sessions — one per user walk-through of a zone."""

    __tablename__ = "guide_sessions"

    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_guide_sessions_rating"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    # user_id FK to users — no cross-module relationship defined
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False)
    zone_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("guide_zones.id"), nullable=False)
    voice_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("guide_voices.id"), nullable=False)
    language: Mapped[str] = mapped_column(String, nullable=False, default="en")
    detail_level: Mapped[str] = mapped_column(String, nullable=False, default="standard")
    # status: 'active' | 'paused' | 'ended'
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    total_seconds_billed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_known_location: Mapped[Optional[Any]] = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    # exit_reason: 'manual' | 'balance_empty' | 'out_of_zone'
    exit_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Post-session feedback (NULL = no rating yet)
    rating: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    review_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    zone: Mapped[GuideZone] = relationship("GuideZone", back_populates="sessions")
    voice: Mapped[GuideVoice] = relationship("GuideVoice", back_populates="sessions")
    gps_log: Mapped[list[GuideSessionGpsLog]] = relationship("GuideSessionGpsLog", back_populates="session")
    visits: Mapped[list[GuideSessionVisit]] = relationship("GuideSessionVisit", back_populates="session")
    qa_entries: Mapped[list[GuideSessionQA]] = relationship("GuideSessionQA", back_populates="session")
    transactions: Mapped[list[GuideMinuteTransaction]] = relationship("GuideMinuteTransaction", back_populates="session")
    analytics_events: Mapped[list[GuideAnalyticsEvent]] = relationship("GuideAnalyticsEvent", back_populates="session")


# ============================================================================
# 10. GuideSessionGpsLog
# ============================================================================

class GuideSessionGpsLog(Base):
    """Full GPS track per session — every sample for heat-map and trigger-radius analytics."""

    __tablename__ = "guide_session_gps_log"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("guide_sessions.id", ondelete="CASCADE"), nullable=False
    )
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    heading_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    speed_mps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    accuracy_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    session: Mapped[GuideSession] = relationship("GuideSession", back_populates="gps_log")


# ============================================================================
# 11. GuideSessionVisit
# ============================================================================

class GuideSessionVisit(Base):
    """Visited-point log — replaces visited_point_ids UUID[] column."""

    __tablename__ = "guide_session_visits"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("guide_sessions.id", ondelete="CASCADE"), nullable=False
    )
    point_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("guide_points.id"), nullable=False)
    # content_type_played: 'main' | 'bonus' | 'skipped' | 'zone_transition'
    content_type_played: Mapped[str] = mapped_column(String, nullable=False, default="main")
    visited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    session: Mapped[GuideSession] = relationship("GuideSession", back_populates="visits")
    point: Mapped[GuidePoint] = relationship("GuidePoint", back_populates="visits")


# ============================================================================
# 12. GuideSessionQA
# ============================================================================

class GuideSessionQA(Base):
    """Q&A pairs per session — replaces qa_history JSONB column."""

    __tablename__ = "guide_session_qa"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("guide_sessions.id", ondelete="CASCADE"), nullable=False
    )
    # point_id nullable — user may ask away from any POI
    point_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), ForeignKey("guide_points.id"), nullable=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    audio_question_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    audio_answer_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    session: Mapped[GuideSession] = relationship("GuideSession", back_populates="qa_entries")
    point: Mapped[Optional[GuidePoint]] = relationship("GuidePoint", back_populates="qa_entries")


# ============================================================================
# 13. GuideUserPreference
# ============================================================================

class GuideUserPreference(Base):
    """Per-user guide defaults — one row per user (user_id is PK)."""

    __tablename__ = "guide_user_preferences"

    # user_id is both PK and FK — no cross-module relationship to UserModel
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    preferred_voice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("guide_voices.id"), nullable=True
    )
    preferred_language: Mapped[str] = mapped_column(String, nullable=False, default="en")
    preferred_detail_level: Mapped[str] = mapped_column(String, nullable=False, default="standard")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    preferred_voice: Mapped[Optional[GuideVoice]] = relationship("GuideVoice", back_populates="user_preferences")


# ============================================================================
# 14. GuideAnalyticsEvent
# ============================================================================

class GuideAnalyticsEvent(Base):
    """In-house product analytics events — mirrors key events from Mixpanel/Amplitude."""

    __tablename__ = "guide_analytics_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    # user_id nullable — supports anonymous pre-auth events
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), ForeignKey("users.id"), nullable=True)
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("guide_sessions.id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    event_data: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    session: Mapped[Optional[GuideSession]] = relationship("GuideSession", back_populates="analytics_events")


# ============================================================================
# 15. GuideMinuteBalance
# ============================================================================

class GuideMinuteBalance(Base):
    """User minute balance stored in seconds for sub-minute billing precision."""

    __tablename__ = "guide_minute_balances"

    # user_id is both PK and FK — no cross-module relationship to UserModel
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    seconds_remaining: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trial_seconds_granted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trial_seconds_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


# ============================================================================
# 16. GuideIAPPurchase
# ============================================================================

class GuideIAPPurchase(Base):
    """Server-validated IAP receipts — UNIQUE(transaction_id) prevents double-crediting."""

    __tablename__ = "guide_iap_purchases"

    __table_args__ = (
        UniqueConstraint("transaction_id", name="uq_guide_iap_transaction_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    # user_id FK to users — no cross-module relationship
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False)
    # platform: 'apple' | 'google'
    platform: Mapped[str] = mapped_column(String, nullable=False)
    product_id: Mapped[str] = mapped_column(String, nullable=False)
    transaction_id: Mapped[str] = mapped_column(String, nullable=False)
    original_transaction_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    minutes_purchased: Mapped[int] = mapped_column(Integer, nullable=False)
    price_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    # status: 'valid' | 'revoked' | 'refunded'
    status: Mapped[str] = mapped_column(String, nullable=False, default="valid")


# ============================================================================
# 17. GuideMinuteTransaction
# ============================================================================

class GuideMinuteTransaction(Base):
    """Immutable audit log for every balance change (purchase / trial / debit / refund)."""

    __tablename__ = "guide_minute_transactions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    # user_id FK to users — no cross-module relationship
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False)
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("guide_sessions.id"), nullable=True
    )
    # transaction_type: 'purchase' | 'trial' | 'debit' | 'refund'
    transaction_type: Mapped[str] = mapped_column(String, nullable=False)
    # seconds_delta: positive = credit, negative = debit
    seconds_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    # package_id references guide_packages.id (string PK) — no FK constraint in migration
    package_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # iap_purchase_id — plain UUID, no FK constraint in migration
    iap_purchase_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    session: Mapped[Optional[GuideSession]] = relationship("GuideSession", back_populates="transactions")


# ============================================================================
# 18. GuidePackage
# ============================================================================

class GuidePackage(Base):
    """Minute package catalog — seeded with 3 rows (30/60/120 min)."""

    __tablename__ = "guide_packages"

    # String PK (e.g. "guide_30min") — not a UUID
    id: Mapped[str] = mapped_column(String, primary_key=True)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    price_usd: Mapped[float] = mapped_column(Float, nullable=False)
    apple_product_id: Mapped[str] = mapped_column(String, nullable=False)
    google_product_id: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


# ============================================================================
# 19. GuideSeedJob
# ============================================================================

class GuideSeedJob(Base):
    """City Seeder job status tracking — one job per city run."""

    __tablename__ = "guide_seed_jobs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    city_name: Mapped[str] = mapped_column(String, nullable=False)
    # status phases: running | awaiting_zone_approval | placing_points |
    #   building_graph | collecting_knowledge | generating_content | complete | failed
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    current_phase: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    city_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), ForeignKey("guide_cities.id"), nullable=True)
    progress_json: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    city: Mapped[Optional[GuideCity]] = relationship("GuideCity", back_populates="seed_jobs")
