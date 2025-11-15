from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from backend.auth.exceptions import InvalidTokenError, TokenExpiredError
from backend.core.config import Settings


@dataclass(frozen=True)
class TokenPayload:
    """Decoded information embedded within JWTs."""

    subject: uuid.UUID
    session_id: uuid.UUID
    token_type: str
    role: str
    expires_at: datetime
    issued_at: datetime


@dataclass(frozen=True)
class TokenPair:
    """Pair of access and refresh tokens issued to clients."""

    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime
    session_id: uuid.UUID


class TokenService:
    """Handles encoding and decoding of access and refresh tokens."""

    def __init__(self, settings: Settings) -> None:
        self._secret = settings.jwt.secret.get_secret_value()
        self._algorithm = settings.jwt.algorithm
        self._access_expiry = timedelta(minutes=settings.jwt.access_token_exp_minutes)
        self._refresh_expiry = timedelta(days=settings.jwt.refresh_token_exp_days)

    def create_token_pair(
        self,
        *,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        role: str,
    ) -> TokenPair:
        access_token, access_exp = self.create_access_token(
            user_id=user_id,
            session_id=session_id,
            role=role,
        )
        refresh_token, refresh_exp = self.create_refresh_token(
            user_id=user_id,
            session_id=session_id,
            role=role,
        )
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            access_expires_at=access_exp,
            refresh_expires_at=refresh_exp,
            session_id=session_id,
        )

    def create_access_token(
        self, *, user_id: uuid.UUID, session_id: uuid.UUID, role: str
    ) -> tuple[str, datetime]:
        return self._encode(
            user_id=user_id,
            session_id=session_id,
            token_type="access",
            expires_delta=self._access_expiry,
            role=role,
        )

    def create_refresh_token(
        self, *, user_id: uuid.UUID, session_id: uuid.UUID, role: str
    ) -> tuple[str, datetime]:
        return self._encode(
            user_id=user_id,
            session_id=session_id,
            token_type="refresh",
            expires_delta=self._refresh_expiry,
            role=role,
        )

    def decode_access_token(self, token: str) -> TokenPayload:
        return self._decode(token, expected_type="access")

    def decode_refresh_token(self, token: str) -> TokenPayload:
        return self._decode(token, expected_type="refresh")

    def _encode(
        self,
        *,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        token_type: str,
        expires_delta: timedelta,
        role: str,
    ) -> tuple[str, datetime]:
        now = datetime.now(UTC)
        expires_at = now + expires_delta
        payload = {
            "sub": str(user_id),
            "sid": str(session_id),
            "type": token_type,
            "role": role,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        token = jwt.encode(payload, self._secret, algorithm=self._algorithm)
        return token, expires_at

    def _decode(self, token: str, *, expected_type: str) -> TokenPayload:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                options={"require": ["exp", "iat", "sub", "sid", "type"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise TokenExpiredError("Token has expired") from exc
        except jwt.InvalidTokenError as exc:
            raise InvalidTokenError("Unable to decode token") from exc

        token_type = payload.get("type")
        if token_type != expected_type:
            raise InvalidTokenError("Unexpected token type")

        try:
            subject = uuid.UUID(str(payload["sub"]))
            session_id = uuid.UUID(str(payload["sid"]))
        except (KeyError, ValueError) as exc:
            raise InvalidTokenError("Token payload is malformed") from exc

        issued_at = datetime.fromtimestamp(int(payload["iat"]), tz=UTC)
        expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=UTC)
        role = str(payload.get("role", "user"))

        return TokenPayload(
            subject=subject,
            session_id=session_id,
            token_type=token_type,
            role=role,
            issued_at=issued_at,
            expires_at=expires_at,
        )
