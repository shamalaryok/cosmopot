from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies.users import (
    get_current_user,
    get_user_from_path,
)
from backend.api.schemas.users import (
    BalanceAdjustmentRequest,
    BalanceResponse,
    GDPRRequestResponse,
    QuotaSummary,
    RoleUpdateRequest,
    SessionResponse,
    SessionStatus,
    SubscriptionSummary,
    UserProfilePayload,
    UserProfileResponse,
    UserResponse,
)
from backend.core.config import get_settings
from backend.db.dependencies import get_db_session
from backend.security import GDPRDataExporter
from user_service.enums import SubscriptionStatus, UserRole
from user_service.models import (
    Subscription,
    User,
    UserProfile,
    UserSession,
)
from user_service.repository import (
    TelegramIdConflictError,
    adjust_user_balance,
    create_profile,
    get_profile_by_user_id,
    get_user_with_related,
    update_profile,
    update_user,
)
from user_service.schemas import UserProfileCreate, UserProfileUpdate, UserUpdate

router = APIRouter(prefix="/api/v1/users", tags=["users"])
logger = structlog.get_logger(__name__)

_QUOTA_PRESETS: dict[str, int] = {
    "free": 500,
    "basic": 2_000,
    "premium": 10_000,
    "enterprise": 50_000,
}

ACTIVE_SUBSCRIPTION_STATUSES: set[SubscriptionStatus] = {
    SubscriptionStatus.ACTIVE,
    SubscriptionStatus.TRIALING,
}


@dataclass(frozen=True)
class PlanSnapshot:
    id: int
    name: str
    level: str
    monthly_cost: Decimal


def _select_active_subscription(
    subscriptions: Sequence[Subscription] | None,
) -> Subscription | None:
    if not subscriptions:
        return None
    active = [
        subscription
        for subscription in subscriptions
        if subscription.status in ACTIVE_SUBSCRIPTION_STATUSES
    ]
    if not active:
        return None
    return max(active, key=lambda item: item.current_period_end)


def _current_plan_snapshot(user: User) -> PlanSnapshot | None:
    plan = user.subscription_plan
    if plan is not None:
        return PlanSnapshot(
            id=plan.id,
            name=plan.name,
            level=plan.level,
            monthly_cost=plan.monthly_cost,
        )

    active_subscription = _select_active_subscription(user.subscriptions)
    if active_subscription is None:
        return None

    tier_value = active_subscription.tier.value.strip()
    level = tier_value or "free"
    name = level.replace("_", " ").title()
    return PlanSnapshot(
        id=active_subscription.id,
        name=name,
        level=level,
        monthly_cost=Decimal("0"),
    )


def _normalised_plan(plan_snapshot: PlanSnapshot | None) -> str:
    """Extract a normalized plan identifier from a snapshot."""
    if plan_snapshot is None:
        return "free"
    candidates = [plan_snapshot.level, plan_snapshot.name]
    for candidate in candidates:
        stripped = candidate.strip()
        if stripped:
            return stripped.lower()
    return "free"


def _quota_summary(
    plan_snapshot: PlanSnapshot | None, balance: Decimal
) -> QuotaSummary:
    """Generate a QuotaSummary from a plan snapshot and user balance."""
    plan_key = _normalised_plan(plan_snapshot)
    monthly_allocation = _QUOTA_PRESETS.get(plan_key, 5_000)
    requires_top_up = balance <= Decimal("0")
    remaining_allocation = monthly_allocation if not requires_top_up else 0
    plan_label = (
        plan_snapshot.name if plan_snapshot and plan_snapshot.name else plan_key.title()
    )

    return QuotaSummary(
        plan=plan_label,
        monthly_allocation=monthly_allocation,
        remaining_allocation=remaining_allocation,
        requires_top_up=requires_top_up,
    )


def _session_status(session: UserSession) -> SessionStatus:
    now = datetime.now(UTC)
    expires_at = session.expires_at
    if expires_at.tzinfo is None or expires_at.tzinfo.utcoffset(expires_at) is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if session.revoked_at is not None:
        return SessionStatus.REVOKED
    if session.ended_at is not None or expires_at <= now:
        return SessionStatus.EXPIRED
    return SessionStatus.ACTIVE


def _build_session_payload(sessions: Sequence[UserSession]) -> list[SessionResponse]:
    ordered = sorted(sessions, key=lambda item: item.created_at, reverse=True)
    return [
        SessionResponse(
            id=session.id,
            session_token=session.session_token,
            user_agent=session.user_agent,
            ip_address=session.ip_address,
            expires_at=session.expires_at,
            created_at=session.created_at,
            revoked_at=session.revoked_at,
            ended_at=session.ended_at,
            status=_session_status(session),
        )
        for session in ordered
    ]


def _build_profile_payload(profile: UserProfile) -> UserProfileResponse:
    return UserProfileResponse(
        id=profile.id,
        first_name=profile.first_name,
        last_name=profile.last_name,
        telegram_id=profile.telegram_id,
        phone_number=profile.phone_number,
        country=profile.country,
        city=profile.city,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        deleted_at=profile.deleted_at,
    )


def _build_user_payload(
    user: User, *, include_sessions: Iterable[UserSession]
) -> UserResponse:
    plan_snapshot = _current_plan_snapshot(user)
    subscription_summary = (
        SubscriptionSummary.model_validate(plan_snapshot)
        if plan_snapshot is not None
        else None
    )
    quotas = _quota_summary(plan_snapshot, user.balance or Decimal("0"))
    sessions_payload = _build_session_payload(list(include_sessions))
    profile_payload = (
        _build_profile_payload(user.profile) if user.profile is not None else None
    )

    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        balance=user.balance,
        is_active=user.is_active,
        subscription=subscription_summary,
        quotas=quotas,
        profile=profile_payload,
        sessions=sessions_payload,
    )


def _gdpr_response(operation: str) -> GDPRRequestResponse:
    now = datetime.now(UTC)
    reference = f"{operation}-{uuid4()}"
    note = (
        "Operation queued for downstream security workflow. "
        "No immediate action is performed in this service."
    )
    return GDPRRequestResponse(
        status="scheduled",
        requested_at=now,
        reference=reference,
        note=note,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Retrieve the authenticated user's profile and account information",
)
async def read_current_user(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    user = await get_user_with_related(session, current_user.id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return _build_user_payload(user, include_sessions=user.sessions or [])


@router.patch(
    "/me/profile",
    response_model=UserProfileResponse,
    summary="Create or update the authenticated user's profile information",
)
async def upsert_profile(
    payload: UserProfilePayload,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> UserProfileResponse:
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No changes supplied"
        )

    # Capture user ID before try/except to avoid lazy loading in exception handler
    user_id = current_user.id
    profile = await get_profile_by_user_id(session, user_id)

    try:
        if profile is None:
            create_schema = UserProfileCreate(user_id=user_id, **update_data)
            profile = await create_profile(session, create_schema)
        else:
            update_schema = UserProfileUpdate(**update_data)
            profile = await update_profile(session, profile, update_schema)
        await session.commit()
    except TelegramIdConflictError as exc:
        await session.rollback()
        logger.warning("telegram_id_conflict", user_id=user_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="telegram_id is already in use by another user",
        ) from exc
    except IntegrityError as exc:
        await session.rollback()
        logger.warning("profile_update_conflict", user_id=user_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Profile update violates uniqueness constraints",
        ) from exc

    await session.refresh(profile)
    return _build_profile_payload(profile)


@router.get(
    "/me/balance",
    response_model=BalanceResponse,
    summary="Return the authenticated user's balance and quota placeholders",
)
async def read_balance(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> BalanceResponse:
    user = await get_user_with_related(session, current_user.id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    plan_snapshot = _current_plan_snapshot(user)
    quotas = _quota_summary(plan_snapshot, user.balance or Decimal("0"))
    return BalanceResponse(balance=user.balance, quotas=quotas)


@router.post(
    "/{user_id}/balance/adjust",
    response_model=BalanceResponse,
    summary="Adjust a user's balance within a guarded transaction",
)
async def adjust_balance(
    payload: BalanceAdjustmentRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    target_user: User = Depends(get_user_from_path),
) -> BalanceResponse:
    is_self_adjustment = target_user.id == current_user.id
    if not is_self_adjustment and current_user.role is not UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Administrators only"
        )

    if payload.delta == Decimal("0"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Delta must be non-zero"
        )

    try:
        new_balance = await adjust_user_balance(session, target_user.id, payload.delta)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        detail = str(exc)
        status_code = (
            status.HTTP_404_NOT_FOUND
            if detail == "user not found"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail=detail) from exc

    await session.refresh(target_user)
    plan_snapshot = _current_plan_snapshot(target_user)
    quotas = _quota_summary(plan_snapshot, new_balance)

    logger.info(
        "balance_adjusted",
        actor_id=current_user.id,
        target_id=target_user.id,
        delta=str(payload.delta),
        resulting_balance=str(new_balance),
        reason=payload.reason,
    )

    return BalanceResponse(balance=new_balance, quotas=quotas)


@router.post(
    "/{user_id}/role",
    response_model=UserResponse,
    summary="Update a user's role (administrator only)",
)
async def update_role(
    payload: RoleUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    target_user: User = Depends(get_user_from_path),
) -> UserResponse:
    if current_user.role is not UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Administrators only"
        )

    update_schema = UserUpdate(role=payload.role)
    await update_user(session, target_user, update_schema)
    await session.commit()

    updated_user = await get_user_with_related(session, target_user.id)
    if updated_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    logger.info(
        "role_updated",
        actor_id=current_user.id,
        target_id=updated_user.id,
        new_role=str(updated_user.role),
    )

    return _build_user_payload(
        updated_user, include_sessions=updated_user.sessions or []
    )


@router.get(
    "/me/sessions",
    response_model=list[SessionResponse],
    summary="List authentication sessions for the authenticated user",
)
async def list_sessions(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[SessionResponse]:
    user = await get_user_with_related(session, current_user.id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return _build_session_payload(user.sessions or [])


@router.delete(
    "/me/sessions/{session_id}",
    response_model=SessionResponse,
    summary="Terminate an active session for the authenticated user",
)
async def terminate_session(
    session_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> SessionResponse:
    stmt = select(UserSession).where(UserSession.id == session_id)
    result = await session.execute(stmt)
    user_session = result.scalar_one_or_none()
    if user_session is None or user_session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    now = datetime.now(UTC)
    if user_session.revoked_at is None:
        user_session.revoked_at = now
    user_session.ended_at = now

    await session.flush()
    await session.commit()
    await session.refresh(user_session)

    logger.info(
        "session_revoked",
        user_id=current_user.id,
        session_id=user_session.id,
        token=user_session.session_token,
    )

    return _build_session_payload([user_session])[0]


@router.post(
    "/me/data-export",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GDPRRequestResponse,
    summary="Schedule a GDPR-compliant data export",
)
async def schedule_data_export(
    current_user: User = Depends(get_current_user),
) -> GDPRRequestResponse:
    try:
        settings = get_settings()
        exporter = GDPRDataExporter(settings)
        result = await exporter.export_user_data(current_user.id)
        
        now = datetime.now(UTC)
        reference = f"export-{uuid4()}"
        
        return GDPRRequestResponse(
            status=result["status"],
            requested_at=now,
            reference=reference,
            note=(
                "Your data export has been scheduled and will be available "
                "in your export location."
            ),
        )
    except Exception as exc:
        logger.exception("gdpr_export_endpoint_failed", user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to schedule data export",
        ) from exc


@router.post(
    "/me/data-delete",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GDPRRequestResponse,
    summary="Schedule a GDPR-compliant account deletion",
)
async def schedule_data_delete(
    current_user: User = Depends(get_current_user),
) -> GDPRRequestResponse:
    try:
        settings = get_settings()
        exporter = GDPRDataExporter(settings)
        result = await exporter.mark_user_for_deletion(current_user.id)
        
        now = datetime.now(UTC)
        reference = f"delete-{uuid4()}"
        
        retention_days = settings.gdpr.result_retention_days
        return GDPRRequestResponse(
            status=result["status"],
            requested_at=now,
            reference=reference,
            note=(
                f"Your account deletion has been scheduled. "
                f"Hard deletion will occur after {retention_days} days."
            ),
        )
    except Exception as exc:
        logger.exception("gdpr_delete_endpoint_failed", user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to schedule account deletion",
        ) from exc
