from __future__ import annotations

from decimal import Decimal

from sqlalchemy import MetaData

from backend.db.base import Base
from backend.payments.models import Payment


def test_payment_metadata_descriptor_behaviour() -> None:
    class_metadata = Payment.metadata

    assert isinstance(class_metadata, MetaData)
    assert class_metadata is Base.metadata

    payload = {"provider_info": "test"}
    payment = Payment(
        user_id=1,
        subscription_id=10,
        provider_payment_id="test_123",
        idempotency_key="key_123",
        amount=Decimal("100.00"),
        currency="USD",
        metadata=payload,
    )

    assert payment.metadata_dict == payload
    assert payment.meta_data == payload

    new_payload = {"updated": "data"}
    payment.metadata_dict = new_payload

    assert payment.meta_data == new_payload
