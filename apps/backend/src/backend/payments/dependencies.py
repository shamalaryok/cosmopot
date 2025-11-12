from __future__ import annotations

from fastapi import Depends, HTTPException, status

from backend.core.config import Settings, get_settings
from backend.payments.enums import PaymentProvider
from backend.payments.gateway import PaymentGateway, StripeGateway, YooKassaGateway
from backend.payments.notifications import LoggingPaymentNotifier, PaymentNotifier
from backend.payments.service import PaymentService
from backend.referrals.dependencies import get_referral_service
from backend.referrals.service import ReferralService

_GATEWAYS: dict[PaymentProvider, PaymentGateway] = {}
_NOTIFIER: PaymentNotifier | None = None


def get_payment_gateway(settings: Settings = Depends(get_settings)) -> PaymentGateway:
    """Return the default (YooKassa) payment gateway for backward compatibility."""
    return _get_gateway_for_provider(PaymentProvider.YOOKASSA, settings)


def _get_gateway_for_provider(
    provider: PaymentProvider, settings: Settings
) -> PaymentGateway:
    """Get or create a gateway for the specified provider."""
    if provider in _GATEWAYS:
        return _GATEWAYS[provider]

    if provider == PaymentProvider.YOOKASSA:
        yookassa = settings.yookassa
        if yookassa.shop_id is None or yookassa.secret_key is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="YooKassa integration is not configured",
            )
        gateway: PaymentGateway = YooKassaGateway(
            shop_id=str(yookassa.shop_id),
            secret_key=yookassa.secret_key.get_secret_value(),
        )
    elif provider == PaymentProvider.STRIPE:
        stripe = settings.stripe
        if stripe.api_key is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Stripe integration is not configured",
            )
        gateway = StripeGateway(api_key=stripe.api_key.get_secret_value())
    else:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Unknown payment provider: {provider}",
        )

    _GATEWAYS[provider] = gateway
    return gateway


def get_payment_notifier() -> PaymentNotifier:
    global _NOTIFIER
    if _NOTIFIER is None:
        _NOTIFIER = LoggingPaymentNotifier()
    return _NOTIFIER


def get_payment_service(
    settings: Settings = Depends(get_settings),
    gateway: PaymentGateway = Depends(get_payment_gateway),
    notifier: PaymentNotifier = Depends(get_payment_notifier),
    referral_service: ReferralService = Depends(get_referral_service),
) -> PaymentService:
    return PaymentService(
        settings=settings,
        gateway=gateway,
        notifier=notifier,
        referral_service=referral_service,
    )


def reset_payment_dependencies() -> None:
    """Reset cached singletons to allow reconfiguration during tests."""

    global _GATEWAYS, _NOTIFIER
    _GATEWAYS.clear()
    _NOTIFIER = None
