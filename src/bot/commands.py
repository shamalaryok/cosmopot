"""Bot command registration utilities."""

from __future__ import annotations

from collections.abc import Sequence

from aiogram import Bot
from aiogram.types import BotCommand

BOT_COMMANDS: tuple[BotCommand, ...] = (
    BotCommand(command="start", description="Start the assistant"),
    BotCommand(command="menu", description="Show available actions"),
    BotCommand(command="profile", description="View your profile"),
    BotCommand(command="generate", description="Create AI-generated visuals"),
    BotCommand(command="subscribe", description="Manage subscription"),
    BotCommand(command="history", description="See recent generations"),
    BotCommand(command="balance", description="Check remaining credits"),
    BotCommand(command="help", description="Show usage instructions"),
)


def get_bot_commands() -> Sequence[BotCommand]:
    return BOT_COMMANDS


async def setup_bot_commands(bot: Bot) -> None:
    """Register the bot command list shown in the Telegram UI."""

    await bot.set_my_commands(list(BOT_COMMANDS))
