from __future__ import annotations

import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

import backend.analytics.models  # noqa: F401 - ensure analytics models are registered with SQLAlchemy metadata
import backend.generation.models  # noqa: F401 - ensure generation models are registered
import backend.payments.models  # noqa: F401 - ensure models are registered with SQLAlchemy metadata
import backend.referrals.models  # noqa: F401 - ensure referral models are registered with SQLAlchemy metadata
from backend.analytics.dependencies import get_analytics_service
from backend.analytics.middleware import AnalyticsMiddleware
from backend.api.middleware import CorrelationIdMiddleware, RequestLoggingMiddleware
from backend.api.routes import load_routers
from backend.auth.middleware import CurrentUserMiddleware
from backend.auth.tokens import TokenService
from backend.core.config import Settings, get_settings
from backend.core.lifespan import create_lifespan
from backend.core.logging import configure_logging
from backend.observability import (
    configure_sentry,
    metrics_service,
    setup_sentry_middleware,
)
from backend.security import RateLimitMiddleware


def _register_middlewares(
    app: FastAPI, settings: Settings, token_service: TokenService
) -> None:
    if settings.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allow_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    redis_client = redis.from_url(settings.redis.url, decode_responses=False)
    app.add_middleware(
        RateLimitMiddleware,
        redis_client=redis_client,
        global_requests_per_minute=settings.rate_limit.global_requests_per_minute,
        window_seconds=settings.rate_limit.window_seconds,
    ) 

    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CurrentUserMiddleware,
        token_service=token_service,
        access_cookie_name=settings.jwt.access_cookie_name,
    )

    # Add analytics middleware if enabled
    if settings.analytics.enabled:
        analytics_service = get_analytics_service()
        app.add_middleware(
            AnalyticsMiddleware,
            analytics_service=analytics_service,
            settings=settings,
        )


def _register_routers(app: FastAPI) -> None:
    for router in load_routers():
        app.include_router(router)


def create_app() -> FastAPI:
    settings: Settings = get_settings()
    configure_logging(settings)

    # Configure Sentry first to capture all initialization errors
    if settings.sentry.enabled and settings.sentry.dsn:
        configure_sentry(settings.sentry)

    token_service = TokenService(settings)

    app = FastAPI(
        title=settings.project_name,
        description=settings.project_description,
        version=settings.project_version,
        docs_url=settings.docs_url,
        redoc_url=settings.redoc_url,
        openapi_url=settings.openapi_url,
        default_response_class=ORJSONResponse,
        lifespan=create_lifespan(settings),
    )

    app.state.settings = settings
    app.state.token_service = token_service
    app.state.bot_runtime = None
    app.openapi_tags = [
        {"name": "health", "description": "Service health check operations"},
        {"name": "auth", "description": "Authentication and session management"},
        {
            "name": "users",
            "description": (
                "User profile management, balance adjustments, session lifecycle, "
                "and GDPR stubs."
            ),
        },
        {
            "name": "referrals",
            "description": (
                "Referral system management, earnings tracking, and withdrawals."
            ),
        },
        {
            "name": "admin",
            "description": (
                "Admin panel endpoints for managing users, subscriptions, prompts, "
                "generations, and viewing analytics. Requires admin role."
            ),
        },
        {
            "name": "analytics",
            "description": (
                "Analytics tracking, metrics calculation, and reporting endpoints."
            ),
        },
    ]

    # Setup observability stack
    setup_sentry_middleware(app, settings.sentry)
    metrics_service.instrument_app(app, settings.prometheus)

    _register_middlewares(app, settings, token_service)
    _register_routers(app)

    return app
