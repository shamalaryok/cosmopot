from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics.decorators import AnalyticsTracker
from backend.analytics.dependencies import get_analytics_service
from backend.api.dependencies.users import get_current_user
from backend.api.schemas.payments import (
    PaymentCreateRequest,
    PaymentCreateResponse,
)
from backend.auth.dependencies import get_rate_limiter
from backend.auth.rate_limiter import RateLimiter
from backend.db.dependencies import get_db_session
from backend.payments.dependencies import get_payment_service
from backend.payments.exceptions import (
    PaymentConfigurationError,
    PaymentGatewayError,
    PaymentPlanNotFoundError,
)
from backend.payments.service import PaymentService
from user_service.models import User

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


def _map_payment_to_response(payment) -> PaymentCreateResponse:  # type: ignore[no-untyped-def]
    return PaymentCreateResponse(
        id=payment.id,
        provider_payment_id=payment.provider_payment_id,
        status=payment.status,
        confirmation_url=payment.confirmation_url,
        amount=payment.amount,
        currency=payment.currency,
    )


@router.post(
    "/create",
    response_model=PaymentCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a payment for a subscription plan",
)
async def create_payment(
    payload: PaymentCreateRequest,
    analytics_service = Depends(get_analytics_service),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    payment_service: PaymentService = Depends(get_payment_service),
) -> PaymentCreateResponse:
    await rate_limiter.check("payments:create", str(current_user.id))

    # Track payment initiation
    analytics_tracker = AnalyticsTracker(analytics_service, session)
    await analytics_tracker.track_payment(
        user_id=str(current_user.id),
        amount=float(payload.plan_code),
        currency=payload.currency or "RUB",
        payment_method=payload.provider.value,
        status="initiated",
        plan_code=payload.plan_code,
    )

    try:
        payment = await payment_service.create_payment(
            session, current_user, payload.to_domain()
        )
        await session.commit()
        
        # Track payment created successfully
        await analytics_tracker.track_payment(
            user_id=str(current_user.id),
            amount=float(payment.amount),
            currency=payment.currency,
            payment_method=payment.provider.value,
            status="initiated",
            plan_code=payload.plan_code,
            payment_id=str(payment.id),
        )
        
    except PaymentPlanNotFoundError as exc:
        await session.rollback()
        # Track payment failed - plan not found
        await analytics_tracker.track_payment(
            user_id=str(current_user.id),
            amount=float(payload.plan_code),
            currency=payload.currency or "RUB",
            payment_method=payload.provider.value,
            status="failed",
            plan_code=payload.plan_code,
            error="plan_not_found",
        )
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PaymentConfigurationError as exc:
        await session.rollback()
        # Track payment failed - configuration error
        await analytics_tracker.track_payment(
            user_id=str(current_user.id),
            amount=float(payload.plan_code),
            currency=payload.currency or "RUB",
            payment_method=payload.provider.value,
            status="failed",
            plan_code=payload.plan_code,
            error="configuration_error",
        )
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except PaymentGatewayError as exc:
        await session.rollback()
        # Track payment failed - gateway error
        await analytics_tracker.track_payment(
            user_id=str(current_user.id),
            amount=float(payload.plan_code),
            currency=payload.currency or "RUB",
            payment_method=payload.provider.value,
            status="failed",
            plan_code=payload.plan_code,
            error="gateway_error",
        )
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception:
        await session.rollback()
        # Track payment failed - unknown error
        await analytics_tracker.track_payment(
            user_id=str(current_user.id),
            amount=float(payload.plan_code),
            currency=payload.currency or "RUB",
            payment_method=payload.provider.value,
            status="failed",
            plan_code=payload.plan_code,
            error="unknown_error",
        )
        raise

    await session.refresh(payment)
    return _map_payment_to_response(payment)
