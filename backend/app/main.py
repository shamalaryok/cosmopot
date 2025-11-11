from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlparse

import aio_pika
import sentry_sdk
from celery.result import AsyncResult
from fastapi import FastAPI, status
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel
from redis.asyncio import Redis
from starlette.responses import RedirectResponse

from . import db
from .celery_app import celery_app
from .config import settings
from .tasks import compute_sum

redis_client: Redis | None = None
rabbitmq_connection: aio_pika.RobustConnection | None = None
instrumentator = Instrumentator()

if TYPE_CHECKING:
    from minio import Minio

minio_client: Minio | None = None

app = FastAPI(title=settings.app_name, debug=settings.debug)


class DependencyStatus(BaseModel):
    status: Literal["ok", "error"]
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    dependencies: dict[str, DependencyStatus]


class SumRequest(BaseModel):
    a: int
    b: int


class TaskSubmissionResponse(BaseModel):
    task_id: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: Any | None = None
    error: str | None = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    global redis_client, rabbitmq_connection, minio_client

    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.2)

    await db.wait_for_database()

    redis_client = Redis.from_url(
        settings.redis_url, encoding="utf-8", decode_responses=True
    )
    await redis_client.ping()

    rabbitmq_connection = await aio_pika.connect_robust(settings.celery_broker_url)
    channel = await rabbitmq_connection.channel()
    await channel.close()

    minio_client = _build_minio_client()
    await _probe_minio()

    instrumentator.instrument(application).expose(application)

    yield

    await db.close_pool()

    if redis_client is not None:
        await redis_client.close()

    if rabbitmq_connection is not None:
        await rabbitmq_connection.close()


app.router.lifespan_context = lifespan


def _build_minio_client():
    from minio import Minio

    parsed = urlparse(settings.minio_endpoint)
    secure = parsed.scheme == "https"
    endpoint = parsed.netloc or parsed.path
    return Minio(
        endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=secure,
        region=settings.minio_region,
    )


async def _probe_minio() -> None:
    if minio_client is None:
        raise RuntimeError("MinIO client not initialized")

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, minio_client.list_buckets)


async def _check_redis() -> DependencyStatus:
    client = redis_client
    if client is None:
        return DependencyStatus(status="error", detail="Redis client not ready")
    try:
        await client.ping()
        return DependencyStatus(status="ok")
    except Exception as exc:  # pragma: no cover - runtime safeguard
        return DependencyStatus(status="error", detail=str(exc))


async def _check_rabbitmq() -> DependencyStatus:
    connection = rabbitmq_connection
    if connection is None:
        return DependencyStatus(status="error", detail="RabbitMQ connection not ready")
    try:
        channel = await connection.channel()
        await channel.close()
        return DependencyStatus(status="ok")
    except Exception as exc:  # pragma: no cover - runtime safeguard
        return DependencyStatus(status="error", detail=str(exc))


async def _check_minio() -> DependencyStatus:
    try:
        await _probe_minio()
        return DependencyStatus(status="ok")
    except Exception as exc:  # pragma: no cover - runtime safeguard
        return DependencyStatus(status="error", detail=str(exc))


async def _check_database() -> DependencyStatus:
    try:
        await db.healthcheck()
        return DependencyStatus(status="ok")
    except Exception as exc:  # pragma: no cover - runtime safeguard
        return DependencyStatus(status="error", detail=str(exc))


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/docs", status_code=status.HTTP_302_FOUND)


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health() -> HealthResponse:
    db_status, redis_status, rabbitmq_status, minio_status = await asyncio.gather(
        _check_database(),
        _check_redis(),
        _check_rabbitmq(),
        _check_minio(),
    )

    dependencies = {
        "postgres": db_status,
        "redis": redis_status,
        "rabbitmq": rabbitmq_status,
        "minio": minio_status,
    }
    overall_status: Literal["ok", "degraded"] = (
        "ok"
        if all(item.status == "ok" for item in dependencies.values())
        else "degraded"
    )
    return HealthResponse(status=overall_status, dependencies=dependencies)


@app.post(
    "/tasks/sum",
    response_model=TaskSubmissionResponse,
    tags=["Tasks"],
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_sum_task(payload: SumRequest) -> TaskSubmissionResponse:
    task = compute_sum.delay(payload.a, payload.b)
    return TaskSubmissionResponse(task_id=task.id)


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse, tags=["Tasks"])
async def get_task_status(task_id: str) -> TaskStatusResponse:
    result = AsyncResult(task_id, app=celery_app)
    response = TaskStatusResponse(task_id=task_id, status=result.status)
    if result.successful():
        response.result = result.result
    elif result.failed():
        response.error = str(result.info)
    return response
