"""
Configuration management for the Trip Planning backend.
Uses Pydantic Settings to load configuration from environment variables.
"""
from typing import Optional
from pydantic import Field, model_validator, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://tripplanner:tripplanner@db:5432/tripplanner",
        description="PostgreSQL connection URL with asyncpg driver"
    )

    # LLM Provider Selection
    llm_provider: str = Field(
        default="ionet",
        description="LLM provider to use: 'ionet' or 'anthropic'"
    )

    # IO Intelligence (io.net) - OpenAI-compatible API
    ionet_api_key: Optional[str] = Field(
        default=None,
        description="IO Intelligence API key"
    )
    ionet_base_url: str = Field(
        default="https://api.intelligence.io.solutions/api/v1/",
        description="Base URL for IO Intelligence API"
    )

    @model_validator(mode='after')
    def check_api_keys(self) -> 'Settings':
        if self.llm_provider == 'ionet':
            if not self.ionet_api_key:
                raise ValueError(
                    "IONET_API_KEY is not set. "
                    "Please provide a valid API key in your .env file."
                )
        elif self.llm_provider == 'anthropic':
            if not self.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY is not set.")

        supported_languages = self.i18n_supported_languages_list
        if self.i18n_source_language not in supported_languages:
            raise ValueError(
                f"I18N_SOURCE_LANGUAGE={self.i18n_source_language} must be included in "
                f"I18N_SUPPORTED_LANGUAGES={supported_languages}"
            )
        if self.i18n_fallback_language not in supported_languages:
            raise ValueError(
                f"I18N_FALLBACK_LANGUAGE={self.i18n_fallback_language} must be included in "
                f"I18N_SUPPORTED_LANGUAGES={supported_languages}"
            )
        if self.i18n_budget_guard_enabled:
            if self.i18n_max_chars_per_day <= 0:
                raise ValueError("I18N_MAX_CHARS_PER_DAY must be > 0")
            if self.i18n_max_chars_per_month <= 0:
                raise ValueError("I18N_MAX_CHARS_PER_MONTH must be > 0")

        allowed_translation_providers = {"echo", "google"}
        if self.i18n_translation_provider not in allowed_translation_providers:
            raise ValueError(
                "I18N_TRANSLATION_PROVIDER must be one of: "
                + ", ".join(sorted(allowed_translation_providers))
            )
        if self.i18n_translation_poll_interval_seconds <= 0:
            raise ValueError("I18N_TRANSLATION_POLL_INTERVAL_SECONDS must be > 0")
        if self.i18n_translation_max_attempts <= 0:
            raise ValueError("I18N_TRANSLATION_MAX_ATTEMPTS must be > 0")
        if self.i18n_translation_retry_backoff_seconds <= 0:
            raise ValueError("I18N_TRANSLATION_RETRY_BACKOFF_SECONDS must be > 0")
        if self.i18n_translation_timeout_seconds <= 0:
            raise ValueError("I18N_TRANSLATION_TIMEOUT_SECONDS must be > 0")
        if not (0 < self.i18n_budget_alert_day_ratio <= 1):
            raise ValueError("I18N_BUDGET_ALERT_DAY_RATIO must be in (0, 1]")
        if not (0 < self.i18n_budget_alert_month_ratio <= 1):
            raise ValueError("I18N_BUDGET_ALERT_MONTH_RATIO must be in (0, 1]")
        unsupported_rollout_locales = [
            locale
            for locale in self.i18n_rollout_enabled_locales_list
            if locale not in supported_languages
        ]
        if unsupported_rollout_locales:
            raise ValueError(
                "I18N_ROLLOUT_ENABLED_LOCALES contains unsupported locales: "
                + ", ".join(sorted(unsupported_rollout_locales))
            )
        if (
            self.i18n_machine_translation_enabled
            and self.i18n_translation_provider == "google"
            and not self.google_translate_api_key
        ):
            raise ValueError(
                "GOOGLE_TRANSLATE_API_KEY must be set when "
                "I18N_MACHINE_TRANSLATION_ENABLED=true and I18N_TRANSLATION_PROVIDER=google"
            )
        return self

    # Anthropic Claude (legacy/alternative provider)
    anthropic_api_key: Optional[str] = Field(
        default=None,
        description="Anthropic API key for Claude"
    )
    anthropic_base_url: str = Field(
        default="https://api.anthropic.com",
        description="Base URL for Anthropic API"
    )
    anthropic_model: str = Field(
        default="claude-3-5-sonnet-20241022",
        description="Claude model to use for macro planning"
    )

    # Trip Chat Mode - optimized for cost (use cheaper/faster model)
    # io.net default: mistralai/Mistral-Nemo-Instruct-2407 (full model path required)
    # Anthropic default: claude-3-5-haiku-20241022
    trip_chat_model: str = Field(
        default="mistralai/Mistral-Nemo-Instruct-2407",
        description="Model for trip chat (cheaper, faster for conversational updates). Use full model path for io.net."
    )

    # Macro Planning Mode - uses more powerful model for complex reasoning
    # io.net default: meta-llama/Llama-3.3-70B-Instruct
    # Anthropic default: claude-3-5-sonnet-20241022
    trip_planning_model: str = Field(
        default="meta-llama/Llama-3.3-70B-Instruct",
        description="Model for macro planning (more powerful for itinerary generation)"
    )

    # LLM-based POI Selection (experimental feature)
    # When enabled, uses LLM to select/re-rank POI candidates after deterministic filtering
    use_llm_for_poi_selection: bool = Field(
        default=False,
        description="Enable LLM-assisted POI selection (default: off, uses deterministic ranking)"
    )
    poi_selection_model: str = Field(
        default="",
        description="Model for POI selection (defaults to trip_planning_model if empty)"
    )
    poi_selection_max_candidates: int = Field(
        default=15,
        description="Maximum candidates to send to LLM for POI selection (cost control)"
    )
    poi_preference_llm_timeout_seconds: int = Field(
        default=6,
        description="Timeout for POI preference LLM call"
    )
    curator_llm_timeout_seconds: int = Field(
        default=8,
        description="Timeout for curator LLM directive generation"
    )
    day_level_selection_llm_timeout_seconds: int = Field(
        default=6,
        description="Timeout for day-level POI selection LLM"
    )
    route_engineer_llm_timeout_seconds: int = Field(
        default=6,
        description="Timeout for route engineer LLM calls"
    )
    curator_model: str = Field(
        default="",
        description="Optional model override for POI curator (defaults to trip_planning_model)"
    )
    route_engineer_model: str = Field(
        default="",
        description="Optional model override for route engineer (defaults to trip_planning_model)"
    )

    # Preference profile generation for POI scoring
    use_llm_for_poi_preferences: bool = Field(
        default=True,
        description="Use LLM to build preference profile for POI ranking"
    )

    # Agentic planning (POI Curator + Route Engineer)
    enable_agentic_planning: bool = Field(
        default=True,
        description="Use agentic Curator/Engineer pipeline when smart routing is enabled"
    )
    agentic_candidate_multiplier: int = Field(
        default=5,
        description="Candidate multiplier per required block for agentic POI curation (increased for longer trips)"
    )
    agentic_min_candidates_per_category: int = Field(
        default=20,
        description="Minimum POI candidates per category for agentic planning (increased to support 7+ day trips)"
    )
    agentic_max_candidates_per_category: int = Field(
        default=200,
        description="Maximum POI candidates per category for agentic planning (increased for major tourist cities)"
    )
    agentic_llm_score_weight: float = Field(
        default=0.35,
        description="Weight for curator LLM scores when ranking candidates"
    )
    agentic_llm_scoring_max_categories: int = Field(
        default=1,
        description="Max categories to LLM-score per curation pass"
    )
    agentic_day_selection_max_candidates: int = Field(
        default=6,
        description="Max candidates per block sent to day-level LLM in agentic planning"
    )
    agentic_use_fast_macro_plan: bool = Field(
        default=True,
        description="Use fast chat model for macro planning when agentic pipeline is enabled"
    )
    agentic_use_template_macro_plan: bool = Field(
        default=True,
        description="Use template macro plan instead of LLM when agentic pipeline is enabled"
    )
    planning_deadline_seconds: int = Field(
        default=60,
        description="Max end-to-end planning time budget in seconds"
    )
    agentic_use_llm_for_district_planning: bool = Field(
        default=False,
        description="Use LLM for district planning in agentic pipeline"
    )
    agentic_use_llm_for_route_optimization: bool = Field(
        default=True,
        description="Use LLM for route ordering in agentic pipeline"
    )
    agentic_use_day_level_poi_selection: bool = Field(
        default=True,
        description="Use day-level LLM selection in agentic pipeline"
    )

    # Day-level LLM selection for POIs (selects one candidate per block)
    enable_day_level_poi_selection: bool = Field(
        default=True,
        description="Use LLM to select POIs for all blocks in a day"
    )

    # Google Maps Platform / Places API
    google_maps_api_key: Optional[str] = Field(
        default=None,
        description="Google Maps API key for Places API"
    )
    google_places_base_url: str = Field(
        default="https://maps.googleapis.com/maps/api/place/textsearch/json",
        description="Base URL for Google Places Text Search API"
    )
    google_place_details_base_url: str = Field(
        default="https://maps.googleapis.com/maps/api/place/details/json",
        description="Base URL for Google Places Details API"
    )
    google_place_photo_base_url: str = Field(
        default="https://maps.googleapis.com/maps/api/place/photo",
        description="Base URL for Google Places Photo API"
    )
    google_translate_api_key: Optional[str] = Field(
        default=None,
        description="Google Cloud Translation API key"
    )
    google_places_default_language: str = Field(
        default="ru",
        description="Default language for Places API responses"
    )
    google_places_default_radius_meters: int = Field(
        default=50000,
        description="Default search radius in meters (50km)"
    )
    google_places_timeout_seconds: int = Field(
        default=10,
        description="HTTP timeout for Google Places API calls"
    )

    # Google Routes API
    google_routes_base_url: str = Field(
        default="https://routes.googleapis.com/directions/v2:computeRoutes",
        description="Base URL for Google Routes API"
    )
    google_routes_timeout_seconds: int = Field(
        default=10,
        description="HTTP timeout for Google Routes API calls"
    )

    # Travel Time Provider Selection
    travel_time_provider: str = Field(
        default="simple",
        description="Travel time provider: 'simple' (heuristic) or 'google_maps'"
    )

    # =========================================================================
    # Geo-Adequate Routing Settings
    # =========================================================================

    # Hotel Anchor: Bias first blocks of day toward hotel location
    hotel_anchor_enabled: bool = Field(
        default=True,
        description="Enable hotel anchor bias for first blocks of day"
    )
    hotel_anchor_blocks: int = Field(
        default=2,
        description="Number of first blocks per day to apply hotel proximity bias"
    )
    hotel_anchor_distance_weight: float = Field(
        default=0.5,
        description="Weight for distance penalty: score = rank_score - weight * distance_km"
    )

    # Daily Route Optimization: Reorder blocks within a day to minimize travel
    enable_daily_route_optimization: bool = Field(
        default=True,
        description="Enable reordering of activity blocks to minimize travel time"
    )
    max_optimization_blocks_per_cluster: int = Field(
        default=5,
        description="Maximum number of contiguous blocks to consider for reordering (prevents factorial explosion)"
    )

    # Max Per-Hop Travel Time: Limit long travel between consecutive POIs
    enable_travel_hop_limit: bool = Field(
        default=True,
        description="Enable maximum travel time constraint between consecutive POIs"
    )
    max_travel_minutes_per_hop: int = Field(
        default=40,
        description="Maximum allowed travel time in minutes between consecutive POIs"
    )

    max_hop_distance_km: float = Field(
        default=8.0,
        description="Maximum straight-line distance in km between consecutive POIs"
    )

    use_llm_for_route_optimization: bool = Field(
        default=True,
        description="Use LLM to order reorderable activity blocks within a day"
    )

    # =========================================================================
    # Smart District-Based Routing (new algorithm)
    # =========================================================================

    # Enable smart routing with geographic clustering
    enable_smart_routing: bool = Field(
        default=True,
        description="Enable district-based smart routing for optimized walking routes"
    )

    # Use LLM for district planning (vs deterministic fallback)
    use_llm_for_district_planning: bool = Field(
        default=True,
        description="Use LLM to assign districts to time blocks (more intelligent routing)"
    )

    # Clustering parameters
    cluster_cell_size_km: float = Field(
        default=1.5,
        description="Grid cell size for geographic clustering (larger = fewer, bigger districts)"
    )

    max_poi_radius_km: float = Field(
        default=15.0,
        description="Maximum distance from city center for POI inclusion (km). POIs beyond this are excluded to prevent far suburbs like Peterhof."
    )
    min_pois_per_district: int = Field(
        default=5,
        description="Minimum POIs to form a standalone district"
    )
    max_districts_per_city: int = Field(
        default=8,
        description="Maximum number of districts per city"
    )

    # POI quality threshold for smart routing
    smart_routing_min_rating: float = Field(
        default=4.0,
        description="Minimum POI rating for smart routing selection (lowered to include more quality venues)"
    )

    # Candidate expansion when insufficient POIs in district
    district_poi_min_candidates: int = Field(
        default=3,
        description="Minimum candidates needed per block; triggers expansion if fewer"
    )
    district_poi_expansion_factor: float = Field(
        default=2.0,
        description="Factor to expand search when insufficient candidates (e.g., 2.0 = double radius)"
    )

    # i18n rollout and machine-translation guardrails
    i18n_source_language: str = Field(
        default="ru",
        description="Primary source language for untranslated keys/content"
    )
    i18n_fallback_language: str = Field(
        default="ru",
        description="Global fallback language when localized value is missing"
    )
    i18n_supported_languages: str = Field(
        default="en,ru,zh,fr,es,ar,de",
        description="Comma-separated list of supported BCP-47 base language codes"
    )
    i18n_machine_translation_enabled: bool = Field(
        default=False,
        description="Enable machine translation provider calls (keep false in budget-safe mode)"
    )
    i18n_budget_guard_enabled: bool = Field(
        default=True,
        description="Hard guardrail to block translation calls when character limits are reached"
    )
    i18n_max_chars_per_day: int = Field(
        default=50000,
        description="Hard daily character budget for machine translation"
    )
    i18n_max_chars_per_month: int = Field(
        default=300000,
        description="Hard monthly character budget for machine translation"
    )
    i18n_translation_worker_enabled: bool = Field(
        default=True,
        description="Enable background translation queue worker"
    )
    i18n_translation_provider: str = Field(
        default="echo",
        description="Machine translation provider: 'echo' or 'google'"
    )
    i18n_translation_poll_interval_seconds: float = Field(
        default=1.0,
        description="Polling interval for translation queue worker"
    )
    i18n_translation_max_attempts: int = Field(
        default=3,
        description="Maximum retry attempts for failed translation jobs"
    )
    i18n_translation_retry_backoff_seconds: int = Field(
        default=30,
        description="Base retry backoff in seconds for failed translation jobs"
    )
    i18n_translation_timeout_seconds: int = Field(
        default=12,
        description="HTTP timeout for translation provider requests"
    )
    i18n_tier_a_require_manual_review: bool = Field(
        default=True,
        description="Require manual review before Tier A translations are served"
    )
    i18n_glossary_overrides_enabled: bool = Field(
        default=True,
        description="Apply glossary overrides to machine-translated text"
    )
    i18n_rollout_enforced: bool = Field(
        default=False,
        description="Enforce per-locale rollout feature flags at runtime"
    )
    i18n_rollout_enabled_locales: str = Field(
        default="ru",
        description="Comma-separated locales enabled when rollout enforcement is on"
    )
    i18n_budget_alert_day_ratio: float = Field(
        default=0.8,
        description="Trigger app-side day budget alert at this usage ratio"
    )
    i18n_budget_alert_month_ratio: float = Field(
        default=0.8,
        description="Trigger app-side month budget alert at this usage ratio"
    )

    # =========================================================================
    # Hotel Picker — Booking.com / RapidAPI
    # =========================================================================

    rapidapi_key: str = Field(
        default="",
        description="RapidAPI key for Booking.com (x-rapidapi-key header)"
    )
    rapidapi_host: str = Field(
        default="booking-com15.p.rapidapi.com",
        description="RapidAPI host for Booking.com (x-rapidapi-host header)"
    )
    booking_api_base_url: str = Field(
        default="https://booking-com15.p.rapidapi.com",
        description="Base URL for Booking.com RapidAPI (direct httpx calls, no MCP)"
    )
    hotel_search_timeout_seconds: int = Field(
        default=15,
        description="HTTP timeout for Booking.com API calls"
    )
    hotel_max_candidates: int = Field(
        default=25,
        description="Maximum finalist candidates for deep analysis (after L1 filter)"
    )
    hotel_results_count: int = Field(
        default=10,
        description="Number of hotel results to return in response"
    )
    hotel_session_ttl_minutes: int = Field(
        default=30,
        description="TTL for search session cache in minutes (for pagination)"
    )

    # Hotel LLM model tiering (empty string → use project default)
    hotel_intent_model: str = Field(
        default="",
        description="Model for IntentParser; empty → TRIP_CHAT_MODEL"
    )
    hotel_review_model: str = Field(
        default="",
        description="Model for ReviewAnalyzer batches; empty → TRIP_CHAT_MODEL"
    )
    hotel_ranking_model: str = Field(
        default="",
        description="Model for MasterRanker; empty → TRIP_PLANNING_MODEL"
    )
    hotel_vision_model: str = Field(
        default="",
        description="Multimodal model for PhotoAnalyzer; empty → skip vision phase"
    )

    # Hotel LLM budget control
    hotel_llm_budget_cents: float = Field(
        default=50.0,
        description="Max LLM spend per hotel search in cents (0 = unlimited)"
    )

    # Server
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    debug: bool = Field(default=False, description="Debug mode")
    auto_init_db: bool = Field(
        default=False,
        description="Auto-create database tables on startup (dev only)"
    )

    @field_validator("debug", mode="before")
    @classmethod
    def coerce_debug_value(cls, v):
        """
        Accept non-standard debug env values (for example DEBUG=release).
        """
        if isinstance(v, str):
            normalized = v.strip().lower()
            if normalized in {"release", "prod", "production", "false", "0", "no", "off"}:
                return False
            if normalized in {"debug", "dev", "development", "true", "1", "yes", "on"}:
                return True
        return v

    # CORS Configuration
    allowed_origins: str = Field(
        default="*",
        description="Comma-separated list of allowed origins for CORS. Use '*' for development only."
    )

    @property
    def cors_origins(self) -> list[str]:
        """Parse ALLOWED_ORIGINS into a list."""
        if self.allowed_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def i18n_supported_languages_list(self) -> list[str]:
        """Parse I18N_SUPPORTED_LANGUAGES into normalized language codes."""
        return [
            language.strip().lower()
            for language in self.i18n_supported_languages.split(",")
            if language.strip()
        ]

    @property
    def i18n_rollout_enabled_locales_list(self) -> list[str]:
        """Parse I18N_ROLLOUT_ENABLED_LOCALES into normalized language codes."""
        return [
            language.strip().lower()
            for language in self.i18n_rollout_enabled_locales.split(",")
            if language.strip()
        ]

    # =========================================================================
    # Live Audio Guide — ElevenLabs TTS
    # =========================================================================

    elevenlabs_api_key: str = Field(
        default="",
        description="ElevenLabs API key (xi-api-key header)"
    )
    elevenlabs_base_url: str = Field(
        default="https://api.elevenlabs.io",
        description="ElevenLabs REST API base URL"
    )
    elevenlabs_model_id: str = Field(
        default="eleven_multilingual_v2",
        description=(
            "ElevenLabs model for batch TTS (pre-recorded content). "
            "eleven_multilingual_v2: highest quality, supports EN+RU (29 languages). "
            "Verified via MCP 2026-04-07."
        )
    )
    elevenlabs_streaming_model_id: str = Field(
        default="eleven_turbo_v2_5",
        description=(
            "ElevenLabs model for streaming Q&A (WebSocket). "
            "eleven_turbo_v2_5: low latency + EN+RU support (32 languages). "
            "Preferred over eleven_flash_v2_5 for better quality in narration."
        )
    )
    elevenlabs_timeout_seconds: int = Field(
        default=30,
        description="HTTP timeout for ElevenLabs batch synthesis requests"
    )
    guide_tts_max_parallel: int = Field(
        default=1,
        description=(
            "Max concurrent ElevenLabs TTS synthesis requests. "
            "Free tier: 1. Starter/Creator: 2-3. Scale: 5+. "
            "Increase when upgrading ElevenLabs subscription."
        )
    )

    # =========================================================================
    # Live Audio Guide — STT (Speech-to-Text)
    # =========================================================================

    stt_provider: str = Field(
        default="deepgram",
        description="STT provider: 'deepgram' (primary, low latency) or 'whisper' (fallback)"
    )
    deepgram_api_key: str = Field(
        default="",
        description="Deepgram API key for Nova-2 speech recognition"
    )
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key for Whisper STT fallback"
    )
    stt_timeout_seconds: int = Field(
        default=30,
        description="HTTP timeout for STT transcription requests"
    )

    # =========================================================================
    # Live Audio Guide — S3 / CDN Audio Storage
    # =========================================================================

    aws_access_key_id: str = Field(
        default="",
        description="AWS access key ID for S3 audio storage"
    )
    aws_secret_access_key: str = Field(
        default="",
        description="AWS secret access key for S3 audio storage"
    )
    aws_region: str = Field(
        default="eu-central-1",
        description="AWS region for S3 bucket"
    )
    aws_s3_bucket: str = Field(
        default="",
        description="S3 bucket name for guide audio files"
    )
    aws_cdn_base_url: str = Field(
        default="",
        description="CDN base URL served from the S3 bucket (e.g. https://cdn.locally.app)"
    )

    # =========================================================================
    # Live Audio Guide — IAP (In-App Purchases)
    # =========================================================================

    apple_shared_secret: str = Field(
        default="",
        description="Apple App Store shared secret for verifyReceipt validation"
    )
    apple_bundle_id: str = Field(
        default="com.locally.guide",
        description="Apple app bundle ID for IAP product matching"
    )
    google_play_package_name: str = Field(
        default="com.locally.guide",
        description="Google Play package name for Publisher API validation"
    )
    google_service_account_json_b64: str = Field(
        default="",
        description=(
            "Base64-encoded Google service account JSON for Android Publisher API OAuth2. "
            "Generate via GCP IAM → Service Accounts → Keys → JSON → base64 encode."
        )
    )

    # =========================================================================
    # Live Audio Guide — Content Pipeline
    # =========================================================================

    guide_content_generation_timeout_seconds: int = Field(
        default=120,
        description="Timeout for LLM narrative generation per content block"
    )
    guide_coherence_score_threshold: float = Field(
        default=3.5,
        description=(
            "Minimum coherence score for auto-approval of generated content. "
            "Blocks below threshold → needs_manual_review."
        )
    )
    guide_transition_coherence_threshold: float = Field(
        default=4.0,
        description="Minimum coherence score for transition/zone_transition blocks (stricter)"
    )
    guide_trial_seconds: int = Field(
        default=600,
        description="Free trial seconds granted on first guide session (default: 10 min)"
    )

    # =========================================================================
    # Live Audio Guide — City Seeder (Zone Discovery)
    # =========================================================================

    seeder_dbscan_eps_m: float = Field(
        default=400.0,
        description=(
            "DBSCAN epsilon in metres for tourist-zone clustering. "
            "POIs within this distance are considered neighbours. "
            "400m ≈ comfortable 5-min walk — keeps clusters in walkable districts."
        )
    )
    seeder_dbscan_min_samples: int = Field(
        default=10,
        description=(
            "DBSCAN min_samples: minimum POIs to form a zone cluster. "
            "Lower = more (smaller) zones; higher = fewer (denser) zones. "
            "10 matches the typical density of tourist districts in major cities."
        )
    )
    seeder_min_poi_rating: float = Field(
        default=4.0,
        description=(
            "Minimum Google Places rating for a POI to qualify for zone discovery. "
            "4.0 filters out low-quality venues while retaining most tourist attractions."
        )
    )
    seeder_min_poi_reviews: int = Field(
        default=50,
        description=(
            "Minimum number of Google Places reviews for a POI to qualify. "
            "Filters out obscure/newly-opened places with too few ratings to trust."
        )
    )
    seeder_max_pois_per_type: int = Field(
        default=60,
        description=(
            "Maximum POIs to fetch per Google Places type (Nearby Search paginates up to 60). "
            "60 is the Google API hard limit across 3 pages of 20 results each."
        )
    )
    seeder_max_parallel_poi_requests: int = Field(
        default=3,
        description=(
            "Max concurrent Google Places Nearby Search requests during zone discovery. "
            "3 stays well within Google's QPS limits on standard plans. "
            "Increase to 5-10 on high-quota keys."
        )
    )

    # =========================================================================
    # Live Audio Guide — City Seeder (Point Placement + Graph Building)
    # =========================================================================

    seeder_max_snap_distance_m: float = Field(
        default=50.0,
        description=(
            "Maximum distance (metres) a POI may be snapped to the nearest OSM pedestrian "
            "node.  POIs further than this get is_approved=False and require manual review "
            "(e.g. POI on an island, inside a gated complex, or on a motorway)."
        )
    )
    seeder_connector_interval_m: float = Field(
        default=80.0,
        description=(
            "Minimum distance (metres) between consecutive connector nodes on the "
            "pedestrian graph.  Smaller values produce denser coverage and more "
            "audio trigger points; larger values reduce DB size."
        )
    )
    seeder_osmnx_cache_dir: str = Field(
        default="./tmp/osmnx_cache",
        description=(
            "Directory for OSMnx HTTP cache.  Enabling the cache avoids redundant "
            "Overpass API calls when the seeder runs multiple times over the same area."
        )
    )
    seeder_max_neighbor_distance_m: float = Field(
        default=300.0,
        description=(
            "Pre-filter radius (metres) for GraphBuilder shortest-path candidates. "
            "Points further apart than this (straight-line) are never connected by an "
            "edge.  Safe to use as a pre-filter because network distance >= straight-line."
        )
    )
    seeder_k_neighbors: int = Field(
        default=4,
        description=(
            "Maximum number of outgoing edges per guide_point (k-nearest by walk time). "
            "4 gives enough routing options while keeping the graph sparse."
        )
    )

    # =========================================================================
    # Live Audio Guide — Content Pipeline (Stage 1: Draft Generation)
    # =========================================================================

    # LLM model for narrative generation; falls back to trip_planning_model if empty
    guide_narrative_model: str = Field(
        default="",
        description=(
            "io.net model for guide narrative generation (main, bonus, transition, recap). "
            "If empty, falls back to trip_planning_model. "
            "Recommended: meta-llama/Llama-3.3-70B-Instruct for quality."
        )
    )
    guide_narrative_llm_timeout_seconds: int = Field(
        default=30,
        description="Per-call timeout for guide narrative LLM requests (seconds)."
    )
    guide_content_max_parallel_llm: int = Field(
        default=10,
        description=(
            "Maximum concurrent LLM calls during content pipeline execution. "
            "Keep ≤ 20 to respect io.net rate limits."
        )
    )
    guide_content_max_llm_calls_per_job: int = Field(
        default=5000,
        description=(
            "Hard cap on LLM calls per content generation job. "
            "Prevents runaway cost from bugs. Raise for large zones."
        )
    )
    guide_content_retry_attempts: int = Field(
        default=3,
        description="Number of retry attempts when LLM returns invalid JSON or missing fields."
    )
    guide_content_default_languages: list[str] = Field(
        default_factory=lambda: ["en"],
        description="Default language list for content generation (MVP: English only)."
    )
    guide_content_default_detail_levels: list[str] = Field(
        default_factory=lambda: ["standard"],
        description=(
            "Default detail_level list for content generation. "
            "MVP: ['standard'] only. Add 'brief' in next iteration."
        )
    )

    # =========================================================================
    # Live Audio Guide — Navigation Engine (Step 8)
    # =========================================================================

    guide_trigger_radius_default_m: int = Field(
        default=25,
        description="Default trigger radius in metres for guide_points that have no explicit radius set."
    )
    guide_preload_point_count: int = Field(
        default=8,
        description="Number of nearest points to preload CDN audio URLs for on session create and preload refresh."
    )
    guide_out_of_zone_threshold_m: float = Field(
        default=200.0,
        description="Distance in metres beyond which the user is considered out of zone (nearest point > threshold)."
    )
    guide_bonus_idle_seconds: int = Field(
        default=120,
        description=(
            "Seconds the user must be stationary near a visited POI before bonus content is offered. "
            "Resets when the user moves away (> 30 m) or a new point is triggered."
        )
    )
    guide_gps_anomaly_max_speed_mps: float = Field(
        default=16.7,
        description=(
            "Maximum plausible pedestrian speed in m/s (16.7 m/s ≈ 60 km/h). "
            "GPS samples implying higher speeds are flagged as anomalies and ignored."
        )
    )
    guide_preload_refresh_distance_m: float = Field(
        default=50.0,
        description="Minimum distance (metres) the user must move from the last preload position to trigger a refresh."
    )
    guide_max_bearing_diff_deg: float = Field(
        default=60.0,
        description=(
            "Maximum angular difference (degrees) between the user's movement bearing and an edge bearing "
            "for the edge to be selected as the active transition direction."
        )
    )

    # =========================================================================
    # Live Audio Guide — City Seeder (Knowledge Collector — Phase 4)
    # =========================================================================

    wikipedia_timeout_seconds: int = Field(
        default=10,
        description="HTTP timeout (seconds) for Wikipedia REST API calls"
    )
    wikipedia_user_agent: str = Field(
        default="Locally-LiveGuide/1.0 (contact@locally.app)",
        description=(
            "User-Agent header sent to Wikipedia and Wikidata APIs. "
            "Both services require a descriptive User-Agent per their usage policy."
        )
    )
    wikidata_timeout_seconds: int = Field(
        default=15,
        description=(
            "HTTP timeout (seconds) for Wikidata SPARQL endpoint. "
            "SPARQL queries run server-side and can be slower than REST endpoints."
        )
    )
    wikidata_endpoint: str = Field(
        default="https://query.wikidata.org/sparql",
        description="Wikidata SPARQL query endpoint URL"
    )
    knowledge_collector_max_parallel: int = Field(
        default=5,
        description=(
            "Maximum number of guide_points processed concurrently per zone "
            "by KnowledgeCollector (semaphore limit). "
            "Each point makes up to 3 external API calls — keep low to respect rate limits."
        )
    )

    # =========================================================================
    # Live Audio Guide — Streaming Q&A Pipeline (Step 10)
    # =========================================================================

    guide_qa_model: str = Field(
        default="",
        description=(
            "io.net model for Q&A answers. "
            "If empty, falls back to trip_chat_model."
        )
    )
    guide_qa_llm_timeout_seconds: int = Field(
        default=8,
        description="LLM call timeout for Q&A pipeline (seconds)."
    )
    guide_qa_max_answer_tokens: int = Field(
        default=150,
        description="Max tokens in Q&A LLM answer (keep short for audio — 2-4 sentences)."
    )
    guide_qa_max_audio_bytes: int = Field(
        default=5_242_880,
        description="Max audio upload size for Q&A (bytes). Default: 5 MB."
    )
    guide_qa_max_transcript_chars: int = Field(
        default=200,
        description="Max transcript length to send to LLM (safety truncation)."
    )
    guide_qa_questions_per_90s: int = Field(
        default=1,
        description="Max Q&A questions per 90 seconds of billed time."
    )



# Global settings instance
settings = Settings()
