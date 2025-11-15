from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from structlog.stdlib import BoundLogger

__all__ = ["ErrorHandlingMiddleware"]


Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class ErrorHandlingMiddleware(BaseMiddleware):
    """Catch unhandled exceptions from handlers, log them, and notify the user."""

    def __init__(self, logger: BoundLogger) -> None:
        super().__init__()
        self._logger = logger

    async def __call__(
        self,
        handler: Handler,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as exc:  # pragma: no cover - exercised via integration tests
            message = _resolve_message(event, data)
            chat_id = message.chat.id if message is not None else None
            self._logger.exception(
                "bot_handler_exception",
                chat_id=chat_id,
                exc_info=exc,
            )
            if message is not None:
                try:
                    await message.answer(
                        "⚠️ An unexpected error occurred. Please try again later.",
                    )
                except (
                    Exception
                ):  # pragma: no cover - network issues should not fail tests
                    self._logger.warning("failed_to_notify_user", chat_id=chat_id)
            return None


def _resolve_message(
    event: TelegramObject,
    data: dict[str, Any] | None,
) -> Message | None:
    if isinstance(event, Message):
        return event

    if data is not None:
        candidate = data.get("event_message")
        if isinstance(candidate, Message):
            return candidate

    return None
