from __future__ import annotations

import math
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies.users import require_admin
from backend.api.schemas.admin import (
    AdminAnalyticsResponse,
    AdminGenerationResponse,
    AdminGenerationUpdate,
    AdminModerationAction,
    AdminPromptCreate,
    AdminPromptResponse,
    AdminPromptUpdate,
    AdminSubscriptionResponse,
    AdminSubscriptionUpdate,
    AdminUserCreate,
    AdminUserResponse,
    AdminUserUpdate,
    PaginatedResponse,
)
from backend.auth.passwords import hash_password
from backend.db.dependencies import get_db_session
from backend.services.analytics import AnalyticsService
from backend.services.export import ExportService
from user_service.enums import (
    GenerationTaskStatus,
    PromptCategory,
    SubscriptionStatus,
    SubscriptionTier,
    UserRole,
)
from user_service.models import GenerationTask, Prompt, Subscription, User
from user_service.repository import create_user
from user_service.schemas import UserCreate

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
logger = structlog.get_logger(__name__)


@router.get(
    "/analytics",
    response_model=AdminAnalyticsResponse,
    summary="Get admin dashboard analytics",
)
async def get_analytics(
    session: AsyncSession = Depends(get_db_session),
    _admin: User = Depends(require_admin),
) -> AdminAnalyticsResponse:
    analytics_service = AnalyticsService(session)
    metrics = await analytics_service.get_dashboard_metrics()
    return AdminAnalyticsResponse(**metrics)


@router.get(
    "/users",
    response_model=PaginatedResponse,
    summary="List all users with pagination and filters",
)
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    role: UserRole | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
    _admin: User = Depends(require_admin),
) -> PaginatedResponse:
    stmt = select(User).where(User.deleted_at.is_(None))

    if search:
        stmt = stmt.where(User.email.ilike(f"%{search}%"))
    if role is not None:
        stmt = stmt.where(User.role == role)
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    stmt = stmt.order_by(User.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(stmt)
    users = result.scalars().all()

    user_responses = [AdminUserResponse.model_validate(user) for user in users]
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return PaginatedResponse(
        items=user_responses,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/users/{user_id}",
    response_model=AdminUserResponse,
    summary="Get user details by ID",
)
async def get_user(
    user_id: int,
    session: AsyncSession = Depends(get_db_session),
    _admin: User = Depends(require_admin),
) -> AdminUserResponse:
    stmt = select(User).where(User.id == user_id).where(User.deleted_at.is_(None))
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    return AdminUserResponse.model_validate(user)


@router.post(
    "/users",
    response_model=AdminUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user (admin only)",
)
async def create_user_admin(
    payload: AdminUserCreate,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(require_admin),
) -> AdminUserResponse:
    hashed_password = hash_password(payload.password)

    user_create = UserCreate(
        email=payload.email,
        hashed_password=hashed_password,
        role=payload.role,
        is_active=payload.is_active,
    )

    try:
        user = await create_user(session, user_create)
        await session.commit()
        await session.refresh(user)
    except Exception as exc:
        await session.rollback()
        logger.error("user_creation_failed", error=str(exc), admin_id=admin.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User creation failed. Email may already exist.",
        ) from exc

    logger.info("user_created_by_admin", user_id=user.id, admin_id=admin.id)
    return AdminUserResponse.model_validate(user)


@router.patch(
    "/users/{user_id}",
    response_model=AdminUserResponse,
    summary="Update user details",
)
async def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(require_admin),
) -> AdminUserResponse:
    stmt = select(User).where(User.id == user_id).where(User.deleted_at.is_(None))
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)

    try:
        await session.flush()
        await session.commit()
        await session.refresh(user)
    except Exception as exc:
        await session.rollback()
        logger.error(
            "user_update_failed", user_id=user_id, error=str(exc), admin_id=admin.id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User update failed"
        ) from exc

    logger.info("user_updated_by_admin", user_id=user.id, admin_id=admin.id)
    return AdminUserResponse.model_validate(user)


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft delete a user",
)
async def delete_user(
    user_id: int,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(require_admin),
) -> None:
    stmt = select(User).where(User.id == user_id).where(User.deleted_at.is_(None))
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    user.deleted_at = datetime.now(UTC)
    user.is_active = False

    try:
        await session.flush()
        await session.commit()
    except Exception as exc:
        await session.rollback()
        logger.error(
            "user_deletion_failed", user_id=user_id, error=str(exc), admin_id=admin.id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User deletion failed"
        ) from exc

    logger.info("user_deleted_by_admin", user_id=user.id, admin_id=admin.id)


@router.get(
    "/users/export/{format}",
    summary="Export users to CSV or JSON",
)
async def export_users(
    format: str,
    session: AsyncSession = Depends(get_db_session),
    _admin: User = Depends(require_admin),
) -> StreamingResponse:
    if format not in ("csv", "json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid format. Use 'csv' or 'json'.",
        )

    stmt = (
        select(User)
        .where(User.deleted_at.is_(None))
        .order_by(User.created_at.desc())
    )
    result = await session.execute(stmt)
    users = result.scalars().all()

    data = [
        {
            "id": user.id,
            "email": user.email,
            "role": user.role.value,
            "balance": str(user.balance),
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat(),
            "updated_at": user.updated_at.isoformat(),
        }
        for user in users
    ]

    filename = f"users_export_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.{format}"

    if format == "csv":
        return ExportService.export_to_csv(data, filename)
    return ExportService.export_to_json(data, filename)


@router.get(
    "/subscriptions",
    response_model=PaginatedResponse,
    summary="List all subscriptions with pagination and filters",
)
async def list_subscriptions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: int | None = Query(default=None),
    tier: SubscriptionTier | None = Query(default=None),
    status: SubscriptionStatus | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
    _admin: User = Depends(require_admin),
) -> PaginatedResponse:
    stmt = select(Subscription)

    if user_id is not None:
        stmt = stmt.where(Subscription.user_id == user_id)
    if tier is not None:
        stmt = stmt.where(Subscription.tier == tier)
    if status is not None:
        stmt = stmt.where(Subscription.status == status)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    stmt = stmt.order_by(Subscription.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(stmt)
    subscriptions = result.scalars().all()

    subscription_responses = [
        AdminSubscriptionResponse.model_validate(sub) for sub in subscriptions
    ]
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return PaginatedResponse(
        items=subscription_responses,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/subscriptions/{subscription_id}",
    response_model=AdminSubscriptionResponse,
    summary="Get subscription details by ID",
)
async def get_subscription(
    subscription_id: int,
    session: AsyncSession = Depends(get_db_session),
    _admin: User = Depends(require_admin),
) -> AdminSubscriptionResponse:
    stmt = select(Subscription).where(Subscription.id == subscription_id)
    result = await session.execute(stmt)
    subscription = result.scalar_one_or_none()

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found"
        )

    return AdminSubscriptionResponse.model_validate(subscription)


@router.patch(
    "/subscriptions/{subscription_id}",
    response_model=AdminSubscriptionResponse,
    summary="Update subscription details",
)
async def update_subscription(
    subscription_id: int,
    payload: AdminSubscriptionUpdate,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(require_admin),
) -> AdminSubscriptionResponse:
    stmt = select(Subscription).where(Subscription.id == subscription_id)
    result = await session.execute(stmt)
    subscription = result.scalar_one_or_none()

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found"
        )

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(subscription, key, value)

    try:
        await session.flush()
        await session.commit()
        await session.refresh(subscription)
    except Exception as exc:
        await session.rollback()
        logger.error(
            "subscription_update_failed",
            subscription_id=subscription_id,
            error=str(exc),
            admin_id=admin.id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription update failed",
        ) from exc

    logger.info(
        "subscription_updated_by_admin",
        subscription_id=subscription.id,
        admin_id=admin.id,
    )
    return AdminSubscriptionResponse.model_validate(subscription)


@router.get(
    "/subscriptions/export/{format}",
    summary="Export subscriptions to CSV or JSON",
)
async def export_subscriptions(
    format: str,
    session: AsyncSession = Depends(get_db_session),
    _admin: User = Depends(require_admin),
) -> StreamingResponse:
    if format not in ("csv", "json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid format. Use 'csv' or 'json'.",
        )

    stmt = select(Subscription).order_by(Subscription.created_at.desc())
    result = await session.execute(stmt)
    subscriptions = result.scalars().all()

    data = [
        {
            "id": sub.id,
            "user_id": sub.user_id,
            "tier": sub.tier.value,
            "status": sub.status.value,
            "quota_limit": sub.quota_limit,
            "quota_used": sub.quota_used,
            "current_period_start": sub.current_period_start.isoformat(),
            "current_period_end": sub.current_period_end.isoformat(),
            "created_at": sub.created_at.isoformat(),
        }
        for sub in subscriptions
    ]

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"subscriptions_export_{timestamp}.{format}"

    if format == "csv":
        return ExportService.export_to_csv(data, filename)
    return ExportService.export_to_json(data, filename)


@router.get(
    "/prompts",
    response_model=PaginatedResponse,
    summary="List all prompts with pagination and filters",
)
async def list_prompts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    category: PromptCategory | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
    _admin: User = Depends(require_admin),
) -> PaginatedResponse:
    stmt = select(Prompt)

    if search:
        stmt = stmt.where(
            or_(Prompt.name.ilike(f"%{search}%"), Prompt.slug.ilike(f"%{search}%"))
        )
    if category is not None:
        stmt = stmt.where(Prompt.category == category)
    if is_active is not None:
        stmt = stmt.where(Prompt.is_active == is_active)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    stmt = stmt.order_by(Prompt.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(stmt)
    prompts = result.scalars().all()

    prompt_responses = [
        AdminPromptResponse.model_validate(prompt)
        for prompt in prompts
    ]
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return PaginatedResponse(
        items=prompt_responses,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/prompts/{prompt_id}",
    response_model=AdminPromptResponse,
    summary="Get prompt details by ID",
)
async def get_prompt(
    prompt_id: int,
    session: AsyncSession = Depends(get_db_session),
    _admin: User = Depends(require_admin),
) -> AdminPromptResponse:
    stmt = select(Prompt).where(Prompt.id == prompt_id)
    result = await session.execute(stmt)
    prompt = result.scalar_one_or_none()

    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found"
        )

    return AdminPromptResponse.model_validate(prompt)


@router.post(
    "/prompts",
    response_model=AdminPromptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new prompt",
)
async def create_prompt_admin(
    payload: AdminPromptCreate,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(require_admin),
) -> AdminPromptResponse:
    prompt_data = payload.model_dump()

    prompt = Prompt(**prompt_data)
    session.add(prompt)

    try:
        await session.flush()
        await session.commit()
        await session.refresh(prompt)
    except Exception as exc:
        await session.rollback()
        logger.error("prompt_creation_failed", error=str(exc), admin_id=admin.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Prompt creation failed. "
                "Slug/version combination may already exist."
            ),
        ) from exc

    logger.info("prompt_created_by_admin", prompt_id=prompt.id, admin_id=admin.id)
    return AdminPromptResponse.model_validate(prompt)


@router.patch(
    "/prompts/{prompt_id}",
    response_model=AdminPromptResponse,
    summary="Update prompt details",
)
async def update_prompt(
    prompt_id: int,
    payload: AdminPromptUpdate,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(require_admin),
) -> AdminPromptResponse:
    stmt = select(Prompt).where(Prompt.id == prompt_id)
    result = await session.execute(stmt)
    prompt = result.scalar_one_or_none()

    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found"
        )

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(prompt, key, value)

    try:
        await session.flush()
        await session.commit()
        await session.refresh(prompt)
    except Exception as exc:
        await session.rollback()
        logger.error(
            "prompt_update_failed",
            prompt_id=prompt_id,
            error=str(exc),
            admin_id=admin.id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Prompt update failed"
        ) from exc

    logger.info("prompt_updated_by_admin", prompt_id=prompt.id, admin_id=admin.id)
    return AdminPromptResponse.model_validate(prompt)


@router.delete(
    "/prompts/{prompt_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate a prompt",
)
async def delete_prompt(
    prompt_id: int,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(require_admin),
) -> None:
    stmt = select(Prompt).where(Prompt.id == prompt_id)
    result = await session.execute(stmt)
    prompt = result.scalar_one_or_none()

    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found"
        )

    prompt.is_active = False

    try:
        await session.flush()
        await session.commit()
    except Exception as exc:
        await session.rollback()
        logger.error(
            "prompt_deactivation_failed",
            prompt_id=prompt_id,
            error=str(exc),
            admin_id=admin.id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prompt deactivation failed",
        ) from exc

    logger.info("prompt_deactivated_by_admin", prompt_id=prompt.id, admin_id=admin.id)


@router.get(
    "/prompts/export/{format}",
    summary="Export prompts to CSV or JSON",
)
async def export_prompts(
    format: str,
    session: AsyncSession = Depends(get_db_session),
    _admin: User = Depends(require_admin),
) -> StreamingResponse:
    if format not in ("csv", "json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid format. Use 'csv' or 'json'.",
        )

    stmt = select(Prompt).order_by(Prompt.created_at.desc())
    result = await session.execute(stmt)
    prompts = result.scalars().all()

    data = [
        {
            "id": prompt.id,
            "slug": prompt.slug,
            "name": prompt.name,
            "category": prompt.category.value,
            "source": prompt.source.value,
            "version": prompt.version,
            "is_active": prompt.is_active,
            "created_at": prompt.created_at.isoformat(),
        }
        for prompt in prompts
    ]

    filename = f"prompts_export_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.{format}"

    if format == "csv":
        return ExportService.export_to_csv(data, filename)
    return ExportService.export_to_json(data, filename)


@router.get(
    "/generations",
    response_model=PaginatedResponse,
    summary="List all generations with pagination and filters",
)
async def list_generations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: int | None = Query(default=None),
    prompt_id: int | None = Query(default=None),
    status: GenerationTaskStatus | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
    _admin: User = Depends(require_admin),
) -> PaginatedResponse:
    stmt = select(GenerationTask)

    if user_id is not None:
        stmt = stmt.where(GenerationTask.user_id == user_id)
    if prompt_id is not None:
        stmt = stmt.where(GenerationTask.prompt_id == prompt_id)
    if status is not None:
        stmt = stmt.where(GenerationTask.status == status)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    stmt = stmt.order_by(GenerationTask.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(stmt)
    generations = result.scalars().all()

    generation_responses = [
        AdminGenerationResponse.model_validate(gen) for gen in generations
    ]
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return PaginatedResponse(
        items=generation_responses,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/generations/{generation_id}",
    response_model=AdminGenerationResponse,
    summary="Get generation details by ID",
)
async def get_generation(
    generation_id: int,
    session: AsyncSession = Depends(get_db_session),
    _admin: User = Depends(require_admin),
) -> AdminGenerationResponse:
    stmt = select(GenerationTask).where(GenerationTask.id == generation_id)
    result = await session.execute(stmt)
    generation = result.scalar_one_or_none()

    if not generation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found"
        )

    return AdminGenerationResponse.model_validate(generation)


@router.patch(
    "/generations/{generation_id}",
    response_model=AdminGenerationResponse,
    summary="Update generation status (for moderation)",
)
async def update_generation(
    generation_id: int,
    payload: AdminGenerationUpdate,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(require_admin),
) -> AdminGenerationResponse:
    stmt = select(GenerationTask).where(GenerationTask.id == generation_id)
    result = await session.execute(stmt)
    generation = result.scalar_one_or_none()

    if not generation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found"
        )

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(generation, key, value)

    try:
        await session.flush()
        await session.commit()
        await session.refresh(generation)
    except Exception as exc:
        await session.rollback()
        logger.error(
            "generation_update_failed",
            generation_id=generation_id,
            error=str(exc),
            admin_id=admin.id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Generation update failed",
        ) from exc

    logger.info(
        "generation_updated_by_admin", generation_id=generation.id, admin_id=admin.id
    )
    return AdminGenerationResponse.model_validate(generation)


@router.post(
    "/generations/{generation_id}/moderate",
    response_model=AdminGenerationResponse,
    summary="Moderate generation result (approve/reject/flag)",
)
async def moderate_generation(
    generation_id: int,
    payload: AdminModerationAction,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(require_admin),
) -> AdminGenerationResponse:
    stmt = select(GenerationTask).where(GenerationTask.id == generation_id)
    result = await session.execute(stmt)
    generation = result.scalar_one_or_none()

    if not generation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found"
        )

    action_map = {
        "approve": GenerationTaskStatus.COMPLETED,
        "reject": GenerationTaskStatus.FAILED,
        "flag": GenerationTaskStatus.PENDING,
    }

    generation.status = action_map[payload.action]
    if payload.reason:
        generation.error = payload.reason

    try:
        await session.flush()
        await session.commit()
        await session.refresh(generation)
    except Exception as exc:
        await session.rollback()
        logger.error(
            "generation_moderation_failed",
            generation_id=generation_id,
            error=str(exc),
            admin_id=admin.id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Generation moderation failed",
        ) from exc

    logger.info(
        "generation_moderated_by_admin",
        generation_id=generation.id,
        action=payload.action,
        admin_id=admin.id,
    )
    return AdminGenerationResponse.model_validate(generation)


@router.get(
    "/generations/export/{format}",
    summary="Export generations to CSV or JSON",
)
async def export_generations(
    format: str,
    session: AsyncSession = Depends(get_db_session),
    _admin: User = Depends(require_admin),
) -> StreamingResponse:
    if format not in ("csv", "json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid format. Use 'csv' or 'json'.",
        )

    stmt = select(GenerationTask).order_by(GenerationTask.created_at.desc())
    result = await session.execute(stmt)
    generations = result.scalars().all()

    data = [
        {
            "id": gen.id,
            "user_id": gen.user_id,
            "prompt_id": gen.prompt_id,
            "status": gen.status.value,
            "source": gen.source.value,
            "result_asset_url": gen.result_asset_url or "",
            "error": gen.error or "",
            "created_at": gen.created_at.isoformat(),
        }
        for gen in generations
    ]

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"generations_export_{timestamp}.{format}"

    if format == "csv":
        return ExportService.export_to_csv(data, filename)
    return ExportService.export_to_json(data, filename)
