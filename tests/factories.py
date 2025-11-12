from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import count
from secrets import token_hex
from typing import Any

from user_service.enums import (
    GenerationTaskSource,
    GenerationTaskStatus,
    PaymentStatus,
    PromptCategory,
    PromptSource,
    SubscriptionStatus,
    SubscriptionTier,
    TransactionType,
    UserRole,
)
from user_service.schemas import (
    GenerationTaskCreate,
    GenerationTaskFailureUpdate,
    GenerationTaskResultUpdate,
    PaymentCreate,
    PromptCreate,
    SubscriptionCreate,
    SubscriptionRenew,
    TransactionCreate,
    UserCreate,
    UserProfileCreate,
    UserSessionCreate,
)

_counter = count(1)


def user_create_factory(
    *, email: str | None = None, role: UserRole = UserRole.USER
) -> UserCreate:
    index = next(_counter)
    return UserCreate(
        email=email or f"user{index}@example.com",
        hashed_password="hashed-password-value",
        role=role,
        balance=Decimal("0.00"),
        subscription_id=None,
        is_active=True,
    )


def user_profile_create_factory(
    user_id: int, *, telegram_id: int | None = None
) -> UserProfileCreate:
    index = next(_counter)
    return UserProfileCreate(
        user_id=user_id,
        first_name=f"First{index}",
        last_name=f"Last{index}",
        telegram_id=telegram_id or 1_000_000 + index,
        phone_number="+123456789",
        country="Wonderland",
        city="Hearts",
    )


def user_session_create_factory(
    user_id: int, *, expires_in: int = 3600
) -> UserSessionCreate:
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
    return UserSessionCreate(
        user_id=user_id,
        session_token=token_hex(16),
        user_agent="pytest",
        ip_address="127.0.0.1",
        expires_at=expires_at,
    )


def subscription_create_factory(
    user_id: int,
    *,
    tier: SubscriptionTier = SubscriptionTier.STANDARD,
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
    auto_renew: bool = True,
    quota_limit: int = 1_000,
    quota_used: int = 0,
    period_days: int = 30,
    provider_metadata: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> SubscriptionCreate:
    index = next(_counter)
    start = datetime.now(UTC)
    end = start + timedelta(days=period_days)
    return SubscriptionCreate(
        user_id=user_id,
        tier=tier,
        status=status,
        auto_renew=auto_renew,
        quota_limit=quota_limit,
        quota_used=quota_used,
        provider_subscription_id=f"sub_{index}",
        provider_data=(
            dict(provider_metadata)
            if provider_metadata is not None
            else {"cycle": index}
        ),
        metadata=(dict(metadata) if metadata is not None else {"source": "tests"}),
        current_period_start=start,
        current_period_end=end,
    )


def subscription_renew_factory(
    *,
    days: int = 30,
    quota_limit: int | None = None,
    provider_data: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    reason: str | None = "renewal",
) -> SubscriptionRenew:
    end = datetime.now(UTC) + timedelta(days=days)
    return SubscriptionRenew(
        new_period_end=end,
        quota_limit=quota_limit,
        provider_data=(
            dict(provider_data) if provider_data is not None else {"cycle": "renewal"}
        ),
        metadata=(dict(metadata) if metadata is not None else {"note": "renewal"}),
        reason=reason,
    )


def payment_create_factory(
    user_id: int,
    subscription_id: int | None,
    *,
    amount: Decimal = Decimal("19.99"),
    currency: str = "usd",
    status: PaymentStatus = PaymentStatus.COMPLETED,
    provider_payment_id: str | None = None,
    provider_data: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> PaymentCreate:
    index = next(_counter)
    return PaymentCreate(
        user_id=user_id,
        subscription_id=subscription_id,
        amount=amount,
        currency=currency,
        status=status,
        provider_payment_id=provider_payment_id or f"pm_{index}",
        provider_data=(
            dict(provider_data)
            if provider_data is not None
            else {"processor": "stripe"}
        ),
        metadata=(dict(metadata) if metadata is not None else {"note": "test"}),
        paid_at=datetime.now(UTC),
    )


def transaction_create_factory(
    user_id: int,
    subscription_id: int | None,
    *,
    amount: Decimal = Decimal("19.99"),
    currency: str = "usd",
    txn_type: TransactionType = TransactionType.CHARGE,
    description: str | None = None,
    provider_reference: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> TransactionCreate:
    index = next(_counter)
    return TransactionCreate(
        subscription_id=subscription_id,
        user_id=user_id,
        amount=amount,
        currency=currency,
        type=txn_type,
        description=description or "Test transaction",
        provider_reference=provider_reference or f"txn_{index}",
        metadata=(
            dict(metadata) if metadata is not None else {"note": "test-transaction"}
        ),
    )


def prompt_create_factory(
    *,
    slug: str | None = None,
    source: PromptSource = PromptSource.SYSTEM,
    category: PromptCategory = PromptCategory.GENERIC,
    parameters: Mapping[str, Any] | None = None,
    parameters_schema: Mapping[str, Any] | None = None,
    is_active: bool = True,
) -> PromptCreate:
    index = next(_counter)
    schema_payload = (
        dict(parameters_schema)
        if parameters_schema is not None
        else {
            "type": "object",
            "properties": {
                "temperature": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "style": {"type": "string"},
            },
            "required": ["temperature"],
            "additionalProperties": False,
        }
    )
    parameters_payload = (
        dict(parameters)
        if parameters is not None
        else {"temperature": 0.5, "style": "natural"}
    )
    return PromptCreate(
        slug=slug or f"prompt-{index}",
        name=f"Prompt {index}",
        description="Default prompt used for tests",
        category=category,
        source=source,
        parameters_schema=schema_payload,
        parameters=parameters_payload,
        is_active=is_active,
        preview_asset_url=f"s3://prompts/{index}/preview.png",
    )


def generation_task_create_factory(
    user_id: int,
    prompt_id: int,
    *,
    status: GenerationTaskStatus = GenerationTaskStatus.PENDING,
    source: GenerationTaskSource = GenerationTaskSource.API,
    parameters: Mapping[str, Any] | None = None,
) -> GenerationTaskCreate:
    index = next(_counter)
    return GenerationTaskCreate(
        user_id=user_id,
        prompt_id=prompt_id,
        status=status,
        source=source,
        parameters=(
            dict(parameters) if parameters is not None else {"size": "1024x1024"}
        ),
        result_parameters={},
        input_asset_url=f"s3://tasks/{index}/input.json",
        result_asset_url=None,
    )


def generation_task_result_update_factory(
    *,
    result_asset_url: str | None = None,
    result_parameters: Mapping[str, Any] | None = None,
) -> GenerationTaskResultUpdate:
    return GenerationTaskResultUpdate(
        result_asset_url=result_asset_url or "s3://tasks/results/output.png",
        result_parameters=(
            dict(result_parameters)
            if result_parameters is not None
            else {"duration": 1.23}
        ),
    )


def generation_task_failure_update_factory(
    *,
    error: str = "task failed",
    result_asset_url: str | None = None,
    result_parameters: Mapping[str, Any] | None = None,
) -> GenerationTaskFailureUpdate:
    return GenerationTaskFailureUpdate(
        error=error,
        result_asset_url=result_asset_url or "s3://tasks/results/error.log",
        result_parameters=(
            dict(result_parameters) if result_parameters is not None else {"retries": 3}
        ),
    )
