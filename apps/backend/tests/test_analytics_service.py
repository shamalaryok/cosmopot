"""Tests for analytics service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.analytics.enums import AnalyticsEvent
from backend.analytics.service import AnalyticsError, AnalyticsService
from backend.core.config import Settings


@pytest.fixture
def mock_settings() -> Settings:
    """Mock analytics settings."""
    return Settings(
        analytics=MagicMock(
            enabled=True,
            amplitude_api_key="test_amplitude_key",
            mixpanel_token="test_mixpanel_token",
            batch_size=10,
            flush_interval_seconds=60,
            max_retries=3,
            retry_delay_seconds=5,
            enable_pii_tracking=False,
            enable_user_properties=True,
            enable_session_tracking=True,
            data_retention_days=365,
            sandbox_mode=True,
        )
    )


@pytest.fixture
def analytics_service(mock_settings: Settings) -> AnalyticsService:
    """Create analytics service with mocked settings."""
    return AnalyticsService(mock_settings)


class TestAnalyticsService:
    """Test analytics service functionality."""

    @pytest.mark.asyncio
    async def test_track_event_success(
        self,
        analytics_service: AnalyticsService,
    ) -> None:
        """Test successful event tracking."""
        mock_session = AsyncMock()

        with patch("backend.analytics.service.create_analytics_event") as mock_create:
            mock_event = MagicMock()
            mock_event.id = "test-event-id"
            mock_create.return_value = mock_event

            event = await analytics_service.track_event(
                session=mock_session,
                event_type=AnalyticsEvent.SIGNUP_COMPLETED,
                event_data={"test": "data"},
                user_id="test-user-id",
            )

        assert event.id == "test-event-id"
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_track_event_disabled(self, mock_settings: Settings) -> None:
        """Test event tracking when analytics is disabled."""
        mock_settings.analytics.enabled = False
        service = AnalyticsService(mock_settings)

        mock_session = AsyncMock()

        with patch("backend.analytics.service.create_analytics_event") as mock_create:
            event = await service.track_event(
                session=mock_session,
                event_type=AnalyticsEvent.SIGNUP_COMPLETED,
                event_data={"test": "data"},
                user_id="test-user-id",
            )

        assert event.is_successful is True
        mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_pii_filtering(
        self,
        analytics_service: AnalyticsService,
    ) -> None:
        """Test PII data filtering."""
        mock_session = AsyncMock()

        with patch("backend.analytics.service.create_analytics_event") as mock_create:
            mock_event = MagicMock()
            mock_event.id = "test-event-id"
            mock_create.return_value = mock_event

            await analytics_service.track_event(
                session=mock_session,
                event_type=AnalyticsEvent.SIGNUP_COMPLETED,
                event_data={
                    "email": "test@example.com",
                    "name": "John Doe",
                    "safe_data": "should_remain",
                },
                user_id="test-user-id",
                user_properties={
                    "email": "test@example.com",
                    "name": "John Doe",
                    "safe_prop": "should_remain",
                },
            )

        call_args = mock_create.call_args
        event_data = call_args.kwargs["event_data"]
        user_properties = call_args.kwargs["user_properties"]

        assert "email" not in event_data
        assert "name" not in event_data
        assert "safe_data" in event_data
        assert "email" not in user_properties
        assert "name" not in user_properties
        assert "safe_prop" in user_properties

    @pytest.mark.asyncio
    async def test_event_validation(
        self,
        analytics_service: AnalyticsService,
    ) -> None:
        """Test event data validation."""
        mock_session = AsyncMock()

        with patch("backend.analytics.service.create_analytics_event"):
            with pytest.raises(AnalyticsError):
                await analytics_service.track_event(
                    session=mock_session,
                    event_type=AnalyticsEvent.PAYMENT_INITIATED,
                    event_data={},
                    user_id="test-user-id",
                )

    @pytest.mark.asyncio
    async def test_process_pending_events(
        self,
        analytics_service: AnalyticsService,
    ) -> None:
        """Test processing of pending events."""
        mock_session = AsyncMock()

        mock_event1 = MagicMock()
        mock_event1.id = "event1"
        mock_event1.user_id = "user1"
        mock_event1.event_type = AnalyticsEvent.SIGNUP_COMPLETED
        mock_event1.event_data = {"test": "data1"}
        mock_event1.user_properties = None
        mock_event1.retry_count = 0

        mock_event2 = MagicMock()
        mock_event2.id = "event2"
        mock_event2.user_id = "user2"
        mock_event2.event_type = AnalyticsEvent.LOGIN
        mock_event2.event_data = {"test": "data2"}
        mock_event2.user_properties = {"prop": "value"}
        mock_event2.retry_count = 0

        with (
            patch("backend.analytics.service.get_pending_events") as mock_get_pending,
            patch(
                "backend.analytics.service.mark_event_processed"
            ) as mock_mark_processed,
            patch.object(analytics_service, "_send_to_amplitude") as mock_amplitude,
            patch.object(analytics_service, "_send_to_mixpanel") as mock_mixpanel,
        ):
            mock_get_pending.return_value = [mock_event1, mock_event2]
            mock_amplitude.return_value = {"status": "success"}
            mock_mixpanel.return_value = {"status": "success"}

            result = await analytics_service.process_pending_events(mock_session)

        assert result["processed"] == 2
        assert result["failed"] == 0
        assert mock_amplitude.call_count == 2
        assert mock_mixpanel.call_count == 2
        assert mock_mark_processed.call_count == 2

    @pytest.mark.asyncio
    async def test_update_user_properties(
        self,
        analytics_service: AnalyticsService,
    ) -> None:
        """Test updating user properties."""
        with (
            patch.object(analytics_service, "_send_to_amplitude") as mock_amplitude,
            patch.object(analytics_service, "_send_to_mixpanel") as mock_mixpanel,
        ):
            await analytics_service.update_user_properties(
                user_id="test-user",
                properties={"subscription_level": "pro", "last_login": "2024-01-01"},
            )

        mock_amplitude.assert_called_once()
        mock_mixpanel.assert_called_once()

    @pytest.mark.asyncio
    async def test_pii_filtering_user_properties(
        self,
        analytics_service: AnalyticsService,
    ) -> None:
        """Test PII filtering in user properties."""
        with (
            patch.object(analytics_service, "_send_to_amplitude") as mock_amplitude,
            patch.object(analytics_service, "_send_to_mixpanel") as mock_mixpanel,
        ):
            await analytics_service.update_user_properties(
                user_id="test-user",
                properties={
                    "email": "test@example.com",
                    "name": "John Doe",
                    "subscription_level": "pro",
                },
            )

        amplitude_call = mock_amplitude.call_args
        mixpanel_call = mock_mixpanel.call_args
        expected_props = {"subscription_level": "pro"}

        assert amplitude_call.kwargs["user_properties"] == expected_props
        assert mixpanel_call.kwargs["properties"] == expected_props
