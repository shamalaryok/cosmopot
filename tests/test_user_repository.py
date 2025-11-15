from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from user_service import services
from user_service.models import UserProfile
from user_service.repository import (
    TelegramIdConflictError,
    create_profile,
    create_session,
    create_subscription_plan,
    create_user,
    get_profile_by_user_id,
    get_user_by_email,
    get_user_with_related,
    hard_delete_user,
    update_profile,
)
from user_service.schemas import UserProfileUpdate, UserUpdate

from .factories import (
    user_create_factory,
    user_profile_create_factory,
    user_session_create_factory,
)


@pytest.mark.asyncio
async def test_create_user_and_profile(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user_data = user_create_factory()
        user = await create_user(session, user_data)
        profile_data = user_profile_create_factory(user.id)
        profile = await create_profile(session, profile_data)
        await session.refresh(user, ["profile"])

        assert user.id is not None
        assert profile.user_id == user.id
        assert user.profile is not None
        assert user.profile.telegram_id == profile_data.telegram_id


@pytest.mark.asyncio
async def test_unique_email_constraint(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user_data = user_create_factory(email="unique@example.com")
        await create_user(session, user_data)

        with pytest.raises(IntegrityError):
            await create_user(session, user_data)


@pytest.mark.asyncio
async def test_unique_telegram_constraint(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        first_user = await create_user(session, user_create_factory())
        second_user = await create_user(session, user_create_factory())

        profile_one = user_profile_create_factory(first_user.id, telegram_id=9_999_999)
        await create_profile(session, profile_one)

        profile_two = user_profile_create_factory(second_user.id, telegram_id=9_999_999)
        with pytest.raises(TelegramIdConflictError):
            await create_profile(session, profile_two)


@pytest.mark.asyncio
async def test_adjust_balance_via_service(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await create_user(session, user_create_factory())

        increased = await services.adjust_balance_by(session, user, Decimal("10.25"))
        assert increased == Decimal("10.25")

        decreased = await services.adjust_balance_by(session, user, Decimal("-3.257"))
        assert decreased == Decimal("6.99")


@pytest.mark.asyncio
async def test_session_service_lifecycle(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await create_user(session, user_create_factory())
        session_data = user_session_create_factory(user.id)
        user_session = await services.open_session(session, session_data)

        assert user_session.revoked_at is None

        revoked = await services.revoke_session_by_token(
            session, user_session.session_token
        )
        assert revoked is not None
        assert revoked.revoked_at is not None

        expired = await services.expire_session_by_token(
            session, user_session.session_token
        )
        assert expired is not None
        assert expired.ended_at is not None


@pytest.mark.asyncio
async def test_cascade_delete_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        subscription = await create_subscription_plan(
            session, "Pro", "gold", Decimal("19.99")
        )
        user = await create_user(
            session,
            user_create_factory(email="cascade@example.com"),
        )
        user.subscription_id = subscription.id
        await session.flush()

        await create_profile(session, user_profile_create_factory(user.id))
        created_session = await create_session(
            session, user_session_create_factory(user.id)
        )
        assert created_session is not None

        await hard_delete_user(session, user)

        profile = await get_profile_by_user_id(session, user.id)
        assert profile is None

        related = await get_user_with_related(session, user.id)
        assert related is None


@pytest.mark.asyncio
async def test_soft_delete_sets_timestamp(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await create_user(session, user_create_factory())
        assert user.deleted_at is None

        updated = await services.soft_delete_account(session, user)
        assert updated.deleted_at is not None


@pytest.mark.asyncio
async def test_service_register_user_with_profile(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user_data = user_create_factory(email="register@example.com")
        profile_template = user_profile_create_factory(user_id=0)

        user = await services.register_user(session, user_data, profile_template)

        fetched = await get_user_with_related(session, user.id)
        assert fetched is not None
        assert fetched.profile is not None
        assert fetched.profile.telegram_id == profile_template.telegram_id


@pytest.mark.asyncio
async def test_service_update_and_balance_workflow(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await services.register_user(session, user_create_factory())
        await services.update_user_details(
            session, user, UserUpdate(is_active=False, role=user.role)
        )
        await services.adjust_balance_by(session, user, Decimal("5.00"))

        refreshed = await get_user_by_email(session, user.email)
        assert refreshed is not None
        assert refreshed.is_active is False
        assert refreshed.balance == Decimal("5.00")


@pytest.mark.asyncio
async def test_profile_update_and_uniqueness(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await create_user(session, user_create_factory())
        profile = await create_profile(session, user_profile_create_factory(user.id))

        updated_profile = await update_profile(
            session,
            profile,
            UserProfileUpdate(city="Paris", phone_number="+987654321"),
        )
        assert isinstance(updated_profile, UserProfile)
        assert updated_profile.city == "Paris"

        duplicate_profile = user_profile_create_factory(user.id, telegram_id=7_000_000)
        with pytest.raises(IntegrityError):
            await create_profile(session, duplicate_profile)
