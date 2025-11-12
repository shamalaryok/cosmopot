from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

import pytest
import pytest_asyncio
import redis.asyncio as redis
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from fakeredis import aioredis as fakeredis

from backend.security.rate_limit import RateLimitMiddleware, RedisRateLimiter


@pytest_asyncio.fixture
async def redis_client() -> AsyncIterator[redis.Redis]:
    """Provide an in-memory Redis client for testing."""
    client = fakeredis.FakeRedis()
    try:
        yield cast(redis.Redis, client)
    finally:
        await client.flushdb()
        await client.close()


@pytest_asyncio.fixture
async def rate_limiter(
    redis_client: redis.Redis,
) -> AsyncIterator[RedisRateLimiter]:
    """Provide a rate limiter instance."""
    limiter = RedisRateLimiter(
        redis_client,
        requests_per_minute=5,
        window_seconds=60,
    )
    try:
        yield limiter
    finally:
        await redis_client.flushdb()


@pytest.mark.asyncio
async def test_rate_limit_allows_requests_within_limit(
    rate_limiter: RedisRateLimiter,
) -> None:
    """Test that requests within the limit are allowed."""
    for attempt in range(5):
        is_allowed, reset_after = await rate_limiter.check_rate_limit(
            "test_user",
            max_requests=5,
        )
        assert is_allowed, f"Request {attempt + 1} should be allowed"
        assert reset_after == 0


@pytest.mark.asyncio
async def test_rate_limit_blocks_requests_exceeding_limit(
    rate_limiter: RedisRateLimiter,
) -> None:
    """Test that requests exceeding the limit are blocked."""
    for _ in range(5):
        is_allowed, _ = await rate_limiter.check_rate_limit(
            "test_user",
            max_requests=5,
        )
        assert is_allowed

    is_allowed, reset_after = await rate_limiter.check_rate_limit(
        "test_user",
        max_requests=5,
    )
    assert not is_allowed
    assert reset_after > 0


@pytest.mark.asyncio
async def test_rate_limit_different_identifiers_independent(
    rate_limiter: RedisRateLimiter,
) -> None:
    """Test that different identifiers have independent rate limits."""
    for _ in range(5):
        is_allowed, _ = await rate_limiter.check_rate_limit(
            "user_a",
            max_requests=5,
        )
        assert is_allowed

    for _ in range(5):
        is_allowed, _ = await rate_limiter.check_rate_limit(
            "user_b",
            max_requests=5,
        )
        assert is_allowed


@pytest.mark.asyncio
async def test_rate_limit_resets_after_window(
    rate_limiter: RedisRateLimiter,
) -> None:
    """Test that rate limit resets after the window expires."""
    identifier = "test_window"

    for _ in range(5):
        is_allowed, _ = await rate_limiter.check_rate_limit(
            identifier,
            max_requests=5,
        )
        assert is_allowed

    is_allowed, _ = await rate_limiter.check_rate_limit(
        identifier,
        max_requests=5,
    )
    assert not is_allowed

    await rate_limiter.redis_client.delete(f"rate_limit:{identifier}")
    is_allowed, _ = await rate_limiter.check_rate_limit(
        identifier,
        max_requests=5,
    )
    assert is_allowed


@pytest.mark.asyncio
async def test_rate_limit_middleware_enforces_per_ip(
    redis_client: redis.Redis,
) -> None:
    """Test that RateLimitMiddleware enforces per-IP rate limiting."""
    app = FastAPI()

    app.add_middleware(
        RateLimitMiddleware,
        redis_client=redis_client,
        global_requests_per_minute=2,
        window_seconds=60,
    )

    @app.get("/test")
    def test_endpoint() -> dict[str, str]:
        return {"message": "ok"}

    client = TestClient(app)

    client.get("/test", headers={"X-Forwarded-For": "192.168.1.1"})
    client.get("/test", headers={"X-Forwarded-For": "192.168.1.1"})

    response = client.get("/test", headers={"X-Forwarded-For": "192.168.1.1"})
    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert "Retry-After" in response.headers

    await redis_client.flushdb()


@pytest.mark.asyncio
async def test_rate_limit_middleware_different_ips(
    redis_client: redis.Redis,
) -> None:
    """Test that different IPs have independent rate limits."""
    app = FastAPI()

    app.add_middleware(
        RateLimitMiddleware,
        redis_client=redis_client,
        global_requests_per_minute=1,
        window_seconds=60,
    )

    @app.get("/test")
    def test_endpoint() -> dict[str, str]:
        return {"message": "ok"}

    client = TestClient(app)

    response1 = client.get("/test", headers={"X-Forwarded-For": "192.168.1.1"})
    assert response1.status_code == status.HTTP_200_OK

    response2 = client.get("/test", headers={"X-Forwarded-For": "192.168.1.2"})
    assert response2.status_code == status.HTTP_200_OK

    await redis_client.flushdb()
