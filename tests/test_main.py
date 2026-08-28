from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest

from src import main as main_module

BOT_TOKEN = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"


async def test_configure_bot_commands_registers_supported_commands() -> None:
    bot = AsyncMock()

    await main_module.configure_bot_commands(bot)

    bot.set_my_commands.assert_awaited_once()
    commands = bot.set_my_commands.await_args.args[0]
    assert [command.command for command in commands] == [
        "start",
        "resync",
        "mute",
        "unmute",
    ]


async def test_create_bot_uses_standard_telegram_api_by_default() -> None:
    bot = main_module.create_bot(token=BOT_TOKEN, api_url=None)

    assert bot.session.api.api_url(BOT_TOKEN, "getMe") == (
        f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
    )
    await bot.session.close()


async def test_create_bot_uses_custom_api_for_methods_and_files() -> None:
    bot = main_module.create_bot(
        token=BOT_TOKEN,
        api_url=" https://api.mtlminiapps.us/ ",
    )

    assert bot.session.api.api_url(BOT_TOKEN, "getMe") == (
        f"https://api.mtlminiapps.us/bot{BOT_TOKEN}/getMe"
    )
    assert bot.session.api.file_url(BOT_TOKEN, "documents/file.txt") == (
        f"https://api.mtlminiapps.us/file/bot{BOT_TOKEN}/documents/file.txt"
    )
    assert bot.session.api.is_local is False
    await bot.session.close()


def test_settings_reads_telegram_api_url_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("TELEGRAM_API_URL", "https://api.mtlminiapps.us")

    settings = main_module.Settings(telegram_bot_token=BOT_TOKEN)

    assert settings.telegram_api_url == "https://api.mtlminiapps.us"


def test_log_startup_includes_image_commit_sha(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("GIT_COMMIT_SHA", "abc123def456")

    with caplog.at_level(logging.INFO, logger="src.main"):
        main_module.log_startup()

    assert "MaxLinkBot starting git_commit_sha=abc123def456" in caplog.text
