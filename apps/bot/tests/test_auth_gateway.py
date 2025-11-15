from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from aiogram.types import User

from backend.services.telegram import TelegramLoginPayload
from bot_runtime.services.auth import TelegramAuthGateway


@pytest.mark.asyncio
async def test_auth_gateway_signs_payload_correctly() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        captured.update(payload)
        return httpx.Response(
            status_code=200,
            json={
                "access_token": "token-1234567890",
                "token_type": "bearer",
                "expires_at": datetime.now(UTC).isoformat(),
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://backend.test"
    ) as client:
        gateway = TelegramAuthGateway(
            http_client=client,
            bot_token="super-secret-token",
            login_ttl_seconds=60,
        )
        user = User(id=42, is_bot=False, first_name="Ada")
        result = await gateway.authenticate(user)
        assert result.access_token == "token-1234567890"

    payload = TelegramLoginPayload.model_validate(captured)
    data_check_string = "\n".join(
        f"{key}={value}" for key, value in payload.data_check_items()
    )
    expected_hash = hmac.new(
        hashlib.sha256(b"super-secret-token").digest(),
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    assert captured["hash"] == expected_hash
