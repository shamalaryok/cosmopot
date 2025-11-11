"""Analytics aggregation service for calculating daily metrics."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics.enums import AnalyticsEvent
from backend.analytics.repository import (
    create_or_update_aggregated_metrics,
    delete_old_events,
    get_event_metrics,
)
from backend.auth.models import User
from backend.payments.models import Payment
from backend.referrals.models import Referral

logger = structlog.get_logger(__name__)

AggregatedMetrics = dict[str, float]
MetricValue = int | float | Decimal


def _as_metric_value(value: MetricValue) -> float:
    """Normalize numeric metric values to floats."""
    return float(value)


class AnalyticsAggregationService:
    """Service for calculating and storing aggregated analytics metrics."""

    def __init__(self) -> None:
        self.logger = structlog.get_logger(__name__)

    async def calculate_daily_metrics(
        self, session: AsyncSession, date: dt.date
    ) -> AggregatedMetrics:
        """Calculate all daily metrics for a specific date."""
        self.logger.info(
            "Starting daily metrics calculation",
            date=date.isoformat(),
        )

        metrics: AggregatedMetrics = {}

        # DAU (Daily Active Users)
        dau_value = await self._calculate_dau(session, date)
        metrics["dau"] = _as_metric_value(dau_value)

        # New User Registrations
        new_registrations_value = await self._calculate_new_registrations(
            session, date
        )
        metrics["new_registrations"] = _as_metric_value(new_registrations_value)

        # Generation Metrics
        generations_completed_value = await self._calculate_generations_completed(
            session, date
        )
        generations_failed_value = await self._calculate_generations_failed(
            session, date
        )
        metrics["generations_completed"] = _as_metric_value(
            generations_completed_value
        )
        metrics["generations_failed"] = _as_metric_value(generations_failed_value)

        # Payment Metrics
        revenue_value = await self._calculate_revenue(session, date)
        metrics["revenue"] = _as_metric_value(revenue_value)
        successful_payments_value = await self._calculate_successful_payments(
            session, date
        )
        metrics["successful_payments"] = _as_metric_value(successful_payments_value)
        failed_payments_value = await self._calculate_failed_payments(session, date)
        metrics["failed_payments"] = _as_metric_value(failed_payments_value)

        # Subscription Metrics
        new_subscriptions_value = await self._calculate_new_subscriptions(
            session, date
        )
        metrics["new_subscriptions"] = _as_metric_value(new_subscriptions_value)
        cancelled_subscriptions_value = (
            await self._calculate_cancelled_subscriptions(session, date)
        )
        metrics["cancelled_subscriptions"] = _as_metric_value(
            cancelled_subscriptions_value
        )

        # Referral Metrics
        referrals_sent_value = await self._calculate_referrals_sent(session, date)
        metrics["referrals_sent"] = _as_metric_value(referrals_sent_value)
        referrals_accepted_value = await self._calculate_referrals_accepted(
            session, date
        )
        metrics["referrals_accepted"] = _as_metric_value(referrals_accepted_value)

        # Conversion Metrics
        signup_to_payment_conversion_value = (
            await self._calculate_signup_to_payment_conversion(session, date)
        )
        metrics["signup_to_payment_conversion"] = _as_metric_value(
            signup_to_payment_conversion_value
        )

        # Store all metrics
        for metric_name, value in metrics.items():
            await create_or_update_aggregated_metrics(
                session=session,
                metric_date=date,
                metric_type=metric_name,
                period="daily",
                value=value,
                metadata={"calculated_at": dt.datetime.now(dt.UTC).isoformat()},
            )

        await session.commit()

        self.logger.info(
            "Daily metrics calculation completed",
            date=date.isoformat(),
            metrics_count=len(metrics),
        )

        return metrics

    async def calculate_weekly_metrics(
        self, session: AsyncSession, week_start: dt.date
    ) -> AggregatedMetrics:
        """Calculate weekly metrics starting from the given week start date."""
        week_end = week_start + dt.timedelta(days=6)

        self.logger.info(
            "Starting weekly metrics calculation",
            week_start=week_start.isoformat(),
            week_end=week_end.isoformat(),
        )

        # WAU (Weekly Active Users)
        wau = _as_metric_value(
            await self._calculate_active_users_in_period(session, week_start, week_end)
        )

        # Weekly Revenue
        weekly_revenue = _as_metric_value(
            await self._calculate_revenue_in_period(session, week_start, week_end)
        )

        # Weekly New Users
        weekly_new_users = _as_metric_value(
            await self._calculate_new_users_in_period(session, week_start, week_end)
        )

        metrics: AggregatedMetrics = {
            "wau": wau,
            "weekly_revenue": weekly_revenue,
            "weekly_new_users": weekly_new_users,
        }

        # Store weekly metrics
        for metric_name, value in metrics.items():
            await create_or_update_aggregated_metrics(
                session=session,
                metric_date=week_start,
                metric_type=metric_name,
                period="weekly",
                value=value,
                metadata={
                    "week_end": week_end.isoformat(),
                    "calculated_at": dt.datetime.now(dt.UTC).isoformat(),
                },
            )

        await session.commit()

        return metrics

    async def calculate_monthly_metrics(
        self, session: AsyncSession, year: int, month: int
    ) -> AggregatedMetrics:
        """Calculate monthly metrics for the given year and month."""
        month_start = dt.date(year, month, 1)
        if month == 12:
            month_end = dt.date(year + 1, 1, 1) - dt.timedelta(days=1)
        else:
            month_end = dt.date(year, month + 1, 1) - dt.timedelta(days=1)

        self.logger.info(
            "Starting monthly metrics calculation",
            year=year,
            month=month,
            month_start=month_start.isoformat(),
            month_end=month_end.isoformat(),
        )

        # MAU (Monthly Active Users)
        mau_value = await self._calculate_active_users_in_period(
            session, month_start, month_end
        )
        mau = _as_metric_value(mau_value)

        # Monthly Revenue
        monthly_revenue_value = await self._calculate_revenue_in_period(
            session, month_start, month_end
        )
        monthly_revenue = _as_metric_value(monthly_revenue_value)

        # Monthly New Users
        monthly_new_users_value = await self._calculate_new_users_in_period(
            session, month_start, month_end
        )
        monthly_new_users = _as_metric_value(monthly_new_users_value)

        # Churn Rate (simplified - users who haven't been active in 30 days)
        churn_rate_value = await self._calculate_churn_rate(session, month_end)
        churn_rate = _as_metric_value(churn_rate_value)

        # LTV/CAC ratio (simplified calculation)
        ltv_cac_ratio_value = await self._calculate_ltv_cac_ratio(
            session, month_end
        )
        ltv_cac_ratio = _as_metric_value(ltv_cac_ratio_value)

        metrics: AggregatedMetrics = {
            "mau": mau,
            "monthly_revenue": monthly_revenue,
            "monthly_new_users": monthly_new_users,
            "churn_rate": churn_rate,
            "ltv_cac_ratio": ltv_cac_ratio,
        }

        # Store monthly metrics
        for metric_name, value in metrics.items():
            await create_or_update_aggregated_metrics(
                session=session,
                metric_date=month_start,
                metric_type=metric_name,
                period="monthly",
                value=value,
                metadata={
                    "month_end": month_end.isoformat(),
                    "calculated_at": dt.datetime.now(dt.UTC).isoformat(),
                },
            )

        await session.commit()

        return metrics

    async def _calculate_dau(self, session: AsyncSession, date: dt.date) -> int:
        """Calculate Daily Active Users."""
        start_datetime = dt.datetime.combine(date, dt.time.min).replace(
            tzinfo=dt.UTC
        )
        end_datetime = dt.datetime.combine(date, dt.time.max).replace(tzinfo=dt.UTC)
        stmt = (
            select(func.count(func.distinct(User.id)))
            .select_from(User)
            .where(
                User.created_at >= start_datetime,
                User.created_at <= end_datetime,
            )
        )

        result = await session.execute(stmt)
        count_raw = result.scalar_one()
        count: int = int(count_raw)
        return count

    async def _calculate_new_registrations(
        self, session: AsyncSession, date: dt.date
    ) -> int:
        """Calculate new user registrations for the date."""
        start_datetime = dt.datetime.combine(
            date, dt.time.min
        ).replace(tzinfo=dt.UTC)
        end_datetime = dt.datetime.combine(
            date, dt.time.max
        ).replace(tzinfo=dt.UTC)

        stmt = (
            select(func.count(User.id))
            .where(
                User.created_at >= start_datetime,
                User.created_at <= end_datetime,
            )
        )

        result = await session.execute(stmt)
        count_raw = result.scalar_one()
        count: int = int(count_raw)
        return count

    async def _calculate_generations_completed(
        self, session: AsyncSession, date: dt.date
    ) -> int:
        """Calculate completed generations for the date."""
        metrics = await get_event_metrics(
            session=session,
            event_type=AnalyticsEvent.GENERATION_COMPLETED,
            start_date=date,
            end_date=date,
        )
        return metrics["total_events"]

    async def _calculate_generations_failed(
        self, session: AsyncSession, date: dt.date
    ) -> int:
        """Calculate failed generations for the date."""
        metrics = await get_event_metrics(
            session=session,
            event_type=AnalyticsEvent.GENERATION_FAILED,
            start_date=date,
            end_date=date,
        )
        return metrics["total_events"]

    async def _calculate_revenue(self, session: AsyncSession, date: dt.date) -> Decimal:
        """Calculate total revenue for the date."""
        start_datetime = dt.datetime.combine(
            date, dt.time.min
        ).replace(tzinfo=dt.UTC)
        end_datetime = dt.datetime.combine(
            date, dt.time.max
        ).replace(tzinfo=dt.UTC)
        
        stmt = (
            select(func.sum(Payment.amount))
            .where(
                Payment.created_at >= start_datetime,
                Payment.created_at <= end_datetime,
                Payment.status == "succeeded",  # Assuming status field exists
            )
        )

        result = await session.execute(stmt)
        raw_amount = result.scalar()
        if raw_amount is None:
            return Decimal("0")

        amount: Decimal = (
            raw_amount if isinstance(raw_amount, Decimal) else Decimal(raw_amount)
        )
        return amount

    async def _calculate_successful_payments(
        self, session: AsyncSession, date: dt.date
    ) -> int:
        """Calculate successful payments for the date."""
        start_datetime = dt.datetime.combine(
            date, dt.time.min
        ).replace(tzinfo=dt.UTC)
        end_datetime = dt.datetime.combine(
            date, dt.time.max
        ).replace(tzinfo=dt.UTC)

        stmt = (
            select(func.count(Payment.id))
            .where(
                Payment.created_at >= start_datetime,
                Payment.created_at <= end_datetime,
                Payment.status == "succeeded",
            )
        )

        result = await session.execute(stmt)
        count_raw = result.scalar_one()
        count: int = int(count_raw)
        return count

    async def _calculate_failed_payments(
        self, session: AsyncSession, date: dt.date
    ) -> int:
        """Calculate failed payments for the date."""
        start_datetime = dt.datetime.combine(
            date, dt.time.min
        ).replace(tzinfo=dt.UTC)
        end_datetime = dt.datetime.combine(
            date, dt.time.max
        ).replace(tzinfo=dt.UTC)

        stmt = (
            select(func.count(Payment.id))
            .where(
                Payment.created_at >= start_datetime,
                Payment.created_at <= end_datetime,
                Payment.status == "failed",
            )
        )

        result = await session.execute(stmt)
        count_raw = result.scalar_one()
        count: int = int(count_raw)
        return count

    async def _calculate_new_subscriptions(
        self, session: AsyncSession, date: dt.date
    ) -> int:
        """Calculate new subscriptions for the date."""
        metrics = await get_event_metrics(
            session=session,
            event_type=AnalyticsEvent.SUBSCRIPTION_CREATED,
            start_date=date,
            end_date=date,
        )
        return metrics["total_events"]

    async def _calculate_cancelled_subscriptions(
        self, session: AsyncSession, date: dt.date
    ) -> int:
        """Calculate cancelled subscriptions for the date."""
        metrics = await get_event_metrics(
            session=session,
            event_type=AnalyticsEvent.SUBSCRIPTION_CANCELLED,
            start_date=date,
            end_date=date,
        )
        return metrics["total_events"]

    async def _calculate_referrals_sent(
        self, session: AsyncSession, date: dt.date
    ) -> int:
        """Calculate referrals sent for the date."""
        start_datetime = dt.datetime.combine(
            date, dt.time.min
        ).replace(tzinfo=dt.UTC)
        end_datetime = dt.datetime.combine(
            date, dt.time.max
        ).replace(tzinfo=dt.UTC)

        stmt = (
            select(func.count(Referral.id))
            .where(
                Referral.created_at >= start_datetime,
                Referral.created_at <= end_datetime,
            )
        )

        result = await session.execute(stmt)
        count_raw = result.scalar_one()
        count: int = int(count_raw)
        return count

    async def _calculate_referrals_accepted(
        self, session: AsyncSession, date: dt.date
    ) -> int:
        """Calculate referrals accepted for the date."""
        metrics = await get_event_metrics(
            session=session,
            event_type=AnalyticsEvent.REFERRAL_ACCEPTED,
            start_date=date,
            end_date=date,
        )
        return metrics["total_events"]

    async def _calculate_signup_to_payment_conversion(
        self, session: AsyncSession, date: dt.date
    ) -> float:
        """Calculate signup to payment conversion rate for the date."""
        new_registrations = await self._calculate_new_registrations(session, date)
        successful_payments = await self._calculate_successful_payments(session, date)
        
        if new_registrations == 0:
            return 0.0
        
        return round((successful_payments / new_registrations) * 100, 2)

    async def _calculate_active_users_in_period(
        self, session: AsyncSession, start_date: dt.date, end_date: dt.date
    ) -> int:
        """Calculate active users in a period."""
        # This is a simplified calculation
        start_datetime = dt.datetime.combine(
            start_date, dt.time.min
        ).replace(tzinfo=dt.UTC)
        end_datetime = dt.datetime.combine(
            end_date, dt.time.max
        ).replace(tzinfo=dt.UTC)
        
        stmt = (
            select(func.count(func.distinct(User.id)))
            .where(
                User.created_at >= start_datetime,
                User.created_at <= end_datetime,
            )
        )

        result = await session.execute(stmt)
        count_raw = result.scalar_one()
        count: int = int(count_raw)
        return count

    async def _calculate_revenue_in_period(
        self, session: AsyncSession, start_date: dt.date, end_date: dt.date
    ) -> Decimal:
        """Calculate total revenue in a period."""
        start_datetime = dt.datetime.combine(
            start_date, dt.time.min
        ).replace(tzinfo=dt.UTC)
        end_datetime = dt.datetime.combine(
            end_date, dt.time.max
        ).replace(tzinfo=dt.UTC)
        
        stmt = (
            select(func.sum(Payment.amount))
            .where(
                Payment.created_at >= start_datetime,
                Payment.created_at <= end_datetime,
                Payment.status == "succeeded",
            )
        )

        result = await session.execute(stmt)
        raw_amount = result.scalar()
        if raw_amount is None:
            return Decimal("0")

        amount: Decimal = (
            raw_amount if isinstance(raw_amount, Decimal) else Decimal(raw_amount)
        )
        return amount

    async def _calculate_new_users_in_period(
        self, session: AsyncSession, start_date: dt.date, end_date: dt.date
    ) -> int:
        """Calculate new users in a period."""
        start_datetime = dt.datetime.combine(
            start_date, dt.time.min
        ).replace(tzinfo=dt.UTC)
        end_datetime = dt.datetime.combine(
            end_date, dt.time.max
        ).replace(tzinfo=dt.UTC)
        
        stmt = (
            select(func.count(User.id))
            .where(
                User.created_at >= start_datetime,
                User.created_at <= end_datetime,
            )
        )

        result = await session.execute(stmt)
        count_raw = result.scalar_one()
        count: int = int(count_raw)
        return count

    async def _calculate_churn_rate(
        self, session: AsyncSession, as_of_date: dt.date
    ) -> float:
        """Calculate simplified churn rate."""
        # This is a very simplified churn calculation
        # In practice, you'd want to track last activity dates per user
        thirty_days_ago = as_of_date - dt.timedelta(days=30)
        
        # Count users created more than 30 days ago
        stmt_old_users = (
            select(func.count(User.id))
            .where(User.created_at < thirty_days_ago)
        )
        
        # Count users with activity in the last 30 days
        stmt_active_users = (
            select(func.count(func.distinct(User.id)))
            .where(User.created_at >= thirty_days_ago)
        )
        
        old_users_result = await session.execute(stmt_old_users)
        active_users_result = await session.execute(stmt_active_users)

        old_users_raw = old_users_result.scalar_one()
        active_users_raw = active_users_result.scalar_one()
        old_users: int = int(old_users_raw)
        active_users: int = int(active_users_raw)
        
        if old_users == 0:
            return 0.0
        
        # Simplified churn: users who haven't been active
        churned_users = max(0, old_users - active_users)
        return round((churned_users / old_users) * 100, 2)

    async def _calculate_ltv_cac_ratio(
        self, session: AsyncSession, as_of_date: dt.date
    ) -> float:
        """Calculate simplified LTV/CAC ratio."""
        # This is a very simplified calculation
        # LTV: Average revenue per user over their lifetime
        # CAC: Customer acquisition cost
        
        # For simplicity, we'll use monthly revenue / new users as a proxy
        month_start = as_of_date.replace(day=1)
        monthly_revenue = await self._calculate_revenue_in_period(
            session, month_start, as_of_date
        )
        monthly_new_users = await self._calculate_new_users_in_period(
            session, month_start, as_of_date
        )
        
        if monthly_new_users == 0:
            return 0.0
        
        # Simplified CAC (you'd want to include marketing costs in reality)
        cac = Decimal("50.0")  # Placeholder value
        
        # Simplified LTV (monthly revenue * average months * profit margin)
        avg_monthly_revenue_per_user = monthly_revenue / monthly_new_users
        ltv = (
            avg_monthly_revenue_per_user * 12 * Decimal("0.7")
        )  # 12 months * 70% margin
        
        if cac == 0:
            return 0.0
        
        return float(ltv / cac)

    async def cleanup_old_data(self, session: AsyncSession, retention_days: int) -> int:
        """Clean up old analytics data based on retention policy."""
        deleted_count = await delete_old_events(session, retention_days)
        await session.commit()
        
        self.logger.info(
            "Analytics cleanup completed",
            deleted_events=deleted_count,
            retention_days=retention_days,
        )
        
        return deleted_count