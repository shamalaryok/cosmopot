from __future__ import annotations

from typing import NotRequired, TypedDict

__all__ = [
    "PaymentConfirmationPayload",
    "PaymentProviderResponse",
    "YooKassaAmountPayload",
    "YooKassaMetadataPayload",
    "YooKassaConfirmationPayload",
    "YooKassaPaymentPayload",
    "StripeMetadataPayload",
    "StripePaymentPayload",
    "ProviderPayload",
    "PaymentMetadataPayload",
]


class PaymentConfirmationPayload(TypedDict, total=False):
    """Provider-agnostic confirmation payload returned by gateways."""

    confirmation_url: NotRequired[str]
    url: NotRequired[str]
    client_secret: NotRequired[str]


class PaymentProviderResponse(TypedDict):
    """Structured response returned by payment gateways."""

    id: str
    status: NotRequired[str]
    confirmation: NotRequired[PaymentConfirmationPayload]
    client_secret: NotRequired[str]


class YooKassaAmountPayload(TypedDict):
    value: str
    currency: str


class YooKassaMetadataPayload(TypedDict, total=False):
    user_id: int
    plan: str
    cancel_url: str | None


class YooKassaConfirmationPayload(TypedDict):
    type: str
    return_url: str


class YooKassaPaymentPayload(TypedDict):
    amount: YooKassaAmountPayload
    capture: bool
    confirmation: YooKassaConfirmationPayload
    description: str
    metadata: YooKassaMetadataPayload


class StripeMetadataPayload(TypedDict):
    user_id: str
    plan: str
    cancel_url: str


class StripePaymentPayload(TypedDict):
    amount: int
    currency: str
    payment_method_types: list[str]
    description: str
    metadata: StripeMetadataPayload


ProviderPayload = YooKassaPaymentPayload | StripePaymentPayload


class PaymentMetadataPayload(TypedDict, total=False):
    plan_code: str
    plan_level: str
    plan_name: str
    plan_id: int
    success_url: str
    cancel_url: str | None
    provider_payload: ProviderPayload
    provider_response: PaymentProviderResponse
