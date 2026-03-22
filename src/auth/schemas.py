"""
Pydantic schemas for authentication API requests and responses.
"""
from typing import Optional
from pydantic import BaseModel, Field, EmailStr
from uuid import UUID
from datetime import datetime


# =============================================================================
# User & Session Responses
# =============================================================================

class UserResponse(BaseModel):
    """User data returned to client."""
    id: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SessionResponse(BaseModel):
    """Session data returned after successful authentication."""
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int  # Access token expiration in seconds
    user: UserResponse


# =============================================================================
# Apple Sign-In
# =============================================================================

class AppleAuthRequest(BaseModel):
    """Request for Apple Sign-In authentication."""
    id_token: str = Field(..., description="Apple ID token from Sign in with Apple")
    # Apple may provide these on first sign-in
    first_name: Optional[str] = Field(None, description="User's first name (only on first auth)")
    last_name: Optional[str] = Field(None, description="User's last name (only on first auth)")


# =============================================================================
# Google Sign-In
# =============================================================================

class GoogleAuthRequest(BaseModel):
    """Request for Google Sign-In authentication."""
    id_token: str = Field(..., description="Google ID token from Google Sign-In")


# =============================================================================
# Email OTP
# =============================================================================

class EmailStartRequest(BaseModel):
    """Request to start email OTP flow."""
    email: EmailStr = Field(..., description="Email address to send OTP code to")


class EmailStartResponse(BaseModel):
    """Response after starting email OTP flow."""
    challenge_id: str = Field(..., description="Challenge ID to use for verification")
    message: str = Field(default="OTP code sent to your email")
    delivery_method: str = Field(default="email", description="How the OTP was delivered")
    debug_code: Optional[str] = Field(default=None, description="OTP code returned in local debug mode")


class EmailVerifyRequest(BaseModel):
    """Request to verify email OTP code."""
    challenge_id: str = Field(..., description="Challenge ID from start response")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code")


# =============================================================================
# Token Refresh
# =============================================================================

class RefreshRequest(BaseModel):
    """Request to refresh access token."""
    refresh_token: str = Field(..., description="Refresh token from previous session")


# =============================================================================
# Logout
# =============================================================================

class LogoutRequest(BaseModel):
    """Request to logout (revoke session)."""
    refresh_token: Optional[str] = Field(None, description="Refresh token to revoke (optional)")


# =============================================================================
# Error Responses
# =============================================================================

class PaywallErrorResponse(BaseModel):
    """Error response for paywall-gated actions."""
    code: str = "PAYWALL_REQUIRED"
    message: str = Field(..., description="Human-readable error message")
    detail: Optional[str] = Field(None, description="Additional details")


class AuthErrorResponse(BaseModel):
    """Error response for authentication errors."""
    code: str
    message: str
    detail: Optional[str] = None
