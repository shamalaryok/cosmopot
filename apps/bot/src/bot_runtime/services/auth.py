from __future__ import annotations

import hashlib
import hmac
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from aiogram.types import User
from pydantic import BaseModel, ConfigDict, ValidationError

from backend.services.telegram import TelegramLoginPayload

__all__ = [
    "BotAuthenticationError",
    "TelegramAuthGateway",
    "TelegramAuthResult",
]


class BotAuthenticationError(RuntimeError):
    """Raised when the bot fails to authenticate the user with the backend."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class TelegramAuthResult(BaseModel):
    """Response returned by the backend after a successful Telegram auth flow."""

    access_token: str
    token_type: str
    expires_at: datetime

    model_config = ConfigDict(coerce_numbers_to_str=True)

    @property
    def preview(self) -> str:
        """Return a truncated preview of the access token for logging purposes."""

        if len(self.access_token) <= 12:
            return self.access_token
        return f"{self.access_token[:4]}…{self.access_token[-4:]}"


class TelegramAuthGateway:
    """Client responsible for exchanging Telegram identities for backend JWTs."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        bot_token: str,
        login_ttl_seconds: int,
    ) -> None:
        if not bot_token:
            raise ValueError("bot_token must be provided for TelegramAuthGateway")
        if login_ttl_seconds <= 0:
            raise ValueError("login_ttl_seconds must be positive")

        self._http = http_client
        self._login_ttl_seconds = login_ttl_seconds
        self._secret = hashlib.sha256(bot_token.encode("utf-8")).digest()

    async def authenticate(self, user: User) -> TelegramAuthResult:
        """Authenticate the given Telegram user via the backend service."""

        payload = self._build_payload(user)

        try:
            response = await self._http.post(
                "/api/v1/auth/telegram",
                json=payload.model_dump(mode="json"),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            text = exc.response.text.strip() or exc.response.reason_phrase
            raise BotAuthenticationError(
                text, status_code=exc.response.status_code
            ) from exc
        except (
            httpx.HTTPError
        ) as exc:  # pragma: no cover - network level errors are rare in tests
            raise BotAuthenticationError(
                "Failed to call backend authentication endpoint"
            ) from exc

        try:
            result = TelegramAuthResult.model_validate(response.json())
        except (
            TypeError,
            ValidationError,
        ) as exc:  # pragma: no cover - validated upstream in tests
            raise BotAuthenticationError(
                "Received invalid authentication payload from backend"
            ) from exc

        return result

    def _build_payload(self, user: User) -> TelegramLoginPayload:
        auth_date = int(time.time())

        raw_payload: dict[str, Any] = {
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "username": user.username,
            "photo_url": None,
            "auth_date": auth_date,
        }

        # Remove fields that are None to match Telegram's canonical form.
        filtered = {
            key: value for key, value in raw_payload.items() if value is not None
        }
        signature = self._sign(filtered)

        return TelegramLoginPayload.model_validate({**filtered, "hash": signature})

    def _sign(self, payload: dict[str, Any]) -> str:
        items = []
        for key, value in sorted(payload.items()):
            items.append(f"{key}={self._stringify(value)}")
        data_check_string = "\n".join(items)
        digest = hmac.new(
            self._secret, data_check_string.encode("utf-8"), hashlib.sha256
        )
        return digest.hexdigest()

    @staticmethod
    def _stringify(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, datetime):
            return str(int(value.replace(tzinfo=UTC).timestamp()))
        return str(value)
