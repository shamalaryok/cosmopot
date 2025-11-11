"""Sentry error tracking integration."""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any, Protocol, TypeAlias

import sentry_sdk
from sentry_sdk.integrations import Integration as SentryIntegration
from sentry_sdk.integrations.aiohttp import AioHttpIntegration
from sentry_sdk.integrations.argv import ArgvIntegration
from sentry_sdk.integrations.atexit import AtexitIntegration
from sentry_sdk.integrations.dedupe import DedupeIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.modules import ModulesIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.stdlib import StdlibIntegration
from sentry_sdk.integrations.threading import ThreadingIntegration

if TYPE_CHECKING:
    from fastapi import FastAPI
    from pydantic import SecretStr

logger = logging.getLogger(__name__)

# Optional Tornado integration - only add if tornado is available
try:
    from sentry_sdk.integrations.tornado import (
        TornadoIntegration as _TornadoIntegration,
    )
except Exception:  # pragma: no cover - tornado is optional
    _TornadoIntegration = None

# Type alias for optional Tornado integration
TornadoIntegrationType: TypeAlias = type[SentryIntegration] | None
TornadoIntegration: TornadoIntegrationType = _TornadoIntegration

ASGIScope: TypeAlias = dict[str, Any]
ASGIReceive: TypeAlias = Callable[[], Awaitable[dict[str, Any]]]
ASGISend: TypeAlias = Callable[[dict[str, Any]], Awaitable[None]]


class SentrySettingsProtocol(Protocol):
    """Protocol defining required Sentry settings fields."""

    enabled: bool
    dsn: SecretStr | None
    environment: str | None
    release: str | None
    server_name: str | None
    dist: str | None
    sample_rate: float
    max_breadcrumbs: int
    attach_stacktrace: bool
    send_default_pii: bool
    debug: bool
    enable_tracing: bool
    traces_sample_rate: float
    profiles_sample_rate: float | None
    ignore_errors: Sequence[str]


def configure_sentry(settings: SentrySettingsProtocol) -> None:
    """Configure Sentry SDK with provided settings."""
    if not settings.enabled or settings.dsn is None:
        return

    # Default integrations to include
    integrations: list[SentryIntegration] = [
        FastApiIntegration(),
        SqlalchemyIntegration(),
        RedisIntegration(),
        AioHttpIntegration(),
        LoggingIntegration(
            level=logging.INFO,
            event_level=logging.ERROR,
        ),
        DedupeIntegration(),
        StdlibIntegration(),
        ThreadingIntegration(),
        ModulesIntegration(),
        AtexitIntegration(),
        ArgvIntegration(),
    ]

    # Add Tornado integration only if available
    if isinstance(TornadoIntegration, type) and issubclass(
        TornadoIntegration,
        SentryIntegration,
    ):
        try:
            integrations.append(TornadoIntegration())
        except Exception:  # pragma: no cover - defensive guard
            logger.debug("Failed to initialise Tornado Sentry integration", exc_info=True)

    # Configure tracing if enabled
    traces_sampler: Callable[[dict[str, Any]], float] | None = None
    if settings.enable_tracing:

        def traces_sampler_context(
            sampling_context: dict[str, Any],
        ) -> float:
            """Custom traces sampler based on context."""
            transaction = sampling_context.get("transaction_context", {})
            transaction_name = transaction.get("name", "")

            if transaction_name.startswith("/health"):
                return 0.1
            if "/admin" in transaction_name:
                return 0.5
            return settings.traces_sample_rate

        traces_sampler = traces_sampler_context

    sentry_sdk.init(
        dsn=settings.dsn.get_secret_value(),
        environment=(
            settings.environment or os.getenv("ENVIRONMENT", "development")
        ),
        release=settings.release or os.getenv("APP_VERSION", "unknown"),
        server_name=settings.server_name,
        dist=settings.dist,
        sample_rate=settings.sample_rate,
        max_breadcrumbs=settings.max_breadcrumbs,
        attach_stacktrace=settings.attach_stacktrace,
        send_default_pii=settings.send_default_pii,
        debug=settings.debug,
        traces_sampler=traces_sampler,
        profiles_sample_rate=settings.profiles_sample_rate,
        integrations=integrations,
        before_send=_before_send,
        before_breadcrumb=_before_breadcrumb,
        ignore_errors=settings.ignore_errors,
    )


def _before_send(
    event: dict[str, Any],
    hint: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Filter and modify events before sending to Sentry."""
    # Filter out health check errors
    if event.get("request", {}).get("url", "").endswith("/health"):
        return None
    
    # Filter out 404 errors (they're not usually actionable)
    exception_values = event.get("exception", {}).get("values", [{}])
    if exception_values[0].get("type") == "NotFound":
        return None

    # Add custom context
    event.setdefault("extra", {})["filtered"] = True

    return event


def _before_breadcrumb(
    breadcrumb: dict[str, Any],
    hint: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Filter and modify breadcrumbs before sending to Sentry."""
    # Filter out health check breadcrumbs
    url = breadcrumb.get("data", {}).get("url", "")
    if breadcrumb.get("category") == "http" and "/health" in url:
        return None

    # Filter out noisy breadcrumbs
    duration = breadcrumb.get("data", {}).get("duration", 0)
    if breadcrumb.get("category") in ["redis", "sql"] and duration < 10:
        return None

    return breadcrumb


def add_sentry_context(
    user_id: str | None = None,
    **additional_context: Any,
) -> None:
    """Add user context to Sentry."""
    try:
        if user_id:
            sentry_sdk.set_user({"id": user_id})

        if additional_context:
            sentry_sdk.set_tags(additional_context)
    except Exception:
        # Sentry not initialized, skip context setting
        pass


def capture_exception(exception: Exception, **extra_context: Any) -> None:
    """Capture exception with additional context."""
    try:
        with sentry_sdk.configure_scope() as scope:
            for key, value in extra_context.items():
                scope.set_extra(key, value)

        sentry_sdk.capture_exception(exception)
    except Exception:
        # Sentry not initialized, skip exception capture
        pass


def capture_message(
    message: str,
    level: str = "info",
    **extra_context: Any,
) -> None:
    """Capture message with additional context."""
    try:
        with sentry_sdk.configure_scope() as scope:
            for key, value in extra_context.items():
                scope.set_extra(key, value)

        sentry_sdk.capture_message(message, level=level)
    except Exception:
        # Sentry not initialized, skip message capture
        pass


def set_transaction_name(name: str) -> None:
    """Set transaction name for the current scope."""
    sentry_sdk.set_transaction_name(name)


def add_breadcrumb(
    category: str,
    message: str,
    level: str = "info",
    **data: Any,
) -> None:
    """Add custom breadcrumb."""
    try:
        sentry_sdk.add_breadcrumb(
            category=category,
            message=message,
            level=level,
            data=data,
        )
    except Exception:
        # Sentry not initialized, skip breadcrumb addition
        pass


class SentryMiddleware:
    """Middleware to add Sentry context to requests."""

    def __init__(self, app: "FastAPI") -> None:
        self.app = app

    async def __call__(
        self,
        scope: ASGIScope,
        receive: ASGIReceive,
        send: ASGISend,
    ) -> None:
        """ASGI middleware implementation."""
        if scope["type"] == "http":
            # Add request context only if Sentry is initialized
            try:
                request_id = scope.get("state", {}).get("request_id")
                if request_id:
                    with sentry_sdk.configure_scope() as scope_obj:
                        scope_obj.set_tag("request_id", request_id)
            except Exception:
                # Sentry not initialized, skip context setting
                pass

        await self.app(scope, receive, send)


def setup_sentry_middleware(app: "FastAPI", settings: SentrySettingsProtocol | None = None) -> None:
    """Set up Sentry middleware for FastAPI app."""
    # Only set up middleware if Sentry is enabled
    if settings is not None and (not settings.enabled or settings.dsn is None):
        return

    app.middleware("http")(SentryMiddleware(app))