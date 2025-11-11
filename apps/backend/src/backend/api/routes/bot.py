from __future__ import annotations

import structlog
from aiogram.types import Update
from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import ValidationError

from backend.core.config import Settings
from bot_runtime.runtime import BotRuntime

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/bot", tags=["bot"])

_logger = structlog.get_logger(__name__)


@router.post("/webhook", status_code=status.HTTP_204_NO_CONTENT)
async def telegram_webhook(request: Request) -> Response:
    """Receive Telegram webhook updates and forward them to the dispatcher."""

    runtime: BotRuntime | None = getattr(request.app.state, "bot_runtime", None)
    if runtime is None or runtime.bot is None or runtime.dispatcher is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bot runtime is not initialised",
        )

    settings: Settings = request.app.state.settings
    secret = settings.telegram_webhook_secret_token
    if secret is not None:
        header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if header != secret.get_secret_value():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook secret",
            )

    try:
        payload = await request.json()
    except Exception as exc:  # pragma: no cover - FastAPI handles malformed JSON
        _logger.warning("webhook_invalid_json", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload"
        ) from exc

    try:
        update = Update.model_validate(payload)
    except ValidationError as exc:
        _logger.warning("webhook_validation_error", errors=exc.errors())
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid update payload",
        ) from exc

    await runtime.dispatcher.feed_update(runtime.bot, update)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
