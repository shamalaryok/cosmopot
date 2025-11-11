from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = Field(default="Dev Stack Backend", description="Application name")
    debug: bool = Field(default=False, description="Enable debug mode")

    database_url: str = Field(..., description="PostgreSQL connection string")
    redis_url: str = Field(..., description="Redis connection string")
    celery_broker_url: str = Field(..., description="Celery broker URL")
    celery_result_backend: str = Field(..., description="Celery results backend URL")

    minio_endpoint: str = Field(..., description="MinIO endpoint including protocol")
    minio_access_key: str = Field(..., description="MinIO access key")
    minio_secret_key: str = Field(..., description="MinIO secret key")
    minio_region: str = Field(default="us-east-1", description="Default MinIO region")

    sentry_dsn: str | None = Field(
        default=None, description="Optional Sentry DSN routed through relay"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
