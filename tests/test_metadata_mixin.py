from __future__ import annotations

from sqlalchemy import MetaData

from user_service.models import (
    Base,
    Payment,
    Subscription,
    SubscriptionHistory,
    Transaction,
)


def test_user_service_payment_metadata_descriptor() -> None:
    class_metadata = Payment.metadata

    assert isinstance(class_metadata, MetaData)
    assert class_metadata is Base.metadata

    payload = {"provider_info": "test"}
    payment = Payment(
        user_id=1,
        subscription_id=10,
        amount=100.00,
        currency="USD",
        metadata=payload,
    )

    assert payment.metadata == payload
    assert payment.meta_data == payload

    new_payload = {"updated": "data"}
    payment.metadata = new_payload

    assert payment.meta_data == new_payload


def test_user_service_subscription_metadata_descriptor() -> None:
    class_metadata = Subscription.metadata

    assert isinstance(class_metadata, MetaData)
    assert class_metadata is Base.metadata

    payload = {"source": "web"}
    subscription = Subscription(
        user_id=1,
        tier="premium",
        status="active",
        quota_limit=1000,
        quota_used=0,
        current_period_start="2024-01-01T00:00:00Z",
        current_period_end="2024-02-01T00:00:00Z",
        metadata=payload,
    )

    assert subscription.metadata == payload
    assert subscription.meta_data == payload


def test_user_service_subscription_history_metadata_descriptor() -> None:
    class_metadata = SubscriptionHistory.metadata

    assert isinstance(class_metadata, MetaData)
    assert class_metadata is Base.metadata


def test_user_service_transaction_metadata_descriptor() -> None:
    class_metadata = Transaction.metadata

    assert isinstance(class_metadata, MetaData)
    assert class_metadata is Base.metadata
