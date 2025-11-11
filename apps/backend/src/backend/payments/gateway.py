from __future__ import annotations

import asyncio
from typing import Any, Protocol, cast

import stripe
from yookassa import Configuration
from yookassa import Payment as YooPayment

try:  # pragma: no cover - compatibility layer for SDK import changes
    from yookassa.exceptions import YooKassaError
except ImportError:  # pragma: no cover
    from yookassa.domain.exceptions import ApiError as YooKassaError

# Resilient import for Stripe exceptions - stripe v7.0+ moved exceptions to top-level
try:  # pragma: no cover - compatibility with stripe <7.0
    from stripe.error import StripeError
except (ImportError, ModuleNotFoundError):  # pragma: no cover - stripe >=7.0
    from stripe import StripeError

from .exceptions import PaymentGatewayError
from .types import PaymentProviderResponse, ProviderPayload


class PaymentGateway(Protocol):
    """Protocol describing the operations required from a payment provider."""

    async def create_payment(
        self, payload: ProviderPayload, idempotency_key: str
    ) -> PaymentProviderResponse:
        """Create a payment with the provider and return its serialised response."""


class YooKassaGateway:
    """Thin asynchronous wrapper around the official YooKassa SDK."""

    def __init__(self, *, shop_id: str, secret_key: str) -> None:
        if not shop_id:
            raise ValueError("shop_id must be provided")
        if not secret_key:
            raise ValueError("secret_key must be provided")
        self._shop_id = str(shop_id)
        self._secret_key = secret_key
        Configuration.configure(self._shop_id, self._secret_key)

    async def create_payment(
        self, payload: ProviderPayload, idempotency_key: str
    ) -> PaymentProviderResponse:
        def _call() -> PaymentProviderResponse:
            Configuration.configure(self._shop_id, self._secret_key)
            result = YooPayment.create(payload, idempotency_key)
            return self._normalise_response(result)

        try:
            return await asyncio.to_thread(_call)
        except YooKassaError as exc:
            raise PaymentGatewayError(str(exc)) from exc

    def _normalise_response(self, result: Any) -> PaymentProviderResponse:
        """Normalize YooKassa SDK response to PaymentProviderResponse."""
        if isinstance(result, dict):
            payment_id = result.get("id")
            if not isinstance(payment_id, str):
                raise PaymentGatewayError("YooKassa response missing 'id' field")
            return cast(PaymentProviderResponse, result)
        if hasattr(result, "to_dict"):
            normalized = result.to_dict()
            if not isinstance(normalized, dict):
                raise PaymentGatewayError("YooKassa to_dict() returned non-dict")
            payment_id = normalized.get("id")
            if not isinstance(payment_id, str):
                raise PaymentGatewayError("YooKassa response missing 'id' field")
            return cast(PaymentProviderResponse, normalized)
        raise PaymentGatewayError(
            f"Unexpected YooKassa response type: {type(result).__name__}"
        )


class StripeGateway:
    """Thin asynchronous wrapper around the Stripe SDK."""

    def __init__(self, *, api_key: str) -> None:
        if not api_key:
            raise ValueError("api_key must be provided")
        self._api_key = api_key
        stripe.api_key = api_key

    async def create_payment(
        self, payload: ProviderPayload, idempotency_key: str
    ) -> PaymentProviderResponse:
        def _call() -> PaymentProviderResponse:
            stripe.api_key = self._api_key
            intent = stripe.PaymentIntent.create(
                idempotency_key=idempotency_key,
                **payload,
            )
            return self._normalise_response(intent)

        try:
            return await asyncio.to_thread(_call)
        except StripeError as exc:
            raise PaymentGatewayError(str(exc)) from exc

    def _normalise_response(self, intent: Any) -> PaymentProviderResponse:
        """Normalise Stripe PaymentIntent to PaymentProviderResponse."""
        if hasattr(intent, "to_dict"):
            serialized = intent.to_dict()
            if isinstance(serialized, dict):
                payment_id = serialized.get("id")
                if isinstance(payment_id, str):
                    return cast(PaymentProviderResponse, serialized)
                raise PaymentGatewayError("Stripe response missing 'id' field")
            raise PaymentGatewayError("Stripe to_dict() returned non-dict payload")
        raise PaymentGatewayError(
            f"Unexpected Stripe response type: {type(intent).__name__}"
        )
