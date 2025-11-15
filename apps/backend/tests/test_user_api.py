from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TypeVar
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from user_service.enums import SubscriptionTier, UserRole
from user_service.models import (
    Subscription,
    SubscriptionPlan,
    User,
    UserProfile,
    UserSession,
)

T = TypeVar("T")


async def _persist(session: AsyncSession, instance: T) -> T:
    session.add(instance)
    await session.commit()
    await session.refresh(instance)
    return instance


async def create_subscription_plan(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    name: str = "Pro",
    level: str = "premium",
    monthly_cost: Decimal = Decimal("19.99"),
) -> SubscriptionPlan:
    async with session_factory() as session:
        plan = SubscriptionPlan(name=name, level=level, monthly_cost=monthly_cost)
        persisted_plan = await _persist(session, plan)
        return persisted_plan


async def create_user(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    role: UserRole = UserRole.USER,
    balance: Decimal = Decimal("0.00"),
    is_active: bool = True,
    subscription_plan: SubscriptionPlan | None = None,
) -> User:
    async with session_factory() as session:
        user = User(
            email=f"user-{uuid4().hex}@example.com",
            hashed_password="hashed-password",
            role=role,
            balance=balance,
            is_active=is_active,
        )
        if subscription_plan is not None:
            user.subscription_id = subscription_plan.id
        persisted = await _persist(session, user)
        return persisted


async def create_active_subscription(
    session_factory: async_sessionmaker[AsyncSession],
    user: User,
    *,
    tier: SubscriptionTier = SubscriptionTier.PRO,
) -> Subscription:
    async with session_factory() as session:
        subscription = Subscription(
            user_id=user.id,
            tier=tier,
            current_period_end=datetime.now(UTC) + timedelta(days=30),
        )
        persisted = await _persist(session, subscription)
        return persisted


async def create_profile(
    session_factory: async_sessionmaker[AsyncSession],
    user: User,
    *,
    first_name: str = "Alice",
    telegram_id: int | None = None,
) -> UserProfile:
    async with session_factory() as session:
        profile = UserProfile(
            user_id=user.id,
            first_name=first_name,
            last_name="Example",
            telegram_id=telegram_id or int(uuid4().int % 9_000_000 + 1_000_000),
            phone_number="+123456789",
            country="Wonderland",
            city="Tea Party",
        )
        persisted = await _persist(session, profile)
        return persisted


async def create_session(
    session_factory: async_sessionmaker[AsyncSession],
    user: User,
    *,
    expires_delta: timedelta = timedelta(hours=1),
    revoked: bool = False,
    ended: bool = False,
) -> UserSession:
    async with session_factory() as session:
        now = datetime.now(UTC)
        user_session = UserSession(
            user_id=user.id,
            session_token=uuid4().hex,
            user_agent="pytest",
            ip_address="127.0.0.1",
            expires_at=now + expires_delta,
            revoked_at=now if revoked else None,
            ended_at=now if ended else None,
        )
        persisted = await _persist(session, user_session)
        return persisted


def auth_headers(user: User) -> dict[str, str]:
    return {"X-User-Id": str(user.id)}


@pytest.mark.asyncio
async def test_get_current_user_profile(
    async_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    subscription_plan = await create_subscription_plan(
        session_factory, name="Enterprise", level="enterprise"
    )
    user = await create_user(
        session_factory, balance=Decimal("42.50"), subscription_plan=subscription_plan
    )
    await create_profile(session_factory, user, first_name="Eve")
    await create_session(session_factory, user)

    response = await async_client.get("/api/v1/users/me", headers=auth_headers(user))
    assert response.status_code == 200

    payload = response.json()
    assert payload["email"] == user.email
    assert payload["profile"]["first_name"] == "Eve"
    assert payload["subscription"]["name"] == subscription_plan.name
    assert payload["quotas"]["plan"].lower().startswith("enterprise")
    assert payload["sessions"][0]["status"] == "active"


@pytest.mark.asyncio
async def test_upsert_profile_create_and_update(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await create_user(session_factory)

    create_payload = {
        "first_name": "Taylor",
        "last_name": "Swift",
        "phone_number": "+111111",
    }
    create_response = await async_client.patch(
        "/api/v1/users/me/profile",
        headers=auth_headers(user),
        json=create_payload,
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["first_name"] == "Taylor"

    update_response = await async_client.patch(
        "/api/v1/users/me/profile",
        headers=auth_headers(user),
        json={"city": "Paris", "telegram_id": 9876543},
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["city"] == "Paris"
    assert updated["telegram_id"] == 9876543


@pytest.mark.asyncio
async def test_upsert_profile_conflict_raises(
    async_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    user_one = await create_user(session_factory)
    user_two = await create_user(session_factory)
    profile = await create_profile(session_factory, user_one, telegram_id=1234567)
    assert profile.telegram_id == 1234567

    response = await async_client.patch(
        "/api/v1/users/me/profile",
        headers=auth_headers(user_two),
        json={"telegram_id": 1234567},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_balance_endpoints(
    async_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    user = await create_user(session_factory, balance=Decimal("5.00"))

    balance_response = await async_client.get(
        "/api/v1/users/me/balance", headers=auth_headers(user)
    )
    assert balance_response.status_code == 200
    balance_payload = balance_response.json()
    assert Decimal(str(balance_payload["balance"])) == Decimal("5.00")

    adjust_response = await async_client.post(
        f"/api/v1/users/{user.id}/balance/adjust",
        headers=auth_headers(user),
        json={"delta": "10.00", "reason": "top up"},
    )
    assert adjust_response.status_code == 200
    payload = adjust_response.json()
    assert Decimal(str(payload["balance"])) == Decimal("15.00")
    assert payload["quotas"]["requires_top_up"] is False


@pytest.mark.asyncio
async def test_balance_adjust_requires_admin(
    async_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    actor = await create_user(session_factory)
    target = await create_user(session_factory, balance=Decimal("20.00"))

    response = await async_client.post(
        f"/api/v1/users/{target.id}/balance/adjust",
        headers=auth_headers(actor),
        json={"delta": "-5.00"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_balance_adjust_missing_user_returns_404(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    admin = await create_user(session_factory, role=UserRole.ADMIN)

    response = await async_client.post(
        "/api/v1/users/99999/balance/adjust",
        headers=auth_headers(admin),
        json={"delta": "1.00"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_balance_adjust_admin(
    async_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    admin = await create_user(session_factory, role=UserRole.ADMIN)
    target = await create_user(session_factory, balance=Decimal("12.00"))

    response = await async_client.post(
        f"/api/v1/users/{target.id}/balance/adjust",
        headers=auth_headers(admin),
        json={"delta": "-5.00", "reason": "usage"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert Decimal(str(payload["balance"])) == Decimal("7.00")

    async with session_factory() as session:
        refreshed = await session.get(User, target.id)
        assert refreshed is not None
        assert refreshed.balance == Decimal("7.00")


@pytest.mark.asyncio
async def test_balance_adjust_prevents_negative(
    async_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    admin = await create_user(session_factory, role=UserRole.ADMIN)
    target = await create_user(session_factory, balance=Decimal("3.00"))

    response = await async_client.post(
        f"/api/v1/users/{target.id}/balance/adjust",
        headers=auth_headers(admin),
        json={"delta": "-5.00"},
    )
    assert response.status_code == 400
    assert "cannot be negative" in response.json()["detail"]


@pytest.mark.asyncio
async def test_balance_adjust_rejects_zero_delta(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await create_user(session_factory)

    response = await async_client.post(
        f"/api/v1/users/{user.id}/balance/adjust",
        headers=auth_headers(user),
        json={"delta": "0"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Delta must be non-zero"


@pytest.mark.asyncio
async def test_role_update(
    async_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    admin = await create_user(session_factory, role=UserRole.ADMIN)
    target = await create_user(session_factory)

    response = await async_client.post(
        f"/api/v1/users/{target.id}/role",
        headers=auth_headers(admin),
        json={"role": UserRole.MODERATOR.value},
    )
    assert response.status_code == 200
    payload = response.json()
    assert UserRole(payload["role"]) is UserRole.MODERATOR

    async with session_factory() as session:
        refreshed = await session.get(User, target.id)
        assert refreshed is not None
        assert refreshed.role is UserRole.MODERATOR


@pytest.mark.asyncio
async def test_role_update_forbidden(
    async_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    actor = await create_user(session_factory)
    target = await create_user(session_factory)

    response = await async_client.post(
        f"/api/v1/users/{target.id}/role",
        headers=auth_headers(actor),
        json={"role": UserRole.ADMIN.value},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_session_listing_and_termination(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await create_user(session_factory)
    active_session = await create_session(session_factory, user)
    await create_session(session_factory, user, expires_delta=timedelta(minutes=-5))

    list_response = await async_client.get(
        "/api/v1/users/me/sessions",
        headers=auth_headers(user),
    )
    assert list_response.status_code == 200
    sessions = list_response.json()
    assert len(sessions) == 2
    assert {item["status"] for item in sessions} == {"active", "expired"}

    delete_response = await async_client.delete(
        f"/api/v1/users/me/sessions/{active_session.id}",
        headers=auth_headers(user),
    )
    assert delete_response.status_code == 200
    terminated = delete_response.json()
    assert terminated["status"] == "revoked"

    async with session_factory() as session:
        refreshed = await session.get(UserSession, active_session.id)
        assert refreshed is not None
        assert refreshed.revoked_at is not None
        assert refreshed.ended_at is not None


@pytest.mark.asyncio
async def test_terminate_nonexistent_session(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await create_user(session_factory)

    response = await async_client.delete(
        "/api/v1/users/me/sessions/99999",
        headers=auth_headers(user),
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_balance_adjust_race_condition(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    admin = await create_user(session_factory, role=UserRole.ADMIN)
    target = await create_user(session_factory, balance=Decimal("10.00"))

    async def adjust(delta: str) -> int:
        response = await async_client.post(
            f"/api/v1/users/{target.id}/balance/adjust",
            headers=auth_headers(admin),
            json={"delta": delta},
        )
        return response.status_code

    results = await asyncio.gather(adjust("10.00"), adjust("-3.00"))
    assert list(results) == [200, 200]

    async with session_factory() as session:
        refreshed = await session.get(User, target.id)
        assert refreshed is not None
        assert refreshed.balance == Decimal("17.00")


@pytest.mark.asyncio
async def test_gdpr_placeholders(
    async_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    user = await create_user(session_factory)

    export_response = await async_client.post(
        "/api/v1/users/me/data-export",
        headers=auth_headers(user),
    )
    assert export_response.status_code == 202
    assert export_response.json()["status"] == "scheduled"

    delete_response = await async_client.post(
        "/api/v1/users/me/data-delete",
        headers=auth_headers(user),
    )
    assert delete_response.status_code == 202
    assert delete_response.json()["status"] == "scheduled"


@pytest.mark.asyncio
async def test_me_requires_valid_active_user(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await create_user(session_factory)

    missing_response = await async_client.get(
        "/api/v1/users/me",
        headers={"X-User-Id": "99999"},
    )
    assert missing_response.status_code == 401

    inactive = await create_user(session_factory, is_active=False)
    inactive_response = await async_client.get(
        "/api/v1/users/me",
        headers=auth_headers(inactive),
    )
    assert inactive_response.status_code == 403


@pytest.mark.asyncio
async def test_get_user_without_subscription_plan(
    async_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    user = await create_user(session_factory, balance=Decimal("10.00"))

    response = await async_client.get("/api/v1/users/me", headers=auth_headers(user))
    assert response.status_code == 200

    payload = response.json()
    assert payload["email"] == user.email
    assert payload["subscription"] is None
    assert payload["quotas"]["plan"] == "Free"
    assert payload["quotas"]["monthly_allocation"] == 500


@pytest.mark.asyncio
async def test_get_balance_with_subscription_plan(
    async_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    subscription_plan = await create_subscription_plan(
        session_factory, name="Basic", level="basic", monthly_cost=Decimal("9.99")
    )
    user = await create_user(
        session_factory, balance=Decimal("5.00"), subscription_plan=subscription_plan
    )

    response = await async_client.get(
        "/api/v1/users/me/balance", headers=auth_headers(user)
    )
    assert response.status_code == 200

    payload = response.json()
    assert Decimal(str(payload["balance"])) == Decimal("5.00")
    assert payload["quotas"]["plan"] == "Basic"
    assert payload["quotas"]["monthly_allocation"] == 2_000


@pytest.mark.asyncio
async def test_get_user_with_active_subscription_fallback(
    async_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    user = await create_user(session_factory, balance=Decimal("20.00"))
    await create_active_subscription(session_factory, user, tier=SubscriptionTier.PRO)

    response = await async_client.get("/api/v1/users/me", headers=auth_headers(user))
    assert response.status_code == 200

    payload = response.json()
    assert payload["email"] == user.email
    assert payload["subscription"] is not None
    assert payload["subscription"]["name"] == "Pro"
    assert payload["subscription"]["level"] == "pro"
    assert payload["quotas"]["plan"] == "Pro"
