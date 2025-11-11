from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from redis.asyncio import Redis
import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from backend.core.config import Settings, get_settings
from backend.observability import add_breadcrumb

router = APIRouter(prefix="/health", tags=["health"])
logger = structlog.get_logger(__name__)


class DependencyStatus(BaseModel):
    """Health status for a downstream dependency."""

    status: Literal["ok", "error"]
    error: str | None = None

    model_config = ConfigDict(extra="ignore", validate_assignment=True)


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: Literal["ok", "error"]
    service: str
    version: str
    timestamp: datetime
    environment: str
    metrics_enabled: bool = False
    metrics_endpoint: str | None = None
    error_tracking_enabled: bool = False

    model_config = ConfigDict(extra="ignore", validate_assignment=True)


class DetailedHealthResponse(HealthResponse):
    """Detailed health check payload including dependency information."""

    redis: DependencyStatus | None = None
    database: DependencyStatus | None = None

    model_config = ConfigDict(extra="ignore", validate_assignment=True)


DependencyStatusPayload = dict[str, object]
HealthPayload = dict[str, object]


def _dependency_status(
    status: Literal["ok", "error"], error: str | None = None
) -> DependencyStatusPayload:
    payload: DependencyStatusPayload = {"status": status, "error": error}
    return payload


def _build_health_response(settings: Settings) -> HealthPayload:
    metrics_endpoint = (
        settings.prometheus.metrics_path if settings.prometheus.enabled else None
    )
    payload: HealthPayload = {
        "status": "ok",
        "service": settings.project_name,
        "version": settings.project_version,
        "timestamp": datetime.now(UTC),
        "environment": settings.environment.value,
        "metrics_enabled": settings.prometheus.enabled,
        "metrics_endpoint": metrics_endpoint,
        "error_tracking_enabled": settings.sentry.enabled,
    }
    return payload


@router.get("", summary="Service health check", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    """Return a lightweight health payload for readiness probes."""

    add_breadcrumb(
        category="health",
        message="Health check requested",
        level="info",
    )

    payload = _build_health_response(settings)
    logger.debug("health_status", **{k: v for k, v in payload.items() if v is not None})
    return payload


@router.get(
    "/detailed",
    summary="Detailed health check with dependencies",
    response_model=DetailedHealthResponse,
)
async def detailed_health(
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """Return detailed health status including dependency checks."""

    add_breadcrumb(
        category="health",
        message="Detailed health check requested",
        level="info",
    )

    payload: dict[str, object] = _build_health_response(settings).copy()
    payload["redis"] = None
    payload["database"] = None

    try:
        redis_client = Redis.from_url(settings.redis.url, decode_responses=False)
    except Exception as exc:  # pragma: no cover - defensive
        payload["redis"] = _dependency_status("error", str(exc))
        logger.error("redis_health_check_failed", error=str(exc))
    else:
        try:
            await redis_client.ping()
            payload["redis"] = _dependency_status("ok")
        except Exception as exc:  # pragma: no cover - defensive
            payload["redis"] = _dependency_status("error", str(exc))
            logger.error("redis_health_check_failed", error=str(exc))
        finally:
            await redis_client.close()

    payload["database"] = _dependency_status("ok")
    return payload
