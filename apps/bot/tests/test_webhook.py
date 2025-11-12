from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from aiogram.types import Update
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI

from backend.api.routes.bot import router as bot_router
from backend.core.config import Settings
from bot_runtime.runtime import BotRuntime


@pytest.mark.asyncio
async def test_webhook_route_dispatches_update(
    bot_settings: Settings, fake_redis: FakeRedis
) -> None:
    async def backend_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "access_token": "token-xyz",
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
            # Мокируем сессию бота, чтобы предотвратить реальные API вызовы
            make_request_mock = AsyncMock(
                return_value={
                    "ok": True,
                    "result": {
                        "message_id": 123,
                        "date": int(datetime.now(UTC).timestamp()),
                        "chat": {"id": 200, "type": "private"},
                        "text": "Welcome! You are authenticated.",
                    },
                }
            )

            app = FastAPI()
            app.state.settings = bot_settings
            app.state.bot_runtime = runtime
            app.include_router(bot_router)

            update = Update.model_validate(
                {
                    "update_id": 77,
                    "message": {
                        "message_id": 10,
                        "date": int(datetime.now(UTC).timestamp()),
                        "chat": {"id": 200, "type": "private"},
                        "from": {"id": 88, "is_bot": False, "first_name": "Grace"},
                        "text": "/start",
                        "entities": [{"offset": 0, "length": 6, "type": "bot_command"}],
                    },
                }
            )

            token = bot_settings.telegram_webhook_secret_token
            assert token is not None
            headers = {
                "X-Telegram-Bot-Api-Secret-Token": token.get_secret_value()
            }

            asgi_transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=asgi_transport, base_url="http://testserver"
            ) as test_client:
                with patch.object(
                    runtime.bot.session, "make_request", new=make_request_mock
                ):
                    response = await test_client.post(
                        "/api/v1/bot/webhook",
                        json=update.model_dump(mode="json"),
                        headers=headers,
                    )

            assert response.status_code == httpx.codes.NO_CONTENT
            make_request_mock.assert_awaited()
        finally:
            await runtime.shutdown()
