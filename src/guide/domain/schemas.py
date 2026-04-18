"""
Pydantic v2 request/response schemas for the Live Audio Guide API.

Grouped into four sections:
  1. Shared types & enums (Literal constants, GeoJSON helpers)
  2. Client API schemas  — /api/guide/... (requires JWT auth)
  3. Admin API schemas   — /api/guide/admin/... (requires admin role)
  4. SSE event schemas   — streaming Q&A responses
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

# ============================================================================
# Base
# ============================================================================


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# 1. Shared types & Literals
# ============================================================================

# Used as Literal type aliases — import these in routers/services as needed.

NavigationState = str   # "INIT" | "RESUMING" | "NARRATING" | "TRANSITIONING" | "AT_BONUS" | "OUT_OF_ZONE"
ContentType = str       # "main" | "bonus" | "transition" | "zone_transition" | "recap"
GenerationStatus = str  # "pending" | "draft" | "validated" | "needs_manual_review"
                        # | "reviewed" | "synthesizing" | "synthesized" | "failed"
VoiceStyleGroup = str   # "academic" | "friendly" | "dramatic" | "minimal"
DetailLevel = str       # "brief" | "standard"
Language = str          # "en" | "ru"
PointType = str         # "poi" | "connector"
Platform = str          # "apple" | "google"

# GeoJSON geometry helpers — plain dicts for MVP, shape documented here.
# GeoJSONPoint:   {"type": "Point",   "coordinates": [lng, lat]}
# GeoJSONPolygon: {"type": "Polygon", "coordinates": [[[lng, lat], ...]]}
GeoJSONPoint = dict[str, Any]
GeoJSONPolygon = dict[str, Any]
GeoJSONLineString = dict[str, Any]


# ============================================================================
# 2. Client API schemas
# ============================================================================

# === Coverage & Zones ===

class VoiceOption(_Base):
    id: uuid.UUID
    name: str
    style_group: VoiceStyleGroup
    language: Language
    preview_audio_url: Optional[str] = None


class ZoneSummary(_Base):
    id: uuid.UUID
    name: str
    theme: Optional[str] = None
    city_name: str
    boundary_geojson: GeoJSONPolygon
    poi_count: int
    voice_options: list[VoiceOption]
    distance_m: float
    is_user_inside: bool


class CoverageResponse(_Base):
    zones: list[ZoneSummary]


class ZoneDetailResponse(_Base):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    theme: Optional[str] = None
    boundary_geojson: GeoJSONPolygon
    point_count: int
    available_voices: list[VoiceOption]
    available_languages: list[Language]
    sample_audio_url: Optional[str] = None


# === Sessions ===

class LocationInput(_Base):
    lat: float
    lng: float


class SessionCreateRequest(_Base):
    zone_id: uuid.UUID
    voice_id: uuid.UUID
    language: Language = "en"
    detail_level: DetailLevel = "standard"
    initial_location: LocationInput


class TransitionContent(_Base):
    # key: to_point_id (str), value: CDN audio URL
    to_point_id: uuid.UUID
    audio_url: str
    duration_seconds: Optional[float] = None


class PointContent(_Base):
    point_id: uuid.UUID
    main_audio_url: Optional[str] = None
    main_duration_s: Optional[float] = None
    bonus_audio_url: Optional[str] = None
    bonus_duration_s: Optional[float] = None
    transitions: list[TransitionContent] = []


class SessionCreateResponse(_Base):
    session_id: uuid.UUID
    balance_seconds: int
    trial_seconds_remaining: int
    preload_content: list[PointContent]


class HeartbeatRequest(_Base):
    seconds_active: int
    location: LocationInput
    heading_deg: Optional[float] = None


class HeartbeatResponse(_Base):
    seconds_remaining: int
    continue_session: bool
    stop_reason: Optional[str] = None        # "balance_empty" | "out_of_zone"
    nearby_content: list[PointContent] = []


class PauseResponse(_Base):
    paused_at: datetime
    seconds_billed_total: int


class ResumeResponse(_Base):
    resumed_at: datetime
    seconds_remaining: int


class SessionEndRequest(_Base):
    exit_reason: str   # "manual" | "out_of_zone" | "balance_empty"


class SessionSummary(_Base):
    session_id: uuid.UUID
    zone_name: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_seconds: int
    minutes_used: float
    points_visited: int
    path_geojson: Optional[GeoJSONLineString] = None
    questions_asked: int
    balance_remaining_seconds: int


class SessionHistoryItem(_Base):
    session_id: uuid.UUID
    zone_name: str
    city_name: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_seconds: int
    minutes_used: float
    points_visited: int
    rating: Optional[int] = None


class SessionsHistoryResponse(_Base):
    sessions: list[SessionHistoryItem]
    total: int


class SessionRateRequest(_Base):
    rating: int           # 1–5
    review_text: Optional[str] = None


class SessionRateResponse(_Base):
    session_id: uuid.UUID
    rating: int
    review_text: Optional[str] = None


# === Navigation ===

class PointContentDetails(_Base):
    main_audio_url: Optional[str] = None
    main_duration_s: Optional[float] = None
    bonus_audio_url: Optional[str] = None
    bonus_duration_s: Optional[float] = None
    transitions: dict[str, str] = {}    # {to_point_id: audio_url}


class NearestPoint(_Base):
    point_id: uuid.UUID
    name: Optional[str] = None
    dist_m: float
    bearing_deg: Optional[float] = None
    is_in_trigger_radius: bool
    already_visited: bool
    content: PointContentDetails


class NavigationNextResponse(_Base):
    current_point_id: Optional[uuid.UUID] = None
    nearest_points: list[NearestPoint]
    navigation_state: NavigationState


# === Streaming Q&A ===

class QAAskRequest(_Base):
    """Multipart form fields for POST /api/guide/qa/ask (audio file sent separately)."""
    session_id: uuid.UUID
    current_point_id: Optional[uuid.UUID] = None


# === Balance ===

class BalanceResponse(_Base):
    seconds_remaining: int
    minutes_remaining: float
    trial_minutes_remaining: float
    last_purchase_at: Optional[datetime] = None


# === Packages ===

class Package(_Base):
    id: str
    minutes: int
    price_usd: float
    apple_product_id: str
    google_product_id: str
    label: Optional[str] = None
    is_active: bool = True


class PackagesResponse(_Base):
    packages: list[Package]


# === Purchases & IAP ===

class PurchaseValidateRequest(_Base):
    platform: Platform
    receipt_data: str           # base64 receipt (Apple) or purchase token (Google)
    product_id: str
    transaction_id: str


class PurchaseValidateResponse(_Base):
    success: bool
    minutes_credited: int
    new_balance_seconds: int
    transaction_id: str


class RefundWebhookRequest(_Base):
    platform: Platform
    transaction_id: str
    original_transaction_id: Optional[str] = None
    product_id: str
    refund_reason: Optional[str] = None


class RefundWebhookResponse(_Base):
    acknowledged: bool
    minutes_revoked: int


# ============================================================================
# 3. Admin API schemas
# ============================================================================

# === City Seeder ===

class SeedRequest(_Base):
    city_name: str
    country: Optional[str] = None


class SeedResponse(_Base):
    job_id: uuid.UUID
    status: str


class SeedJobProgress(_Base):
    zones_found: int = 0
    points_placed: int = 0
    edges_built: int = 0
    cards_collected: int = 0
    blocks_generated: int = 0
    blocks_synthesized: int = 0


class SeedJobStatusResponse(_Base):
    job_id: uuid.UUID
    city_name: str
    status: str
    current_phase: Optional[str] = None
    progress: SeedJobProgress
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


# === Zones admin ===

class ZoneAdminView(_Base):
    id: uuid.UUID
    city_id: uuid.UUID
    name: str
    description: Optional[str] = None
    theme: Optional[str] = None
    boundary_geojson: GeoJSONPolygon
    poi_count: int
    point_count: int
    is_approved: bool
    is_active: bool
    approved_at: Optional[datetime] = None
    created_at: datetime


class ZonesAdminListResponse(_Base):
    zones: list[ZoneAdminView]
    total: int


class ZoneApproveRequest(_Base):
    approved: bool
    adjusted_boundary_geojson: Optional[GeoJSONPolygon] = None


class ZoneApproveResponse(_Base):
    zone_id: uuid.UUID
    is_approved: bool
    approved_at: Optional[datetime] = None


# === Points admin ===

class PointAdminView(_Base):
    id: uuid.UUID
    zone_id: uuid.UUID
    name: Optional[str] = None
    point_type: PointType
    lat: float
    lng: float
    trigger_radius_m: int
    google_place_id: Optional[str] = None
    osm_node_id: Optional[int] = None
    is_approved: bool
    is_active: bool
    neighbor_count: int = 0
    content_status: Optional[str] = None


class PointsAdminListResponse(_Base):
    points: list[PointAdminView]
    total: int


class PointUpdateRequest(_Base):
    lat: Optional[float] = None
    lng: Optional[float] = None
    trigger_radius_m: Optional[int] = None
    is_active: Optional[bool] = None
    is_approved: Optional[bool] = None


# === Content pipeline ===

class ContentGenerateRequest(_Base):
    zone_id: uuid.UUID
    voice_ids: Optional[list[uuid.UUID]] = None     # None = all active voices
    force_regenerate: bool = False


class ContentGenerateResponse(_Base):
    job_id: uuid.UUID
    blocks_queued: int


class ContentSynthesizeRequest(_Base):
    zone_id: uuid.UUID
    voice_ids: Optional[list[uuid.UUID]] = None


class ContentSynthesizeResponse(_Base):
    job_id: uuid.UUID
    files_queued: int


class VoiceStatus(_Base):
    voice_id: uuid.UUID
    name: str
    style_group: VoiceStyleGroup
    language: Language
    ready_pct: float


class ContentStatusResponse(_Base):
    total_blocks: int
    ready: int
    pending: int
    failed: int
    voices: list[VoiceStatus]


# === Content review ===

class ContentBlockReviewView(_Base):
    id: uuid.UUID
    point_id: uuid.UUID
    point_name: Optional[str] = None
    zone_id: uuid.UUID
    voice_id: uuid.UUID
    voice_name: str
    language: Language
    detail_level: DetailLevel
    content_type: ContentType
    variant_index: int
    text_script: str
    audio_url: Optional[str] = None
    audio_duration_seconds: Optional[float] = None
    generation_status: GenerationStatus
    coherence_score: Optional[float] = None
    review_notes: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime


class ContentReviewListResponse(_Base):
    blocks: list[ContentBlockReviewView]
    total: int


class ContentReviewActionRequest(_Base):
    # action: "approve" | "reject" | "flag_for_review"
    action: str
    review_notes: Optional[str] = None
    reviewed_by: Optional[str] = None


class ContentReviewActionResponse(_Base):
    block_id: uuid.UUID
    generation_status: GenerationStatus
    reviewed_at: Optional[datetime] = None


# === Content validation ===

class ContentValidateRequest(_Base):
    zone_id: uuid.UUID
    voice_ids: Optional[list[uuid.UUID]] = None
    # Validate only blocks in this status
    filter_status: Optional[GenerationStatus] = "draft"


class ContentValidateResponse(_Base):
    job_id: uuid.UUID
    blocks_queued: int


# === Analytics dashboard ===

class AnalyticsDashboardResponse(_Base):
    total_sessions: int
    active_sessions: int
    total_minutes_sold: float
    total_questions_asked: int
    avg_session_duration_minutes: float
    avg_rating: Optional[float] = None
    top_zones: list[dict[str, Any]]
    events_by_type: dict[str, int]


# ============================================================================
# 4. SSE event schemas (Streaming Q&A)
# ============================================================================

class SSETranscriptEvent(_Base):
    """Fired once when STT transcript is ready."""
    text: str


class SSEAnswerChunkEvent(_Base):
    """Fired for each LLM text chunk (sentence-by-sentence)."""
    text: str


class SSEAudioChunkUrlEvent(_Base):
    """Fired when a TTS audio chunk is uploaded to CDN."""
    url: str
    chunk_index: int


class SSEAudioChunkInlineEvent(_Base):
    """Fired when a TTS audio chunk is sent inline (base64-encoded fallback)."""
    base64: str
    chunk_index: int
    mime: str = "audio/mpeg"


class SSEDoneEvent(_Base):
    """Fired when the full Q&A pair is persisted."""
    qa_entry_id: uuid.UUID


class SSEErrorEvent(_Base):
    """Fired on STT/LLM/TTS failure."""
    code: str      # "stt_failed" | "llm_timeout" | "tts_failed"
    message: str
