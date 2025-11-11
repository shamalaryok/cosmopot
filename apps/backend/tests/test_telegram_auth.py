# ruff: noqa: I001
"""Test telegram authentication."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from conftest import TEST_BOT_TOKEN
from backend.db.session import get_session_factory
from user_service import services
from user_service.models import User, UserProfile, UserSession
from user_service.schemas import UserCreate, UserProfileCreate

BASE_PAYLOAD = {
    "id": 777000,
    "first_name": "Telegram",
    "last_name": "User",
    "username": "telegram",
    "photo_url": "https://t.me/i/userpic/320/telegram.jpg",
}


@pytest.mark.asyncio
async def test_telegram_auth_creates_user_and_session(
    async_client: AsyncClient,
) -> None:
    payload = build_payload()

    response = await async_client.post("/api/v1/auth/telegram", json=payload)
    assert response.status_code == 200

    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]

    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await _fetch_user_by_telegram_id(session, payload["id"])
        assert user is not None
        assert user.profile is not None
        assert user.profile.telegram_id == payload["id"]

        sessions = await _fetch_sessions_for_user(session, user.id)
        assert len(sessions) == 1
        assert sessions[0].session_token == body["access_token"]


@pytest.mark.asyncio
async def test_telegram_auth_is_idempotent(async_client: AsyncClient) -> None:
    first_payload = build_payload()
    second_payload = build_payload()

    first_response = await async_client.post(
        "/api/v1/auth/telegram", json=first_payload
    )
    assert first_response.status_code == 200

    second_response = await async_client.post(
        "/api/v1/auth/telegram", json=second_payload
    )
    assert second_response.status_code == 200

    session_factory = get_session_factory()
    async with session_factory() as session:
        user_count = await session.scalar(select(func.count()).select_from(User))
        assert user_count == 1

        sessions = await _fetch_sessions_for_user(
            session, first_payload["id"], by_telegram=True
        )
        assert len(sessions) == 2


@pytest.mark.asyncio
async def test_telegram_auth_signature_mismatch(async_client: AsyncClient) -> None:
    payload = build_payload()
    payload["first_name"] = "Tampered"

    response = await async_client.post("/api/v1/auth/telegram", json=payload)

    assert response.status_code == 400
    assert "signature" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_telegram_auth_rejects_replay(async_client: AsyncClient) -> None:
    stale_payload = build_payload(auth_date=datetime.now(UTC) - timedelta(days=2))

    response = await async_client.post("/api/v1/auth/telegram", json=stale_payload)

    assert response.status_code == 401
    assert "old" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_telegram_auth_inactive_user_forbidden(async_client: AsyncClient) -> None:
    payload = build_payload()

    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await services.register_user(
            session,
            UserCreate(
                email="existing-user.777000@example.com",
                hashed_password=hashlib.sha256(b"password").hexdigest(),
                is_active=False,
            ),
            UserProfileCreate(
                user_id=0,
                first_name="Existing",
                last_name="User",
                telegram_id=payload["id"],
            ),
        )
        await session.commit()
        await session.refresh(user)

    response = await async_client.post("/api/v1/auth/telegram", json=payload)

    assert response.status_code == 403
    assert "disabled" in response.json()["detail"].lower()


def build_payload(
    auth_date: datetime | None = None, **overrides: Any
) -> dict[str, Any]:
    moment = auth_date or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    else:
        moment = moment.astimezone(UTC)

    auth_timestamp = int(moment.timestamp())
    payload = BASE_PAYLOAD | {"auth_date": auth_timestamp}
    payload.update(overrides)
    payload["hash"] = compute_hash(payload)
    return payload


def compute_hash(payload: dict[str, Any]) -> str:
    data_check_string = "\n".join(
        f"{key}={_stringify(value)}"
        for key, value in sorted(payload.items())
        if key != "hash"
    )
    secret_key = hashlib.sha256(TEST_BOT_TOKEN.encode("utf-8")).digest()
    return hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


async def _fetch_user_by_telegram_id(
    session: AsyncSession, telegram_id: int
) -> User | None:
    stmt = (
        select(User)
        .options(joinedload(User.profile))
        .join(UserProfile, UserProfile.user_id == User.id)
        .where(UserProfile.telegram_id == telegram_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _fetch_sessions_for_user(
    session: AsyncSession, identifier: int, *, by_telegram: bool = False
) -> list[UserSession]:
    if by_telegram:
        user = await _fetch_user_by_telegram_id(session, identifier)
        if user is None:
            return []
        user_id = user.id
    else:
        user_id = identifier

    stmt = select(UserSession).where(UserSession.user_id == user_id)
    result = await session.execute(stmt)
    return list(result.scalars())
