"""Tests for analytics aggregation service."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.analytics.aggregation import AnalyticsAggregationService


@pytest.fixture
def aggregation_service() -> AnalyticsAggregationService:
    """Create analytics aggregation service."""
    return AnalyticsAggregationService()


class TestAnalyticsAggregationService:
    """Test analytics aggregation functionality."""

    @pytest.mark.asyncio
    async def test_calculate_daily_metrics(
        self,
        aggregation_service: AnalyticsAggregationService,
    ) -> None:
        """Test daily metrics calculation."""
        mock_session = AsyncMock()

        with (
            patch(
                "backend.analytics.aggregation.get_event_metrics"
            ) as mock_get_metrics,
            patch(
                "backend.analytics.aggregation.create_or_update_aggregated_metrics"
            ) as mock_create,
        ):
            mock_get_metrics.side_effect = [
                {"total_events": 10, "unique_users": 8},  # GENERATION_COMPLETED
                {"total_events": 2, "unique_users": 2},  # GENERATION_FAILED
                {"total_events": 3, "unique_users": 3},  # SUBSCRIPTION_CREATED
                {"total_events": 1, "unique_users": 1},  # SUBSCRIPTION_CANCELLED
                {"total_events": 5, "unique_users": 5},  # REFERRAL_ACCEPTED
            ]

            # Mock session.execute to return result objects with scalar values
            # Each call to execute should return a synchronous result object
            mock_results = [
                MagicMock(
                    scalar_one=MagicMock(return_value=15),
                ),  # DAU
                MagicMock(
                    scalar_one=MagicMock(return_value=10),
                ),  # new_registrations
                MagicMock(
                    scalar=MagicMock(return_value=Decimal("999.99")),
                ),  # revenue
                MagicMock(
                    scalar_one=MagicMock(return_value=5),
                ),  # successful_payments
                MagicMock(
                    scalar_one=MagicMock(return_value=1),
                ),  # failed_payments
                MagicMock(
                    scalar_one=MagicMock(return_value=7),
                ),  # referrals_sent
                MagicMock(
                    scalar_one=MagicMock(return_value=10),
                ),  # new_registrations (for conversion)
                MagicMock(
                    scalar_one=MagicMock(return_value=5),
                ),  # successful_payments (for conversion)
            ]
            mock_session.execute.side_effect = mock_results

            metrics = await aggregation_service.calculate_daily_metrics(
                mock_session,
                dt.date(2024, 1, 1),
            )

        assert "dau" in metrics
        assert "new_registrations" in metrics
        assert "generations_completed" in metrics
        assert "generations_failed" in metrics
        assert "revenue" in metrics
        assert "successful_payments" in metrics
        assert "failed_payments" in metrics
        assert "new_subscriptions" in metrics
        assert "cancelled_subscriptions" in metrics
        assert "referrals_sent" in metrics
        assert "referrals_accepted" in metrics
        assert "signup_to_payment_conversion" in metrics

        assert metrics["generations_completed"] == 10
        assert metrics["generations_failed"] == 2
        assert metrics["successful_payments"] == 5
        assert metrics["failed_payments"] == 1
        assert metrics["new_subscriptions"] == 3
        assert metrics["cancelled_subscriptions"] == 1
        assert metrics["referrals_sent"] == 7
        assert metrics["referrals_accepted"] == 5

        assert mock_create.call_count == 12

    @pytest.mark.asyncio
    async def test_calculate_weekly_metrics(
        self,
        aggregation_service: AnalyticsAggregationService,
    ) -> None:
        """Test weekly metrics calculation."""
        mock_session = AsyncMock()

        with (
            patch.object(
                aggregation_service, "_calculate_active_users_in_period"
            ) as mock_active_users,
            patch.object(
                aggregation_service, "_calculate_revenue_in_period"
            ) as mock_revenue,
            patch.object(
                aggregation_service, "_calculate_new_users_in_period"
            ) as mock_new_users,
            patch(
                "backend.analytics.aggregation.create_or_update_aggregated_metrics"
            ) as mock_create,
        ):
            mock_active_users.return_value = 150
            mock_revenue.return_value = Decimal("2997.00")
            mock_new_users.return_value = 25

            metrics = await aggregation_service.calculate_weekly_metrics(
                mock_session,
                dt.date(2024, 1, 1),
            )

        assert metrics["wau"] == 150
        assert metrics["weekly_revenue"] == 2997.00
        assert metrics["weekly_new_users"] == 25
        assert mock_create.call_count == 3

    @pytest.mark.asyncio
    async def test_calculate_monthly_metrics(
        self,
        aggregation_service: AnalyticsAggregationService,
    ) -> None:
        """Test monthly metrics calculation."""
        mock_session = AsyncMock()

        with (
            patch.object(
                aggregation_service, "_calculate_active_users_in_period"
            ) as mock_active_users,
            patch.object(
                aggregation_service, "_calculate_revenue_in_period"
            ) as mock_revenue,
            patch.object(
                aggregation_service, "_calculate_new_users_in_period"
            ) as mock_new_users,
            patch.object(aggregation_service, "_calculate_churn_rate") as mock_churn,
            patch.object(
                aggregation_service, "_calculate_ltv_cac_ratio"
            ) as mock_ltv_cac,
            patch(
                "backend.analytics.aggregation.create_or_update_aggregated_metrics"
            ) as mock_create,
        ):
            mock_active_users.return_value = 500
            mock_revenue.return_value = Decimal("15000.00")
            mock_new_users.return_value = 100
            mock_churn.return_value = 5.5
            mock_ltv_cac.return_value = 3.2

            metrics = await aggregation_service.calculate_monthly_metrics(
                mock_session,
                year=2024,
                month=1,
            )

        assert metrics["mau"] == 500
        assert metrics["monthly_revenue"] == 15000.00
        assert metrics["monthly_new_users"] == 100
        assert metrics["churn_rate"] == 5.5
        assert metrics["ltv_cac_ratio"] == 3.2
        assert mock_create.call_count == 5

    @pytest.mark.asyncio
    async def test_signup_to_payment_conversion(
        self,
        aggregation_service: AnalyticsAggregationService,
    ) -> None:
        """Test signup to payment conversion calculation."""
        mock_session = AsyncMock()

        with (
            patch.object(
                aggregation_service, "_calculate_new_registrations"
            ) as mock_registrations,
            patch.object(
                aggregation_service, "_calculate_successful_payments"
            ) as mock_payments,
        ):
            calculate_conversion = (
                aggregation_service._calculate_signup_to_payment_conversion
            )

            mock_registrations.return_value = 100
            mock_payments.return_value = 25
            conversion_rate = await calculate_conversion(
                mock_session,
                dt.date(2024, 1, 1),
            )

            assert conversion_rate == 25.0

            mock_registrations.return_value = 0
            mock_payments.return_value = 0
            conversion_rate = await calculate_conversion(
                mock_session,
                dt.date(2024, 1, 1),
            )

        assert conversion_rate == 0.0

    @pytest.mark.asyncio
    async def test_churn_rate_calculation(
        self,
        aggregation_service: AnalyticsAggregationService,
    ) -> None:
        """Test churn rate calculation."""
        mock_session = AsyncMock()

        old_users_result = MagicMock()
        old_users_result.scalar_one.return_value = 100
        active_users_result = MagicMock()
        active_users_result.scalar_one.return_value = 80
        mock_session.execute = AsyncMock(
            side_effect=[old_users_result, active_users_result]
        )

        churn_rate = await aggregation_service._calculate_churn_rate(
            mock_session,
            dt.date(2024, 1, 31),
        )

        assert churn_rate == 20.0

        zero_old_users_result = MagicMock()
        zero_old_users_result.scalar_one.return_value = 0
        zero_active_users_result = MagicMock()
        zero_active_users_result.scalar_one.return_value = 0
        mock_session.execute = AsyncMock(
            side_effect=[zero_old_users_result, zero_active_users_result]
        )

        churn_rate = await aggregation_service._calculate_churn_rate(
            mock_session,
            dt.date(2024, 1, 31),
        )

        assert churn_rate == 0.0

    @pytest.mark.asyncio
    async def test_ltv_cac_ratio_calculation(
        self,
        aggregation_service: AnalyticsAggregationService,
    ) -> None:
        """Test LTV/CAC ratio calculation."""
        mock_session = AsyncMock()

        with (
            patch.object(
                aggregation_service,
                "_calculate_revenue_in_period",
            ) as mock_revenue,
            patch.object(
                aggregation_service,
                "_calculate_new_users_in_period",
            ) as mock_new_users,
        ):
            mock_revenue.return_value = Decimal("5000.00")
            mock_new_users.return_value = 50
            ratio = await aggregation_service._calculate_ltv_cac_ratio(
                mock_session,
                dt.date(2024, 1, 31),
            )

            assert abs(ratio - 16.8) < 0.01

            mock_revenue.return_value = Decimal("0.00")
            mock_new_users.return_value = 0
            ratio = await aggregation_service._calculate_ltv_cac_ratio(
                mock_session,
                dt.date(2024, 1, 31),
            )

        assert ratio == 0.0

    @pytest.mark.asyncio
    async def test_cleanup_old_data(
        self,
        aggregation_service: AnalyticsAggregationService,
    ) -> None:
        """Test cleanup of old analytics data."""
        mock_session = AsyncMock()

        with patch("backend.analytics.aggregation.delete_old_events") as mock_delete:
            mock_delete.return_value = 1000
            deleted_count = await aggregation_service.cleanup_old_data(
                mock_session,
                365,
            )

        assert deleted_count == 1000
        mock_delete.assert_called_once_with(mock_session, 365)
