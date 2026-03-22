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


# Global settings instance
settings = Settings()
