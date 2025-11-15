from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.factories import (
    payment_create_factory,
    subscription_create_factory,
    subscription_renew_factory,
    transaction_create_factory,
    user_create_factory,
)
from user_service import repository, services
from user_service.enums import SubscriptionStatus, TransactionType
from user_service.models import Subscription


@pytest.mark.asyncio
async def test_activate_subscription_creates_history_and_uniqueness(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await repository.create_user(session, user_create_factory())

        subscription = await services.activate_subscription(
            session, subscription_create_factory(user.id)
        )
        await session.refresh(subscription, attribute_names=["history"])
        assert len(subscription.history) == 1
        assert subscription.history[0].reason == "activated"

        with pytest.raises(IntegrityError):
            await services.activate_subscription(
                session, subscription_create_factory(user.id)
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_renew_subscription_resets_quota_and_logs_history(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await repository.create_user(session, user_create_factory())
        subscription = await services.activate_subscription(
            session,
            subscription_create_factory(user.id, quota_limit=100, quota_used=0),
        )

        await services.increment_subscription_usage_by(session, subscription, 40)
        renew_payload = subscription_renew_factory(
            days=60,
            quota_limit=250,
            metadata={"cycle": "renewal"},
        )
        renewed = await services.renew_subscription(
            session, subscription, renew_payload
        )

        assert renewed.quota_used == 0
        assert renewed.quota_limit == 250
        assert renewed.status == SubscriptionStatus.ACTIVE

        await session.refresh(renewed, attribute_names=["history"])
        assert len(renewed.history) == 2
        assert renewed.history[-1].reason == "renewal"
        assert renewed.history[-1].quota_limit == 250


@pytest.mark.asyncio
async def test_cancel_subscription_sets_flags_and_history(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await repository.create_user(session, user_create_factory())
        subscription = await services.activate_subscription(
            session, subscription_create_factory(user.id)
        )

        canceled = await services.cancel_subscription(
            session, subscription, reason="user"
        )
        assert canceled.status == SubscriptionStatus.CANCELED
        assert canceled.auto_renew is False
        assert canceled.canceled_at is not None

        await session.refresh(canceled, attribute_names=["history"])
        assert len(canceled.history) == 2
        assert canceled.history[-1].reason == "user"

        # Calling cancellation twice should be idempotent.
        second = await services.cancel_subscription(session, subscription)
        await session.refresh(second, attribute_names=["history"])
        assert len(second.history) == 2


@pytest.mark.asyncio
async def test_record_transaction_creates_payment_and_history(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await repository.create_user(session, user_create_factory())
        subscription = await services.activate_subscription(
            session, subscription_create_factory(user.id)
        )

        payment_data = payment_create_factory(
            user.id, subscription.id, amount=Decimal("24.99")
        )
        transaction_data = transaction_create_factory(
            user.id,
            subscription.id,
            amount=Decimal("24.99"),
            txn_type=TransactionType.CHARGE,
        )

        transaction = await services.record_subscription_transaction(
            session,
            subscription,
            payment_data,
            transaction_data,
        )

        assert transaction.payment_id is not None
        assert transaction.amount == Decimal("24.99")

        await session.refresh(
            subscription,
            attribute_names=["payments", "transactions", "history"],
        )
        assert len(subscription.payments) == 1
        assert len(subscription.transactions) == 1
        assert subscription.history[-1].reason == "transaction-recorded"


@pytest.mark.asyncio
async def test_usage_increment_and_constraint(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await repository.create_user(session, user_create_factory())
        subscription = await services.activate_subscription(
            session, subscription_create_factory(user.id, quota_limit=10)
        )

        updated = await services.increment_subscription_usage_by(
            session, subscription, 10
        )
        assert updated.quota_used == 10

        with pytest.raises(ValueError):
            await services.increment_subscription_usage_by(session, subscription, 1)

        subscription_id = subscription.id
        await session.commit()

        # Manipulate directly to assert database constraint enforcement.
        subscription.quota_used = subscription.quota_limit + 1
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

        # Ensure record remains valid after rollback.
        refreshed = await repository.get_subscription_by_id(session, subscription_id)
        assert isinstance(refreshed, Subscription)
        assert refreshed.quota_used == 10
