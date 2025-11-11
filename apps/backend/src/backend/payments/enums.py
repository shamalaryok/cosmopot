from __future__ import annotations

from enum import StrEnum


class PaymentStatus(StrEnum):
    """Life cycle states for a payment attempt."""

    PENDING = "pending"
    WAITING_FOR_CAPTURE = "waiting_for_capture"
    SUCCEEDED = "succeeded"
    CANCELED = "canceled"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentEventType(StrEnum):
    """Source for payment events stored in the audit log."""

    REQUEST = "request"
    WEBHOOK = "webhook"
    SYSTEM = "system"


class PaymentProvider(StrEnum):
    """Payment provider identifier."""

    YOOKASSA = "yookassa"
    STRIPE = "stripe"
