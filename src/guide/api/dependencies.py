"""
FastAPI dependency injection for the Live Audio Guide module.

Mirrors the patterns in src/auth/dependencies.py:
  - get_current_user       → JWT required
  - get_current_user_admin → JWT + admin role required
  - get_db                 → async DB session
  - get_navigation_repo    → NavigationRepository scoped to request
  - get_session_manager    → shared SessionManager singleton
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database import get_db
from src.auth.jwt import TokenExpiredError, TokenInvalidError, verify_token
from src.auth.models import UserModel
from src.guide.application.navigation_repository import NavigationRepository
from src.guide.application.session_manager import SessionManager
from sqlalchemy import select

# ---------------------------------------------------------------------------
# Bearer schemes (re-use auth module's token verification)
# ---------------------------------------------------------------------------

_required_bearer = HTTPBearer(auto_error=True)
_optional_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_required_bearer),
    db: AsyncSession = Depends(get_db),
) -> UserModel:
    """Require a valid JWT access token. Raises 401 on failure."""
    try:
        payload = verify_token(credentials.credentials, expected_type="access")
        user_id = uuid.UUID(payload["sub"])
        result = await db.execute(select(UserModel).where(UserModel.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (TokenInvalidError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_admin(
    user: UserModel = Depends(get_current_user),
) -> UserModel:
    """Require a valid JWT token AND admin role. Raises 403 for non-admins."""
    # Admin role stored in UserModel.role field (if it exists) or as a flag.
    # Adjust to match the actual UserModel schema.
    role = getattr(user, "role", None)
    if role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


# ---------------------------------------------------------------------------
# Repository & service factories
# ---------------------------------------------------------------------------

def get_navigation_repo(db: AsyncSession = Depends(get_db)) -> NavigationRepository:
    """Create a NavigationRepository scoped to the current request's DB session."""
    return NavigationRepository(db)


# Module-level singleton — created once, shared across all requests
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """
    Return the shared SessionManager singleton.
    Lazy-initialised on first request.
    """
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
