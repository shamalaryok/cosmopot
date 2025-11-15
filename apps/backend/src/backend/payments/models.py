from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Enum,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import (
    Base,
    JSONDataMixin,
    MetadataAliasMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from backend.db.types import GUID, JSONType, UTCDateTime

from .enums import PaymentEventType, PaymentProvider, PaymentStatus


class Payment(Base, MetadataAliasMixin, UUIDPrimaryKeyMixin, TimestampMixin):
    """Represents a payment attempt from a payment provider."""

    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_payments_idempotency_key"),
        UniqueConstraint("provider_payment_id", name="uq_payments_provider_id"),
    )

    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    subscription_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    provider: Mapped[PaymentProvider] = mapped_column(
        Enum(PaymentProvider, name="payment_provider", native_enum=False),
        nullable=False,
        default=PaymentProvider.YOOKASSA,
    )
    provider_payment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", native_enum=False),
        nullable=False,
        default=PaymentStatus.PENDING,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")
    confirmation_url: Mapped[str | None] = mapped_column(String(2048))
    description: Mapped[str | None] = mapped_column(String(255))
    meta_data: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONType(), default=dict, nullable=False
    )
    captured_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    canceled_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    failure_reason: Mapped[str | None] = mapped_column(String(255))

    events: Mapped[list[PaymentEvent]] = relationship(
        back_populates="payment",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PaymentEvent(UUIDPrimaryKeyMixin, TimestampMixin, JSONDataMixin, Base):
    """Audit trail entry for payment status changes and webhooks."""

    __tablename__ = "payment_events"

    payment_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[PaymentEventType] = mapped_column(
        Enum(PaymentEventType, name="payment_event_type", native_enum=False),
        nullable=False,
    )
    provider_status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_event_status", native_enum=False),
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(String(255))

    payment: Mapped[Payment] = relationship(back_populates="events")
