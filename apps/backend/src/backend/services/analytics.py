from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from user_service.enums import GenerationTaskStatus, SubscriptionStatus
from user_service.models import GenerationTask, Payment, Subscription, User

__all__ = ["AnalyticsService"]


class AnalyticsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_dashboard_metrics(self) -> dict:
        now = datetime.now(UTC)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=7)
        month_start = today_start.replace(day=1)

        total_users = await self._get_total_users()
        active_users = await self._get_active_users()
        total_subscriptions = await self._get_total_subscriptions()
        active_subscriptions = await self._get_active_subscriptions()
        total_generations = await self._get_total_generations()
        generations_today = await self._get_generations_since(today_start)
        generations_this_week = await self._get_generations_since(week_start)
        generations_this_month = await self._get_generations_since(month_start)
        failed_generations = await self._get_failed_generations()
        revenue_total = await self._get_total_revenue()
        revenue_this_month = await self._get_revenue_since(month_start)

        return {
            "total_users": total_users,
            "active_users": active_users,
            "total_subscriptions": total_subscriptions,
            "active_subscriptions": active_subscriptions,
            "total_generations": total_generations,
            "generations_today": generations_today,
            "generations_this_week": generations_this_week,
            "generations_this_month": generations_this_month,
            "failed_generations": failed_generations,
            "revenue_total": revenue_total,
            "revenue_this_month": revenue_this_month,
        }

    async def _get_total_users(self) -> int:
        stmt = select(func.count()).select_from(User).where(User.deleted_at.is_(None))
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def _get_active_users(self) -> int:
        stmt = (
            select(func.count())
            .select_from(User)
            .where(User.deleted_at.is_(None))
            .where(User.is_active.is_(True))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def _get_total_subscriptions(self) -> int:
        stmt = select(func.count()).select_from(Subscription)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def _get_active_subscriptions(self) -> int:
        stmt = (
            select(func.count())
            .select_from(Subscription)
            .where(
                Subscription.status.in_(
                    [
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.TRIALING,
                    ]
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def _get_total_generations(self) -> int:
        stmt = select(func.count()).select_from(GenerationTask)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def _get_generations_since(self, since: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(GenerationTask)
            .where(GenerationTask.created_at >= since)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def _get_failed_generations(self) -> int:
        stmt = (
            select(func.count())
            .select_from(GenerationTask)
            .where(GenerationTask.status == GenerationTaskStatus.FAILED)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def _get_total_revenue(self) -> Decimal:
        stmt = select(func.coalesce(func.sum(Payment.amount), 0)).select_from(Payment)
        result = await self.session.execute(stmt)
        return Decimal(str(result.scalar_one()))

    async def _get_revenue_since(self, since: datetime) -> Decimal:
        stmt = (
            select(func.coalesce(func.sum(Payment.amount), 0))
            .select_from(Payment)
            .where(Payment.created_at >= since)
        )
        result = await self.session.execute(stmt)
        return Decimal(str(result.scalar_one()))
