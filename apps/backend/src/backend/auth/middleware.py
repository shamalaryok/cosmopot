from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict
from uuid import UUID

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp

from backend.auth.dependencies import CurrentUser
from backend.auth.enums import UserRole
from backend.auth.exceptions import InvalidTokenError, TokenExpiredError
from backend.auth.models import User, UserSession
from backend.auth.tokens import TokenService
from backend.db.session import get_session_factory


class _TokenPayload(TypedDict):
    user_id: UUID
    session_id: UUID
    role: UserRole


def _now() -> datetime:
    return datetime.now(UTC)


def _payload_to_current_user(payload: _TokenPayload, user: User) -> CurrentUser:
    """Convert a token payload and user model into CurrentUser."""
    return CurrentUser(
        id=payload["user_id"],
        email=user.email,
        role=user.role,
    )


class CurrentUserMiddleware(BaseHTTPMiddleware):
    """Populate ``request.state.current_user`` when a valid access token is supplied."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        token_service: TokenService,
        access_cookie_name: str,
    ) -> None:
        super().__init__(app)
        self._token_service = token_service
        self._access_cookie_name = access_cookie_name
        self._session_factory = get_session_factory()

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request.state.current_user = None
        token = self._extract_token(request)

        if token is not None:
            payload = await self._decode_token(token)
            if payload is not None:
                current_user = await self._resolve_current_user(payload)
                if current_user is not None:
                    request.state.current_user = current_user

        response = await call_next(request)
        return response

    async def _resolve_current_user(self, payload: _TokenPayload) -> CurrentUser | None:
        """Resolve and validate the current user from a token payload."""
        async with self._session_factory() as session:
            user = await session.get(User, payload["user_id"])
            session_model = await session.get(UserSession, payload["session_id"])

        if user is None or session_model is None:
            return None
        if not self._is_session_valid(user, session_model):
            return None

        return _payload_to_current_user(payload, user)

    async def _decode_token(self, token: str) -> _TokenPayload | None:
        try:
            payload = self._token_service.decode_access_token(token)
        except (InvalidTokenError, TokenExpiredError):
            return None

        return _TokenPayload(
            user_id=payload.subject,
            session_id=payload.session_id,
            role=UserRole(payload.role),
        )

    def _extract_token(self, request: Request) -> str | None:
        authorization = request.headers.get("Authorization")
        if authorization and authorization.lower().startswith("bearer "):
            return authorization.split(" ", 1)[1].strip()

        cookie_token = request.cookies.get(self._access_cookie_name)
        if cookie_token:
            return cookie_token
        return None

    def _is_session_valid(
        self,
        user: User | None,
        session: UserSession | None,
    ) -> bool:
        if user is None or session is None:
            return False
        if not user.is_active or not user.is_verified:
            return False
        if session.revoked_at is not None:
            return False
        if session.expires_at <= _now():
            return False
        return True
