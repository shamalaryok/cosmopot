from __future__ import annotations

from urllib.parse import urlparse

import httpx
import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.redis import RedisStorage
from httpx import AsyncClient
from redis.asyncio import Redis

from backend.core.config import Settings
from bot_runtime._aiogram_compat import DefaultKeyBuilder
from bot_runtime.handlers import get_routers
from bot_runtime.middlewares import (
    DependencyInjectionMiddleware,
    ErrorHandlingMiddleware,
    LoggingMiddleware,
)
from bot_runtime.services.auth import TelegramAuthGateway

try:  # pragma: no cover - optional dependency in production
    from fakeredis.aioredis import FakeRedis as _FakeRedis
    FakeRedisFactory: type[Redis] | None = _FakeRedis
except ModuleNotFoundError:  # pragma: no cover - fakeredis is only needed for tests
    FakeRedisFactory = None

__all__ = ["BotRuntime"]


class BotRuntime:
    """Container responsible for initialising and shutting down bot resources."""

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: AsyncClient | None = None,
        redis: Redis | None = None,
        storage: BaseStorage | None = None,
    ) -> None:
        self._settings = settings
        self._http_client: AsyncClient | None = http_client
        self._redis: Redis | None = redis
        self._storage = storage

        self._owns_http_client = http_client is None
        self._owns_storage = storage is None

        self.bot: Bot | None = None
        self.dispatcher: Dispatcher | None = None
        self.auth_gateway: TelegramAuthGateway | None = None

        self._logger = structlog.get_logger(__name__).bind(component="bot_runtime")

    async def startup(self) -> None:
        if self._settings.telegram_bot_token is None:
            raise RuntimeError("Telegram bot token is not configured")

        token = self._settings.telegram_bot_token.get_secret_value()
        self.bot = Bot(
            token=token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )

        storage = await self._ensure_storage()
        self.dispatcher = Dispatcher(storage=storage)

        client = self._http_client or self._build_http_client()
        self._http_client = client

        self.auth_gateway = TelegramAuthGateway(
            http_client=client,
            bot_token=token,
            login_ttl_seconds=self._settings.telegram_login_ttl_seconds,
        )

        self._attach_middlewares()
        self._register_routers()

        self._logger.info("bot_runtime_started")

    async def shutdown(self) -> None:
        self._logger.info("bot_runtime_shutting_down")

        if self.dispatcher is not None and self._owns_storage:
            await self.dispatcher.storage.close()

        if self.bot is not None:
            await self.bot.session.close()

        if self._owns_http_client and self._http_client is not None:
            await self._http_client.aclose()

        self.dispatcher = None
        self.bot = None
        self.auth_gateway = None
        self._logger.info("bot_runtime_stopped")

    async def _ensure_storage(self) -> BaseStorage:
        if self._storage is not None:
            return self._storage

        redis = self._redis
        if redis is None:
            redis_url = str(self._settings.redis.url)
            scheme = (urlparse(redis_url).scheme or "").lower()

            if scheme in {"fakeredis", "memory"}:
                if FakeRedisFactory is None:
                    raise RuntimeError(
                        "fakeredis URL scheme requires the fakeredis dependency to be "
                        "installed."
                    )
                redis = FakeRedisFactory()
            else:
                redis = Redis.from_url(redis_url)

        self._redis = redis
        key_builder = DefaultKeyBuilder(with_bot_id=False)
        storage = RedisStorage(redis=redis, key_builder=key_builder)
        self._storage = storage
        return storage

    def _build_http_client(self) -> AsyncClient:
        timeout = httpx.Timeout(10.0, connect=5.0)
        return httpx.AsyncClient(
            base_url=str(self._settings.backend_base_url),
            timeout=timeout,
            headers={"User-Agent": "telegram-bot/1.0"},
        )

    def _attach_middlewares(self) -> None:
        assert self.dispatcher is not None
        assert self.auth_gateway is not None

        logger = structlog.get_logger("bot.dispatcher")
        self.dispatcher.update.middleware.register(LoggingMiddleware(logger))
        self.dispatcher.update.middleware.register(ErrorHandlingMiddleware(logger))
        self.dispatcher.message.middleware.register(
            DependencyInjectionMiddleware(auth_client=self.auth_gateway, logger=logger)
        )

    def _register_routers(self) -> None:
        assert self.dispatcher is not None

        for router in get_routers():
            if hasattr(router, "_parent_router") and router._parent_router is not None:
                router._parent_router = None
            self.dispatcher.include_router(router)

    async def start_polling(self) -> None:
        if self.bot is None or self.dispatcher is None:
            raise RuntimeError("Bot runtime must be started before polling")

        await self.dispatcher.start_polling(self.bot)
