from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from bot.commands import BOT_COMMANDS, get_bot_commands, setup_bot_commands


def test_get_bot_commands_matches_constant() -> None:
    assert tuple(get_bot_commands()) == BOT_COMMANDS


@pytest.mark.asyncio
async def test_setup_bot_commands_sets_expected_list() -> None:
    bot = AsyncMock()
    await setup_bot_commands(bot)
    bot.set_my_commands.assert_awaited_once()
    (commands,), _ = bot.set_my_commands.await_args
    assert len(commands) == len(BOT_COMMANDS)
    assert all(command in commands for command in BOT_COMMANDS)
