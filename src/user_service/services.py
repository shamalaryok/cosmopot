from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from . import repository
from .enums import SubscriptionStatus
from .models import Subscription, Transaction, User, UserSession
from .schemas import (
    PaymentCreate,
    SubscriptionCreate,
    SubscriptionRenew,
    TransactionCreate,
    UserCreate,
    UserProfileCreate,
    UserSessionCreate,
    UserUpdate,
)


def _ensure_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


async def register_user(
    session: AsyncSession,
    user_data: UserCreate,
    profile_data: UserProfileCreate | None = None,
) -> User:
    """Create a user and optional profile within a single transaction."""

    user = await repository.create_user(session, user_data)
    if profile_data is not None:
        enriched = profile_data.model_copy(update={"user_id": user.id})
        await repository.create_profile(session, enriched)
        await session.refresh(user, ["profile"])
    return user


async def update_user_details(
    session: AsyncSession, user: User, updates: UserUpdate
) -> User:
    return await repository.update_user(session, user, updates)


async def adjust_balance_by(
    session: AsyncSession, user: User, delta: Decimal
) -> Decimal:
    new_balance = await repository.adjust_user_balance(session, user.id, delta)
    await session.refresh(user)
    return new_balance


async def soft_delete_account(session: AsyncSession, user: User) -> User:
    return await repository.soft_delete_user(session, user)


async def permanently_delete_account(session: AsyncSession, user: User) -> None:
    await repository.hard_delete_user(session, user)


async def open_session(session: AsyncSession, data: UserSessionCreate) -> UserSession:
    return await repository.create_session(session, data)


async def revoke_session_by_token(
    session: AsyncSession, token: str
) -> UserSession | None:
    return await repository.revoke_session(session, token)


async def expire_session_by_token(
    session: AsyncSession, token: str
) -> UserSession | None:
    return await repository.expire_session(session, token)


async def activate_subscription(
    session: AsyncSession,
    data: SubscriptionCreate,
    *,
    reason: str | None = None,
) -> Subscription:
    """Activate a subscription for a user and capture an audit snapshot."""

    subscription = await repository.create_subscription(session, data)
    await repository.create_subscription_history_snapshot(
        session, subscription, reason=reason or "activated"
    )
    await session.refresh(subscription)
    return subscription


async def renew_subscription(
    session: AsyncSession,
    subscription: Subscription,
    data: SubscriptionRenew,
) -> Subscription:
    """Extend a subscription period, resetting quota and recording a snapshot."""

    current_end = _ensure_utc_aware(subscription.current_period_end)
    new_period_end = _ensure_utc_aware(data.new_period_end)
    if new_period_end <= current_end:
        raise ValueError("renewal must extend the current period end")

    subscription.current_period_start = current_end
    subscription.current_period_end = new_period_end
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.canceled_at = None

    if data.quota_limit is not None:
        subscription.quota_limit = data.quota_limit
    subscription.quota_used = 0

    if data.provider_data:
        subscription.provider_data = {
            **(subscription.provider_data or {}),
            **data.provider_data,
        }
    if data.metadata:
        subscription.metadata_dict = {
            **subscription.metadata_dict,
            **data.metadata,
        }

    await session.flush()
    await repository.create_subscription_history_snapshot(
        session, subscription, reason=data.reason or "renewed"
    )
    await session.refresh(subscription)
    return subscription


async def cancel_subscription(
    session: AsyncSession,
    subscription: Subscription,
    *,
    reason: str | None = None,
    effective_at: datetime | None = None,
) -> Subscription:
    """Mark a subscription as canceled while preserving historical context."""

    effective_source = effective_at or datetime.now(UTC)
    effective = _ensure_utc_aware(effective_source)

    if subscription.status == SubscriptionStatus.CANCELED and subscription.canceled_at:
        return subscription

    subscription.status = SubscriptionStatus.CANCELED
    subscription.auto_renew = False
    subscription.canceled_at = effective

    current_end = _ensure_utc_aware(subscription.current_period_end)
    if current_end < effective:
        subscription.current_period_end = effective

    await session.flush()
    await repository.create_subscription_history_snapshot(
        session, subscription, reason=reason or "canceled"
    )
    await session.refresh(subscription)
    return subscription


async def increment_subscription_usage_by(
    session: AsyncSession, subscription: Subscription, amount: int
) -> Subscription:
    """Convenience wrapper to adjust a subscription's usage counters."""

    updated = await repository.increment_subscription_usage(
        session, subscription, amount
    )
    await session.refresh(subscription)
    return updated


async def record_subscription_transaction(
    session: AsyncSession,
    subscription: Subscription,
    payment_data: PaymentCreate,
    transaction_data: TransactionCreate,
    *,
    reason: str | None = None,
) -> Transaction:
    """Create a payment and ledger transaction tied to a subscription."""

    prepared_payment = payment_data.model_copy(
        update={
            "subscription_id": subscription.id,
            "user_id": subscription.user_id,
        }
    )
    payment = await repository.create_payment(session, prepared_payment)

    prepared_transaction = transaction_data.model_copy(
        update={
            "subscription_id": subscription.id,
            "user_id": subscription.user_id,
        }
    )
    transaction = await repository.create_transaction(
        session, payment_id=payment.id, data=prepared_transaction
    )

    await repository.create_subscription_history_snapshot(
        session, subscription, reason=reason or "transaction-recorded"
    )
    await session.refresh(subscription)
    return transaction
