from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import quote_plus

from pydantic import (
    AliasChoices,
    AnyUrl,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    TypeAdapter,
    computed_field,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.core.constants import DEFAULT_ENV_FILE, SECRETS_DIR, SERVICE_NAME


class Environment(StrEnum):
    """Deployment environments supported by the service."""

    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class AsyncPostgresDsn(AnyUrl):
    allowed_schemes = {"postgresql", "postgresql+asyncpg"}
    host_required = True


class DatabaseSettings(BaseModel):
    """Database connectivity configuration."""

    model_config = ConfigDict(extra="ignore")

    url: AsyncPostgresDsn | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "DATABASE__URL", "database__url", "DATABASE_URL", "database_url"
        ),
    )
    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    password: SecretStr = SecretStr("postgres")
    name: str = SERVICE_NAME
    echo: bool = False

    def _build_dsn(self) -> str:
        if self.url is not None:
            return str(self.url)

        password = quote_plus(self.password.get_secret_value())
        return (
            f"postgresql+asyncpg://{self.user}:{password}"
            f"@{self.host}:{self.port}/{self.name}"
        )

    @computed_field
    @property
    def dsn(self) -> str:
        """Assemble the SQLAlchemy async DSN."""
        return self._build_dsn()

    @computed_field
    @property
    def async_fallback_dsn(self) -> str:
        """Alias retained for external tooling expecting `async_fallback_dsn`."""
        return self._build_dsn()


class RedisSettings(BaseSettings):
    """Redis connection configuration."""

    model_config = SettingsConfigDict(env_prefix="REDIS__", extra="ignore")

    url: str = "redis://localhost:6379/0"


class S3Settings(BaseModel):
    """Amazon S3 compatible object storage configuration."""

    model_config = ConfigDict(extra="ignore")

    bucket: str = Field(
        default="generation-inputs",
        min_length=3,
        validation_alias=AliasChoices(
            "S3__BUCKET",
            "s3__bucket",
            "S3_BUCKET",
            "storage__bucket",
        ),
    )
    region: str = Field(
        default="us-east-1",
        min_length=1,
        validation_alias=AliasChoices(
            "S3__REGION",
            "s3__region",
            "S3_REGION",
            "storage__region",
        ),
    )
    endpoint_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "S3__ENDPOINT_URL",
            "s3__endpoint_url",
            "S3_ENDPOINT_URL",
            "storage__endpoint_url",
        ),
    )
    access_key_id: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "S3__ACCESS_KEY_ID",
            "s3__access_key_id",
            "S3_ACCESS_KEY_ID",
            "storage__access_key_id",
        ),
    )
    secret_access_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "S3__SECRET_ACCESS_KEY",
            "s3__secret_access_key",
            "S3_SECRET_ACCESS_KEY",
            "storage__secret_access_key",
        ),
    )
    presign_ttl_seconds: int = Field(
        default=1_800,
        ge=60,
        le=86_400,
        validation_alias=AliasChoices(
            "S3__PRESIGN_TTL_SECONDS",
            "s3__presign_ttl_seconds",
            "S3_PRESIGN_TTL_SECONDS",
            "storage__presign_ttl_seconds",
        ),
    )


class JWTSettings(BaseModel):
    """JWT issuance and cookie configuration."""

    model_config = ConfigDict(extra="ignore")

    secret: SecretStr = Field(
        default=SecretStr("change-me"),
        validation_alias=AliasChoices(
            "JWT__SECRET", "jwt__secret", "JWT_SECRET", "jwt_secret"
        ),
    )
    algorithm: str = Field(default="HS256")
    access_token_exp_minutes: int = Field(default=15, ge=1)
    refresh_token_exp_days: int = Field(default=30, ge=1)
    cookie_secure: bool = True
    cookie_domain: str | None = None
    cookie_path: str = "/"
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    access_cookie_name: str = "access_token"
    refresh_cookie_name: str = "refresh_token"


class RateLimitSettings(BaseModel):
    """Per-IP and per-user rate limiter configuration."""

    model_config = ConfigDict(extra="ignore")

    global_requests_per_minute: int = Field(
        default=100,
        ge=1,
        validation_alias=AliasChoices(
            "RATE_LIMIT__GLOBAL_REQUESTS_PER_MINUTE",
            "rate_limit__global_requests_per_minute",
        ),
    )
    generation_requests_per_minute: int = Field(
        default=10,
        ge=1,
        validation_alias=AliasChoices(
            "RATE_LIMIT__GENERATION_REQUESTS_PER_MINUTE",
            "rate_limit__generation_requests_per_minute",
        ),
    )
    window_seconds: int = Field(
        default=60,
        ge=1,
        validation_alias=AliasChoices(
            "RATE_LIMIT__WINDOW_SECONDS",
            "rate_limit__window_seconds",
        ),
    )


class EncryptionSettings(BaseModel):
    """Application-layer encryption configuration."""

    model_config = ConfigDict(extra="ignore")

    key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "ENCRYPTION__KEY",
            "encryption__key",
            "ENCRYPTION_KEY",
        ),
    )
    enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "ENCRYPTION__ENABLED",
            "encryption__enabled",
            "ENCRYPTION_ENABLED",
        ),
    )


class GDPRSettings(BaseModel):
    """GDPR and data retention configuration."""

    model_config = ConfigDict(extra="ignore")

    input_retention_days: int = Field(
        default=7,
        ge=1,
        validation_alias=AliasChoices(
            "GDPR__INPUT_RETENTION_DAYS",
            "gdpr__input_retention_days",
        ),
    )
    result_retention_days: int = Field(
        default=90,
        ge=1,
        validation_alias=AliasChoices(
            "GDPR__RESULT_RETENTION_DAYS",
            "gdpr__result_retention_days",
        ),
    )
    purge_schedule: str = Field(
        default="0 1 * * *",
        validation_alias=AliasChoices(
            "GDPR__PURGE_SCHEDULE",
            "gdpr__purge_schedule",
        ),
    )


class RabbitMQSettings(BaseModel):
    """Durable queue configuration for asynchronous task dispatch."""

    model_config = ConfigDict(extra="ignore")

    url: str = Field(
        default="amqp://guest:guest@localhost:5672/",
        validation_alias=AliasChoices(
            "RABBITMQ__URL",
            "rabbitmq__url",
            "RABBITMQ_URL",
            "queue__url",
        ),
    )
    exchange: str = Field(
        default="generation",
        min_length=1,
        max_length=255,
        validation_alias=AliasChoices(
            "RABBITMQ__EXCHANGE",
            "rabbitmq__exchange",
            "RABBITMQ_EXCHANGE",
            "queue__exchange",
        ),
    )
    queue: str = Field(
        default="generation",
        min_length=1,
        max_length=255,
        validation_alias=AliasChoices(
            "RABBITMQ__QUEUE",
            "rabbitmq__queue",
            "RABBITMQ_QUEUE",
            "queue__queue",
        ),
    )
    routing_key: str = Field(
        default="generation",
        min_length=1,
        max_length=255,
        validation_alias=AliasChoices(
            "RABBITMQ__ROUTING_KEY",
            "rabbitmq__routing_key",
            "RABBITMQ_ROUTING_KEY",
            "queue__routing_key",
        ),
    )
    max_priority: int = Field(
        default=10,
        ge=1,
        le=10,
        validation_alias=AliasChoices(
            "RABBITMQ__MAX_PRIORITY",
            "rabbitmq__max_priority",
            "RABBITMQ_MAX_PRIORITY",
            "queue__max_priority",
        ),
    )


class PaymentPlan(BaseModel):
    """Definition for a purchasable subscription plan."""

    model_config = ConfigDict(extra="ignore")

    code: str = Field(..., min_length=2, max_length=64)
    subscription_level: str = Field(..., min_length=2, max_length=64)
    amount: Decimal = Field(..., ge=Decimal("0.00"))
    currency: str = Field(default="RUB", min_length=3, max_length=3)
    description: str | None = None

    @model_validator(mode="after")
    def _normalise(self) -> PaymentPlan:
        self.code = self.code.strip().lower()
        self.subscription_level = self.subscription_level.strip().lower()
        self.currency = self.currency.upper()
        return self


def _default_payment_plans() -> dict[str, PaymentPlan]:
    result: dict[str, PaymentPlan] = {
        "basic": PaymentPlan(
            code="basic",
            subscription_level="basic",
            amount=Decimal("9.99"),
            currency="RUB",
            description="Basic monthly subscription",
        ),
        "pro": PaymentPlan(
            code="pro",
            subscription_level="pro",
            amount=Decimal("29.99"),
            currency="RUB",
            description="Pro monthly subscription",
        ),
        "enterprise": PaymentPlan(
            code="enterprise",
            subscription_level="enterprise",
            amount=Decimal("99.99"),
            currency="RUB",
            description="Enterprise monthly subscription",
        ),
    }
    return result


class PaymentsSettings(BaseModel):
    """High-level configuration for payment flows and tiers."""

    model_config = ConfigDict(extra="ignore")

    default_currency: str = Field(default="RUB", min_length=3, max_length=3)
    plans: dict[str, PaymentPlan] = Field(default_factory=_default_payment_plans)

    @model_validator(mode="after")
    def _normalise(self) -> PaymentsSettings:
        self.default_currency = self.default_currency.upper()
        normalised: dict[str, PaymentPlan] = {}
        for key, plan in self.plans.items():
            normalised_key = key.strip().lower()
            if plan.code != normalised_key:
                plan = plan.model_copy(update={"code": normalised_key})
            normalised[normalised_key] = plan
        self.plans = normalised
        return self

    def get_plan(self, code: str) -> PaymentPlan:
        normalised = code.strip().lower()
        if not normalised or normalised not in self.plans:
            raise KeyError(code)
        return self.plans[normalised]


class YooKassaSettings(BaseSettings):
    """Credentials for the YooKassa payment provider."""

    model_config = SettingsConfigDict(
        env_prefix="YOOKASSA__",
        extra="ignore",
        case_sensitive=False,
    )

    shop_id: str | None = None
    secret_key: SecretStr | None = None
    webhook_secret: SecretStr | None = None


class StripeSettings(BaseSettings):
    """Credentials for the Stripe payment provider."""

    model_config = SettingsConfigDict(
        env_prefix="STRIPE__",
        extra="ignore",
        case_sensitive=False,
    )

    api_key: SecretStr | None = None
    webhook_secret: SecretStr | None = None
    enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "STRIPE__ENABLED",
            "stripe__enabled",
        ),
    )


class AnalyticsSettings(BaseSettings):
    """Analytics provider configuration and PII policies."""

    model_config = SettingsConfigDict(
        env_prefix="ANALYTICS__",
        extra="ignore",
        case_sensitive=False,
    )

    enabled: bool = True
    amplitude_api_key: SecretStr | None = None
    mixpanel_token: SecretStr | None = None
    batch_size: int = Field(default=100, ge=1, le=1000)
    flush_interval_seconds: int = Field(default=60, ge=10, le=3600)
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_delay_seconds: int = Field(default=5, ge=1, le=60)
    enable_pii_tracking: bool = False
    enable_user_properties: bool = True
    enable_session_tracking: bool = True
    data_retention_days: int = Field(default=365, ge=30, le=2555)
    sandbox_mode: bool = Field(default=False)


class PrometheusSettings(BaseSettings):
    """Prometheus metrics configuration."""

    model_config = SettingsConfigDict(
        env_prefix="PROMETHEUS__",
        extra="ignore",
        case_sensitive=False,
    )

    enabled: bool = True
    metrics_path: str = "/metrics"
    include_in_response: bool = False
    should_group_status_codes: bool = True
    should_ignore_untemplated: bool = True
    should_group_untemplated: bool = True
    should_round_latency_decimals: bool = False
    should_respect_env_var: bool = True
    excluded_handlers: list[str] = Field(
        default_factory=lambda: ["/metrics", "/health", "/docs", "/redoc"]
    )
    bucket_format: str = "le_{0}"
    default_buckets: list[float] = Field(
        default_factory=lambda: [
            0.005,
            0.01,
            0.025,
            0.05,
            0.075,
            0.1,
            0.25,
            0.5,
            0.75,
            1.0,
            2.5,
            5.0,
            7.5,
            10.0,
            float("inf"),
        ]
    )


class SentrySettings(BaseSettings):
    """Sentry error tracking configuration."""

    model_config = SettingsConfigDict(
        env_prefix="SENTRY__",
        extra="ignore",
        case_sensitive=False,
    )

    enabled: bool = True
    dsn: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "SENTRY_DSN",
            "sentry__dsn",
        ),
    )
    environment: str | None = None
    release: str | None = None
    server_name: str | None = None
    dist: str | None = None
    sample_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    max_breadcrumbs: int = Field(default=100, ge=0, le=1000)
    attach_stacktrace: bool = True
    send_default_pii: bool = False
    debug: bool = False
    enable_tracing: bool = True
    traces_sample_rate: float = Field(default=0.1, ge=0.0, le=1.0)
    profiles_sample_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    before_send: str | None = None
    before_breadcrumb: str | None = None
    ignore_errors: list[str] = Field(default_factory=list)
    request_bodies: str = "small"
    max_request_body_size: str = "medium"


_ANY_URL_ADAPTER = TypeAdapter(AnyUrl)


def _default_backend_base_url() -> AnyUrl:
    return _ANY_URL_ADAPTER.validate_python("http://localhost:8000")


class Settings(BaseSettings):
    """Application settings loaded from the environment or secret stores."""

    model_config = SettingsConfigDict(
        env_file=DEFAULT_ENV_FILE,
        env_nested_delimiter="__",
        secrets_dir=SECRETS_DIR,
        extra="ignore",
        validate_default=True,
        case_sensitive=False,
    )

    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    log_level: str = "INFO"

    project_name: str = "Backend Service"
    project_description: str = "Backend FastAPI service"
    project_version: str = "0.1.0"
    docs_url: str | None = "/docs"
    redoc_url: str | None = "/redoc"
    openapi_url: str = "/openapi.json"

    cors_allow_origins: list[str] = Field(default_factory=list)

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    s3: S3Settings = Field(default_factory=S3Settings)
    jwt: JWTSettings = Field(default_factory=JWTSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    encryption: EncryptionSettings = Field(default_factory=EncryptionSettings)
    gdpr: GDPRSettings = Field(default_factory=GDPRSettings)
    rabbitmq: RabbitMQSettings = Field(default_factory=RabbitMQSettings)
    payments: PaymentsSettings = Field(default_factory=PaymentsSettings)
    yookassa: YooKassaSettings = Field(default_factory=YooKassaSettings)
    stripe: StripeSettings = Field(default_factory=StripeSettings)
    analytics: AnalyticsSettings = Field(default_factory=AnalyticsSettings)
    prometheus: PrometheusSettings = Field(default_factory=PrometheusSettings)
    sentry: SentrySettings = Field(default_factory=SentrySettings)

    telegram_bot_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "TELEGRAM__BOT_TOKEN",
            "telegram__bot_token",
            "TELEGRAM_BOT_TOKEN",
        ),
    )
    backend_base_url: AnyUrl = Field(
        default_factory=_default_backend_base_url,
        validation_alias=AliasChoices(
            "BACKEND__BASE_URL",
            "backend__base_url",
            "BACKEND_BASE_URL",
        ),
    )
    telegram_webhook_path: str = Field(
        default="/api/v1/bot/webhook",
        validation_alias=AliasChoices(
            "TELEGRAM__WEBHOOK_PATH",
            "telegram__webhook_path",
            "TELEGRAM_WEBHOOK_PATH",
        ),
    )
    telegram_webhook_secret_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "TELEGRAM__WEBHOOK_SECRET",
            "telegram__webhook_secret",
            "TELEGRAM_WEBHOOK_SECRET",
        ),
    )
    telegram_login_ttl_seconds: int = Field(
        default=86_400,
        ge=60,
        validation_alias=AliasChoices(
            "TELEGRAM__LOGIN_TTL_SECONDS",
            "telegram__login_ttl_seconds",
            "TELEGRAM_LOGIN_TTL_SECONDS",
        ),
    )
    jwt_secret_key: SecretStr = Field(
        default=SecretStr("change-me"),
        validation_alias=AliasChoices(
            "JWT__SECRET_KEY",
            "jwt__secret_key",
            "JWT_SECRET_KEY",
            "SECURITY__JWT_SECRET_KEY",
            "security__jwt_secret_key",
        ),
    )
    jwt_algorithm: str = Field(
        default="HS256",
        validation_alias=AliasChoices(
            "JWT__ALGORITHM",
            "jwt__algorithm",
            "JWT_ALGORITHM",
            "SECURITY__JWT_ALGORITHM",
            "security__jwt_algorithm",
        ),
    )
    jwt_access_ttl_seconds: int = Field(
        default=3_600,
        ge=60,
        validation_alias=AliasChoices(
            "JWT__ACCESS_TTL_SECONDS",
            "jwt__access_ttl_seconds",
            "JWT_ACCESS_TTL_SECONDS",
            "SECURITY__JWT_ACCESS_TTL_SECONDS",
            "security__jwt_access_ttl_seconds",
        ),
    )

    @model_validator(mode="after")
    def _normalize(self) -> Settings:
        self.log_level = self.log_level.upper()

        if self.environment in {Environment.DEVELOPMENT, Environment.TEST}:
            self.debug = True

        return self

    @computed_field
    @property
    def is_development(self) -> bool:
        return self.environment is Environment.DEVELOPMENT

    @computed_field
    @property
    def is_testing(self) -> bool:
        return self.environment is Environment.TEST

    @computed_field
    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached instance of the application settings."""

    return Settings()
