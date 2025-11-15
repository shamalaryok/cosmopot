from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, TypeVar, cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.payments.dependencies import (
    get_payment_service,
    reset_payment_dependencies,
)
from backend.payments.enums import PaymentProvider, PaymentStatus
from backend.payments.models import Payment
from backend.payments.service import PaymentService
from backend.payments.types import (
    PaymentProviderResponse,
    ProviderPayload,
    StripePaymentPayload,
)
from user_service.models import SubscriptionPlan, User

T = TypeVar("T", SubscriptionPlan, User)


@dataclass(slots=True)
class StubGateway:
    """Deterministic gateway stub returning queued responses."""

    responses: list[PaymentProviderResponse]
    calls: list[tuple[ProviderPayload, str]] = field(default_factory=list)

    async def create_payment(
        self, payload: ProviderPayload, idempotency_key: str
    ) -> PaymentProviderResponse:
        self.calls.append((payload, idempotency_key))
        response: PaymentProviderResponse
        if self.responses:
            response = self.responses.pop(0)
        else:
            response = {
                "id": f"pi_{uuid4().hex}",
                "status": "requires_payment_method",
                "client_secret": "pi_test#secret",
            }
        return cast(PaymentProviderResponse, json.loads(json.dumps(response)))


class StubNotifier:
    def __init__(self) -> None:
        self.notifications: list[dict[str, Any]] = []

    async def notify(
        self,
        user: User,
        payment: Payment,
        status: PaymentStatus,
        context: dict[str, Any],
    ) -> None:
        self.notifications.append(
            {
                "user_id": user.id,
                "payment_id": str(payment.id),
                "status": status,
                "context": context,
            }
        )


async def _persist(
    session_factory: async_sessionmaker[AsyncSession],
    instance: T,
) -> T:
    async with session_factory() as session:
        session.add(instance)
        await session.commit()
        await session.refresh(instance)
        return instance


async def create_subscription_plan(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    name: str = "Basic",
    level: str = "basic",
    monthly_cost: Decimal = Decimal("9.99"),
) -> SubscriptionPlan:
    plan = SubscriptionPlan(name=name, level=level, monthly_cost=monthly_cost)
    return await _persist(session_factory, plan)


async def create_user(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    balance: Decimal = Decimal("0.00"),
    subscription_plan: SubscriptionPlan | None = None,
) -> User:
    user = User(
        email=f"user-{uuid4().hex}@example.com",
        hashed_password="hashed",
        balance=balance,
    )
    if subscription_plan is not None:
        user.subscription_id = subscription_plan.id
    return await _persist(session_factory, user)


@pytest.fixture()
async def stripe_payment_dependencies(
    app: FastAPI,
) -> AsyncIterator[tuple[StubGateway, StubNotifier, PaymentService]]:
    reset_payment_dependencies()
    gateway = StubGateway(
        responses=[
            {
                "id": "pi_test_stripe_1",
                "status": "requires_payment_method",
                "client_secret": "pi_test_stripe_1#secret",
            }
        ]
    )
    notifier = StubNotifier()
    service = PaymentService(
        settings=app.state.settings, gateway=gateway, notifier=notifier
    )
    app.dependency_overrides[get_payment_service] = lambda: service
    try:
        yield gateway, notifier, service
    finally:
        app.dependency_overrides.pop(get_payment_service, None)
        reset_payment_dependencies()


@pytest.mark.asyncio
async def test_create_stripe_payment_persists_record(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    stripe_payment_dependencies: tuple[StubGateway, StubNotifier, PaymentService],
) -> None:
    gateway, notifier, _service = stripe_payment_dependencies
    subscription_plan = await create_subscription_plan(session_factory)
    user = await create_user(session_factory)

    response = await async_client.post(
        "/api/v1/payments/create",
        headers={"X-User-Id": str(user.id)},
        json={
            "plan_code": "basic",
            "success_url": "https://example.com/success",
            "provider": "stripe",
            "currency": "USD",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["provider"] == "stripe"
    assert payload["provider_payment_id"] == "pi_test_stripe_1"
    assert payload["status"] == PaymentStatus.PENDING.value
    assert payload["currency"] == "USD"

    async with session_factory() as session:
        payment_id = UUID(payload["id"])
        db_payment = await session.get(Payment, payment_id)
        assert db_payment is not None
        assert db_payment.user_id == user.id
        assert db_payment.provider == PaymentProvider.STRIPE
        assert db_payment.subscription_id == subscription_plan.id
        assert db_payment.currency == "USD"

    assert len(gateway.calls) == 1
    request_payload, idempotency_key = gateway.calls[0]
    stripe_payload = cast(StripePaymentPayload, request_payload)
    assert stripe_payload["amount"] == 999  # 9.99 in cents
    assert stripe_payload["currency"] == "usd"
    assert idempotency_key.startswith(str(user.id))


@pytest.mark.asyncio
async def test_create_stripe_payment_with_international_currency(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    stripe_payment_dependencies: tuple[StubGateway, StubNotifier, PaymentService],
) -> None:
    gateway, _notifier, _service = stripe_payment_dependencies
    await create_subscription_plan(session_factory)
    user = await create_user(session_factory)

    response = await async_client.post(
        "/api/v1/payments/create",
        headers={"X-User-Id": str(user.id)},
        json={
            "plan_code": "basic",
            "success_url": "https://example.com/success",
            "provider": "stripe",
            "currency": "EUR",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["currency"] == "EUR"

    request_payload, _ = gateway.calls[0]
    stripe_payload = cast(StripePaymentPayload, request_payload)
    assert stripe_payload["currency"] == "eur"


@pytest.mark.asyncio
async def test_stripe_payment_respects_idempotency_key(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    stripe_payment_dependencies: tuple[StubGateway, StubNotifier, PaymentService],
) -> None:
    gateway, _notifier, _service = stripe_payment_dependencies
    await create_subscription_plan(session_factory)
    user = await create_user(session_factory)

    idempotency_key = "test-stripe-idempotency-12345"
    for _ in range(2):
        response = await async_client.post(
            "/api/v1/payments/create",
            headers={"X-User-Id": str(user.id)},
            json={
                "plan_code": "basic",
                "success_url": "https://example.com/success",
                "provider": "stripe",
                "idempotency_key": idempotency_key,
            },
        )
        assert response.status_code == 201

    assert len(gateway.calls) == 1

    async with session_factory() as session:
        payments = (await session.execute(Payment.__table__.select())).all()
        assert len(payments) == 1


@pytest.mark.asyncio
async def test_stripe_webhook_success_updates_subscription_and_balance(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    stripe_payment_dependencies: tuple[StubGateway, StubNotifier, PaymentService],
) -> None:
    gateway, notifier, service = stripe_payment_dependencies
    subscription_plan = await create_subscription_plan(session_factory)
    user = await create_user(session_factory)

    create_response = await async_client.post(
        "/api/v1/payments/create",
        headers={"X-User-Id": str(user.id)},
        json={
            "plan_code": "basic",
            "success_url": "https://example.com/success",
            "provider": "stripe",
        },
    )
    payment_payload = create_response.json()

    webhook_payload = {
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "pi_test_stripe_1",
                "status": "succeeded",
            }
        },
    }

    raw_body = json.dumps(webhook_payload).encode("utf-8")

    webhook_response = await async_client.post(
        "/api/v1/webhooks/stripe",
        content=raw_body,
        headers={"Stripe-Signature": "test_signature"},
    )
    assert webhook_response.status_code == 200

    async with session_factory() as session:
        payment_id = UUID(payment_payload["id"])
        payment = await session.get(Payment, payment_id)
        assert payment is not None
        assert payment.status is PaymentStatus.SUCCEEDED
        assert payment.captured_at is not None

        refreshed_user = await session.get(User, user.id)
        assert refreshed_user is not None
        assert refreshed_user.subscription_id == subscription_plan.id
        assert refreshed_user.balance == Decimal("9.99")

    assert notifier.notifications
    notification = notifier.notifications[-1]
    assert notification["status"] is PaymentStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_stripe_webhook_payment_failed(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    stripe_payment_dependencies: tuple[StubGateway, StubNotifier, PaymentService],
) -> None:
    gateway, notifier, _service = stripe_payment_dependencies
    await create_subscription_plan(session_factory)
    user = await create_user(session_factory)

    await async_client.post(
        "/api/v1/payments/create",
        headers={"X-User-Id": str(user.id)},
        json={
            "plan_code": "basic",
            "success_url": "https://example.com/success",
            "provider": "stripe",
        },
    )

    webhook_payload = {
        "type": "payment_intent.payment_failed",
        "data": {
            "object": {
                "id": "pi_test_stripe_1",
                "status": "requires_payment_method",
                "last_payment_error": {
                    "message": "Your card was declined",
                },
            }
        },
    }
    raw_body = json.dumps(webhook_payload).encode("utf-8")

    webhook_response = await async_client.post(
        "/api/v1/webhooks/stripe",
        content=raw_body,
        headers={"Stripe-Signature": "test_signature"},
    )
    assert webhook_response.status_code == 200

    async with session_factory() as session:
        result = await session.execute(select(Payment))
        payment = result.scalars().first()
        assert payment is not None
        assert payment.status is PaymentStatus.FAILED

    assert notifier.notifications
    assert notifier.notifications[-1]["status"] is PaymentStatus.FAILED


@pytest.mark.asyncio
async def test_stripe_webhook_payment_canceled(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    stripe_payment_dependencies: tuple[StubGateway, StubNotifier, PaymentService],
) -> None:
    gateway, notifier, _service = stripe_payment_dependencies
    await create_subscription_plan(session_factory)
    user = await create_user(session_factory)

    await async_client.post(
        "/api/v1/payments/create",
        headers={"X-User-Id": str(user.id)},
        json={
            "plan_code": "basic",
            "success_url": "https://example.com/success",
            "provider": "stripe",
        },
    )

    webhook_payload = {
        "type": "payment_intent.canceled",
        "data": {
            "object": {
                "id": "pi_test_stripe_1",
                "status": "canceled",
                "cancellation_reason": "abandoned",
            }
        },
    }
    raw_body = json.dumps(webhook_payload).encode("utf-8")

    webhook_response = await async_client.post(
        "/api/v1/webhooks/stripe",
        content=raw_body,
        headers={"Stripe-Signature": "test_signature"},
    )
    assert webhook_response.status_code == 200

    async with session_factory() as session:
        result = await session.execute(select(Payment))
        payment = result.scalars().first()
        assert payment is not None
        assert payment.status is PaymentStatus.CANCELED

    assert notifier.notifications
    assert notifier.notifications[-1]["status"] is PaymentStatus.CANCELED


@pytest.mark.asyncio
async def test_stripe_webhook_invalid_signature_rejected(
    async_client: AsyncClient,
    stripe_payment_dependencies: tuple[StubGateway, StubNotifier, PaymentService],
) -> None:
    gateway, notifier, _service = stripe_payment_dependencies
    payload = {
        "type": "payment_intent.succeeded",
        "data": {"object": {"id": "unknown"}},
    }
    response = await async_client.post(
        "/api/v1/webhooks/stripe",
        content=json.dumps(payload).encode("utf-8"),
        headers={"Stripe-Signature": "invalid_signature"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_stripe_webhook_missing_payment_returns_404(
    async_client: AsyncClient,
    stripe_payment_dependencies: tuple[StubGateway, StubNotifier, PaymentService],
) -> None:
    gateway, notifier, _service = stripe_payment_dependencies
    payload = {
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "pi_missing",
                "status": "succeeded",
            }
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")

    response = await async_client.post(
        "/api/v1/webhooks/stripe",
        content=raw_body,
        headers={"Stripe-Signature": "test_signature"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_dual_provider_coexistence(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    stripe_payment_dependencies: tuple[StubGateway, StubNotifier, PaymentService],
) -> None:
    """Test that both YooKassa and Stripe can coexist."""
    gateway, _notifier, _service = stripe_payment_dependencies
    await create_subscription_plan(
        session_factory,
        name="Pro",
        level="pro",
        monthly_cost=Decimal("29.99"),
    )
    user = await create_user(session_factory)

    stripe_response = await async_client.post(
        "/api/v1/payments/create",
        headers={"X-User-Id": str(user.id)},
        json={
            "plan_code": "basic",
            "success_url": "https://example.com/success",
            "provider": "stripe",
        },
    )
    assert stripe_response.status_code == 201
    stripe_payment = stripe_response.json()
    assert stripe_payment["provider"] == "stripe"

    yookassa_response = await async_client.post(
        "/api/v1/payments/create",
        headers={"X-User-Id": str(user.id)},
        json={
            "plan_code": "pro",
            "success_url": "https://example.com/success",
            "provider": "yookassa",
        },
    )
    assert yookassa_response.status_code == 201
    yookassa_payment = yookassa_response.json()
    assert yookassa_payment["provider"] == "yookassa"

    async with session_factory() as session:
        payments = (await session.execute(select(Payment))).scalars().all()
        assert len(payments) == 2
        providers = {p.provider for p in payments}
        assert PaymentProvider.STRIPE in providers
        assert PaymentProvider.YOOKASSA in providers
