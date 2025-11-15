from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import Update
from fakeredis.aioredis import FakeRedis

from backend.core.config import Settings
from bot_runtime.runtime import BotRuntime


@pytest.mark.asyncio
async def test_start_command_authenticates_and_persists_state(
    bot_settings: Settings, fake_redis: FakeRedis
) -> None:
    async def backend_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "access_token": "token-abcdef-123456",
                "token_type": "bearer",
                "expires_at": datetime.now(UTC).isoformat(),
            },
        )

    transport = httpx.MockTransport(backend_handler)
    async with httpx.AsyncClient(
        transport=transport, base_url=str(bot_settings.backend_base_url)
    ) as client:
        runtime = BotRuntime(bot_settings, http_client=client, redis=fake_redis)
        await runtime.startup()
        try:
            assert runtime.bot is not None and runtime.dispatcher is not None

            update = Update.model_validate(
                {
                    "update_id": 1,
                    "message": {
                        "message_id": 1,
                        "date": int(datetime.now(UTC).timestamp()),
                        "chat": {"id": 100, "type": "private"},
                        "from": {"id": 55, "is_bot": False, "first_name": "Ada"},
                        "text": "/start",
                        "entities": [{"offset": 0, "length": 6, "type": "bot_command"}],
                    },
                }
            )

            with patch(
                "aiogram.types.message.Message.answer",
                new_callable=AsyncMock,
            ) as mock_answer:
                await runtime.dispatcher.feed_update(runtime.bot, update)

                mock_answer.assert_awaited()

            key = StorageKey(bot_id=runtime.bot.id or 0, chat_id=100, user_id=55)
            data = await runtime.dispatcher.storage.get_data(key)
            assert data["access_token"] == "token-abcdef-123456"
        finally:
            await runtime.shutdown()
