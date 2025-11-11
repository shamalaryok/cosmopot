"""Analytics repository for database operations."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.analytics.enums import AnalyticsEvent, AnalyticsProvider
from backend.analytics.models import AggregatedMetrics, AnalyticsEventRecord

EventPayload = dict[str, Any]
UserProperties = dict[str, Any]
MetricMetadata = dict[str, Any]


class EventMetrics(TypedDict):
    total_events: int
    unique_users: int
    event_type: str
    start_date: str
    end_date: str


def _coerce_user_id(user_id: str | None) -> uuid.UUID | None:
    if user_id is None:
        return None
    return uuid.UUID(user_id)


def _date_bounds(
    start_date: dt.date, end_date: dt.date
) -> tuple[dt.datetime, dt.datetime]:
    start = dt.datetime.combine(start_date, dt.time.min).replace(tzinfo=dt.UTC)
    end = dt.datetime.combine(end_date, dt.time.max).replace(tzinfo=dt.UTC)
    return start, end


async def create_analytics_event(
    session: AsyncSession,
    user_id: str | None,
    event_type: AnalyticsEvent,
    provider: AnalyticsProvider,
    event_data: EventPayload,
    user_properties: UserProperties | None = None,
    session_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AnalyticsEventRecord:
    """Create a new analytics event record."""

    analytics_event = AnalyticsEventRecord(
        user_id=_coerce_user_id(user_id),
        event_type=event_type,
        provider=provider,
        event_data=event_data,
        user_properties=user_properties,
        session_id=session_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    session.add(analytics_event)
    await session.flush()
    await session.refresh(analytics_event)

    return analytics_event


async def get_pending_events(
    session: AsyncSession,
    batch_size: int = 100,
    max_retries: int = 3,
) -> list[AnalyticsEventRecord]:
    """Get pending analytics events for processing."""
    stmt = (
        select(AnalyticsEventRecord)
        .where(
            AnalyticsEventRecord.is_successful.is_(False),
            AnalyticsEventRecord.retry_count < max_retries,
        )
        .order_by(AnalyticsEventRecord.created_at)
        .limit(batch_size)
        .options(selectinload(AnalyticsEventRecord.user))
    )

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def mark_event_processed(
    session: AsyncSession,
    event_id: uuid.UUID,
    provider_response: dict[str, object] | None = None,
) -> None:
    """Mark an analytics event as successfully processed."""
    stmt = select(AnalyticsEventRecord).where(AnalyticsEventRecord.id == event_id)

    result = await session.execute(stmt)
    event = result.scalar_one_or_none()

    if event is not None:
        event.is_successful = True
        event.processed_at = dt.datetime.now(dt.UTC)
        event.provider_response = provider_response or {}
        await session.flush()


async def mark_event_failed(
    session: AsyncSession,
    event_id: uuid.UUID,
    error_message: str,
) -> None:
    """Mark an analytics event as failed and increment retry count."""
    stmt = select(AnalyticsEventRecord).where(AnalyticsEventRecord.id == event_id)

    result = await session.execute(stmt)
    event = result.scalar_one_or_none()

    if event is not None:
        event.retry_count += 1
        event.last_error = error_message
        await session.flush()


async def get_event_metrics(
    session: AsyncSession,
    event_type: AnalyticsEvent,
    start_date: dt.date,
    end_date: dt.date,
) -> EventMetrics:
    """Get metrics for a specific event type within a date range."""
    start_dt, end_dt = _date_bounds(start_date, end_date)

    stmt = (
        select(AnalyticsEventRecord)
        .where(
            AnalyticsEventRecord.event_type == event_type,
            AnalyticsEventRecord.created_at >= start_dt,
            AnalyticsEventRecord.created_at <= end_dt,
            AnalyticsEventRecord.is_successful.is_(True),
        )
    )

    result = await session.execute(stmt)
    events = list(result.scalars().all())

    total_events = len(events)
    unique_users = len({event.user_id for event in events if event.user_id is not None})

    return EventMetrics(
        total_events=total_events,
        unique_users=unique_users,
        event_type=event_type.value,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )


async def create_or_update_aggregated_metrics(
    session: AsyncSession,
    metric_date: dt.date,
    metric_type: str,
    period: str,
    value: float,
    metadata: MetricMetadata | None = None,
) -> AggregatedMetrics:
    """Create or update aggregated metrics."""
    stmt = (
        select(AggregatedMetrics)
        .where(
            AggregatedMetrics.metric_date == metric_date,
            AggregatedMetrics.metric_type == metric_type,
            AggregatedMetrics.period == period,
        )
    )

    result = await session.execute(stmt)
    metric = result.scalar_one_or_none()

    if metric is not None:
        metric.value = value
        metric.metric_data = metadata or {}
    else:
        metric = AggregatedMetrics(
            metric_date=metric_date,
            metric_type=metric_type,
            period=period,
            value=value,
            metric_data=metadata or {},
        )
        session.add(metric)

    await session.flush()
    await session.refresh(metric)

    return metric


async def get_aggregated_metrics(
    session: AsyncSession,
    metric_type: str | None = None,
    period: str | None = None,
    start_date: dt.date | None = None,
    end_date: dt.date | None = None,
) -> list[AggregatedMetrics]:
    """Get aggregated metrics with optional filtering."""
    stmt = select(AggregatedMetrics)

    if metric_type:
        stmt = stmt.where(AggregatedMetrics.metric_type == metric_type)

    if period:
        stmt = stmt.where(AggregatedMetrics.period == period)

    if start_date:
        stmt = stmt.where(AggregatedMetrics.metric_date >= start_date)

    if end_date:
        stmt = stmt.where(AggregatedMetrics.metric_date <= end_date)

    stmt = stmt.order_by(AggregatedMetrics.metric_date.desc())

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def delete_old_events(
    session: AsyncSession,
    retention_days: int,
) -> int:
    """Delete old analytics events based on retention policy."""
    cutoff_date = dt.datetime.now(dt.UTC) - dt.timedelta(days=retention_days)

    stmt = select(AnalyticsEventRecord).where(
        AnalyticsEventRecord.created_at < cutoff_date
    )
    result = await session.execute(stmt)
    events_to_delete = list(result.scalars().all())

    for event in events_to_delete:
        await session.delete(event)

    await session.flush()

    return len(events_to_delete)
