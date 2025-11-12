from __future__ import annotations

import json

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.schemas.payments import PaymentWebhookAck
from backend.db.dependencies import get_db_session
from backend.payments.dependencies import get_payment_service
from backend.payments.enums import PaymentProvider
from backend.payments.exceptions import (
    PaymentConfigurationError,
    PaymentNotFoundError,
    PaymentSignatureError,
)
from backend.payments.service import PaymentService

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

logger = structlog.get_logger(__name__)


@router.post(
    "/yukassa",
    response_model=PaymentWebhookAck,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Handle YooKassa webhook callbacks",
)
async def handle_yookassa_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    payment_service: PaymentService = Depends(get_payment_service),
) -> PaymentWebhookAck:
    raw_body = await request.body()
    signature = request.headers.get("Content-Hmac")

    try:
        payment_service.verify_webhook_signature(
            signature, raw_body, PaymentProvider.YOOKASSA
        )
    except PaymentSignatureError as exc:
        logger.warning("webhook_signature_error", error=str(exc))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PaymentConfigurationError as exc:
        logger.error("webhook_configuration_error", error=str(exc))
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except ValueError as exc:
        logger.warning("webhook_payload_invalid", error=str(exc))
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload"
        ) from exc

    try:
        await payment_service.process_webhook(
            session, payload, PaymentProvider.YOOKASSA
        )
        await session.commit()
    except PaymentNotFoundError as exc:
        await session.rollback()
        logger.warning("webhook_payment_missing", error=str(exc))
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        await session.rollback()
        logger.exception("webhook_processing_failed", error=str(exc))
        raise

    logger.info("webhook_processed", status_code=status.HTTP_202_ACCEPTED)
    return PaymentWebhookAck()


@router.post(
    "/stripe",
    response_model=PaymentWebhookAck,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Handle Stripe webhook callbacks",
)
async def handle_stripe_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    payment_service: PaymentService = Depends(get_payment_service),
) -> PaymentWebhookAck:
    raw_body = await request.body()
    signature = request.headers.get("Stripe-Signature")

    try:
        payment_service.verify_webhook_signature(
            signature, raw_body, PaymentProvider.STRIPE
        )
    except PaymentSignatureError as exc:
        logger.warning("stripe_webhook_signature_error", error=str(exc))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PaymentConfigurationError as exc:
        logger.error("stripe_webhook_configuration_error", error=str(exc))
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except ValueError as exc:
        logger.warning("stripe_webhook_payload_invalid", error=str(exc))
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload"
        ) from exc

    try:
        await payment_service.process_webhook(session, payload, PaymentProvider.STRIPE)
        await session.commit()
    except PaymentNotFoundError as exc:
        await session.rollback()
        logger.warning("stripe_webhook_payment_missing", error=str(exc))
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        await session.rollback()
        logger.exception("stripe_webhook_processing_failed", error=str(exc))
        raise

    logger.info("stripe_webhook_processed", status_code=status.HTTP_202_ACCEPTED)
    return PaymentWebhookAck()
