from __future__ import annotations

from fastapi import HTTPException, status
from redis.asyncio import Redis


class RateLimitExceeded(HTTPException):
    """Exception raised when a client exceeds the permitted request quota."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please retry later.",
            headers={"Retry-After": str(max(1, retry_after))},
        )


class RateLimiter:
    """Simple sliding-window rate limiter backed by Redis."""

    def __init__(
        self,
        redis: Redis,
        *,
        limit: int,
        window_seconds: int = 60,
        prefix: str = "rate",
    ) -> None:
        self._redis = redis
        self._limit = limit
        self._window_seconds = window_seconds
        self._prefix = prefix

    async def check(self, scope: str, identifier: str) -> None:
        key = f"{self._prefix}:{scope}:{identifier}"
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, self._window_seconds)
        if count > self._limit:
            ttl = await self._redis.ttl(key)
            retry_after = int(ttl) if ttl and ttl > 0 else self._window_seconds
            raise RateLimitExceeded(retry_after)

    async def reset(self, scope: str, identifier: str) -> None:
        key = f"{self._prefix}:{scope}:{identifier}"
        await self._redis.delete(key)
