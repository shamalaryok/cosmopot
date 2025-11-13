"""Tests for analytics API endpoints."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from backend.analytics.enums import AnalyticsEvent
from backend.analytics.schemas import AnalyticsConfigResponse, AnalyticsEventCreate
from backend.auth.dependencies import CurrentUser
from backend.auth.enums import UserRole


class TestAnalyticsAPI:
    """Test analytics API endpoints."""

    @pytest.fixture
    def mock_analytics_service(self) -> MagicMock:
        """Provide a mocked analytics service."""
        service = MagicMock()
        service.track_event = AsyncMock()
        service.process_pending_events = AsyncMock(
            return_value={"processed": 5, "failed": 1}
        )
        return service

    @pytest.mark.asyncio()
    async def test_get_analytics_config(
        self,
        async_client: AsyncClient,
        mock_analytics_service: MagicMock,
    ) -> None:
        """Test fetching analytics configuration."""
        with patch(
            "backend.analytics.routes.get_analytics_service"
        ) as mock_get_service:
            mock_get_service.return_value = mock_analytics_service

            response = await async_client.get("/api/v1/analytics/config")

        assert response.status_code == 200
        config = AnalyticsConfigResponse.model_validate(response.json())

        assert isinstance(config.enabled, bool)
        assert isinstance(config.amplitude_configured, bool)
        assert isinstance(config.mixpanel_configured, bool)
        assert isinstance(config.pii_tracking_enabled, bool)
        assert isinstance(config.sandbox_mode, bool)
        assert isinstance(config.batch_size, int)
        assert isinstance(config.flush_interval_seconds, int)

    @pytest.mark.asyncio()
    async def test_track_event_success(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        mock_analytics_service: MagicMock,
    ) -> None:
        """Test successful event tracking."""
        from backend.analytics.dependencies import get_analytics_service
        from backend.db.dependencies import get_db_session

        # Override dependencies
        mock_session_obj = AsyncMock()
        mock_session_obj.commit = AsyncMock()
        mock_session_obj.refresh = AsyncMock()
        mock_session_obj.rollback = AsyncMock()

        async def override_get_db_session() -> AsyncIterator[AsyncMock]:
            yield mock_session_obj

        app.dependency_overrides[get_analytics_service] = lambda: mock_analytics_service
        app.dependency_overrides[get_db_session] = override_get_db_session

        try:
            with (
                patch("backend.analytics.routes.auth_get_current_user") as mock_user,
                patch("backend.analytics.routes.get_rate_limiter") as mock_rate_limiter,
            ):
                mock_user.return_value = CurrentUser(
                    id=uuid.uuid4(),
                    email="test@example.com",
                    role=UserRole.USER,
                )

                mock_rate_limiter.return_value.check = AsyncMock()

                mock_event = SimpleNamespace(
                    id=str(uuid.uuid4()),
                    user_id=str(uuid.uuid4()),
                    event_type=AnalyticsEvent.SIGNUP_COMPLETED,
                    event_data={"test": "data"},
                    user_properties={"prop": "value"},
                    provider="both",
                    created_at="2025-01-01T00:00:00Z",
                    processed_at=None,
                    is_successful=True,
                    retry_count=0,
                    last_error=None,
                    session_id=None,
                    ip_address=None,
                    user_agent=None,
                )
                mock_analytics_service.track_event.return_value = mock_event

                event_data = AnalyticsEventCreate(
                    event_type="signup_completed",
                    event_data={"test": "data"},
                    user_properties={"prop": "value"},
                )

                response = await async_client.post(
                    "/api/v1/analytics/events",
                    json=event_data.model_dump(),
                )
        finally:
            app.dependency_overrides.pop(get_analytics_service, None)
            app.dependency_overrides.pop(get_db_session, None)

        assert response.status_code == 201
        response_data = response.json()
        assert response_data["event_type"] == "signup_completed"
        assert response_data["event_data"] == {"test": "data"}
        assert response_data["user_properties"] == {"prop": "value"}

    @pytest.mark.asyncio()
    async def test_track_event_invalid_event_type(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test tracking an event with an invalid type."""
        with (
            patch("backend.analytics.routes.auth_get_current_user") as mock_user,
            patch("backend.analytics.routes.get_rate_limiter") as mock_rate_limiter,
        ):
            mock_user.return_value = CurrentUser(
                id=uuid.uuid4(),
                email="test@example.com",
                role=UserRole.USER,
            )
            mock_rate_limiter.return_value.check = AsyncMock()

            event_data = {
                "event_type": "invalid_event_type",
                "event_data": {"test": "data"},
            }

            response = await async_client.post(
                "/api/v1/analytics/events",
                json=event_data,
            )

        assert response.status_code == 400
        assert "Invalid event type" in response.json()["detail"]

    @pytest.mark.asyncio()
    async def test_list_events(self, async_client: AsyncClient) -> None:
        """Test listing analytics events."""
        with (
            patch("backend.analytics.routes.auth_get_current_user") as mock_user,
            patch("backend.analytics.routes.get_rate_limiter") as mock_rate_limiter,
        ):
            mock_user.return_value = CurrentUser(
                id=uuid.uuid4(),
                email="test@example.com",
                role=UserRole.USER,
            )
            mock_rate_limiter.return_value.check = AsyncMock()

            response = await async_client.get(
                "/api/v1/analytics/events",
                params={"page": 1, "page_size": 10},
            )

        assert response.status_code == 200
        response_data = response.json()
        expected_keys = {"events", "total", "page", "page_size", "total_pages"}
        assert expected_keys <= response_data.keys()
        assert response_data["page"] == 1
        assert response_data["page_size"] == 10

    @pytest.mark.asyncio()
    async def test_list_events_with_filters(self, async_client: AsyncClient) -> None:
        """Test listing analytics events with filters."""
        with (
            patch("backend.analytics.routes.auth_get_current_user") as mock_user,
            patch("backend.analytics.routes.get_rate_limiter") as mock_rate_limiter,
        ):
            mock_user.return_value = CurrentUser(
                id=uuid.uuid4(),
                email="test@example.com",
                role=UserRole.USER,
            )
            mock_rate_limiter.return_value.check = AsyncMock()

            response = await async_client.get(
                "/api/v1/analytics/events",
                params={
                    "event_type": "signup_completed",
                    "user_id": "test-user-id",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-31",
                },
            )

        assert response.status_code == 200
        response_data = response.json()
        assert "events" in response_data

    @pytest.mark.asyncio()
    async def test_get_dashboard_metrics(self, async_client: AsyncClient) -> None:
        """Test getting dashboard metrics."""
        with (
            patch("backend.analytics.routes.auth_get_current_user") as mock_user,
            patch("backend.analytics.routes.get_rate_limiter") as mock_rate_limiter,
            patch(
                "backend.analytics.routes.get_analytics_aggregation_service"
            ) as _mock_aggregation,
            patch("backend.analytics.routes.get_aggregated_metrics") as mock_metrics,
        ):
            mock_user.return_value = CurrentUser(
                id=uuid.uuid4(),
                email="test@example.com",
                role=UserRole.USER,
            )
            mock_rate_limiter.return_value.check = AsyncMock()

            mock_daily_metrics = [
                MagicMock(metric_type="dau", value=100),
                MagicMock(metric_type="new_registrations", value=5),
                MagicMock(metric_type="revenue", value=299.99),
                MagicMock(metric_type="signup_to_payment_conversion", value=20.0),
            ]
            mock_monthly_metrics = [
                MagicMock(metric_type="mau", value=1500),
                MagicMock(metric_type="churn_rate", value=5.5),
                MagicMock(metric_type="ltv_cac_ratio", value=3.2),
            ]
            mock_metrics.side_effect = [mock_daily_metrics, mock_monthly_metrics]

            response = await async_client.get("/api/v1/analytics/metrics/dashboard")

        assert response.status_code == 200
        dashboard_data = response.json()
        assert dashboard_data["daily_active_users"] == 100
        assert dashboard_data["monthly_active_users"] == 1500
        assert dashboard_data["new_registrations_today"] == 5
        assert dashboard_data["revenue_today"] == 299.99
        assert dashboard_data["conversion_rate"] == 20.0
        assert dashboard_data["churn_rate"] == 5.5
        assert dashboard_data["ltv_cac_ratio"] == 3.2

    @pytest.mark.asyncio()
    async def test_get_aggregated_metrics(self, async_client: AsyncClient) -> None:
        """Test getting aggregated metrics."""
        with (
            patch("backend.analytics.routes.auth_get_current_user") as mock_user,
            patch("backend.analytics.routes.get_rate_limiter") as mock_rate_limiter,
            patch("backend.analytics.routes.get_aggregated_metrics") as mock_metrics,
        ):
            mock_user.return_value = CurrentUser(
                id=uuid.uuid4(),
                email="test@example.com",
                role=UserRole.USER,
            )
            mock_rate_limiter.return_value.check = AsyncMock()

            mock_metric = MagicMock(
                metric_date="2024-01-01",
                metric_type="dau",
                period="daily",
                value=100,
                metadata={"calculated_at": "2024-01-02T00:00:00Z"},
            )
            mock_metrics.return_value = [mock_metric]

            response = await async_client.get(
                "/api/v1/analytics/metrics/aggregated",
                params={
                    "metric_type": "dau",
                    "period": "daily",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-31",
                },
            )

        assert response.status_code == 200
        metrics_data = response.json()
        assert len(metrics_data) == 1
        assert metrics_data[0]["metric_type"] == "dau"
        assert metrics_data[0]["period"] == "daily"
        assert metrics_data[0]["value"] == 100

    @pytest.mark.asyncio()
    async def test_calculate_metrics(
        self,
        async_client: AsyncClient,
        mock_analytics_service: MagicMock,
    ) -> None:
        """Test calculating metrics for a date range."""
        with (
            patch("backend.analytics.routes.auth_get_current_user") as mock_user,
            patch("backend.analytics.routes.get_rate_limiter") as mock_rate_limiter,
            patch(
                "backend.analytics.routes.get_analytics_aggregation_service"
            ) as mock_aggregation,
            patch("backend.analytics.routes.get_db_session") as mock_session,
        ):
            mock_user.return_value = CurrentUser(
                id=uuid.uuid4(),
                email="test@example.com",
                role=UserRole.USER,
            )
            mock_rate_limiter.return_value.check = AsyncMock()
            mock_session.return_value.__aenter__.return_value = AsyncMock()

            mock_service = MagicMock()
            mock_service.calculate_daily_metrics = AsyncMock(
                return_value={"dau": 100, "revenue": 299.99}
            )
            mock_aggregation.return_value = mock_service

            response = await async_client.post(
                "/api/v1/analytics/metrics/calculate",
                params={
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-03",
                    "period": "daily",
                },
            )

        assert response.status_code == 200
        metrics_data = response.json()
        assert "metrics" in metrics_data
        assert metrics_data["period"] == "daily"
        assert metrics_data["start_date"] == "2024-01-01"
        assert metrics_data["end_date"] == "2024-01-03"
        assert len(metrics_data["metrics"]) == 3

    @pytest.mark.asyncio()
    async def test_process_events_admin_only(
        self,
        async_client: AsyncClient,
        mock_analytics_service: MagicMock,
    ) -> None:
        """Test that processing events requires admin access."""
        with (
            patch("backend.analytics.routes.auth_get_current_user") as mock_user,
            patch("backend.analytics.routes.get_rate_limiter") as mock_rate_limiter,
        ):
            regular_user = CurrentUser(
                id=uuid.uuid4(),
                email="test@example.com",
                role=UserRole.USER,
            )
            mock_user.return_value = regular_user
            mock_rate_limiter.return_value.check = AsyncMock()

            response = await async_client.post("/api/v1/analytics/process-events")
            assert response.status_code == 403
            assert "Admin access required" in response.json()["detail"]

            admin_user = CurrentUser(
                id=uuid.uuid4(),
                email="admin@example.com",
                role=UserRole.ADMIN,
            )
            mock_user.return_value = admin_user

            from backend.analytics.dependencies import get_analytics_service

            get_analytics_service.cache_clear()

            with (
                patch(
                    "backend.analytics.dependencies.get_analytics_service"
                ) as mock_get_service,
                patch("backend.analytics.routes.get_db_session") as mock_session,
            ):
                mock_get_service.return_value = mock_analytics_service
                mock_session.return_value.__aenter__.return_value = AsyncMock()

                response = await async_client.post("/api/v1/analytics/process-events")

        assert response.status_code == 200
        result = response.json()
        assert result["processed"] == 5
        assert result["failed"] == 1
