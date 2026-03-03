"""
Authentication configuration settings.
Loaded from environment variables via Pydantic Settings.
"""
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    """Authentication-related settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # JWT Configuration
    jwt_secret_key: str = Field(
        default="CHANGE_ME_IN_PRODUCTION_USE_SECURE_RANDOM_STRING",
        description="Secret key for signing JWT tokens. MUST be changed in production!"
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="Algorithm for JWT signing"
    )
    access_token_expire_minutes: int = Field(
        default=15,
        description="Access token expiration time in minutes"
    )
    refresh_token_expire_days: int = Field(
        default=30,
        description="Refresh token expiration time in days"
    )

    # Apple Sign-In
    apple_client_id: Optional[str] = Field(
        default=None,
        description="Apple Sign-In client ID (app bundle ID)"
    )
    apple_team_id: Optional[str] = Field(
        default=None,
        description="Apple Developer Team ID"
    )

    # Google Sign-In
    google_client_id: Optional[str] = Field(
        default=None,
        description="Google OAuth client ID for iOS app"
    )
    google_client_id_web: Optional[str] = Field(
        default=None,
        description="Google OAuth client ID for web (if different)"
    )

    # Email Configuration (Resend HTTP API)
    resend_api_key: Optional[str] = Field(
        default=None,
        description="Resend API key for sending emails"
    )
    email_from: str = Field(
        default="Locally <onboarding@resend.dev>",
        description="From address for emails (e.g. 'Locally <onboarding@resend.dev>')"
    )
    otp_expire_minutes: int = Field(
        default=10,
        description="OTP code expiration time in minutes"
    )
    otp_max_attempts: int = Field(
        default=5,
        description="Maximum OTP verification attempts before invalidation"
    )
    otp_dev_mode: bool = Field(
        default=True,
        description="If True, log OTP to console instead of sending email (for development)"
    )

    # Guest Limits
    guest_max_trips: int = Field(
        default=1,
        description="Maximum number of trips a guest can generate"
    )

    # Freemium Gating (controls auth requirements)
    freemium_enabled: bool = Field(
        default=True,
        description="Enable freemium restrictions (Day 1 only for guests, trip limit). Set to False to disable all auth requirements."
    )


# Global auth settings instance
auth_settings = AuthSettings()
