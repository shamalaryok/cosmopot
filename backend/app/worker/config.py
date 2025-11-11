from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import AliasChoices, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from .banana import GeminiNanoClient
    from .redis_events import RedisNotifier
    from .storage import StorageClient


class WorkerSettings(BaseSettings):
    """Configuration container for the Celery worker pipeline."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    celery_broker_url: str = Field(
        "memory://",
        validation_alias=AliasChoices("WORKER_CELERY_BROKER_URL", "CELERY_BROKER_URL"),
    )
    celery_result_backend: str = Field(
        "redis://localhost:6379/1",
        validation_alias=AliasChoices(
            "WORKER_CELERY_RESULT_BACKEND", "CELERY_RESULT_BACKEND"
        ),
    )
    redis_pubsub_url: str = Field(
        "redis://localhost:6379/0",
        validation_alias=AliasChoices("WORKER_REDIS_URL", "REDIS_URL"),
    )
    redis_status_channel: str = Field("generation.tasks.status")
    redis_dead_letter_channel: str = Field("generation.tasks.dead_letter")
    redis_idempotency_prefix: str = Field("generation-task")
    redis_idempotency_ttl_seconds: int = Field(900)

    database_url: str = Field(
        "sqlite+aiosqlite:///:memory:",
        validation_alias=AliasChoices("WORKER_DATABASE_URL", "DATABASE_URL"),
    )

    s3_bucket: str = Field(
        "generation-artifacts",
        validation_alias=AliasChoices("WORKER_S3_BUCKET", "S3_BUCKET"),
    )
    s3_region: str = Field(
        "us-east-1",
        validation_alias=AliasChoices("WORKER_S3_REGION", "S3_REGION"),
    )
    s3_endpoint: str | None = Field(
        None,
        validation_alias=AliasChoices("WORKER_S3_ENDPOINT", "S3_ENDPOINT"),
    )
    s3_access_key: str | None = Field(
        None,
        validation_alias=AliasChoices("WORKER_S3_ACCESS_KEY", "S3_ACCESS_KEY"),
    )
    s3_secret_key: str | None = Field(
        None,
        validation_alias=AliasChoices("WORKER_S3_SECRET_KEY", "S3_SECRET_KEY"),
    )

    result_prefix: str = Field("results")
    thumbnail_prefix: str = Field("thumbs")

    banana_api_url: str = Field(
        "https://api.banana.dev",
        validation_alias=AliasChoices("WORKER_BANANA_API_URL", "BANANA_API_URL"),
    )
    banana_model_key: str = Field(
        "test-model",
        validation_alias=AliasChoices("WORKER_BANANA_MODEL_KEY", "BANANA_MODEL_KEY"),
    )
    banana_api_key: str = Field(
        "test-api-key",
        validation_alias=AliasChoices("WORKER_BANANA_API_KEY", "BANANA_API_KEY"),
    )
    banana_timeout_seconds: int = Field(60)
    banana_max_attempts: int = Field(3)
    banana_backoff_seconds: tuple[int, int, int] = Field((2, 4, 8))

    thumbnail_size: tuple[int, int] = Field((320, 320))
    log_level: str = Field(
        "INFO", validation_alias=AliasChoices("WORKER_LOG_LEVEL", "LOG_LEVEL")
    )


class RuntimeOverrides(BaseModel):
    """Optional dependency overrides used primarily for tests."""

    settings: WorkerSettings | None = None
    session_factory: async_sessionmaker[AsyncSession] | None = None
    storage: StorageClient | None = None
    notifier: RedisNotifier | None = None
    banana_client: GeminiNanoClient | None = None
    log_level: str | None = None
