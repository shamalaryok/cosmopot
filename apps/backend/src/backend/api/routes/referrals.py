from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics.decorators import AnalyticsTracker
from backend.analytics.dependencies import get_analytics_service
from backend.api.dependencies.users import get_current_user
from backend.api.schemas.referrals import (
    ReferralCodeResponse,
    ReferralStatsResponse,
    WithdrawalListResponse,
    WithdrawalRequest,
    WithdrawalResponse,
)
from backend.auth.dependencies import get_rate_limiter
from backend.auth.rate_limiter import RateLimiter
from backend.core.config import Settings, get_settings
from backend.db.dependencies import get_db_session
from backend.referrals.exceptions import (
    ReferralCodeNotFoundError,
    WithdrawalInsufficientFundsError,
)
from backend.referrals.service import ReferralService
from user_service.models import User

router = APIRouter(prefix="/api/v1/referrals", tags=["referrals"])


def _map_withdrawal_to_response(withdrawal: Any) -> WithdrawalResponse:
    """Map withdrawal model to response schema."""
    processed_at = (
        withdrawal.processed_at.isoformat()
        if withdrawal.processed_at
        else None
    )
    return WithdrawalResponse(
        id=str(withdrawal.id),
        amount=withdrawal.amount,
        status=withdrawal.status.value,
        created_at=withdrawal.created_at.isoformat(),
        notes=withdrawal.notes,
        processed_at=processed_at,
    )


@router.get(
    "/code",
    response_model=ReferralCodeResponse,
    summary="Get user's referral code",
)
async def get_referral_code(
    analytics_service = Depends(get_analytics_service),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    settings: Settings = Depends(get_settings),
) -> ReferralCodeResponse:
    """Get the current user's referral code and referral URL."""
    await rate_limiter.check("referrals:get_code", str(current_user.id))
    
    # Track referral code access
    analytics_tracker = AnalyticsTracker(analytics_service, session)
    await analytics_tracker.track_feature_usage(
        user_id=str(current_user.id),
        feature_name="referral_code_access",
    )
    
    referral_service = ReferralService()
    referral_code = await referral_service.get_referral_code(session, current_user)
    
    # Build referral URL
    base_url = settings.app.base_url or "https://example.com"
    referral_url = f"{base_url}/signup?ref={referral_code}"
    
    return ReferralCodeResponse(
        referral_code=referral_code,
        referral_url=referral_url,
    )


@router.get(
    "/stats",
    response_model=ReferralStatsResponse,
    summary="Get user's referral statistics",
)
async def get_referral_stats(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
) -> ReferralStatsResponse:
    """Get detailed referral statistics for the current user."""
    await rate_limiter.check("referrals:get_stats", str(current_user.id))
    
    referral_service = ReferralService()
    stats = await referral_service.get_referral_stats(session, current_user)
    
    return ReferralStatsResponse(
        referral_code=stats.referral_code,
        total_earnings=stats.total_earnings,
        available_balance=stats.available_balance,
        total_withdrawn=stats.total_withdrawn,
        tier1_count=stats.tier1_count,
        tier2_count=stats.tier2_count,
        pending_withdrawals=stats.pending_withdrawals,
    )


@router.post(
    "/withdraw",
    response_model=WithdrawalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Request withdrawal of referral earnings",
)
async def request_withdrawal(
    payload: WithdrawalRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
) -> WithdrawalResponse:
    """Request a withdrawal of available referral earnings."""
    await rate_limiter.check("referrals:withdraw", str(current_user.id))
    
    referral_service = ReferralService()
    
    try:
        withdrawal = await referral_service.request_withdrawal(
            session, current_user, payload
        )
        await session.commit()
    except WithdrawalInsufficientFundsError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        ) from exc
    except Exception:
        await session.rollback()
        raise
    
    await session.refresh(withdrawal)
    return _map_withdrawal_to_response(withdrawal)


@router.get(
    "/withdrawals",
    response_model=WithdrawalListResponse,
    summary="Get user's withdrawal history",
)
async def get_withdrawals(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    limit: int = Query(default=50, le=100, ge=1),
    offset: int = Query(default=0, ge=0),
) -> WithdrawalListResponse:
    """Get the current user's withdrawal request history."""
    await rate_limiter.check("referrals:get_withdrawals", str(current_user.id))
    
    referral_service = ReferralService()
    withdrawals = await referral_service.get_user_withdrawals(session, current_user)
    
    # Apply pagination
    paginated_withdrawals = withdrawals[offset:offset + limit]
    
    # Count pending withdrawals
    pending_count = sum(1 for w in withdrawals if w.status.value == "pending")
    
    return WithdrawalListResponse(
        withdrawals=[_map_withdrawal_to_response(w) for w in paginated_withdrawals],
        total=len(withdrawals),
        pending_count=pending_count,
    )


@router.post(
    "/apply/{referral_code}",
    summary="Apply a referral code during registration",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def apply_referral_code(
    referral_code: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
) -> None:
    """Apply a referral code to the current user during registration."""
    await rate_limiter.check("referrals:apply_code", str(current_user.id))
    
    referral_service = ReferralService()
    
    try:
        referral = await referral_service.process_referral_code(
            session, referral_code, current_user
        )
        if referral:
            await session.commit()
    except ReferralCodeNotFoundError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=str(exc)
        ) from exc
    except Exception:
        await session.rollback()
        raise