from __future__ import annotations

from collections.abc import Awaitable
from urllib.parse import urlparse

from redis.asyncio import Redis

from backend.core.config import Settings, get_settings

FakeRedisFactory: type[Redis] | None = None

try:  # pragma: no cover - optional dependency in production
    from fakeredis.aioredis import FakeRedis as _FakeRedis

    FakeRedisFactory = _FakeRedis
except ModuleNotFoundError:  # pragma: no cover - fakeredis is only needed for tests
    pass


_REDIS: Redis | None = None


async def init_redis(settings: Settings | None = None) -> Redis:
    """Initialise and cache the Redis client."""

    global _REDIS
    if _REDIS is not None:
        return _REDIS

    settings = settings or get_settings()
    url = settings.redis.url
    parsed = urlparse(url)

    scheme = (parsed.scheme or "").lower()
    # Ensure fakeredis scheme is recognized even if environment parsing fails
    if scheme in {"fakeredis", "memory"}:
        factory = FakeRedisFactory
        if factory is None:
            raise RuntimeError("fakeredis requested but fakeredis is not installed.")
        _REDIS = factory()
    else:
        _REDIS = Redis.from_url(url, encoding="utf-8", decode_responses=True)

    ping_result: bool | Awaitable[bool] = _REDIS.ping()
    if isinstance(ping_result, Awaitable):
        ping_value: bool = await ping_result
    else:
        ping_value = ping_result

    if not isinstance(ping_value, bool):
        raise RuntimeError(f"Expected bool from ping(), got {type(ping_value)}")
    return _REDIS


async def get_redis(settings: Settings | None = None) -> Redis:
    return await init_redis(settings)


async def close_redis() -> None:
    global _REDIS
    if _REDIS is None:
        return

    close = getattr(_REDIS, "aclose", None)
    if callable(close):  # pragma: no branch - mypy friendly
        await close()
    else:  # pragma: no cover - fallback for legacy clients
        await _REDIS.close()
    _REDIS = None
