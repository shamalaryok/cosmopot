from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from backend.payments.enums import PaymentProvider, PaymentStatus
from backend.payments.service import PaymentRequest


class PaymentCreateRequest(BaseModel):
    """Client payload for initiating a payment."""

    plan_code: str = Field(
        ..., min_length=2, max_length=64, description="Pricing tier identifier"
    )
    success_url: HttpUrl = Field(
        ..., description="URL the user should be redirected to after payment"
    )
    cancel_url: HttpUrl | None = Field(
        default=None,
        description=(
            "Optional URL to return to when the payment is cancelled by the user"
        ),
    )
    idempotency_key: str | None = Field(
        default=None,
        min_length=8,
        max_length=128,
        description=(
            "Client-supplied idempotency key to safely retry payment initiation"
        ),
    )
    provider: PaymentProvider = Field(
        default=PaymentProvider.YOOKASSA,
        description="Payment provider (yookassa or stripe)",
    )
    currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        description="Optional currency code for international payments",
    )

    model_config = ConfigDict(str_strip_whitespace=True)

    def to_domain(self) -> PaymentRequest:
        return PaymentRequest(
            plan_code=self.plan_code,
            success_url=str(self.success_url),
            cancel_url=str(self.cancel_url) if self.cancel_url else None,
            idempotency_key=self.idempotency_key,
            provider=self.provider,
            currency=self.currency,
        )


class PaymentCreateResponse(BaseModel):
    """Response describing the initialised payment."""

    id: uuid.UUID = Field(..., description="Internal payment identifier")
    provider: PaymentProvider = Field(
        ...,
        description="Payment provider identifier",
    )
    provider_payment_id: str = Field(
        ...,
        description="Identifier returned by payment provider",
    )
    status: PaymentStatus
    confirmation_url: str | None = Field(
        default=None,
        description="URL to redirect the user in order to complete the payment",
    )
    amount: Decimal
    currency: str

    model_config = ConfigDict(from_attributes=True)


class PaymentWebhookAck(BaseModel):
    """Acknowledgement payload returned to payment provider webhooks."""

    status: str = Field(default="accepted")
