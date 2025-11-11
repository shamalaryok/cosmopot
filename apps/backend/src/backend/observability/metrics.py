"""Prometheus metrics collection and configuration."""

from __future__ import annotations

import time
from collections.abc import AsyncContextManager
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import TYPE_CHECKING, Any

from prometheus_client import Counter, Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator

if TYPE_CHECKING:
    from fastapi import FastAPI, Request
    from prometheus_client.registry import CollectorRegistry
    from starlette.responses import Response

# Business metrics
GENERATION_REQUESTS_TOTAL = Counter(
    "generation_requests_total",
    "Total number of generation requests",
    ["user_id", "status", "model_type"]
)

GENERATION_DURATION_SECONDS = Histogram(
    "generation_duration_seconds",
    "Time spent processing generation requests",
    ["user_id", "model_type"],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0, float("inf")]
)

ACTIVE_GENERATIONS = Gauge(
    "active_generations",
    "Number of currently active generation tasks",
    ["model_type"]
)

PAYMENT_REQUESTS_TOTAL = Counter(
    "payment_requests_total",
    "Total number of payment requests",
    ["provider", "currency", "status"]
)

PAYMENT_AMOUNT_TOTAL = Counter(
    "payment_amount_total",
    "Total amount processed in payments",
    ["provider", "currency"]
)

USER_REGISTRATIONS_TOTAL = Counter(
    "user_registrations_total",
    "Total number of user registrations",
    ["source"]
)

ACTIVE_USERS = Gauge(
    "active_users",
    "Number of active users",
    ["timeframe"]  # 1h, 24h, 7d
)

QUEUE_DEPTH = Gauge(
    "queue_depth",
    "Number of items in processing queues",
    ["queue_name"]
)

DATABASE_CONNECTIONS_ACTIVE = Gauge(
    "database_connections_active",
    "Number of active database connections",
    ["pool"]
)

DATABASE_CONNECTIONS_IDLE = Gauge(
    "database_connections_idle",
    "Number of idle database connections",
    ["pool"]
)

CACHE_HITS_TOTAL = Counter(
    "cache_hits_total",
    "Total number of cache hits",
    ["cache_type"]
)

CACHE_MISSES_TOTAL = Counter(
    "cache_misses_total",
    "Total number of cache misses",
    ["cache_type"]
)

# Infrastructure metrics
SYSTEM_CPU_USAGE = Gauge(
    "system_cpu_usage_percent",
    "CPU usage percentage"
)

SYSTEM_MEMORY_USAGE = Gauge(
    "system_memory_usage_bytes",
    "Memory usage in bytes",
    ["type"]  # used, available, cached
)

DISK_USAGE = Gauge(
    "disk_usage_bytes",
    "Disk usage in bytes",
    ["mount_point", "type"]  # used, available
)


class _GenerationTimeContextManager(AbstractAsyncContextManager[None]):
    """Async context manager for measuring generation duration."""

    def __init__(
        self,
        user_id: str,
        model_type: str,
    ) -> None:
        self.user_id = user_id
        self.model_type = model_type
        self.start_time: float = 0.0
        self.status = "success"

    async def __aenter__(self) -> None:
        self.start_time = time.time()
        ACTIVE_GENERATIONS.labels(model_type=self.model_type).inc()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        if exc_type is not None:
            self.status = "error"

        duration = time.time() - self.start_time
        ACTIVE_GENERATIONS.labels(model_type=self.model_type).dec()
        GENERATION_DURATION_SECONDS.labels(
            user_id=self.user_id, model_type=self.model_type
        ).observe(duration)
        GENERATION_REQUESTS_TOTAL.labels(
            user_id=self.user_id, status=self.status, model_type=self.model_type
        ).inc()

        return False


class MetricsService:
    """Service for managing Prometheus metrics."""

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self.registry: CollectorRegistry | None = registry
        self._instrumentator: Instrumentator | None = None

    def create_instrumentator(self, settings: Any) -> Instrumentator:
        """Create and configure FastAPI instrumentator."""
        instrumentator = Instrumentator(
            should_group_status_codes=settings.should_group_status_codes,
            should_ignore_untemplated=settings.should_ignore_untemplated,
            should_group_untemplated=settings.should_group_untemplated,
            should_round_latency_decimals=settings.should_round_latency_decimals,
            should_respect_env_var=settings.should_respect_env_var,
            excluded_handlers=settings.excluded_handlers,
            env_var_name="ENABLE_METRICS",
            round_latency_decimals=4,
            registry=self.registry,
        )

        # Add custom metrics using the documented add() method
        def request_size_bytes_metric(request: Request, response: Response) -> None:
            """Track request sizes."""
            content_length_header = request.headers.get("content-length")
            if content_length_header is None:
                return
            try:
                int(content_length_header)
            except (TypeError, ValueError):
                return
            _ = response.headers.get("content-length")

        def response_size_bytes_metric(request: Request, response: Response) -> None:
            """Track response sizes."""
            content_length_header = response.headers.get("content-length")
            if content_length_header is None:
                return
            try:
                int(content_length_header)
            except (TypeError, ValueError):
                return
            _ = request.headers.get("content-length")

        instrumentator.add(request_size_bytes_metric)
        instrumentator.add(response_size_bytes_metric)

        return instrumentator

    def instrument_app(self, app: FastAPI, settings: Any) -> None:
        """Instrument FastAPI application with metrics."""
        if not settings.enabled:
            return

        self._instrumentator = self.create_instrumentator(settings)
        self._instrumentator.instrument(app)
        self._instrumentator.expose(
            app,
            should_gzip=True,
            endpoint=settings.metrics_path,
            include_in_schema=False,
        )

    def measure_generation_time(
        self,
        user_id: str,
        model_type: str,
    ) -> AsyncContextManager[None]:
        """Context manager for measuring generation duration."""
        return _GenerationTimeContextManager(user_id, model_type)

    def record_payment(
        self,
        provider: str,
        currency: str,
        amount: float,
        status: str,
    ) -> None:
        """Record payment metrics."""
        PAYMENT_REQUESTS_TOTAL.labels(
            provider=provider,
            currency=currency,
            status=status,
        ).inc()
        if status == "success":
            PAYMENT_AMOUNT_TOTAL.labels(
                provider=provider,
                currency=currency,
            ).inc(amount)

    def record_user_registration(self, source: str = "web") -> None:
        """Record user registration."""
        USER_REGISTRATIONS_TOTAL.labels(source=source).inc()

    def update_active_users(self, count: int, timeframe: str = "24h") -> None:
        """Update active users gauge."""
        ACTIVE_USERS.labels(timeframe=timeframe).set(count)

    def update_queue_depth(self, queue_name: str, depth: int) -> None:
        """Update queue depth gauge."""
        QUEUE_DEPTH.labels(queue_name=queue_name).set(depth)

    def update_database_connections(self, pool: str, active: int, idle: int) -> None:
        """Update database connection metrics."""
        DATABASE_CONNECTIONS_ACTIVE.labels(pool=pool).set(active)
        DATABASE_CONNECTIONS_IDLE.labels(pool=pool).set(idle)

    def record_cache_hit(self, cache_type: str = "redis") -> None:
        """Record cache hit."""
        CACHE_HITS_TOTAL.labels(cache_type=cache_type).inc()

    def record_cache_miss(self, cache_type: str = "redis") -> None:
        """Record cache miss."""
        CACHE_MISSES_TOTAL.labels(cache_type=cache_type).inc()

    def update_system_metrics(
        self,
        cpu_percent: float,
        memory_used: int,
        memory_available: int,
        disk_used: int,
        disk_available: int,
    ) -> None:
        """Update system metrics."""
        SYSTEM_CPU_USAGE.set(cpu_percent)
        SYSTEM_MEMORY_USAGE.labels(type="used").set(memory_used)
        SYSTEM_MEMORY_USAGE.labels(type="available").set(memory_available)
        DISK_USAGE.labels(mount_point="/", type="used").set(disk_used)
        DISK_USAGE.labels(mount_point="/", type="available").set(disk_available)


# Global metrics service instance
metrics_service: MetricsService = MetricsService()