"""Tests for Sentry integration."""

from __future__ import annotations

from unittest.mock import Mock, patch

from backend.core.config import Settings
from backend.observability.sentry import configure_sentry


def test_configure_sentry_disabled() -> None:
    """Test Sentry configuration when disabled."""
    settings = Settings()
    settings.sentry.enabled = False

    configure_sentry(settings.sentry)


def test_configure_sentry_no_dsn() -> None:
    """Test Sentry configuration when no DSN provided."""
    settings = Settings()
    settings.sentry.enabled = True
    settings.sentry.dsn = None

    configure_sentry(settings.sentry)


@patch("sentry_sdk.init")
def test_configure_sentry_enabled(mock_init: Mock) -> None:
    """Test Sentry configuration when enabled."""
    from pydantic import SecretStr

    settings = Settings()
    settings.sentry.enabled = True
    settings.sentry.dsn = SecretStr("https://test@sentry.io/123")
    settings.sentry.environment = "test"
    settings.sentry.sample_rate = 0.5
    settings.sentry.enable_tracing = True
    settings.sentry.traces_sample_rate = 0.2

    configure_sentry(settings.sentry)

    mock_init.assert_called_once()
    call_args = mock_init.call_args

    assert call_args[1]["dsn"] == "https://test@sentry.io/123"
    assert call_args[1]["environment"] == "test"
    assert call_args[1]["sample_rate"] == 0.5
    assert "traces_sampler" in call_args[1]
    assert call_args[1]["traces_sampler"] is not None


@patch("sentry_sdk.capture_exception")
def test_capture_exception(mock_capture: Mock) -> None:
    """Test exception capture with context."""
    from backend.observability import capture_exception

    test_exception = ValueError("Test error")
    capture_exception(test_exception, user_id="test_user", extra_info="test")

    mock_capture.assert_called_once_with(test_exception)


@patch("sentry_sdk.capture_message")
def test_capture_message(mock_capture: Mock) -> None:
    """Test message capture with context."""
    from backend.observability import capture_message

    capture_message("Test message", level="warning", context="test")

    mock_capture.assert_called_once_with("Test message", level="warning")


@patch("sentry_sdk.add_breadcrumb")
def test_add_breadcrumb(mock_breadcrumb: Mock) -> None:
    """Test breadcrumb addition."""
    from backend.observability import add_breadcrumb

    add_breadcrumb("test", "Test message", "info", key="value")

    mock_breadcrumb.assert_called_once_with(
        category="test",
        message="Test message",
        level="info",
        data={"key": "value"},
    )


@patch("sentry_sdk.set_tags")
@patch("sentry_sdk.set_user")
def test_add_sentry_context_user(
    mock_set_user: Mock,
    mock_set_tags: Mock,
) -> None:
    """Test adding user context."""
    from backend.observability import add_sentry_context

    add_sentry_context(user_id="test_user", email="test@example.com")

    mock_set_user.assert_called_once_with({"id": "test_user"})
    mock_set_tags.assert_called_once_with({"email": "test@example.com"})


@patch("sentry_sdk.set_tags")
@patch("sentry_sdk.set_user")
def test_add_sentry_context_tags(
    mock_set_user: Mock,
    mock_set_tags: Mock,
) -> None:
    """Test adding tags context."""
    from backend.observability import add_sentry_context

    add_sentry_context(service="backend", version="1.0.0")

    mock_set_user.assert_not_called()
    mock_set_tags.assert_called_once_with({"service": "backend", "version": "1.0.0"})


@patch("sentry_sdk.set_transaction_name")
def test_set_transaction_name(mock_set_transaction_name: Mock) -> None:
    """Test setting transaction name."""
    from backend.observability import set_transaction_name

    set_transaction_name("test_transaction")

    mock_set_transaction_name.assert_called_once_with("test_transaction")
