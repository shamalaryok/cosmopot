from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .enums import GenerationEventType, GenerationTaskStatus
from .models import GenerationTask, GenerationTaskEvent

__all__ = [
    "create_task",
    "add_event",
    "get_task_by_id",
    "update_task_status",
    "list_tasks_for_user",
    "count_tasks_for_user",
]


def _ensure_dict(payload: dict[str, Any] | None) -> dict[str, Any]:
    return dict(payload or {})


async def create_task(
    session: AsyncSession,
    *,
    user_id: int,
    prompt: str,
    parameters: dict[str, Any],
    status: GenerationTaskStatus,
    priority: int,
    subscription_tier: str,
    s3_bucket: str,
    s3_key: str,
    input_url: str | None,
    metadata: dict[str, Any] | None = None,
    task_id: UUID | None = None,
) -> GenerationTask:
    task = GenerationTask(
        id=task_id,
        user_id=user_id,
        prompt=prompt,
        parameters=_ensure_dict(parameters),
        status=status,
        priority=priority,
        subscription_tier=subscription_tier,
        s3_bucket=s3_bucket,
        s3_key=s3_key,
        input_url=input_url,
        metadata=_ensure_dict(metadata),
    )
    session.add(task)
    await session.flush()
    await session.refresh(task)
    return task


async def list_tasks_for_user(
    session: AsyncSession,
    user_id: int,
    *,
    offset: int,
    limit: int,
) -> list[GenerationTask]:
    stmt = (
        select(GenerationTask)
        .where(GenerationTask.user_id == user_id)
        .order_by(GenerationTask.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_tasks_for_user(session: AsyncSession, user_id: int) -> int:
    stmt = (
        select(func.count())
        .select_from(GenerationTask)
        .where(GenerationTask.user_id == user_id)
    )
    result = await session.execute(stmt)
    return int(result.scalar() or 0)


async def add_event(
    session: AsyncSession,
    *,
    task: GenerationTask,
    event_type: GenerationEventType,
    message: str,
    data: dict[str, Any] | None = None,
) -> GenerationTaskEvent:
    event = GenerationTaskEvent(
        task_id=task.id,
        event_type=event_type,
        message=message,
        data=_ensure_dict(data),
    )
    session.add(event)
    await session.flush()
    await session.refresh(event)
    return event


async def get_task_by_id(session: AsyncSession, task_id: UUID) -> GenerationTask | None:
    stmt = select(GenerationTask).where(GenerationTask.id == task_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_task_status(
    session: AsyncSession,
    task: GenerationTask,
    *,
    status: GenerationTaskStatus,
    error_message: str | None = None,
) -> GenerationTask:
    task.status = status
    task.error_message = error_message
    await session.flush()
    await session.refresh(task)
    return task
