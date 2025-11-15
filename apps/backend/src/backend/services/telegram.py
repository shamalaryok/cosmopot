from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from user_service import repository, services
from user_service.enums import UserRole
from user_service.models import User, UserProfile, UserSession
from user_service.schemas import (
    UserCreate,
    UserProfileCreate,
    UserProfileUpdate,
    UserSessionCreate,
)

__all__ = [
    "TelegramAuthError",
    "TelegramAuthInactiveUserError",
    "TelegramAuthReplayError",
    "TelegramAuthResult",
    "TelegramAuthService",
    "TelegramAuthSignatureError",
    "TelegramLoginPayload",
]


class TelegramAuthError(RuntimeError):
    """Base error raised for Telegram authentication failures."""


class TelegramAuthSignatureError(TelegramAuthError):
    """Raised when the payload signature validation fails."""


class TelegramAuthReplayError(TelegramAuthError):
    """Raised when the payload is considered expired or replayed."""


class TelegramAuthInactiveUserError(TelegramAuthError):
    """Raised when the mapped user account is not permitted to authenticate."""


class TelegramLoginPayload(BaseModel):
    """Pydantic representation of the Telegram auth payload."""

    id: int = Field(..., ge=1)
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    photo_url: HttpUrl | None = None
    auth_date: int = Field(..., ge=0)
    hash: str = Field(..., min_length=64, max_length=64)

    model_config = ConfigDict(extra="ignore")

    @field_validator("hash")
    @classmethod
    def _normalise_hash(cls, value: str) -> str:
        return value.lower()

    @property
    def auth_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.auth_date, tz=UTC)

    def data_check_items(self) -> list[tuple[str, str]]:
        payload = self.model_dump(exclude_none=True)
        payload.pop("hash", None)
        return sorted((key, _stringify(value)) for key, value in payload.items())


@dataclass(slots=True)
class TelegramAuthResult:
    user: User
    access_token: str
    expires_at: datetime
    token_type: str = "bearer"


class TelegramAuthService:
    """Service responsible for validating Telegram logins and issuing sessions."""

    def __init__(
        self,
        *,
        bot_token: str,
        login_ttl_seconds: int,
        jwt_secret: str,
        jwt_algorithm: str,
        access_token_ttl_seconds: int,
    ) -> None:
        if not bot_token:
            raise ValueError("bot_token must be provided for Telegram authentication")
        if login_ttl_seconds <= 0:
            raise ValueError("login_ttl_seconds must be positive")
        if access_token_ttl_seconds <= 0:
            raise ValueError("access_token_ttl_seconds must be positive")
        if not jwt_secret:
            raise ValueError("jwt_secret must be provided")

        self._bot_secret = hashlib.sha256(bot_token.encode("utf-8")).digest()
        self._login_ttl = timedelta(seconds=login_ttl_seconds)
        self._jwt_secret = jwt_secret
        self._jwt_algorithm = jwt_algorithm
        self._access_ttl = timedelta(seconds=access_token_ttl_seconds)

    async def authenticate(
        self,
        session: AsyncSession,
        payload: TelegramLoginPayload,
        *,
        user_agent: str | None,
        ip_address: str | None,
    ) -> TelegramAuthResult:
        """Validate the Telegram payload and return the issued credentials."""

        self._verify_signature(payload)
        self._enforce_replay_protection(payload)

        user = await self._get_user_by_telegram_id(session, payload.id)
        if user is None:
            user = await self._register_user(session, payload)
        else:
            self._ensure_user_is_active(user)
            await self._sync_profile(session, user, payload)

        user_session = await self._persist_session(
            session,
            user,
            user_agent=_truncate(user_agent, 255),
            ip_address=_truncate(ip_address, 45),
        )

        return TelegramAuthResult(
            user=user,
            access_token=user_session.session_token,
            expires_at=user_session.expires_at,
        )

    def _verify_signature(self, payload: TelegramLoginPayload) -> None:
        data_check_string = "\n".join(
            f"{key}={value}" for key, value in payload.data_check_items()
        )
        expected_hash = hmac.new(
            self._bot_secret,
            data_check_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected_hash, payload.hash):
            raise TelegramAuthSignatureError("Invalid Telegram payload signature")

    def _enforce_replay_protection(self, payload: TelegramLoginPayload) -> None:
        now = datetime.now(UTC)
        auth_datetime = payload.auth_datetime
        if auth_datetime > now + timedelta(minutes=5):
            # Auth date should never be in the future. Treat as suspicious.
            raise TelegramAuthReplayError("Telegram payload timestamp is in the future")

        if now - auth_datetime > self._login_ttl:
            raise TelegramAuthReplayError("Telegram payload is too old")

    async def _get_user_by_telegram_id(
        self, session: AsyncSession, telegram_id: int
    ) -> User | None:
        stmt = (
            select(User)
            .options(joinedload(User.profile))
            .join(UserProfile, UserProfile.user_id == User.id)
            .where(UserProfile.telegram_id == telegram_id)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _register_user(
        self, session: AsyncSession, payload: TelegramLoginPayload
    ) -> User:
        email = self._build_email(payload)
        hashed_password = hashlib.sha256(
            f"{payload.id}:{payload.auth_date}".encode()
        ).hexdigest()

        user_data = UserCreate(
            email=email,
            hashed_password=hashed_password,
            role=UserRole.USER,
            is_active=True,
        )
        profile_template = UserProfileCreate(
            user_id=0,
            first_name=payload.first_name,
            last_name=payload.last_name,
            telegram_id=payload.id,
        )
        user = await services.register_user(session, user_data, profile_template)
        return user

    async def _sync_profile(
        self, session: AsyncSession, user: User, payload: TelegramLoginPayload
    ) -> None:
        profile = user.profile
        if profile is None:
            profile_data = UserProfileCreate(
                user_id=user.id,
                first_name=payload.first_name,
                last_name=payload.last_name,
                telegram_id=payload.id,
            )
            await repository.create_profile(session, profile_data)
            await session.refresh(user, ["profile"])
            return

        updates: dict[str, Any] = {}
        if payload.first_name and payload.first_name != profile.first_name:
            updates["first_name"] = payload.first_name
        if payload.last_name and payload.last_name != profile.last_name:
            updates["last_name"] = payload.last_name

        if updates:
            await repository.update_profile(
                session,
                profile,
                UserProfileUpdate(**updates),
            )

    async def _persist_session(
        self,
        session: AsyncSession,
        user: User,
        *,
        user_agent: str | None,
        ip_address: str | None,
    ) -> UserSession:
        max_attempts = 5

        for _ in range(max_attempts):
            token, expires_at = self._issue_token(user)
            existing = await repository.get_session_by_token(session, token)
            if existing is not None:
                if existing.user_id == user.id:
                    now = datetime.now(UTC)
                    if (
                        existing.revoked_at is None
                        and existing.ended_at is None
                        and existing.expires_at > now
                    ):
                        updated = False
                        if existing.user_agent != user_agent:
                            existing.user_agent = user_agent
                            updated = True
                        if existing.ip_address != ip_address:
                            existing.ip_address = ip_address
                            updated = True
                        if expires_at > existing.expires_at:
                            existing.expires_at = expires_at
                            updated = True
                        if updated:
                            await session.flush()
                            await session.refresh(existing)
                        return existing
                continue

            session_data = UserSessionCreate(
                user_id=user.id,
                session_token=token,
                user_agent=user_agent,
                ip_address=ip_address,
                expires_at=expires_at,
            )
            return await services.open_session(session, session_data)

        raise TelegramAuthError(
            "Unable to persist session token after multiple attempts",
        )

    def _ensure_user_is_active(self, user: User) -> None:
        if not user.is_active or user.deleted_at is not None:
            raise TelegramAuthInactiveUserError("User account is disabled")

    def _issue_token(self, user: User) -> tuple[str, datetime]:
        issued_at = datetime.now(UTC)
        expires_at = issued_at + self._access_ttl
        payload = {
            "sub": str(user.id),
            "iat": int(issued_at.timestamp()),
            "exp": int(expires_at.timestamp()),
            "jti": secrets.token_hex(16),
        }
        token = jwt.encode(payload, self._jwt_secret, algorithm=self._jwt_algorithm)
        return token, expires_at

    def _build_email(self, payload: TelegramLoginPayload) -> str:
        if payload.username:
            base = payload.username.lower()
        else:
            base = f"telegram{payload.id}"
        return f"{base}.{payload.id}@example.com"


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _truncate(value: str | None, max_length: int) -> str | None:
    if value is None:
        return None
    return value[:max_length]
