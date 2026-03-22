"""
Authentication API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from src.infrastructure.database import get_db
from src.auth.schemas import (
    AppleAuthRequest,
    GoogleAuthRequest,
    EmailStartRequest,
    EmailStartResponse,
    EmailVerifyRequest,
    RefreshRequest,
    LogoutRequest,
    SessionResponse,
)
from src.auth.service import auth_service
from src.auth.providers import TokenVerificationError
from src.auth.dependencies import get_current_user, get_device_id
from src.auth.models import UserModel


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/apple",
    response_model=SessionResponse,
    summary="Sign in with Apple",
    description="Authenticate using Apple Sign-In ID token."
)
async def auth_apple(
    request: AppleAuthRequest,
    db: AsyncSession = Depends(get_db),
    device_id: Optional[str] = Depends(get_device_id),
) -> SessionResponse:
    """
    Authenticate with Apple Sign-In.

    The mobile app handles the Apple Sign-In flow and sends the resulting
    ID token to this endpoint for verification and session creation.
    """
    try:
        session = await auth_service.authenticate_apple(
            db=db,
            id_token=request.id_token,
            first_name=request.first_name,
            last_name=request.last_name,
            device_id=device_id,
        )
        await db.commit()
        return session

    except TokenVerificationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication failed: {str(e)}",
        )


@router.post(
    "/google",
    response_model=SessionResponse,
    summary="Sign in with Google",
    description="Authenticate using Google Sign-In ID token."
)
async def auth_google(
    request: GoogleAuthRequest,
    db: AsyncSession = Depends(get_db),
    device_id: Optional[str] = Depends(get_device_id),
) -> SessionResponse:
    """
    Authenticate with Google Sign-In.

    The mobile app handles the Google Sign-In flow and sends the resulting
    ID token to this endpoint for verification and session creation.
    """
    try:
        session = await auth_service.authenticate_google(
            db=db,
            id_token=request.id_token,
            device_id=device_id,
        )
        await db.commit()
        return session

    except TokenVerificationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication failed: {str(e)}",
        )


@router.post(
    "/email/start",
    response_model=EmailStartResponse,
    summary="Start email OTP flow",
    description="Send a one-time password to the user's email."
)
async def auth_email_start(
    request: EmailStartRequest,
    db: AsyncSession = Depends(get_db),
) -> EmailStartResponse:
    """
    Start email OTP authentication flow.

    Sends a 6-digit OTP code to the provided email address.
    Returns a challenge_id to use for verification.
    """
    try:
        response = await auth_service.start_email_auth(
            db=db,
            email=request.email,
        )
        await db.commit()
        return response

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send OTP: {str(e)}",
        )


@router.post(
    "/email/verify",
    response_model=SessionResponse,
    summary="Verify email OTP",
    description="Verify the OTP code and complete authentication."
)
async def auth_email_verify(
    request: EmailVerifyRequest,
    db: AsyncSession = Depends(get_db),
    device_id: Optional[str] = Depends(get_device_id),
) -> SessionResponse:
    """
    Verify email OTP and complete authentication.

    Takes the challenge_id from the start response and the OTP code
    entered by the user. Returns session tokens on success.
    """
    try:
        session = await auth_service.verify_email_auth(
            db=db,
            challenge_id=request.challenge_id,
            code=request.code,
            device_id=device_id,
        )
        await db.commit()
        return session

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification failed: {str(e)}",
        )


@router.post(
    "/refresh",
    response_model=SessionResponse,
    summary="Refresh access token",
    description="Get a new access token using a refresh token."
)
async def auth_refresh(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    device_id: Optional[str] = Depends(get_device_id),
) -> SessionResponse:
    """
    Refresh the access token.

    Use this when the access token expires to get a new one without
    requiring the user to re-authenticate.
    """
    try:
        session = await auth_service.refresh_session(
            db=db,
            refresh_token=request.refresh_token,
            device_id=device_id,
        )
        await db.commit()
        return session

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token refresh failed: {str(e)}",
        )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout",
    description="Revoke the current session or all sessions."
)
async def auth_logout(
    request: LogoutRequest = LogoutRequest(),
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Logout the current user.

    If refresh_token is provided, only that session is revoked.
    Otherwise, all sessions for the user are revoked.
    """
    try:
        await auth_service.logout(
            db=db,
            user_id=user.id,
            refresh_token=request.refresh_token,
        )
        await db.commit()

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Logout failed: {str(e)}",
        )


@router.get(
    "/me",
    response_model=dict,
    summary="Get current user",
    description="Get information about the currently authenticated user."
)
async def get_current_user_info(
    user: UserModel = Depends(get_current_user),
) -> dict:
    """Get the current authenticated user's information."""
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "created_at": user.created_at.isoformat(),
    }
