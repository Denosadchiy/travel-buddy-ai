"""
Authentication service - business logic for user authentication.
"""
from typing import Optional, Tuple
from uuid import UUID
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import (
    UserModel,
    AuthIdentityModel,
    SessionModel,
    OTPChallengeModel,
)
from src.auth.schemas import UserResponse, SessionResponse, EmailStartResponse
from src.auth.jwt import (
    create_access_token,
    create_refresh_token,
    verify_token,
    hash_token,
    get_token_expiry_seconds,
    TokenExpiredError,
    TokenInvalidError,
)
from src.auth.providers import (
    apple_provider,
    google_provider,
    email_otp_provider,
    TokenVerificationError,
    ProviderError,
)
from src.auth.config import auth_settings
from src.config import settings


class AuthService:
    """Service class for authentication operations."""

    async def authenticate_apple(
        self,
        db: AsyncSession,
        id_token: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> SessionResponse:
        """
        Authenticate user with Apple Sign-In.

        Args:
            db: Database session
            id_token: Apple ID token
            first_name: User's first name (only on first auth)
            last_name: User's last name (only on first auth)
            device_id: Device ID for session tracking

        Returns:
            SessionResponse with tokens and user info
        """
        # Verify Apple token
        claims = await apple_provider.verify_token(id_token)
        apple_sub = claims["sub"]
        email = claims.get("email")

        # Build display name
        display_name = None
        if first_name or last_name:
            parts = [p for p in [first_name, last_name] if p]
            display_name = " ".join(parts) if parts else None

        # Find or create user
        user, _ = await self._find_or_create_user(
            db=db,
            provider="apple",
            provider_subject=apple_sub,
            email=email,
            display_name=display_name,
        )

        # Create session
        return await self._create_session(db, user, device_id)

    async def authenticate_google(
        self,
        db: AsyncSession,
        id_token: str,
        device_id: Optional[str] = None,
    ) -> SessionResponse:
        """
        Authenticate user with Google Sign-In.

        Args:
            db: Database session
            id_token: Google ID token
            device_id: Device ID for session tracking

        Returns:
            SessionResponse with tokens and user info
        """
        # Verify Google token
        claims = await google_provider.verify_token(id_token)
        google_sub = claims["sub"]
        email = claims.get("email")
        name = claims.get("name")
        picture = claims.get("picture")

        # Find or create user
        user, _ = await self._find_or_create_user(
            db=db,
            provider="google",
            provider_subject=google_sub,
            email=email,
            display_name=name,
            avatar_url=picture,
        )

        # Create session
        return await self._create_session(db, user, device_id)

    async def start_email_auth(
        self,
        db: AsyncSession,
        email: str,
    ) -> EmailStartResponse:
        """
        Start email OTP authentication flow.

        Args:
            db: Database session
            email: Email address

        Returns:
            EmailStartResponse with challenge metadata
        """
        # Generate OTP
        code = email_otp_provider.generate_otp()
        code_hash = email_otp_provider.hash_otp(code)

        # Create challenge
        expires_at = datetime.utcnow() + timedelta(minutes=auth_settings.otp_expire_minutes)
        challenge = OTPChallengeModel(
            email=email.lower(),
            code_hash=code_hash,
            expires_at=expires_at,
        )
        db.add(challenge)
        await db.flush()

        try:
            await email_otp_provider.send_otp_email(email, code)
            return EmailStartResponse(
                challenge_id=str(challenge.id),
                message="OTP code sent to your email",
                delivery_method="email",
            )
        except ProviderError as exc:
            if settings.debug:
                print(f"[DEBUG OTP FALLBACK] {email}: {code} ({exc})")
                return EmailStartResponse(
                    challenge_id=str(challenge.id),
                    message="Email delivery is temporarily unavailable. Use the one-time code below to continue.",
                    delivery_method="debug",
                    debug_code=code,
                )
            raise

    async def verify_email_auth(
        self,
        db: AsyncSession,
        challenge_id: str,
        code: str,
        device_id: Optional[str] = None,
    ) -> SessionResponse:
        """
        Verify email OTP and complete authentication.

        Args:
            db: Database session
            challenge_id: Challenge ID from start response
            code: OTP code entered by user
            device_id: Device ID for session tracking

        Returns:
            SessionResponse with tokens and user info

        Raises:
            ValueError: If challenge invalid, expired, or code wrong
        """
        # Find challenge
        result = await db.execute(
            select(OTPChallengeModel).where(
                OTPChallengeModel.id == UUID(challenge_id)
            )
        )
        challenge = result.scalar_one_or_none()

        if not challenge:
            raise ValueError("Invalid challenge")

        if not challenge.is_valid:
            raise ValueError("Challenge expired or too many attempts")

        # Increment attempts
        challenge.attempts += 1

        # Verify code
        if not email_otp_provider.verify_otp(code, challenge.code_hash):
            await db.flush()
            raise ValueError("Invalid code")

        # Mark as verified
        challenge.verified_at = datetime.utcnow()

        # Find or create user
        user, _ = await self._find_or_create_user(
            db=db,
            provider="email",
            provider_subject=challenge.email,
            email=challenge.email,
        )

        # Create session
        return await self._create_session(db, user, device_id)

    async def refresh_session(
        self,
        db: AsyncSession,
        refresh_token: str,
        device_id: Optional[str] = None,
    ) -> SessionResponse:
        """
        Refresh an access token using a refresh token.

        Args:
            db: Database session
            refresh_token: Refresh token from previous session
            device_id: Device ID for session tracking

        Returns:
            SessionResponse with new tokens

        Raises:
            ValueError: If refresh token invalid or session revoked
        """
        try:
            # Verify refresh token
            payload = verify_token(refresh_token, expected_type="refresh")
            user_id = UUID(payload["sub"])
            session_id = UUID(payload["sid"])

            # Find session
            token_hash = hash_token(refresh_token)
            result = await db.execute(
                select(SessionModel).where(
                    SessionModel.id == session_id,
                    SessionModel.refresh_token_hash == token_hash,
                )
            )
            session = result.scalar_one_or_none()

            if not session or not session.is_valid:
                raise ValueError("Session expired or revoked")

            # Get user
            result = await db.execute(
                select(UserModel).where(UserModel.id == user_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                raise ValueError("User not found")

            # Revoke old session
            session.revoked_at = datetime.utcnow()

            # Create new session
            return await self._create_session(db, user, device_id)

        except TokenExpiredError:
            raise ValueError("Refresh token expired")
        except TokenInvalidError as e:
            raise ValueError(f"Invalid refresh token: {str(e)}")

    async def logout(
        self,
        db: AsyncSession,
        user_id: UUID,
        refresh_token: Optional[str] = None,
    ) -> bool:
        """
        Logout user by revoking session(s).

        Args:
            db: Database session
            user_id: User ID
            refresh_token: Optional specific refresh token to revoke

        Returns:
            True if logout successful
        """
        now = datetime.utcnow()

        if refresh_token:
            # Revoke specific session
            token_hash = hash_token(refresh_token)
            result = await db.execute(
                select(SessionModel).where(
                    SessionModel.user_id == user_id,
                    SessionModel.refresh_token_hash == token_hash,
                    SessionModel.revoked_at.is_(None),
                )
            )
            session = result.scalar_one_or_none()
            if session:
                session.revoked_at = now
        else:
            # Revoke all sessions for user
            result = await db.execute(
                select(SessionModel).where(
                    SessionModel.user_id == user_id,
                    SessionModel.revoked_at.is_(None),
                )
            )
            sessions = result.scalars().all()
            for session in sessions:
                session.revoked_at = now

        return True

    async def _find_or_create_user(
        self,
        db: AsyncSession,
        provider: str,
        provider_subject: str,
        email: Optional[str] = None,
        display_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> Tuple[UserModel, bool]:
        """
        Find existing user by identity or create new user.

        Returns:
            Tuple of (user, created) where created is True if new user
        """
        # Look for existing identity
        result = await db.execute(
            select(AuthIdentityModel).where(
                AuthIdentityModel.provider == provider,
                AuthIdentityModel.provider_subject == provider_subject,
            )
        )
        identity = result.scalar_one_or_none()

        if identity:
            # User exists
            result = await db.execute(
                select(UserModel).where(UserModel.id == identity.user_id)
            )
            user = result.scalar_one()

            # Update user info if provided and changed
            if display_name and not user.display_name:
                user.display_name = display_name
            if avatar_url and not user.avatar_url:
                user.avatar_url = avatar_url
            if email and not user.email:
                user.email = email.lower()

            await db.flush()
            return user, False

        # Check if email matches existing user (link identity)
        user = None
        if email:
            result = await db.execute(
                select(UserModel).where(UserModel.email == email.lower())
            )
            user = result.scalar_one_or_none()

        if not user:
            # Create new user
            user = UserModel(
                email=email.lower() if email else None,
                display_name=display_name,
                avatar_url=avatar_url,
            )
            db.add(user)
            await db.flush()

        # Create identity linking to user
        identity = AuthIdentityModel(
            user_id=user.id,
            provider=provider,
            provider_subject=provider_subject,
            email=email.lower() if email else None,
        )
        db.add(identity)
        await db.flush()

        return user, True

    async def _create_session(
        self,
        db: AsyncSession,
        user: UserModel,
        device_id: Optional[str] = None,
    ) -> SessionResponse:
        """Create new session with access and refresh tokens."""
        # Create access token
        access_token = create_access_token(user.id)

        # Create session record first (need ID for refresh token)
        expires_at = datetime.utcnow() + timedelta(days=auth_settings.refresh_token_expire_days)
        session = SessionModel(
            user_id=user.id,
            refresh_token_hash="placeholder",  # Will update after creating token
            device_id=device_id,
            expires_at=expires_at,
        )
        db.add(session)
        await db.flush()

        # Create refresh token with session ID
        refresh_token = create_refresh_token(user.id, session.id)

        # Update session with actual token hash
        session.refresh_token_hash = hash_token(refresh_token)
        await db.flush()

        # Build user response
        user_response = UserResponse(
            id=str(user.id),
            email=user.email,
            display_name=user.display_name,
            avatar_url=user.avatar_url,
            created_at=user.created_at,
        )

        return SessionResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=get_token_expiry_seconds(),
            user=user_response,
        )


# Global service instance
auth_service = AuthService()
