"""
Configuration management for the Trip Planning backend.
Uses Pydantic Settings to load configuration from environment variables.
"""
from typing import Optional
from pydantic import Field, model_validator
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
        default=2,
        description="Candidate multiplier per required block for agentic POI curation"
    )
    agentic_min_candidates_per_category: int = Field(
        default=6,
        description="Minimum POI candidates per category for agentic planning"
    )
    agentic_max_candidates_per_category: int = Field(
        default=20,
        description="Maximum POI candidates per category for agentic planning"
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
    google_places_default_language: str = Field(
        default="en",
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
        default=4.5,
        description="Minimum POI rating for smart routing selection"
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

    # Server
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    debug: bool = Field(default=False, description="Debug mode")


# Global settings instance
settings = Settings()
