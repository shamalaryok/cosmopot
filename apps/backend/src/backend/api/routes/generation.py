from __future__ import annotations

import uuid
from typing import Any, cast
from uuid import UUID

import structlog
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics.decorators import AnalyticsTracker
from backend.analytics.dependencies import get_analytics_service
from backend.analytics.service import AnalyticsService
from backend.api.dependencies.users import get_current_user
from backend.api.schemas.generation import (
    GenerationParameters,
    GenerationTaskEnvelope,
    GenerationTaskListResponse,
    GenerationTaskStatusResponse,
    PaginationMeta,
)
from backend.core.config import Settings, get_settings
from backend.db.dependencies import get_db_session
from backend.generation.broadcaster import TaskStatusBroadcaster
from backend.generation.enums import GenerationEventType, GenerationTaskStatus
from backend.generation.models import GenerationTask
from backend.generation.repository import (
    add_event,
    count_tasks_for_user,
    create_task,
    get_task_by_id,
    list_tasks_for_user,
)
from backend.generation.service import GenerationService, resolve_priority
from backend.observability.metrics import (
    GENERATION_API_REQUESTS_TOTAL,
    GENERATION_TASKS_ENQUEUED_TOTAL,
)
from user_service.enums import SubscriptionStatus
from user_service.models import Subscription, User

router = APIRouter(prefix="/api/v1", tags=["generation"])
logger = structlog.get_logger(__name__)

_ALLOWS: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
}
_MAX_IMAGE_BYTES = 8 * 1024 * 1024


def get_generation_service(
    settings: Settings = Depends(get_settings),
) -> GenerationService:
    return GenerationService(settings)


async def _get_active_subscription(
    session: AsyncSession, user_id: int
) -> Subscription | None:
    stmt = (
        select(Subscription)
        .where(
            Subscription.user_id == user_id,
            Subscription.status.in_(
                [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]
            ),
        )
        .order_by(Subscription.current_period_end.desc())
        .limit(1)
        .with_for_update()
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _parse_parameters(raw: str | None) -> GenerationParameters:
    if raw is None or not raw.strip():
        return GenerationParameters()
    try:
        return GenerationParameters.model_validate_json(raw)
    except ValidationError as exc:  # pragma: no cover - converted to HTTP error
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid parameters payload"
        ) from exc


def _normalise_prompt(prompt: str) -> str:
    cleaned = prompt.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Prompt must not be empty"
        )
    return cleaned


def _content_type_extension(upload: UploadFile) -> tuple[str, str]:
    content_type = (upload.content_type or "").lower()
    if content_type not in _ALLOWS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported image type",
        )
    return content_type, _ALLOWS[content_type]


async def _broadcast_task_update(request: Request, task: GenerationTask) -> None:
    broadcaster = cast(
        TaskStatusBroadcaster | None,
        getattr(request.app.state, "task_broadcaster", None),
    )
    if broadcaster is None:
        logger.warning("task_broadcaster_unavailable", task_id=str(task.id))
        return

    try:
        await broadcaster.publish(task)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning(
            "task_status_broadcast_failed",
            task_id=str(task.id),
            error=str(exc),
        )


@router.post(
    "/generate",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GenerationTaskEnvelope,
    summary="Submit an image generation job",
)
async def submit_generation_task(
    request: Request,
    prompt: str = Form(..., description="Text prompt guiding the generation"),
    parameters_raw: str | None = Form(
        None,
        description="Optional JSON encoded parameter overrides",
        alias="parameters",
    ),
    file: UploadFile = File(..., description="Input image seed"),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    service: GenerationService = Depends(get_generation_service),
) -> GenerationTaskEnvelope:
    prompt_value = _normalise_prompt(prompt)

    # Track generation start
    analytics_tracker = AnalyticsTracker(analytics_service, session)
    await analytics_tracker.track_generation(
        user_id=str(current_user.id),
        generation_type="image",
        status="started",
        prompt_length=len(prompt_value),
        file_size=file.size if file.size else 0,
        file_type=file.content_type,
    )

    try:
        parameters = _parse_parameters(parameters_raw)
    except HTTPException:
        GENERATION_API_REQUESTS_TOTAL.labels(outcome="invalid_parameters").inc()
        # Track generation failed
        await analytics_tracker.track_generation(
            user_id=str(current_user.id),
            generation_type="image",
            status="failed",
            error="invalid_parameters",
            prompt_length=len(prompt_value),
        )
        raise

    content = await file.read()
    if not content:
        GENERATION_API_REQUESTS_TOTAL.labels(outcome="invalid_image").inc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Image file is required"
        )
    if len(content) > _MAX_IMAGE_BYTES:
        GENERATION_API_REQUESTS_TOTAL.labels(outcome="too_large").inc()
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image exceeds size limit",
        )

    try:
        content_type, extension = _content_type_extension(file)
    except HTTPException:
        GENERATION_API_REQUESTS_TOTAL.labels(outcome="unsupported_type").inc()
        raise

    subscription = await _get_active_subscription(session, current_user.id)
    if subscription is None:
        GENERATION_API_REQUESTS_TOTAL.labels(outcome="no_subscription").inc()
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Active subscription required",
        )

    if subscription.quota_limit and subscription.quota_used >= subscription.quota_limit:
        GENERATION_API_REQUESTS_TOTAL.labels(outcome="quota_exhausted").inc()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Generation quota exhausted"
        )

    subscription.quota_used += 1

    task_id = uuid.uuid4()
    priority = resolve_priority(subscription.tier.value if subscription.tier else None)
    tier_label = subscription.tier.value if subscription.tier else "basic"

    metadata: dict[str, Any] = {
        "filename": file.filename,
        "content_type": content_type,
    }

    try:
        upload_result = await service.store_original(
            user_id=current_user.id,
            task_id=task_id,
            content=content,
            content_type=content_type,
            extension=extension,
        )

        task = await create_task(
            session,
            user_id=current_user.id,
            prompt=prompt_value,
            parameters=parameters.model_dump(),
            status=GenerationTaskStatus.QUEUED,
            priority=priority,
            subscription_tier=tier_label,
            s3_bucket=settings.s3.bucket,
            s3_key=upload_result.key,
            input_url=upload_result.url,
            metadata=metadata,
            task_id=task_id,
        )

        await add_event(
            session,
            task=task,
            event_type=GenerationEventType.CREATED,
            message="Generation task created",
            data={"priority": priority, "subscription_tier": tier_label},
        )
        await add_event(
            session,
            task=task,
            event_type=GenerationEventType.STORAGE_UPLOADED,
            message="Original asset stored",
            data={"key": upload_result.key, "bucket": settings.s3.bucket},
        )

        message_payload = {
            "task_id": str(task.id),
            "user_id": current_user.id,
            "prompt": prompt_value,
            "parameters": parameters.model_dump(),
            "input_url": upload_result.url,
            "s3_bucket": settings.s3.bucket,
            "s3_key": upload_result.key,
            "priority": priority,
            "subscription_tier": tier_label,
        }
        await service.enqueue(message_payload, priority=priority)
        await add_event(
            session,
            task=task,
            event_type=GenerationEventType.QUEUE_PUBLISHED,
            message="Task enqueued for processing",
            data=message_payload,
        )

        await session.commit()
        await session.refresh(task)
    except HTTPException:
        await session.rollback()
        raise
    except Exception as exc:  # pragma: no cover - defensive logging
        await session.rollback()
        logger.exception(
            "generation_submission_failed",
            user_id=current_user.id,
            task_id=str(task_id),
            error=str(exc),
        )
        GENERATION_API_REQUESTS_TOTAL.labels(outcome="error").inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to enqueue generation task",
        ) from exc

    await _broadcast_task_update(request, task)

    GENERATION_API_REQUESTS_TOTAL.labels(outcome="success").inc()
    GENERATION_TASKS_ENQUEUED_TOTAL.inc()
    logger.info(
        "generation_task_submitted",
        user_id=current_user.id,
        task_id=str(task.id),
        priority=priority,
        tier=tier_label,
    )
    return GenerationTaskEnvelope.model_validate(task)


@router.get(
    "/generation/tasks",
    response_model=GenerationTaskListResponse,
    summary="List generation tasks for the authenticated user",
)
async def list_generation_tasks(
    page: int = Query(1, ge=1, description="Page number for pagination"),
    page_size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> GenerationTaskListResponse:
    total = await count_tasks_for_user(session, current_user.id)
    offset = (page - 1) * page_size
    tasks = await list_tasks_for_user(
        session, current_user.id, offset=offset, limit=page_size
    )
    has_next = offset + len(tasks) < total
    items = [GenerationTaskStatusResponse.model_validate(task) for task in tasks]
    pagination = PaginationMeta(
        page=page,
        page_size=page_size,
        total=total,
        has_next=has_next,
        has_previous=page > 1,
    )
    return GenerationTaskListResponse(items=items, pagination=pagination)


@router.get(
    "/tasks/{task_id}/status",
    response_model=GenerationTaskStatusResponse,
    summary="Retrieve the latest status for a generation task",
)
async def get_generation_status(
    task_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> GenerationTaskStatusResponse:
    task = await get_task_by_id(session, task_id)
    if task is None or task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    return GenerationTaskStatusResponse.model_validate(task)
