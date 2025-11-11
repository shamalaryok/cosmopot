from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.enums import UserRole
from backend.auth.exceptions import (
    AccountDisabledError,
    AccountNotVerifiedError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidTokenError,
    SessionRevokedError,
    TokenExpiredError,
    VerificationTokenInvalidError,
)
from backend.auth.models import User, UserSession, VerificationToken
from backend.auth.passwords import hash_password, needs_rehash, verify_password
from backend.auth.tokens import TokenPair, TokenService


@dataclass(frozen=True)
class AuthResult:
    """Result of an authentication workflow."""

    user: User
    tokens: TokenPair


def _now() -> datetime:
    return datetime.now(UTC)


def _hash_token(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return digest


class AuthService:
    """High-level authentication workflows around users and sessions."""

    def __init__(self, token_service: TokenService) -> None:
        self._token_service = token_service
        self._verification_expiry = timedelta(hours=24)

    async def register(
        self,
        session: AsyncSession,
        *,
        email: str,
        password: str,
        role: UserRole = UserRole.USER,
    ) -> tuple[User, str]:
        normalized_email = email.strip().lower()
        existing = await session.scalar(
            select(User).where(User.email == normalized_email)
        )
        if existing is not None:
            raise EmailAlreadyRegisteredError

        hashed = hash_password(password)
        user = User(email=normalized_email, hashed_password=hashed, role=role)
        session.add(user)
        await session.flush()

        verification_token = secrets.token_urlsafe(32)
        token_hash = _hash_token(verification_token)
        token_model = VerificationToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=_now() + self._verification_expiry,
        )
        session.add(token_model)

        await session.commit()
        await session.refresh(user)
        return user, verification_token

    async def verify_account(self, session: AsyncSession, *, token: str) -> User:
        token_hash = _hash_token(token)
        verification = await session.scalar(
            select(VerificationToken)
            .where(VerificationToken.token_hash == token_hash)
            .where(VerificationToken.used_at.is_(None))
        )
        if verification is None or verification.expires_at <= _now():
            raise VerificationTokenInvalidError

        user = await session.get(User, verification.user_id)
        if user is None:
            raise VerificationTokenInvalidError

        user.is_verified = True
        verification.used_at = _now()

        await session.commit()
        await session.refresh(user)
        return user

    async def login(
        self,
        session: AsyncSession,
        *,
        email: str,
        password: str,
        user_agent: str | None,
        ip_address: str | None,
    ) -> AuthResult:
        normalized_email = email.strip().lower()
        user = await session.scalar(select(User).where(User.email == normalized_email))
        if user is None or not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError

        if not user.is_verified:
            raise AccountNotVerifiedError
        if not user.is_active:
            raise AccountDisabledError

        if needs_rehash(user.hashed_password):
            user.hashed_password = hash_password(password)

        result = await self._issue_tokens(
            session,
            user,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        return result

    async def refresh(
        self,
        session: AsyncSession,
        *,
        refresh_token: str,
        user_agent: str | None,
        ip_address: str | None,
    ) -> AuthResult:
        payload = self._token_service.decode_refresh_token(refresh_token)

        token_hash = _hash_token(refresh_token)

        db_session = await session.get(UserSession, payload.session_id)
        if db_session is None:
            raise SessionRevokedError

        if db_session.revoked_at is not None:
            raise SessionRevokedError

        if db_session.expires_at <= _now():
            raise TokenExpiredError("Refresh token expired")

        if not secrets.compare_digest(db_session.refresh_token_hash, token_hash):
            db_session.revoked_at = _now()
            await session.commit()
            raise InvalidTokenError("Refresh token mismatch")

        user = await session.get(User, payload.subject)
        if user is None:
            raise SessionRevokedError
        if not user.is_active:
            raise AccountDisabledError

        db_session.revoked_at = _now()
        db_session.rotated_at = _now()

        result = await self._issue_tokens(
            session,
            user,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        return result

    async def logout(self, session: AsyncSession, *, refresh_token: str) -> None:
        payload = self._token_service.decode_refresh_token(refresh_token)

        db_session = await session.get(UserSession, payload.session_id)
        if db_session is None:
            return

        token_hash = _hash_token(refresh_token)
        if not secrets.compare_digest(db_session.refresh_token_hash, token_hash):
            return

        db_session.revoked_at = _now()
        await session.commit()

    async def _issue_tokens(
        self,
        session: AsyncSession,
        user: User,
        *,
        user_agent: str | None,
        ip_address: str | None,
    ) -> AuthResult:
        session_record = UserSession(
            user_id=user.id,
            refresh_token_hash="",
            user_agent=user_agent,
            ip_address=ip_address,
            expires_at=_now(),
        )
        session.add(session_record)
        await session.flush()

        tokens = self._token_service.create_token_pair(
            user_id=user.id,
            session_id=session_record.id,
            role=user.role.value,
        )

        session_record.refresh_token_hash = _hash_token(tokens.refresh_token)
        session_record.expires_at = tokens.refresh_expires_at

        await session.commit()
        await session.refresh(user)
        return AuthResult(user=user, tokens=tokens)
