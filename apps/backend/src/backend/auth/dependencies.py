from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import cast

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.enums import UserRole
from backend.auth.rate_limiter import RateLimiter
from backend.auth.service import AuthService
from backend.auth.tokens import TokenService
from backend.core.config import Settings, get_settings
from backend.db.dependencies import get_db_session

_TOKEN_SERVICE: TokenService | None = None
_AUTH_SERVICE: AuthService | None = None


@dataclass(frozen=True)
class CurrentUser:
    """Lightweight representation of the authenticated user."""

    id: uuid.UUID
    email: str
    role: UserRole


async def get_db(session: AsyncSession = Depends(get_db_session)) -> AsyncSession:
    return session


def get_token_service(settings: Settings = Depends(get_settings)) -> TokenService:
    global _TOKEN_SERVICE
    if _TOKEN_SERVICE is None:
        _TOKEN_SERVICE = TokenService(settings)
    return _TOKEN_SERVICE


def get_auth_service(
    token_service: TokenService = Depends(get_token_service),
) -> AuthService:
    global _AUTH_SERVICE
    if _AUTH_SERVICE is None:
        _AUTH_SERVICE = AuthService(token_service)
    return _AUTH_SERVICE


def get_rate_limiter(request: Request) -> RateLimiter:
    limiter_obj = getattr(request.app.state, "rate_limiter", None)
    if not isinstance(limiter_obj, RateLimiter):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Rate limiter is not configured",
        )
    return cast(RateLimiter, limiter_obj)


def get_current_user(request: Request) -> CurrentUser:
    current_user_obj = getattr(request.state, "current_user", None)
    if not isinstance(current_user_obj, CurrentUser):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return cast(CurrentUser, current_user_obj)


def require_roles(*roles: UserRole) -> Callable[[CurrentUser], Awaitable[CurrentUser]]:
    async def _dependency(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if roles and current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return _dependency
