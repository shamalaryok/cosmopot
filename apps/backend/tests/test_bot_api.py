from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import AsyncClient


@pytest.mark.asyncio()
async def test_webhook_bot_runtime_not_initialized(
    app: FastAPI,
    async_client: AsyncClient,
) -> None:
    """Test webhook returns 503 when bot runtime is not initialized."""
    # Ensure bot_runtime is None
    app.state.bot_runtime = None

    response = await async_client.post(
        "/api/v1/bot/webhook",
        json={"update_id": 123, "message": {"text": "test"}},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Bot runtime is not initialised"


@pytest.mark.asyncio()
async def test_webhook_invalid_secret_token(
    app: FastAPI,
    async_client: AsyncClient,
) -> None:
    """Test webhook returns 401 when secret token is invalid."""
    # Mock bot runtime
    bot_runtime = MagicMock()
    bot_runtime.bot = MagicMock()
    bot_runtime.dispatcher = MagicMock()
    app.state.bot_runtime = bot_runtime

    # Mock settings with webhook secret
    from pydantic import SecretStr

    settings = app.state.settings
    settings.telegram_webhook_secret_token = SecretStr("correct-secret")

    # Send request with wrong secret
    response = await async_client.post(
        "/api/v1/bot/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
        json={"update_id": 123, "message": {"text": "test"}},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid webhook secret"


@pytest.mark.asyncio()
async def test_webhook_no_secret_when_configured(
    app: FastAPI,
    async_client: AsyncClient,
) -> None:
    """Test webhook returns 401 when secret is required but not provided."""
    # Mock bot runtime
    bot_runtime = MagicMock()
    bot_runtime.bot = MagicMock()
    bot_runtime.dispatcher = MagicMock()
    app.state.bot_runtime = bot_runtime

    # Mock settings with webhook secret
    from pydantic import SecretStr

    settings = app.state.settings
    settings.telegram_webhook_secret_token = SecretStr("required-secret")

    # Send request without secret header
    response = await async_client.post(
        "/api/v1/bot/webhook",
        json={"update_id": 123, "message": {"text": "test"}},
    )
    assert response.status_code == 401


@pytest.mark.asyncio()
async def test_webhook_invalid_update_payload(
    app: FastAPI,
    async_client: AsyncClient,
) -> None:
    """Test webhook returns 422 for invalid Telegram update payload."""
    # Mock bot runtime
    bot_runtime = MagicMock()
    bot_runtime.bot = MagicMock()
    bot_runtime.dispatcher = MagicMock()
    app.state.bot_runtime = bot_runtime

    # No secret configured
    settings = app.state.settings
    settings.telegram_webhook_secret_token = None

    # Send invalid update (missing required fields)
    response = await async_client.post(
        "/api/v1/bot/webhook",
        json={"invalid": "payload"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid update payload"


@pytest.mark.asyncio()
async def test_webhook_success(
    app: FastAPI,
    async_client: AsyncClient,
) -> None:
    """Test webhook successfully processes valid Telegram update."""
    # Mock bot runtime with async dispatcher
    bot_mock = MagicMock()
    dispatcher_mock = AsyncMock()
    dispatcher_mock.feed_update = AsyncMock()

    bot_runtime = MagicMock()
    bot_runtime.bot = bot_mock
    bot_runtime.dispatcher = dispatcher_mock
    app.state.bot_runtime = bot_runtime

    # No secret configured for simplicity
    settings = app.state.settings
    settings.telegram_webhook_secret_token = None

    # Valid Telegram update
    valid_update: dict[str, Any] = {
        "update_id": 123456789,
        "message": {
            "message_id": 1,
            "from": {
                "id": 12345,
                "is_bot": False,
                "first_name": "Test",
            },
            "chat": {
                "id": 12345,
                "type": "private",
            },
            "date": 1234567890,
            "text": "Hello bot!",
        },
    }

    response = await async_client.post(
        "/api/v1/bot/webhook",
        json=valid_update,
    )
    assert response.status_code == 204

    # Verify feed_update was called
    dispatcher_mock.feed_update.assert_called_once()


@pytest.mark.asyncio()
async def test_webhook_success_with_valid_secret(
    app: FastAPI,
    async_client: AsyncClient,
) -> None:
    """Test webhook succeeds with correct secret token."""
    # Mock bot runtime with async dispatcher
    bot_mock = MagicMock()
    dispatcher_mock = AsyncMock()
    dispatcher_mock.feed_update = AsyncMock()

    bot_runtime = MagicMock()
    bot_runtime.bot = bot_mock
    bot_runtime.dispatcher = dispatcher_mock
    app.state.bot_runtime = bot_runtime

    # Configure secret
    from pydantic import SecretStr

    settings = app.state.settings
    settings.telegram_webhook_secret_token = SecretStr("valid-secret")

    # Valid Telegram update
    valid_update: dict[str, Any] = {
        "update_id": 987654321,
        "message": {
            "message_id": 2,
            "from": {
                "id": 54321,
                "is_bot": False,
                "first_name": "User",
            },
            "chat": {
                "id": 54321,
                "type": "private",
            },
            "date": 1234567890,
            "text": "Test message",
        },
    }

    response = await async_client.post(
        "/api/v1/bot/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "valid-secret"},
        json=valid_update,
    )
    assert response.status_code == 204
    dispatcher_mock.feed_update.assert_called_once()
