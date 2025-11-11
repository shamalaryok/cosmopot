from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fakeredis.aioredis import FakeRedis
from pydantic import SecretStr

from backend.core.config import Settings


@pytest.fixture
async def fake_redis() -> AsyncIterator[FakeRedis]:
    client = FakeRedis(decode_responses=False)
    try:
        yield client
    finally:
        await client.close()


@pytest.fixture
def bot_settings() -> Settings:
    base = Settings()
    redis_settings = base.redis.model_copy(update={"url": "redis://localhost:6379/0"})
    return base.model_copy(
        update={
            "telegram_bot_token": SecretStr(
                "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
            ),
            "backend_base_url": "https://backend.test",
            "telegram_webhook_secret_token": SecretStr("secret-token"),
            "redis": redis_settings,
        }
    )
