from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from structlog.stdlib import BoundLogger

__all__ = ["LoggingMiddleware"]


Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class LoggingMiddleware(BaseMiddleware):
    """Middleware responsible for structured logging of every incoming update."""

    def __init__(self, logger: BoundLogger) -> None:
        super().__init__()
        self._logger = logger

    async def __call__(
        self,
        handler: Handler,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        event_type = type(event).__name__
        update_id = getattr(event, "update_id", None)
        self._logger.info(
            "bot_update_received",
            event_type=event_type,
            update_id=update_id,
        )
        try:
            result = await handler(event, data)
        except Exception:
            self._logger.exception(
                "bot_update_failed",
                event_type=event_type,
                update_id=update_id,
            )
            raise
        self._logger.info(
            "bot_update_processed",
            event_type=event_type,
            update_id=update_id,
        )
        return result
