"""Scheduled tasks for analytics processing."""

import asyncio
import datetime as dt
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any, cast

import schedule
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics.aggregation import (
    AggregatedMetrics,
    AnalyticsAggregationService,
)
from backend.analytics.service import AnalyticsService
from backend.core.config import Settings, get_settings
from backend.db.dependencies import get_db_session

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def _get_session() -> AsyncIterator[AsyncSession]:
    """Wrap the async generator as an async context manager."""
    session_gen = cast(AsyncGenerator[AsyncSession, None], get_db_session())
    try:
        session = await anext(session_gen)
        yield session
    finally:
        await session_gen.aclose()


class AnalyticsScheduler:
    """Scheduler for analytics processing tasks."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.analytics_service = AnalyticsService(settings)
        self.aggregation_service = AnalyticsAggregationService()
        self._running = False

    def start(self) -> None:
        """Start the analytics scheduler."""
        if not self.settings.analytics.enabled:
            logger.info("Analytics scheduler disabled")
            return

        logger.info("Starting analytics scheduler")

        # Schedule event processing
        schedule.every(self.settings.analytics.flush_interval_seconds).seconds.do(
            self._run_async_task, self._process_pending_events
        )

        # Schedule daily metrics calculation
        schedule.every().day.at("01:00").do(
            self._run_async_task, self._calculate_daily_metrics
        )

        # Schedule weekly metrics calculation
        schedule.every().week.do(self._run_async_task, self._calculate_weekly_metrics)

        # Schedule monthly metrics calculation (run on the first day of each month)
        schedule.every().day.at("02:00").do(
            self._run_async_task, self._calculate_monthly_metrics
        )

        # Schedule data cleanup
        schedule.every().week.do(self._run_async_task, self._cleanup_old_data)

        self._running = True

        # Run the scheduler in a separate thread
        import threading

        scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        scheduler_thread.start()

    def stop(self) -> None:
        """Stop the analytics scheduler."""
        self._running = False
        schedule.clear()
        logger.info("Analytics scheduler stopped")

    def _run_scheduler(self) -> None:
        """Run the scheduler loop."""
        while self._running:
            try:
                schedule.run_pending()
                import time

                time.sleep(1)
            except Exception as e:
                logger.error("Error in analytics scheduler loop", error=str(e))
                import time

                time.sleep(5)  # Wait before retrying

    def _run_async_task(
        self, task_func: Callable[[], Coroutine[Any, Any, None]]
    ) -> None:
        """Run an async task in a new event loop."""
        try:
            asyncio.run(task_func())
        except Exception as e:
            logger.error(
                "Error running async analytics task",
                task=task_func.__name__,
                error=str(e),
            )

    async def _process_pending_events(self) -> None:
        """Process pending analytics events."""
        try:
            async with _get_session() as session:
                result = await self.analytics_service.process_pending_events(session)
                logger.info(
                    "Processed pending analytics events",
                    processed=result["processed"],
                    failed=result["failed"],
                )
        except Exception as e:
            logger.error("Failed to process pending analytics events", error=str(e))

    async def _calculate_daily_metrics(self) -> None:
        """Calculate daily analytics metrics."""
        try:
            yesterday = dt.date.today() - dt.timedelta(days=1)

            async with _get_session() as session:
                metrics = await self.aggregation_service.calculate_daily_metrics(
                    session, yesterday
                )
                logger.info(
                    "Daily metrics calculated",
                    date=yesterday.isoformat(),
                    metrics_count=len(metrics),
                    metrics=metrics,
                )
        except Exception as e:
            logger.error("Failed to calculate daily metrics", error=str(e))

    async def _calculate_weekly_metrics(self) -> None:
        """Calculate weekly analytics metrics."""
        try:
            # Calculate for last week
            today = dt.date.today()
            last_week_start = today - dt.timedelta(days=today.weekday() + 7)

            async with _get_session() as session:
                metrics = await self.aggregation_service.calculate_weekly_metrics(
                    session, last_week_start
                )
                logger.info(
                    "Weekly metrics calculated",
                    week_start=last_week_start.isoformat(),
                    metrics_count=len(metrics),
                    metrics=metrics,
                )
        except Exception as e:
            logger.error("Failed to calculate weekly metrics", error=str(e))

    async def _calculate_monthly_metrics(self) -> None:
        """Calculate monthly analytics metrics."""
        try:
            # Calculate for last month
            today = dt.date.today()
            if today.month == 1:
                last_month_year = today.year - 1
                last_month = 12
            else:
                last_month_year = today.year
                last_month = today.month - 1

            async with _get_session() as session:
                metrics = await self.aggregation_service.calculate_monthly_metrics(
                    session,
                    last_month_year,
                    last_month,
                )
                logger.info(
                    "Monthly metrics calculated",
                    year=last_month_year,
                    month=last_month,
                    metrics_count=len(metrics),
                    metrics=metrics,
                )
        except Exception as e:
            logger.error("Failed to calculate monthly metrics", error=str(e))

    async def _cleanup_old_data(self) -> None:
        """Clean up old analytics data."""
        try:
            retention_days = self.settings.analytics.data_retention_days

            async with _get_session() as session:
                deleted_count = await self.aggregation_service.cleanup_old_data(
                    session, retention_days
                )
                logger.info(
                    "Analytics data cleanup completed",
                    deleted_events=deleted_count,
                    retention_days=retention_days,
                )
        except Exception as e:
            logger.error("Failed to cleanup old analytics data", error=str(e))


# Global scheduler instance
_scheduler: AnalyticsScheduler | None = None


def get_analytics_scheduler() -> AnalyticsScheduler:
    """Get the global analytics scheduler instance."""
    global _scheduler
    if _scheduler is None:
        settings = get_settings()
        _scheduler = AnalyticsScheduler(settings)
    return _scheduler


def start_analytics_scheduler() -> None:
    """Start the analytics scheduler."""
    scheduler = get_analytics_scheduler()
    scheduler.start()


def stop_analytics_scheduler() -> None:
    """Stop the analytics scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.stop()
        _scheduler = None


# Celery task for processing analytics events (if using Celery)
async def process_analytics_events_task() -> dict[str, int]:
    """Celery task for processing analytics events."""
    settings = get_settings()
    analytics_service = AnalyticsService(settings)

    async with _get_session() as session:
        return await analytics_service.process_pending_events(session)


# Celery task for calculating daily metrics
async def calculate_daily_metrics_task(date_str: str) -> AggregatedMetrics:
    """Celery task for calculating daily metrics."""
    date = dt.datetime.strptime(date_str, "%Y-%m-%d").date()
    aggregation_service = AnalyticsAggregationService()

    async with _get_session() as session:
        return await aggregation_service.calculate_daily_metrics(session, date)


# Celery task for calculating weekly metrics
async def calculate_weekly_metrics_task(week_start_str: str) -> AggregatedMetrics:
    """Celery task for calculating weekly metrics."""
    week_start = dt.datetime.strptime(week_start_str, "%Y-%m-%d").date()
    aggregation_service = AnalyticsAggregationService()

    async with _get_session() as session:
        return await aggregation_service.calculate_weekly_metrics(session, week_start)


# Celery task for calculating monthly metrics
async def calculate_monthly_metrics_task(year: int, month: int) -> AggregatedMetrics:
    """Celery task for calculating monthly metrics."""
    aggregation_service = AnalyticsAggregationService()

    async with _get_session() as session:
        return await aggregation_service.calculate_monthly_metrics(session, year, month)
