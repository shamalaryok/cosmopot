"""Tests for observability metrics."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from backend.app import create_app
from backend.core.config import Settings
from backend.observability import metrics_service
from backend.observability.metrics import (
    ACTIVE_GENERATIONS,
    GENERATION_DURATION_SECONDS,
    GENERATION_REQUESTS_TOTAL,
    PAYMENT_REQUESTS_TOTAL,
)



@pytest.fixture
def app_with_metrics() -> TestClient:
    """Create test app with metrics enabled."""
    settings = Settings()
    settings.prometheus.enabled = True
    settings.sentry.enabled = False

    app = create_app()
    return TestClient(app)


def test_metrics_endpoint_accessible(app_with_metrics: TestClient) -> None:
    """Test that metrics endpoint is accessible."""
    response = app_with_metrics.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]

    metrics_text = response.text
    assert "http_requests_total" in metrics_text
    assert "http_request_duration_seconds" in metrics_text


def test_business_metrics_defined() -> None:
    """Test that business metrics are properly defined."""
    assert GENERATION_REQUESTS_TOTAL._name in REGISTRY._names_to_collectors
    assert GENERATION_DURATION_SECONDS._name in REGISTRY._names_to_collectors
    assert PAYMENT_REQUESTS_TOTAL._name in REGISTRY._names_to_collectors
    assert ACTIVE_GENERATIONS._name in REGISTRY._names_to_collectors


@pytest.mark.asyncio
async def test_metrics_service_context_manager() -> None:
    """Test metrics service context manager for generation timing."""
    initial_requests = REGISTRY.get_sample_value(
        "generation_requests_total",
        {"user_id": "test_user", "status": "success", "model_type": "test"},
    ) or 0
    initial_active = REGISTRY.get_sample_value(
        "active_generations",
        {"model_type": "test"},
    ) or 0

    async with metrics_service.measure_generation_time("test_user", "test"):
        pass

    final_requests = REGISTRY.get_sample_value(
        "generation_requests_total",
        {"user_id": "test_user", "status": "success", "model_type": "test"},
    ) or 0
    final_active = REGISTRY.get_sample_value(
        "active_generations",
        {"model_type": "test"},
    ) or 0

    assert final_requests == initial_requests + 1
    assert final_active == initial_active


def test_payment_metrics_recording() -> None:
    """Test payment metrics recording."""
    metrics_service.record_payment(
        provider="stripe",
        currency="USD",
        amount=10.0,
        status="success",
    )

    requests = REGISTRY.get_sample_value(
        "payment_requests_total",
        {"provider": "stripe", "currency": "USD", "status": "success"},
    ) or 0
    amount = REGISTRY.get_sample_value(
        "payment_amount_total",
        {"provider": "stripe", "currency": "USD"},
    ) or 0

    assert requests > 0
    assert amount == 10.0


def test_user_registration_metrics() -> None:
    """Test user registration metrics."""
    metrics_service.record_user_registration(source="web")

    registrations = REGISTRY.get_sample_value(
        "user_registrations_total",
        {"source": "web"},
    ) or 0

    assert registrations > 0


def test_cache_metrics() -> None:
    """Test cache hit/miss metrics."""
    metrics_service.record_cache_hit()
    metrics_service.record_cache_miss()

    hits = REGISTRY.get_sample_value(
        "cache_hits_total",
        {"cache_type": "redis"},
    ) or 0
    misses = REGISTRY.get_sample_value(
        "cache_misses_total",
        {"cache_type": "redis"},
    ) or 0

    assert hits > 0
    assert misses > 0


def test_queue_depth_metrics() -> None:
    """Test queue depth metrics."""
    metrics_service.update_queue_depth("generation", 42)

    depth = REGISTRY.get_sample_value(
        "queue_depth",
        {"queue_name": "generation"},
    )

    assert depth == 42


def test_system_metrics() -> None:
    """Test system metrics update."""
    metrics_service.update_system_metrics(
        cpu_percent=75.5,
        memory_used=8_000_000_000,
        memory_available=4_000_000_000,
        disk_used=500_000_000_000,
        disk_available=500_000_000_000,
    )

    cpu = REGISTRY.get_sample_value("system_cpu_usage_percent")
    mem_used = REGISTRY.get_sample_value(
        "system_memory_usage_bytes",
        {"type": "used"},
    )
    disk_used = REGISTRY.get_sample_value(
        "disk_usage_bytes",
        {"mount_point": "/", "type": "used"},
    )

    assert cpu == 75.5
    assert mem_used == 8_000_000_000
    assert disk_used == 500_000_000_000
