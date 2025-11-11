from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from structlog.stdlib import BoundLogger

from bot_runtime.services.auth import TelegramAuthGateway

__all__ = ["DependencyInjectionMiddleware"]


Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class DependencyInjectionMiddleware(BaseMiddleware):
    """Populate handler arguments with shared dependencies."""

    def __init__(
        self, *, auth_client: TelegramAuthGateway, logger: BoundLogger
    ) -> None:
        super().__init__()
        self._auth_client = auth_client
        self._logger = logger

    async def __call__(
        self,
        handler: Handler,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data.setdefault("auth_client", self._auth_client)
        data.setdefault("logger", self._bind_logger(event))
        message = _extract_message(event)
        if message is not None:
            data.setdefault("event_message", message)
        return await handler(event, data)

    def _bind_logger(self, event: TelegramObject) -> BoundLogger:
        message = _extract_message(event)
        chat_id = message.chat.id if message is not None else None
        user_id = message.from_user.id if message and message.from_user else None
        return self._logger.bind(chat_id=chat_id, user_id=user_id)


def _extract_message(event: TelegramObject) -> Message | None:
    if isinstance(event, Message):
        return event
    return None
