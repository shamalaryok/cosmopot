from __future__ import annotations

import time
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, cast

import redis.asyncio as redis
import structlog
from fastapi import HTTPException, Request, status
from redis.asyncio.client import Pipeline as RedisPipeline
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

logger = structlog.get_logger(__name__)

if TYPE_CHECKING:
    from redis.asyncio import Redis as RedisClient
else:  # pragma: no cover - runtime alias for type checking
    RedisClient = redis.Redis


class RateLimitExceeded(HTTPException):
    """Raised when rate limit is exceeded."""

    def __init__(self, reset_after: int) -> None:
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(reset_after)},
        )


class RedisRateLimiter:
    """Redis-backed rate limiter using sliding window algorithm."""

    def __init__(
        self,
        redis_client: RedisClient,
        requests_per_minute: int = 100,
        window_seconds: int = 60,
    ) -> None:
        self.redis_client: RedisClient = redis_client
        self.requests_per_minute = requests_per_minute
        self.window_seconds = window_seconds

    async def check_rate_limit(
        self, identifier: str, max_requests: int | None = None
    ) -> tuple[bool, int]:
        """
        Check if identifier is within rate limit.

        Returns:
            Tuple of (is_allowed, seconds_until_reset)
        """
        max_requests = max_requests or self.requests_per_minute
        key = f"rate_limit:{identifier}"
        now = int(time.time())
        window_start = now - self.window_seconds

        try:
            pipeline: RedisPipeline = self.redis_client.pipeline()
            pipeline.zremrangebyscore(key, 0, window_start)
            await pipeline.execute()

            count = await self.redis_client.zcard(key)

            if count < max_requests:
                await self.redis_client.zadd(
                    key,
                    {str(now): now},
                    xx=False,
                )
                await self.redis_client.expire(key, self.window_seconds)
                return True, 0

            oldest_request = cast(
                Sequence[bytes | str],
                await self.redis_client.zrange(key, 0, 0),
            )
            if oldest_request:
                oldest_member = oldest_request[0]
                if isinstance(oldest_member, bytes):
                    oldest_value = oldest_member.decode("utf-8")
                else:
                    oldest_value = str(oldest_member)
                reset_at = int(float(oldest_value)) + self.window_seconds
                reset_after = max(0, reset_at - now)
                return False, reset_after

            return False, self.window_seconds

        except Exception as exc:
            logger.exception(
                "rate_limit_check_error", identifier=identifier, error=str(exc)
            )
            return True, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces per-IP rate limiting."""

    def __init__(
        self,
        app: ASGIApp,
        redis_client: RedisClient,
        global_requests_per_minute: int = 100,
        window_seconds: int = 60,
    ) -> None:
        super().__init__(app)
        self.limiter = RedisRateLimiter(
            redis_client,
            requests_per_minute=global_requests_per_minute,
            window_seconds=window_seconds,
        )

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Any:
        client_ip = self._get_client_ip(request)

        is_allowed, reset_after = await self.limiter.check_rate_limit(
            client_ip,
        )

        if not is_allowed:
            logger.warning(
                "rate_limit_exceeded",
                client_ip=client_ip,
                path=request.url.path,
                reset_after=reset_after,
            )
            raise RateLimitExceeded(reset_after=reset_after)

        response = await call_next(request)
        return response

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """Extract client IP from request, respecting X-Forwarded-For header."""
        if x_forwarded_for := request.headers.get("X-Forwarded-For"):
            return x_forwarded_for.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"


class GenerationRateLimitDependency:
    """Dependency for per-user generation rate limiting."""

    def __init__(
        self,
        redis_client: RedisClient,
        requests_per_minute: int = 10,
        window_seconds: int = 60,
    ) -> None:
        self.limiter = RedisRateLimiter(
            redis_client,
            requests_per_minute=requests_per_minute,
            window_seconds=window_seconds,
        )

    async def __call__(self, user_id: str) -> None:
        """Check if user is within generation rate limit."""
        is_allowed, reset_after = await self.limiter.check_rate_limit(
            f"generation:{user_id}",
            max_requests=self.limiter.requests_per_minute,
        )

        if not is_allowed:
            logger.warning(
                "generation_rate_limit_exceeded",
                user_id=user_id,
                reset_after=reset_after,
            )
            raise RateLimitExceeded(reset_after=reset_after)
