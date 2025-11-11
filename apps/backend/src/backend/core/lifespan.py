from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from starlette.types import Lifespan

from backend.auth.rate_limiter import RateLimiter
from backend.core.config import Settings
from backend.core.redis import close_redis, init_redis
from backend.db.session import dispose_engine, get_engine
from backend.generation.broadcaster import TaskStatusBroadcaster
from bot_runtime.runtime import BotRuntime


def create_lifespan(settings: Settings) -> Lifespan[FastAPI]:
    logger = structlog.get_logger(__name__).bind(environment=settings.environment)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("application_startup")
        # Initialise pooled resources so they can be reused across requests.
        get_engine(settings)
        redis = await init_redis(settings)
        app.state.redis = redis
        app.state.task_broadcaster = TaskStatusBroadcaster(redis)
        app.state.rate_limiter = RateLimiter(
            redis,
            limit=settings.rate_limit.requests_per_minute,
            window_seconds=settings.rate_limit.window_seconds,
        )

        bot_runtime: BotRuntime | None = None
        if settings.telegram_bot_token is not None:
            try:
                bot_runtime = BotRuntime(settings)
                await bot_runtime.startup()
                app.state.bot_runtime = bot_runtime
                logger.info("bot_runtime_started")
            except Exception:
                logger.exception("bot_runtime_start_failed")
                raise
        else:
            app.state.bot_runtime = None

        try:
            yield
        finally:
            if bot_runtime is not None:
                try:
                    await bot_runtime.shutdown()
                    logger.info("bot_runtime_stopped")
                except Exception:
                    logger.exception("bot_runtime_shutdown_failed")
                finally:
                    app.state.bot_runtime = None

            app.state.rate_limiter = None
            app.state.task_broadcaster = None
            await close_redis()
            await dispose_engine()
            logger.info("application_shutdown")

    return lifespan
