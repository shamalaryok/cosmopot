from __future__ import annotations

import hashlib
import hmac
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import stripe
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Resilient import for Stripe signature verification errors
try:  # pragma: no cover - compatibility with stripe >=7.0
    from stripe import SignatureVerificationError
except (ImportError, ModuleNotFoundError):  # pragma: no cover - stripe <7.0 fallback
    from stripe.error import SignatureVerificationError

from backend.core.config import PaymentPlan, Settings
from backend.payments.enums import PaymentEventType, PaymentProvider, PaymentStatus
from backend.payments.exceptions import (
    PaymentConfigurationError,
    PaymentGatewayError,
    PaymentNotFoundError,
    PaymentPlanNotFoundError,
    PaymentSignatureError,
)
from backend.payments.gateway import PaymentGateway, PaymentProviderResponse
from backend.payments.models import Payment, PaymentEvent
from backend.payments.notifications import LoggingPaymentNotifier, PaymentNotifier
from backend.payments.types import (
    PaymentMetadataPayload,
    ProviderPayload,
    StripePaymentPayload,
    YooKassaPaymentPayload,
)
from backend.referrals.service import ReferralService
from user_service.models import SubscriptionPlan, User


@dataclass(slots=True)
class PaymentRequest:
    """Input payload required to initiate a payment."""

    plan_code: str
    success_url: str
    cancel_url: str | None = None
    idempotency_key: str | None = None
    provider: PaymentProvider = PaymentProvider.YOOKASSA
    currency: str | None = None


class PaymentService:
    """Coordinates payment creation, webhook processing, and user notifications."""

    def __init__(
        self,
        *,
        settings: Settings,
        gateway: PaymentGateway | None = None,
        notifier: PaymentNotifier | None = None,
        referral_service: ReferralService | None = None,
    ) -> None:
        self._settings = settings
        self._default_gateway = gateway
        self._notifier = notifier or LoggingPaymentNotifier()
        self._referral_service = referral_service or ReferralService()
        self._logger = structlog.get_logger(__name__)

    async def create_payment(
        self, session: AsyncSession, user: User, request: PaymentRequest
    ) -> Payment:
        plan = self._resolve_plan(request.plan_code)
        subscription_plan = await self._get_subscription_plan(
            session, plan.subscription_level
        )

        currency = (
            request.currency
            or plan.currency
            or self._settings.payments.default_currency
        )
        amount = Decimal(subscription_plan.monthly_cost).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        description = plan.description or f"{subscription_plan.name} subscription"

        idempotency_key = request.idempotency_key or self._generate_idempotency_key(
            user.id
        )
        existing = await self._find_payment(session, user.id, idempotency_key)
        if existing is not None:
            self._logger.info(
                "payment_idempotency_hit",
                user_id=user.id,
                payment_id=str(existing.id),
                idempotency_key=idempotency_key,
            )
            return existing

        provider = request.provider
        provider_payload = self._build_provider_payload(
            provider=provider,
            amount=amount,
            currency=currency,
            plan_code=plan.code,
            description=description,
            user=user,
            success_url=request.success_url,
            cancel_url=request.cancel_url,
        )

        gateway = self._get_gateway_for_provider(provider)
        provider_response: PaymentProviderResponse = await gateway.create_payment(
            provider_payload, idempotency_key=idempotency_key
        )
        provider_payment_id = provider_response.get("id")
        if not isinstance(provider_payment_id, str):
            raise PaymentGatewayError(
                f"{provider.value} response missing payment identifier"
            )

        status = self._map_provider_status(provider, provider_response.get("status"))
        confirmation_url = self._extract_confirmation_url(provider, provider_response)

        payment_description = provider_payload["description"]

        payment = Payment(
            user_id=user.id,
            subscription_id=subscription_plan.id,
            provider=provider,
            provider_payment_id=provider_payment_id,
            idempotency_key=idempotency_key,
            status=status,
            amount=amount,
            currency=currency,
            confirmation_url=confirmation_url,
            description=payment_description,
            metadata=self._build_metadata(
                plan_code=plan.code,
                plan_level=plan.subscription_level,
                plan_name=subscription_plan.name,
                plan_id=subscription_plan.id,
                success_url=request.success_url,
                cancel_url=request.cancel_url,
                provider_payload=provider_payload,
                provider_response=provider_response,
            ),
        )
        session.add(payment)

        session.add(
            PaymentEvent(
                payment=payment,
                event_type=PaymentEventType.REQUEST,
                provider_status=status,
                data={
                    "payload": provider_payload,
                    "response": provider_response,
                },
                note="Payment initiated",
            )
        )

        await session.flush()
        await session.refresh(payment)
        return payment

    async def process_webhook(
        self,
        session: AsyncSession,
        payload: Mapping[str, object],
        provider: PaymentProvider,
    ) -> Payment:
        event_name_raw = self._extract_event_name(payload, provider)
        event_name = event_name_raw if isinstance(event_name_raw, str) else None

        provider_object = self._extract_provider_object(payload, provider)

        provider_payment_id = provider_object.get("id")
        if not isinstance(provider_payment_id, str):
            raise PaymentNotFoundError("Webhook payload missing provider payment id")

        payment = await self._lock_payment_by_provider_id(
            session, provider_payment_id, provider
        )
        if payment is None:
            raise PaymentNotFoundError(
                f"Payment with provider id '{provider_payment_id}' not found"
            )

        provider_status_raw = provider_object.get("status")
        provider_status = (
            provider_status_raw if isinstance(provider_status_raw, str) else None
        )
        new_status = self._map_webhook_status(provider, event_name, provider_status)
        previous_status = payment.status

        payload_dict = dict(payload)

        session.add(
            PaymentEvent(
                payment=payment,
                event_type=PaymentEventType.WEBHOOK,
                provider_status=new_status,
                data=payload_dict,
                note=f"Webhook event {event_name or 'unknown'}",
            )
        )

        metadata_updates: dict[str, Any] = {
            "last_webhook_event": event_name or event_name_raw,
            "provider_status": provider_status_raw,
        }

        if new_status is not payment.status:
            payment.status = new_status
            now = self._now()
            if (
                new_status is PaymentStatus.SUCCEEDED
                and previous_status is not PaymentStatus.SUCCEEDED
            ):
                payment.captured_at = now
                user = await self._activate_subscription(session, payment)
                metadata_updates["activated_at"] = now.isoformat()

                # Create referral earnings for successful payments
                try:
                    earnings = await self._referral_service.create_earning(
                        session,
                        payment,
                    )
                    if earnings:
                        metadata_updates["referral_earnings"] = [
                            {
                                "id": str(earning.id),
                                "amount": str(earning.amount),
                                "tier": earning.tier.value,
                                "percentage": earning.percentage,
                            }
                            for earning in earnings
                        ]
                        self._logger.info(
                            "referral_earnings_created",
                            payment_id=str(payment.id),
                            user_id=payment.user_id,
                            earnings_count=len(earnings),
                        )
                except Exception as exc:
                    self._logger.error(
                        "referral_earnings_failed",
                        payment_id=str(payment.id),
                        user_id=payment.user_id,
                        error=str(exc),
                    )

                await self._notify(user, payment, new_status, payload_dict)
            elif new_status in {
                PaymentStatus.CANCELED,
                PaymentStatus.FAILED,
                PaymentStatus.REFUNDED,
            }:
                payment.canceled_at = now
                cancellation_raw = provider_object.get("cancellation_details")
                cancellation_details = (
                    cancellation_raw if isinstance(cancellation_raw, Mapping) else None
                )
                failure_raw = provider_object.get("failure")
                failure_details = (
                    failure_raw if isinstance(failure_raw, Mapping) else None
                )
                cancellation_reason = (
                    cancellation_details.get("reason")
                    if cancellation_details is not None
                    else None
                )
                failure_description = (
                    failure_details.get("description")
                    if failure_details is not None
                    else None
                )
                payment.failure_reason = cancellation_reason or failure_description
                metadata_updates["cancellation_details"] = (
                    dict(cancellation_details)
                    if cancellation_details is not None
                    else (
                        dict(failure_details)
                        if failure_details is not None
                        else {}
                    )
                )
                user = await session.get(User, payment.user_id)
                await self._notify(user, payment, new_status, payload_dict)
            else:
                user = await session.get(User, payment.user_id)
                await self._notify(user, payment, new_status, payload_dict)

        confirmation_url = self._extract_confirmation_url(provider, provider_object)
        if confirmation_url is not None:
            payment.confirmation_url = confirmation_url

        self._apply_metadata_updates(payment, metadata_updates)
        await session.flush()

        return payment

    def verify_webhook_signature(
        self, signature_header: str | None, raw_body: bytes, provider: PaymentProvider
    ) -> None:
        if provider == PaymentProvider.YOOKASSA:
            self._verify_yookassa_signature(signature_header, raw_body)
        elif provider == PaymentProvider.STRIPE:
            self._verify_stripe_signature(signature_header, raw_body)
        else:
            raise PaymentConfigurationError(f"Unknown payment provider: {provider}")

    def _verify_yookassa_signature(
        self, signature_header: str | None, raw_body: bytes
    ) -> None:
        if not signature_header:
            raise PaymentSignatureError("Missing Content-Hmac header")

        secret = self._settings.yookassa.webhook_secret
        if secret is None:
            raise PaymentConfigurationError("YooKassa webhook secret is not configured")

        algorithm, _, provided = signature_header.partition("=")
        if algorithm.lower() != "sha256" or not provided:
            raise PaymentSignatureError("Unsupported webhook signature format")

        expected = hmac.new(
            secret.get_secret_value().encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected, provided.strip()):
            raise PaymentSignatureError("Webhook signature mismatch")

    def _verify_stripe_signature(
        self, signature_header: str | None, raw_body: bytes
    ) -> None:
        if not signature_header:
            raise PaymentSignatureError("Missing Stripe-Signature header")

        secret = self._settings.stripe.webhook_secret
        if secret is None:
            raise PaymentConfigurationError("Stripe webhook secret is not configured")

        try:
            stripe.Webhook.construct_event(
                raw_body,
                signature_header,
                secret.get_secret_value(),
            )
        except ValueError as exc:
            raise PaymentSignatureError(f"Invalid webhook payload: {exc}") from exc
        except SignatureVerificationError as exc:
            raise PaymentSignatureError(
                f"Webhook signature verification failed: {exc}"
            ) from exc

    async def _notify(
        self,
        user: User | None,
        payment: Payment,
        status: PaymentStatus,
        context: dict[str, Any],
    ) -> None:
        if user is None:
            self._logger.warning(
                "payment_notify_user_missing",
                user_id=payment.user_id,
                payment_id=str(payment.id),
                status=status.value,
            )
            return
        await self._notifier.notify(user, payment, status, context)

    async def _activate_subscription(
        self, session: AsyncSession, payment: Payment
    ) -> User | None:
        stmt = select(User).where(User.id == payment.user_id).with_for_update()
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            self._logger.warning(
                "payment_user_missing",
                user_id=payment.user_id,
                payment_id=str(payment.id),
            )
            return None

        user.subscription_id = payment.subscription_id
        current_balance = Decimal(user.balance or Decimal("0"))
        user.balance = (current_balance + payment.amount).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        await session.flush()
        return user

    async def _lock_payment_by_provider_id(
        self, session: AsyncSession, provider_payment_id: str, provider: PaymentProvider
    ) -> Payment | None:
        stmt = (
            select(Payment)
            .where(
                Payment.provider_payment_id == provider_payment_id,
                Payment.provider == provider,
            )
            .with_for_update()
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_subscription_plan(
        self, session: AsyncSession, level: str
    ) -> SubscriptionPlan:
        normalised_level = level.strip().lower()
        stmt = select(SubscriptionPlan).where(
            func.lower(SubscriptionPlan.level) == normalised_level
        )
        result = await session.execute(stmt)
        subscription_plan = result.scalar_one_or_none()
        if subscription_plan is None:
            raise PaymentPlanNotFoundError(
                "Subscription plan with level "
                f"'{level}' is not configured in the database"
            )
        return subscription_plan

    async def _find_payment(
        self, session: AsyncSession, user_id: int, idempotency_key: str
    ) -> Payment | None:
        stmt = (
            select(Payment)
            .where(
                Payment.user_id == user_id,
                Payment.idempotency_key == idempotency_key,
            )
            .order_by(Payment.created_at.desc())
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    def _resolve_plan(self, code: str) -> PaymentPlan:
        try:
            return self._settings.payments.get_plan(code)
        except KeyError as exc:
            raise PaymentPlanNotFoundError(f"Unknown payment plan '{code}'") from exc

    def _generate_idempotency_key(self, user_id: int) -> str:
        return f"{user_id}-{uuid.uuid4().hex}"

    def _build_provider_payload(
        self,
        *,
        provider: PaymentProvider,
        amount: Decimal,
        currency: str,
        plan_code: str,
        description: str | None,
        user: User,
        success_url: str,
        cancel_url: str | None,
    ) -> ProviderPayload:
        """Build provider-specific payment payload. See types.ProviderPayload for structure."""
        if provider == PaymentProvider.YOOKASSA:
            return self._build_yookassa_payload(
                amount=amount,
                currency=currency,
                plan_code=plan_code,
                description=description,
                user=user,
                success_url=success_url,
                cancel_url=cancel_url,
            )
        if provider == PaymentProvider.STRIPE:
            return self._build_stripe_payload(
                amount=amount,
                currency=currency,
                plan_code=plan_code,
                description=description,
                user=user,
                success_url=success_url,
                cancel_url=cancel_url,
            )
        raise PaymentConfigurationError(f"Unknown payment provider: {provider}")

    def _build_yookassa_payload(
        self,
        *,
        amount: Decimal,
        currency: str,
        plan_code: str,
        description: str | None,
        user: User,
        success_url: str,
        cancel_url: str | None,
    ) -> YooKassaPaymentPayload:
        """Build YooKassa payment payload. See types.YooKassaPaymentPayload for structure."""
        payload: YooKassaPaymentPayload = {
            "amount": {"value": f"{amount:.2f}", "currency": currency},
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": success_url,
            },
            "description": description or f"Subscription upgrade '{plan_code}'",
            "metadata": {
                "user_id": user.id,
                "plan": plan_code,
                "cancel_url": cancel_url,
            },
        }
        return payload

    def _build_stripe_payload(
        self,
        *,
        amount: Decimal,
        currency: str,
        plan_code: str,
        description: str | None,
        user: User,
        success_url: str,
        cancel_url: str | None,
    ) -> StripePaymentPayload:
        """Build Stripe payment payload. See types.StripePaymentPayload for structure."""
        amount_cents = int(amount * 100)
        payload: StripePaymentPayload = {
            "amount": amount_cents,
            "currency": currency.lower(),
            "payment_method_types": ["card"],
            "description": description or f"Subscription upgrade '{plan_code}'",
            "metadata": {
                "user_id": str(user.id),
                "plan": plan_code,
                "cancel_url": cancel_url or "",
            },
        }
        return payload

    def _build_metadata(
        self,
        *,
        plan_code: str,
        plan_level: str,
        plan_name: str,
        plan_id: int,
        success_url: str,
        cancel_url: str | None,
        provider_payload: ProviderPayload,
        provider_response: PaymentProviderResponse,
    ) -> PaymentMetadataPayload:
        """Build payment metadata. See types.PaymentMetadataPayload for structure."""
        metadata: PaymentMetadataPayload = {
            "plan_code": plan_code,
            "plan_level": plan_level,
            "plan_name": plan_name,
            "plan_id": plan_id,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "provider_payload": provider_payload,
            "provider_response": provider_response,
        }
        return metadata

    def _map_provider_status(
        self,
        provider: PaymentProvider,
        status: str | None,
    ) -> PaymentStatus:
        if provider == PaymentProvider.YOOKASSA:
            return self._map_yookassa_status(status)
        if provider == PaymentProvider.STRIPE:
            return self._map_stripe_status(status)
        return PaymentStatus.PENDING

    def _map_yookassa_status(self, status: str | None) -> PaymentStatus:
        mapping = {
            "pending": PaymentStatus.PENDING,
            "waiting_for_capture": PaymentStatus.WAITING_FOR_CAPTURE,
            "succeeded": PaymentStatus.SUCCEEDED,
            "canceled": PaymentStatus.CANCELED,
            "refunded": PaymentStatus.REFUNDED,
            "failed": PaymentStatus.FAILED,
        }
        return mapping.get((status or "").lower(), PaymentStatus.PENDING)

    def _map_stripe_status(self, status: str | None) -> PaymentStatus:
        mapping = {
            "requires_payment_method": PaymentStatus.PENDING,
            "requires_confirmation": PaymentStatus.PENDING,
            "requires_action": PaymentStatus.WAITING_FOR_CAPTURE,
            "processing": PaymentStatus.WAITING_FOR_CAPTURE,
            "succeeded": PaymentStatus.SUCCEEDED,
            "requires_capture": PaymentStatus.WAITING_FOR_CAPTURE,
            "canceled": PaymentStatus.CANCELED,
        }
        return mapping.get((status or "").lower(), PaymentStatus.PENDING)

    def _map_webhook_status(
        self, provider: PaymentProvider, event_name: str | None, status: str | None
    ) -> PaymentStatus:
        if provider == PaymentProvider.YOOKASSA:
            return self._map_yookassa_webhook_status(event_name, status)
        elif provider == PaymentProvider.STRIPE:
            return self._map_stripe_webhook_status(event_name, status)
        else:
            return self._map_provider_status(provider, status)

    def _map_yookassa_webhook_status(
        self, event_name: str | None, status: str | None
    ) -> PaymentStatus:
        event_mapping = {
            "payment.succeeded": PaymentStatus.SUCCEEDED,
            "payment.waiting_for_capture": PaymentStatus.WAITING_FOR_CAPTURE,
            "payment.canceled": PaymentStatus.CANCELED,
            "payment.failed": PaymentStatus.FAILED,
            "refund.succeeded": PaymentStatus.REFUNDED,
        }
        if event_name in event_mapping:
            return event_mapping[event_name]
        return self._map_yookassa_status(status)

    def _map_stripe_webhook_status(
        self, event_name: str | None, status: str | None
    ) -> PaymentStatus:
        event_mapping = {
            "payment_intent.succeeded": PaymentStatus.SUCCEEDED,
            "payment_intent.payment_failed": PaymentStatus.FAILED,
            "payment_intent.canceled": PaymentStatus.CANCELED,
            "charge.refunded": PaymentStatus.REFUNDED,
        }
        if event_name in event_mapping:
            return event_mapping[event_name]
        return self._map_stripe_status(status)

    def _extract_confirmation_url(
        self, provider: PaymentProvider, payload: Mapping[str, object]
    ) -> str | None:
        if provider == PaymentProvider.YOOKASSA:
            confirmation = payload.get("confirmation")
            if isinstance(confirmation, dict):
                url = confirmation.get("confirmation_url") or confirmation.get("url")
                if isinstance(url, str):
                    return url
        elif provider == PaymentProvider.STRIPE:
            client_secret = payload.get("client_secret")
            if isinstance(client_secret, str):
                return client_secret
        return None

    def _apply_metadata_updates(
        self, payment: Payment, updates: Mapping[str, Any]
    ) -> None:
        metadata: dict[str, Any] = dict(payment.metadata_dict)
        metadata.update(updates)
        payment.metadata_dict = metadata

    def _extract_event_name(
        self, payload: Mapping[str, object], provider: PaymentProvider
    ) -> object:
        """Extract event name from webhook payload based on provider format."""
        if provider == PaymentProvider.STRIPE:
            return payload.get("type")
        return payload.get("event")

    def _extract_provider_object(
        self, payload: Mapping[str, object], provider: PaymentProvider
    ) -> Mapping[str, object]:
        """Extract the payment object from webhook payload based on provider format."""
        if provider == PaymentProvider.STRIPE:
            data = payload.get("data")
            if not isinstance(data, Mapping):
                raise PaymentNotFoundError("Stripe webhook payload missing data object")
            obj = data.get("object")
            if not isinstance(obj, Mapping):
                raise PaymentNotFoundError(
                    "Stripe webhook payload missing payment object"
                )
            return obj
        obj = payload.get("object")
        if not isinstance(obj, Mapping):
            raise PaymentNotFoundError("Webhook payload missing payment object")
        return obj

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def _get_gateway_for_provider(self, provider: PaymentProvider) -> PaymentGateway:
        """Get or create gateway for the specified provider."""
        if provider == PaymentProvider.YOOKASSA:
            yookassa = self._settings.yookassa
            if yookassa.shop_id is None or yookassa.secret_key is None:
                raise PaymentConfigurationError(
                    "YooKassa integration is not configured"
                )
            from backend.payments.gateway import YooKassaGateway
            return YooKassaGateway(
                shop_id=str(yookassa.shop_id),
                secret_key=yookassa.secret_key.get_secret_value(),
            )
        elif provider == PaymentProvider.STRIPE:
            stripe_settings = self._settings.stripe
            if stripe_settings.api_key is None:
                raise PaymentConfigurationError("Stripe integration is not configured")
            from backend.payments.gateway import StripeGateway
            return StripeGateway(api_key=stripe_settings.api_key.get_secret_value())
        else:
            raise PaymentConfigurationError(f"Unknown payment provider: {provider}")
