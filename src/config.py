"""
Configuration management for the Trip Planning backend.
Uses Pydantic Settings to load configuration from environment variables.
"""
from typing import Optional
from pydantic import Field
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

    # Google Maps Platform / Places API
    google_maps_api_key: Optional[str] = Field(
        default=None,
        description="Google Maps API key for Places API"
    )
    google_places_base_url: str = Field(
        default="https://maps.googleapis.com/maps/api/place/textsearch/json",
        description="Base URL for Google Places Text Search API"
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

    # Server
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    debug: bool = Field(default=False, description="Debug mode")


# Global settings instance
settings = Settings()
