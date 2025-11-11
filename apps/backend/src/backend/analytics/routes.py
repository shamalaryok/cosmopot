"""Analytics API routes."""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics.aggregation import AnalyticsAggregationService
from backend.analytics.dependencies import (
    get_analytics_aggregation_service,
    get_analytics_service,
)
from backend.analytics.enums import AnalyticsEvent
from backend.analytics.repository import (
    get_aggregated_metrics,
)
from backend.analytics.schemas import (
    AggregatedMetricsResponse,
    AnalyticsConfigResponse,
    AnalyticsDashboardResponse,
    AnalyticsEventCreate,
    AnalyticsEventListResponse,
    AnalyticsEventResponse,
    AnalyticsMetricsResponse,
)
from backend.analytics.service import AnalyticsService
from backend.api.dependencies.users import get_current_user
from backend.auth.dependencies import get_rate_limiter
from backend.auth.rate_limiter import RateLimiter
from backend.core.config import Settings, get_settings
from backend.db.dependencies import get_db_session
from backend.db.models import PaginationParams, paginate_query
from user_service.models import User

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.post(
    "/events",
    response_model=AnalyticsEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Track a custom analytics event",
)
async def track_event(
    event_data: AnalyticsEventCreate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsEventResponse:
    """Track a custom analytics event."""
    await rate_limiter.check("analytics:track_event", str(current_user.id))

    try:
        # Convert string event type to enum
        try:
            event_type = AnalyticsEvent(event_data.event_type)
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid event type: {event_data.event_type}",
            ) from exc

        # Convert string provider to enum
        from backend.analytics.enums import AnalyticsProvider
        try:
            provider = AnalyticsProvider(event_data.provider)
        except ValueError:
            provider = AnalyticsProvider.BOTH

        analytics_event = await analytics_service.track_event(
            session=session,
            event_type=event_type,
            event_data=event_data.event_data,
            user_id=event_data.user_id or str(current_user.id),
            user_properties=event_data.user_properties,
            provider=provider,
            session_id=event_data.session_id,
            ip_address=event_data.ip_address,
            user_agent=event_data.user_agent,
        )

        await session.commit()
        await session.refresh(analytics_event)

        return AnalyticsEventResponse.model_validate(analytics_event)

    except Exception as e:
        await session.rollback()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to track event: {str(e)}",
        ) from e


@router.get(
    "/events",
    response_model=AnalyticsEventListResponse,
    summary="List analytics events",
)
async def list_events(
    pagination: PaginationParams = Depends(),
    event_type: str | None = Query(None, description="Filter by event type"),
    user_id: str | None = Query(None, description="Filter by user ID"),
    start_date: dt.date | None = Query(None, description="Filter by start date"),
    end_date: dt.date | None = Query(None, description="Filter by end date"),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
) -> AnalyticsEventListResponse:
    """List analytics events with filtering and pagination."""
    await rate_limiter.check("analytics:list_events", str(current_user.id))

    from sqlalchemy import select

    from backend.analytics.models import AnalyticsEventRecord

    stmt = select(AnalyticsEventRecord)

    if event_type:
        try:
            event_type_enum = AnalyticsEvent(event_type)
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid event type: {event_type}",
            ) from exc
        stmt = stmt.where(AnalyticsEventRecord.event_type == event_type_enum)

    if user_id:
        try:
            user_uuid = uuid.UUID(user_id)
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid user ID: {user_id}",
            ) from exc
        stmt = stmt.where(AnalyticsEventRecord.user_id == user_uuid)

    if start_date:
        start_dt = dt.datetime.combine(start_date, dt.time.min).replace(tzinfo=dt.UTC)
        stmt = stmt.where(AnalyticsEventRecord.created_at >= start_dt)

    if end_date:
        end_dt = dt.datetime.combine(end_date, dt.time.max).replace(tzinfo=dt.UTC)
        stmt = stmt.where(AnalyticsEventRecord.created_at <= end_dt)

    stmt = stmt.order_by(AnalyticsEventRecord.created_at.desc())

    # Paginate
    result = await paginate_query(session, stmt, pagination)
    events, total = result

    return AnalyticsEventListResponse(
        events=[AnalyticsEventResponse.model_validate(event) for event in events],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=(total + pagination.page_size - 1) // pagination.page_size,
    )


@router.get(
    "/metrics/dashboard",
    response_model=AnalyticsDashboardResponse,
    summary="Get analytics dashboard metrics",
)
async def get_dashboard_metrics(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    aggregation_service: AnalyticsAggregationService = Depends(
        get_analytics_aggregation_service
    ),
) -> AnalyticsDashboardResponse:
    """Get analytics dashboard metrics."""
    await rate_limiter.check("analytics:dashboard", str(current_user.id))

    today = dt.date.today()
    thirty_days_ago = today - dt.timedelta(days=30)

    try:
        # Get recent metrics
        from backend.analytics.repository import get_aggregated_metrics
        
        # Daily metrics for today
        daily_metrics = await get_aggregated_metrics(
            session=session,
            period="daily",
            start_date=today,
            end_date=today,
        )
        
        # Monthly metrics
        monthly_metrics = await get_aggregated_metrics(
            session=session,
            period="monthly",
            start_date=thirty_days_ago,
            end_date=today,
        )

        # Extract values or defaults
        def get_metric_value(metrics_list: list, metric_type: str, default=0) -> float:
            for metric in metrics_list:
                if metric.metric_type == metric_type:
                    return metric.value
            return default

        # Calculate today's metrics
        daily_dau = get_metric_value(daily_metrics, "dau")
        daily_new_registrations = get_metric_value(
            daily_metrics, "new_registrations"
        )
        daily_revenue = get_metric_value(daily_metrics, "revenue")
        daily_conversion_rate = get_metric_value(
            daily_metrics, "signup_to_payment_conversion"
        )

        # Get monthly metrics
        monthly_mau = get_metric_value(monthly_metrics, "mau")
        monthly_churn_rate = get_metric_value(monthly_metrics, "churn_rate")
        monthly_ltv_cac_ratio = get_metric_value(
            monthly_metrics, "ltv_cac_ratio"
        )

        return AnalyticsDashboardResponse(
            daily_active_users=int(daily_dau),
            monthly_active_users=int(monthly_mau),
            new_registrations_today=int(daily_new_registrations),
            revenue_today=daily_revenue,
            conversion_rate=daily_conversion_rate,
            churn_rate=monthly_churn_rate,
            ltv_cac_ratio=monthly_ltv_cac_ratio,
        )

    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get dashboard metrics: {str(e)}",
        ) from e


@router.get(
    "/metrics/aggregated",
    response_model=list[AggregatedMetricsResponse],
    summary="Get aggregated analytics metrics",
)
async def get_aggregated_metrics_endpoint(
    metric_type: str | None = Query(None, description="Filter by metric type"),
    period: str | None = Query(
        None, description="Filter by period (daily, weekly, monthly)"
    ),
    start_date: dt.date | None = Query(
        None, description="Filter by start date"
    ),
    end_date: dt.date | None = Query(None, description="Filter by end date"),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
) -> list[AggregatedMetricsResponse]:
    """Get aggregated analytics metrics."""
    await rate_limiter.check("analytics:aggregated_metrics", str(current_user.id))

    try:
        metrics = await get_aggregated_metrics(
            session=session,
            metric_type=metric_type,
            period=period,
            start_date=start_date,
            end_date=end_date,
        )

        return [AggregatedMetricsResponse.model_validate(metric) for metric in metrics]

    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get aggregated metrics: {str(e)}",
        ) from e


@router.post(
    "/metrics/calculate",
    response_model=AnalyticsMetricsResponse,
    summary="Calculate analytics metrics for a specific date range",
)
async def calculate_metrics(
    start_date: dt.date = Query(..., description="Start date for calculation"),
    end_date: dt.date = Query(..., description="End date for calculation"),
    period: str = Query(
        "daily", description="Period type (daily, weekly, monthly)"
    ),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    aggregation_service: AnalyticsAggregationService = Depends(
        get_analytics_aggregation_service
    ),
) -> AnalyticsMetricsResponse:
    """Calculate analytics metrics for a specific date range."""
    await rate_limiter.check("analytics:calculate_metrics", str(current_user.id))

    try:
        if period not in ["daily", "weekly", "monthly"]:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Period must be one of: daily, weekly, monthly",
            )

        all_metrics = {}
        
        if period == "daily":
            current_date = start_date
            while current_date <= end_date:
                daily_metrics = await aggregation_service.calculate_daily_metrics(
                    session, current_date
                )
                all_metrics[current_date.isoformat()] = daily_metrics
                current_date += dt.timedelta(days=1)

        elif period == "weekly":
            # Calculate for each week in the range
            current_date = start_date
            while current_date <= end_date:
                # Find start of week (Monday)
                week_start = current_date - dt.timedelta(days=current_date.weekday())
                if week_start < start_date:
                    week_start = start_date

                week_end = week_start + dt.timedelta(days=6)
                if week_end > end_date:
                    week_end = end_date

                weekly_metrics = await aggregation_service.calculate_weekly_metrics(
                    session, week_start
                )
                period_key = f"{week_start.isoformat()}_to_{week_end.isoformat()}"
                all_metrics[period_key] = weekly_metrics

                current_date = week_end + dt.timedelta(days=1)

        elif period == "monthly":
            # Calculate for each month in the range
            current_date = start_date
            while current_date <= end_date:
                monthly_metrics = (
                    await aggregation_service.calculate_monthly_metrics(
                        session, current_date.year, current_date.month
                    )
                )
                monthly_key = f"{current_date.year}-{current_date.month:02d}"
                all_metrics[monthly_key] = monthly_metrics

                # Move to next month
                if current_date.month == 12:
                    current_date = current_date.replace(
                        year=current_date.year + 1, month=1
                    )
                else:
                    current_date = current_date.replace(
                        month=current_date.month + 1
                    )

        return AnalyticsMetricsResponse(
            metrics=all_metrics,
            period=period,
            start_date=start_date,
            end_date=end_date,
        )

    except Exception as e:
        await session.rollback()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate metrics: {str(e)}",
        ) from e


@router.get(
    "/config",
    response_model=AnalyticsConfigResponse,
    summary="Get analytics configuration",
)
async def get_analytics_config(
    current_user: User = Depends(get_current_user),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    settings: Settings = Depends(get_settings),
) -> AnalyticsConfigResponse:
    """Get analytics configuration."""
    await rate_limiter.check("analytics:config", str(current_user.id))

    return AnalyticsConfigResponse(
        enabled=settings.analytics.enabled,
        amplitude_configured=bool(settings.analytics.amplitude_api_key),
        mixpanel_configured=bool(settings.analytics.mixpanel_token),
        pii_tracking_enabled=settings.analytics.enable_pii_tracking,
        sandbox_mode=settings.analytics.sandbox_mode,
        batch_size=settings.analytics.batch_size,
        flush_interval_seconds=settings.analytics.flush_interval_seconds,
    )


@router.post(
    "/process-events",
    summary="Process pending analytics events (admin only)",
)
async def process_pending_events(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> dict[str, int]:
    """Process pending analytics events (admin only)."""
    await rate_limiter.check("analytics:process_events", str(current_user.id))

    # Check if user is admin
    if current_user.role.value != "admin":  # Assuming role enum
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    try:
        result = await analytics_service.process_pending_events(session)
        return result

    except Exception as e:
        await session.rollback()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process events: {str(e)}",
        ) from e