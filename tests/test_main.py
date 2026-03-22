from __future__ import annotations

from unittest.mock import AsyncMock

from src.main import configure_bot_commands


async def test_configure_bot_commands_registers_start() -> None:
    bot = AsyncMock()

    await configure_bot_commands(bot)

    bot.set_my_commands.assert_awaited_once()
    commands = bot.set_my_commands.await_args.args[0]
    assert len(commands) == 2
    assert commands[0].command == "start"
    assert commands[1].command == "resync"
