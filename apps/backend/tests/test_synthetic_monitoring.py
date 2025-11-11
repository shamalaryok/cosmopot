"""Tests for synthetic monitoring."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.core.config import Settings
from backend.observability.synthetic import SyntheticMonitor, run_sla_check


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings."""
    settings = Settings()
    settings.backend_base_url = "http://test.local"
    settings.environment.value = "test"
    return settings


@pytest.fixture
def synthetic_monitor(test_settings: Settings) -> SyntheticMonitor:
    """Create synthetic monitor instance."""
    return SyntheticMonitor(test_settings)


@pytest.mark.asyncio
async def test_endpoint_check_success(
    synthetic_monitor: SyntheticMonitor,
) -> None:
    """Test successful endpoint check."""
    mock_response = AsyncMock()
    mock_response.status_code = 200

    endpoint = {
        "name": "test_endpoint",
        "url": "http://test.local/health",
        "method": "GET",
        "expected_status": 200,
        "interval": 30,
    }

    with patch.object(
        synthetic_monitor.client,
        "request",
        return_value=mock_response,
    ):
        result = await synthetic_monitor.check_endpoint(endpoint)

    assert result["success"] is True
    assert result["status_code"] == 200
    assert result["error"] is None
    assert result["response_time"] > 0


@pytest.mark.asyncio
async def test_endpoint_check_failure_status_code(
    synthetic_monitor: SyntheticMonitor,
) -> None:
    """Test endpoint check with wrong status code."""
    mock_response = AsyncMock()
    mock_response.status_code = 500

    endpoint = {
        "name": "test_endpoint",
        "url": "http://test.local/health",
        "method": "GET",
        "expected_status": 200,
        "interval": 30,
    }

    with patch.object(
        synthetic_monitor.client,
        "request",
        return_value=mock_response,
    ):
        result = await synthetic_monitor.check_endpoint(endpoint)

    assert result["success"] is False
    assert result["status_code"] == 500
    assert result["error"] is None


@pytest.mark.asyncio
async def test_endpoint_check_timeout(
    synthetic_monitor: SyntheticMonitor,
) -> None:
    """Test endpoint check with timeout."""
    from httpx import TimeoutException

    endpoint = {
        "name": "test_endpoint",
        "url": "http://test.local/health",
        "method": "GET",
        "expected_status": 200,
        "interval": 30,
    }

    with patch.object(
        synthetic_monitor.client,
        "request",
        side_effect=TimeoutException("Timeout"),
    ):
        result = await synthetic_monitor.check_endpoint(endpoint)

    assert result["success"] is False
    assert result["status_code"] is None
    assert result["error"] == "timeout"


@pytest.mark.asyncio
async def test_endpoint_check_exception(
    synthetic_monitor: SyntheticMonitor,
) -> None:
    """Test endpoint check with exception."""

    endpoint = {
        "name": "test_endpoint",
        "url": "http://test.local/health",
        "method": "GET",
        "expected_status": 200,
        "interval": 30,
    }

    with patch.object(
        synthetic_monitor.client,
        "request",
        side_effect=Exception("Connection error"),
    ):
        result = await synthetic_monitor.check_endpoint(endpoint)

    assert result["success"] is False
    assert result["status_code"] is None
    assert result["error"] == "Connection error"


@pytest.mark.asyncio
async def test_run_checks(synthetic_monitor: SyntheticMonitor) -> None:
    """Test running all endpoint checks."""

    check_result = {
        "success": True,
        "status_code": 200,
        "response_time": 0.1,
        "error": None,
    }

    with patch.object(
        synthetic_monitor,
        "check_endpoint",
        return_value=check_result,
    ) as mock_check:
        results = await synthetic_monitor.run_checks()

    assert mock_check.call_count == len(synthetic_monitor.endpoints)
    for result in results:
        assert result["success"] is True


@pytest.mark.asyncio
async def test_sla_check_compliant() -> None:
    """Test SLA check when compliant."""
    with patch(
        "backend.observability.synthetic.get_synthetic_monitor",
    ) as mock_get_monitor:
        mock_monitor = AsyncMock()
        mock_monitor.run_checks.return_value = [
            {"success": True, "response_time": 0.5},
            {"success": True, "response_time": 0.3},
            {"success": True, "response_time": 0.7},
        ]
        mock_get_monitor.return_value = mock_monitor

        result = await run_sla_check()

    assert result["sla_met"] is True
    assert result["availability"] == 1.0
    assert result["avg_response_time"] == 0.5
    assert result["total_checks"] == 3
    assert result["successful_checks"] == 3


@pytest.mark.asyncio
async def test_sla_check_non_compliant() -> None:
    """Test SLA check when not compliant."""
    with patch(
        "backend.observability.synthetic.get_synthetic_monitor",
    ) as mock_get_monitor:
        mock_monitor = AsyncMock()
        mock_monitor.run_checks.return_value = [
            {"success": True, "response_time": 0.5},
            {"success": False, "response_time": 2.0},
            {"success": True, "response_time": 0.7},
        ]
        mock_get_monitor.return_value = mock_monitor

        result = await run_sla_check()

    assert result["sla_met"] is False
    assert result["availability"] == 0.667
    assert result["avg_response_time"] == 1.067
    assert result["total_checks"] == 3
    assert result["successful_checks"] == 2
