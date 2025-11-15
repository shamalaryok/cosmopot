from __future__ import annotations

import asyncio
import sqlite3
from collections import defaultdict
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, TypeVar

from jsonschema import Draft202012Validator
from sqlalchemy import bindparam, func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import Select

from .enums import (
    GenerationTaskSource,
    GenerationTaskStatus,
    PaymentStatus,
    PromptCategory,
    PromptSource,
    SubscriptionStatus,
    SubscriptionTier,
    TransactionType,
)
from .models import (
    GenerationTask,
    Payment,
    Prompt,
    Subscription,
    SubscriptionHistory,
    SubscriptionPlan,
    Transaction,
    User,
    UserProfile,
    UserSession,
)
from .schemas import (
    GenerationTaskCreate,
    GenerationTaskFailureUpdate,
    GenerationTaskResultUpdate,
    PaymentCreate,
    PromptCreate,
    PromptUpdate,
    SubscriptionCreate,
    TransactionCreate,
    UserCreate,
    UserProfileCreate,
    UserProfileUpdate,
    UserSessionCreate,
    UserUpdate,
)

_PROMPT_VERSION_MAX_RETRIES = 10
_SQLITE_LOCK_ERROR_SUBSTRING = "locked"
_SQLITE_LOCK_RETRY_DELAYS = (0.02, 0.05, 0.1, 0.2, 0.4)

# Per-slug async locks to serialize prompt creation on the same slug.
# This prevents SQLite "database is locked" errors during concurrent writes
# by ensuring only one coroutine per slug enters the critical section at a time.
# Postgres handles concurrency naturally, so this lock is benign there.
_PROMPT_SLUG_LOCKS: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

T = TypeVar("T")


class TelegramIdConflictError(Exception):
    """Raised when setting a telegram_id already used by another user."""

    pass


async def create_user(session: AsyncSession, data: UserCreate) -> User:
    """Persist a new :class:`User` instance."""

    user = User(**data.model_dump())
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def update_user(session: AsyncSession, user: User, data: UserUpdate) -> User:
    """Update mutable fields for a user instance."""

    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(user, key, value)
    await session.flush()
    await session.refresh(user)
    return user


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_with_related(session: AsyncSession, user_id: int) -> User | None:
    stmt = (
        select(User)
        .options(
            joinedload(User.profile),
            joinedload(User.sessions),
            joinedload(User.subscription_plan),
            joinedload(User.subscriptions),
        )
        .where(User.id == user_id)
    )
    result = await session.execute(stmt)
    return result.unique().scalar_one_or_none()


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(User.email == email)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def adjust_user_balance(
    session: AsyncSession, user_id: int, delta: Decimal
) -> Decimal:
    """Atomically adjust a user's balance by a delta amount."""

    quantized_delta = Decimal(delta).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    zero = Decimal("0")
    delta_param = bindparam("delta", type_=User.balance.type)

    stmt = (
        update(User)
        .where(User.id == user_id)
        .where((User.balance + delta_param) >= zero)
        .values(balance=User.balance + delta_param)
        .returning(User.balance)
    )

    result = await session.execute(stmt, {"delta": quantized_delta})
    new_balance = result.scalar_one_or_none()

    if new_balance is None:
        # Check if user exists to determine the error
        exists_stmt = select(User.id).where(User.id == user_id)
        exists_result = await session.execute(exists_stmt)
        if exists_result.scalar_one_or_none() is None:
            raise ValueError("user not found")
        raise ValueError("balance cannot be negative")

    return new_balance


async def soft_delete_user(session: AsyncSession, user: User) -> User:
    user.deleted_at = datetime.now(UTC)
    await session.flush()
    return user


async def hard_delete_user(session: AsyncSession, user: User) -> None:
    await session.delete(user)
    await session.flush()


async def create_subscription_plan(
    session: AsyncSession, name: str, level: str, monthly_cost: Decimal
) -> SubscriptionPlan:
    plan = SubscriptionPlan(
        name=name,
        level=level,
        monthly_cost=Decimal(monthly_cost).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        ),
    )
    session.add(plan)
    await session.flush()
    await session.refresh(plan)
    return plan


async def create_profile(session: AsyncSession, data: UserProfileCreate) -> UserProfile:
    # Check telegram_id uniqueness if provided
    if data.telegram_id is not None:
        is_unique = await check_telegram_id_uniqueness(session, data.telegram_id)
        if not is_unique:
            raise TelegramIdConflictError(
                f"telegram_id {data.telegram_id} is already in use"
            )

    profile = UserProfile(**data.model_dump())
    session.add(profile)
    await session.flush()
    await session.refresh(profile)
    return profile


async def update_profile(
    session: AsyncSession, profile: UserProfile, data: UserProfileUpdate
) -> UserProfile:
    updates = data.model_dump(exclude_unset=True)

    # Check telegram_id uniqueness if being updated
    if "telegram_id" in updates and updates["telegram_id"] is not None:
        is_unique = await check_telegram_id_uniqueness(
            session, updates["telegram_id"], exclude_user_id=profile.user_id
        )
        if not is_unique:
            raise TelegramIdConflictError(
                f"telegram_id {updates['telegram_id']} is already in use"
            )

    for key, value in updates.items():
        setattr(profile, key, value)
    await session.flush()
    await session.refresh(profile)
    return profile


async def get_profile_by_user_id(
    session: AsyncSession, user_id: int
) -> UserProfile | None:
    stmt = select(UserProfile).where(UserProfile.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def check_telegram_id_uniqueness(
    session: AsyncSession, telegram_id: int, exclude_user_id: int | None = None
) -> bool:
    """Check if a telegram_id is unique across all user profiles.

    Args:
        session: Database session
        telegram_id: The telegram_id to check
        exclude_user_id: Optional user ID to exclude from the check (for updates)

    Returns:
        True if the telegram_id is unique, False if it's already taken
    """
    stmt = select(UserProfile).where(UserProfile.telegram_id == telegram_id)
    if exclude_user_id is not None:
        stmt = stmt.where(UserProfile.user_id != exclude_user_id)

    result = await session.execute(stmt)
    existing_profile = result.scalar_one_or_none()
    return existing_profile is None


async def create_session(session: AsyncSession, data: UserSessionCreate) -> UserSession:
    session_model = UserSession(**data.model_dump())
    session.add(session_model)
    await session.flush()
    await session.refresh(session_model)
    return session_model


async def get_session_by_token(session: AsyncSession, token: str) -> UserSession | None:
    stmt = select(UserSession).where(UserSession.session_token == token)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_active_session_by_token(
    session: AsyncSession, token: str
) -> UserSession | None:
    stmt = select(UserSession).where(
        UserSession.session_token == token, UserSession.revoked_at.is_(None)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def revoke_session(
    session: AsyncSession, session_token: str
) -> UserSession | None:
    user_session = await get_active_session_by_token(session, session_token)
    if user_session is None:
        return None
    user_session.revoked_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(user_session)
    return user_session


async def expire_session(
    session: AsyncSession, session_token: str
) -> UserSession | None:
    stmt = select(UserSession).where(UserSession.session_token == session_token)
    result = await session.execute(stmt)
    user_session = result.scalar_one_or_none()
    if user_session is None:
        return None
    user_session.ended_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(user_session)
    return user_session


async def create_subscription(
    session: AsyncSession, data: SubscriptionCreate
) -> Subscription:
    """Persist a new subscription record for a user."""

    payload = data.model_dump()
    payload["tier"] = SubscriptionTier(payload["tier"])
    payload["status"] = SubscriptionStatus(payload["status"])
    payload["provider_data"] = dict(payload.get("provider_data") or {})
    payload["metadata"] = dict(payload.get("metadata") or {})

    subscription = Subscription(**payload)
    session.add(subscription)
    await session.flush()
    await session.refresh(subscription)
    return subscription


async def get_subscription_by_id(
    session: AsyncSession, subscription_id: int
) -> Subscription | None:
    stmt = select(Subscription).where(Subscription.id == subscription_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_subscription_history_snapshot(
    session: AsyncSession,
    subscription: Subscription,
    *,
    reason: str | None = None,
) -> SubscriptionHistory:
    """Capture the current state of a subscription in the history table."""

    snapshot = SubscriptionHistory(
        subscription_id=subscription.id,
        tier=subscription.tier,
        status=subscription.status,
        auto_renew=subscription.auto_renew,
        quota_limit=subscription.quota_limit,
        quota_used=subscription.quota_used,
        provider_subscription_id=subscription.provider_subscription_id,
        provider_data=dict(subscription.provider_data or {}),
        metadata=dict(subscription.metadata_dict),
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        reason=reason,
    )
    session.add(snapshot)
    await session.flush()
    await session.refresh(snapshot)
    return snapshot


async def increment_subscription_usage(
    session: AsyncSession, subscription: Subscription, amount: int
) -> Subscription:
    """Accumulate usage against the subscription's quota within a transaction."""

    if amount < 0:
        raise ValueError("amount must be non-negative")
    updated = subscription.quota_used + amount
    if updated > subscription.quota_limit:
        raise ValueError("quota usage exceeds configured limit")
    subscription.quota_used = updated
    await session.flush()
    await session.refresh(subscription)
    return subscription


async def decrement_subscription_usage(
    session: AsyncSession, subscription: Subscription, amount: int
) -> Subscription:
    """Reduce quota usage, clamping to zero to avoid negative values."""

    if amount < 0:
        raise ValueError("amount must be non-negative")
    updated = subscription.quota_used - amount
    if updated < 0:
        updated = 0
    subscription.quota_used = updated
    await session.flush()
    await session.refresh(subscription)
    return subscription


async def get_active_subscription_for_user(
    session: AsyncSession, user_id: int
) -> Subscription | None:
    stmt = (
        select(Subscription)
        .where(
            Subscription.user_id == user_id,
            Subscription.status.in_(
                [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]
            ),
        )
        .order_by(Subscription.current_period_end.desc())
    )
    result = await session.execute(stmt)
    return result.scalars().first()


async def create_payment(session: AsyncSession, data: PaymentCreate) -> Payment:
    payload = data.model_dump()
    payload["status"] = PaymentStatus(payload["status"])
    payload["provider_data"] = dict(payload.get("provider_data") or {})
    payload["metadata"] = dict(payload.get("metadata") or {})
    payment = Payment(**payload)
    session.add(payment)
    await session.flush()
    await session.refresh(payment)
    return payment


async def create_transaction(
    session: AsyncSession, *, payment_id: int, data: TransactionCreate
) -> Transaction:
    payload = data.model_dump()
    payload["payment_id"] = payment_id
    payload["type"] = TransactionType(payload["type"])
    payload["metadata"] = dict(payload.get("metadata") or {})
    transaction = Transaction(**payload)
    session.add(transaction)
    await session.flush()
    await session.refresh(transaction)
    return transaction


def _coerce_category(value: PromptCategory | str | None) -> PromptCategory | None:
    if value is None:
        return None
    if isinstance(value, PromptCategory):
        return value
    return PromptCategory(str(value))


def _prompt_dict(value: Any | None) -> dict[str, Any]:
    if value is None:
        return {}
    return dict(value)


def _validate_prompt_parameters(
    parameters: dict[str, Any], schema: dict[str, Any]
) -> None:
    validator = Draft202012Validator(schema)
    error = next(validator.iter_errors(parameters), None)
    if error is not None:
        raise ValueError(f"parameters do not conform to schema: {error.message}")


def _supports_select_for_update(session: AsyncSession) -> bool:
    bind = session.bind
    if bind is None:
        return False
    return bind.dialect.name not in {"sqlite"}


def _is_sqlite_session(session: AsyncSession) -> bool:
    bind = session.bind
    if bind is None:
        return False
    return bind.dialect.name == "sqlite"


def _is_sqlite_database_locked_error(error: OperationalError) -> bool:
    orig = getattr(error, "orig", None)
    if not isinstance(orig, sqlite3.OperationalError):
        return False
    message = str(error).lower()
    if _SQLITE_LOCK_ERROR_SUBSTRING in message:
        return True
    if orig is not None and _SQLITE_LOCK_ERROR_SUBSTRING in str(orig).lower():
        return True
    return False


async def _run_with_sqlite_retry(
    session: AsyncSession,
    operation: Callable[[], Awaitable[T]],
) -> T:
    if not _is_sqlite_session(session):
        return await operation()

    delays = _SQLITE_LOCK_RETRY_DELAYS
    for attempt, delay in enumerate(delays):
        try:
            return await operation()
        except OperationalError as exc:
            if not _is_sqlite_database_locked_error(exc):
                raise
            if attempt == len(delays) - 1:
                raise
            await asyncio.sleep(delay)

    raise RuntimeError("sqlite retry loop exhausted without result")


def _latest_prompt_select(
    slug: str, *, active_only: bool = True
) -> Select[tuple[Prompt]]:
    stmt = select(Prompt).where(Prompt.slug == slug)
    if active_only:
        stmt = stmt.where(Prompt.is_active.is_(True))
    return stmt.order_by(Prompt.version.desc()).limit(1)


async def _next_prompt_version(
    session: AsyncSession,
    slug: str,
    *,
    lock: bool,
) -> int:
    stmt = (
        select(Prompt.version)
        .where(Prompt.slug == slug)
        .order_by(Prompt.version.desc())
        .limit(1)
    )
    if lock:
        stmt = stmt.with_for_update()
    result = await session.execute(stmt)
    current = result.scalar_one_or_none()
    return int((current or 0) + 1)


def _is_prompt_version_conflict(error: IntegrityError) -> bool:
    message = str(getattr(error, "orig", error)).lower()
    return (
        "uq_prompts_slug_version" in message
        or "prompts.slug, prompts.version" in message
        or (
            "prompts" in message
            and "slug" in message
            and "version" in message
            and "unique" in message
        )
    )


async def _deactivate_existing_active_versions(
    session: AsyncSession, slug: str, *, exclude_id: int | None = None
) -> None:
    prompts_table = Prompt.__table__
    stmt = (
        update(prompts_table)  # type: ignore[arg-type]
        .where(prompts_table.c.slug == bindparam("b_slug"))
        .where(prompts_table.c.is_active.is_(True))
        .values(is_active=False, updated_at=func.current_timestamp())
    )
    params: dict[str, Any] = {"b_slug": slug}
    if exclude_id is not None:
        stmt = stmt.where(prompts_table.c.id != bindparam("b_exclude_id"))
        params["b_exclude_id"] = exclude_id
    await session.execute(stmt, params)


def _get_slug_lock(slug: str) -> asyncio.Lock:
    """Return the async lock for the given prompt slug.

    Lazily creates a lock per slug to serialize concurrent writes on the same slug.
    This prevents SQLite "database is locked" errors during concurrent prompt creation.
    For Postgres, this lock is benign as the database handles concurrency naturally.
    """
    return _PROMPT_SLUG_LOCKS[slug]


async def create_prompt(session: AsyncSession, data: PromptCreate) -> Prompt:
    """Persist a prompt template definition."""

    payload = data.model_dump()
    slug = payload["slug"]
    category = _coerce_category(payload.get("category")) or PromptCategory.GENERIC
    schema = _prompt_dict(payload.get("parameters_schema"))
    parameters = _prompt_dict(payload.get("parameters"))
    is_active = bool(payload.get("is_active", True))

    _validate_prompt_parameters(parameters, schema)

    payload["category"] = category
    payload["source"] = PromptSource(payload["source"])
    payload["parameters_schema"] = schema
    payload["parameters"] = parameters
    payload["is_active"] = is_active
    payload.pop("version", None)

    lock_for_update = _supports_select_for_update(session)

    # Acquire per-slug lock to serialize concurrent writes on the same slug.
    # This prevents SQLite "database is locked" errors during concurrent prompt creation
    # by ensuring only one coroutine per slug enters the critical section at a time.
    # The lock is benign for Postgres, which handles concurrency naturally.
    async with _get_slug_lock(slug):
        prompt: Prompt | None = None
        last_error: IntegrityError | None = None

        for _ in range(_PROMPT_VERSION_MAX_RETRIES):

            async def _persist_candidate() -> Prompt:
                async with session.begin_nested():
                    version = await _next_prompt_version(
                        session,
                        slug,
                        lock=lock_for_update,
                    )
                    if is_active:
                        await _deactivate_existing_active_versions(session, slug)
                    candidate = Prompt(**payload, version=version)
                    session.add(candidate)
                    try:
                        await session.flush()
                    except Exception:
                        with suppress(Exception):
                            session.expunge(candidate)
                        raise
                return candidate

            try:
                prompt = await _run_with_sqlite_retry(session, _persist_candidate)
                break
            except IntegrityError as exc:
                last_error = exc
                if _is_prompt_version_conflict(exc):
                    continue
                raise
        else:
            raise ValueError("failed to persist prompt version") from last_error

        await session.refresh(prompt)
        return prompt


async def get_latest_prompt_by_slug(
    session: AsyncSession,
    slug: str,
    *,
    active_only: bool = True,
) -> Prompt | None:
    stmt = _latest_prompt_select(slug, active_only=active_only)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_prompt_by_slug(
    session: AsyncSession,
    slug: str,
    *,
    version: int | None = None,
    active_only: bool = True,
) -> Prompt | None:
    if version is not None:
        stmt = select(Prompt).where(
            Prompt.slug == slug,
            Prompt.version == version,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    return await get_latest_prompt_by_slug(
        session,
        slug,
        active_only=active_only,
    )


async def list_prompts(
    session: AsyncSession,
    *,
    category: PromptCategory | str | None = None,
    active_only: bool = True,
) -> list[Prompt]:
    stmt = select(Prompt)
    if active_only:
        stmt = stmt.where(Prompt.is_active.is_(True))
    coerced_category = _coerce_category(category)
    if coerced_category is not None:
        stmt = stmt.where(Prompt.category == coerced_category)
    stmt = stmt.order_by(Prompt.slug.asc(), Prompt.version.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_prompt_by_id(session: AsyncSession, prompt_id: int) -> Prompt | None:
    stmt = select(Prompt).where(Prompt.id == prompt_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_prompt(
    session: AsyncSession, prompt: Prompt, data: PromptUpdate
) -> Prompt:
    updates = data.model_dump(exclude_unset=True)
    if not updates:
        await session.flush()
        await session.refresh(prompt)
        return prompt

    new_schema = (
        _prompt_dict(updates["parameters_schema"])
        if "parameters_schema" in updates
        else None
    )
    new_parameters = (
        _prompt_dict(updates["parameters"]) if "parameters" in updates else None
    )

    schema_after_update = new_schema or dict(prompt.parameters_schema or {})
    parameters_after_update = new_parameters or dict(prompt.parameters or {})
    _validate_prompt_parameters(parameters_after_update, schema_after_update)

    if "name" in updates:
        prompt.name = updates["name"]
    if "description" in updates:
        prompt.description = updates["description"]
    if "category" in updates:
        category = _coerce_category(updates["category"])
        if category is not None:
            prompt.category = category
    if "source" in updates:
        source_value = updates["source"]
        if source_value is not None:
            prompt.source = PromptSource(source_value)
    if new_schema is not None:
        prompt.parameters_schema = new_schema
    if new_parameters is not None:
        prompt.parameters = new_parameters
    if "preview_asset_url" in updates:
        prompt.preview_asset_url = updates["preview_asset_url"]
    if "is_active" in updates:
        active = bool(updates["is_active"])
        prompt.is_active = active
        if active:

            async def _deactivate_active_versions() -> None:
                async with session.begin_nested():
                    await _deactivate_existing_active_versions(
                        session, prompt.slug, exclude_id=prompt.id
                    )

            await _run_with_sqlite_retry(session, _deactivate_active_versions)

    await session.flush()
    await session.refresh(prompt)
    return prompt


async def create_generation_task(
    session: AsyncSession, data: GenerationTaskCreate
) -> GenerationTask:
    """Create a generation task tied to a user and prompt."""

    payload = data.model_dump()
    status_value = payload.get("status")
    if isinstance(status_value, GenerationTaskStatus):
        payload["status"] = status_value
    elif status_value is None:
        payload["status"] = GenerationTaskStatus.PENDING
    else:
        payload["status"] = GenerationTaskStatus.get_by_code(str(status_value))
    payload["source"] = GenerationTaskSource(payload["source"])
    payload["parameters"] = dict(payload.get("parameters") or {})
    payload["result_parameters"] = dict(payload.get("result_parameters") or {})

    task = GenerationTask(**payload)
    session.add(task)
    await session.flush()
    await session.refresh(task)
    return task


async def get_generation_task_by_id(
    session: AsyncSession, task_id: int
) -> GenerationTask | None:
    stmt = select(GenerationTask).where(GenerationTask.id == task_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _ensure_transition_allowed(task: GenerationTask) -> None:
    if task.status in {
        GenerationTaskStatus.SUCCEEDED,
        GenerationTaskStatus.FAILED,
        GenerationTaskStatus.CANCELED,
    }:
        raise ValueError("task is in a terminal state")


async def mark_generation_task_queued(
    session: AsyncSession, task: GenerationTask
) -> GenerationTask:
    """Mark a pending task as queued for processing."""

    _ensure_transition_allowed(task)
    now = datetime.now(UTC)
    if task.status != GenerationTaskStatus.QUEUED:
        task.status = GenerationTaskStatus.QUEUED
    if task.queued_at is None:
        task.queued_at = now
    await session.flush()
    await session.refresh(task)
    return task


async def mark_generation_task_started(
    session: AsyncSession, task: GenerationTask
) -> GenerationTask:
    """Mark a queued task as actively running."""

    _ensure_transition_allowed(task)
    now = datetime.now(UTC)
    task.status = GenerationTaskStatus.RUNNING
    if task.queued_at is None:
        task.queued_at = now
    task.started_at = now
    await session.flush()
    await session.refresh(task)
    return task


async def mark_generation_task_succeeded(
    session: AsyncSession,
    task: GenerationTask,
    data: GenerationTaskResultUpdate,
) -> GenerationTask:
    """Mark a running task as succeeded and persist resulting artifacts."""

    _ensure_transition_allowed(task)
    if task.status not in {
        GenerationTaskStatus.RUNNING,
        GenerationTaskStatus.QUEUED,
        GenerationTaskStatus.PENDING,
    }:
        raise ValueError("task must be running or queued to complete")

    now = datetime.now(UTC)
    updates = data.model_dump(exclude_unset=True)

    task.status = GenerationTaskStatus.SUCCEEDED
    task.error = None
    task.completed_at = now
    task.result_asset_url = updates.get("result_asset_url", task.result_asset_url)
    if "result_parameters" in updates:
        task.result_parameters = dict(updates["result_parameters"] or {})

    await session.flush()
    await session.refresh(task)
    return task


async def mark_generation_task_failed(
    session: AsyncSession,
    task: GenerationTask,
    data: GenerationTaskFailureUpdate,
) -> GenerationTask:
    """Mark a task as failed with an error message."""

    _ensure_transition_allowed(task)

    now = datetime.now(UTC)
    updates = data.model_dump(exclude_unset=True)

    task.status = GenerationTaskStatus.FAILED
    task.error = updates["error"]
    task.completed_at = now
    task.result_asset_url = updates.get("result_asset_url", task.result_asset_url)
    if "result_parameters" in updates:
        task.result_parameters = dict(updates["result_parameters"] or {})

    await session.flush()
    await session.refresh(task)
    return task
