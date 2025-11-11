from __future__ import annotations

from datetime import UTC, datetime

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from structlog.stdlib import BoundLogger

from bot_runtime.services.auth import (
    BotAuthenticationError,
    TelegramAuthGateway,
)

__all__ = ["router"]

router = Router(name="commands")


@router.message(CommandStart())
async def handle_start_command(
    message: Message,
    state: FSMContext,
    auth_client: TelegramAuthGateway,
    logger: BoundLogger,
) -> None:
    """Authenticate the Telegram user via the backend and welcome them."""

    if message.from_user is None:
        await message.answer("This bot works only in private chats.")
        return

    logger = logger.bind(command="/start", telegram_id=message.from_user.id)
    logger.info("start_command_received")

    try:
        result = await auth_client.authenticate(message.from_user)
    except BotAuthenticationError as exc:
        logger.warning(
            "authentication_failed", reason=str(exc), status_code=exc.status_code
        )
        await message.answer(
            "❌ We could not authenticate you right now. Please try again later.",
        )
        return

    await state.update_data(
        access_token=result.access_token,
        token_type=result.token_type,
        expires_at=result.expires_at.isoformat(),
        refreshed_at=datetime.now(UTC).isoformat(),
    )

    logger.info(
        "authentication_succeeded",
        expires_at=result.expires_at.isoformat(),
        token_preview=result.preview,
    )

    preview = result.preview
    await message.answer(
        "✅ Authentication complete!\n"
        "Use the issued token to access the backend services.\n"
        f"Token: <code>{preview}</code>",
        parse_mode="HTML",
    )
