from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile

from src.infrastructure.telegram.adapter import AiogramTelegramAdapter


@pytest.mark.asyncio
async def test_send_audio_to_topic_downloads_and_uploads_when_url_is_rejected() -> None:
    bot = MagicMock()
    bot.send_audio = AsyncMock(return_value=MagicMock(message_id=123))

    adapter = AiogramTelegramAdapter(bot)
    adapter._download_file_bytes = AsyncMock(return_value=b"audio-bytes")  # type: ignore[attr-defined]

    message_id = await adapter.send_audio_to_topic(
        chat_id=1,
        topic_id=2,
        audio_url="https://example.com/audio",
        caption="[Igor 1 22.03.26 22:30]",
    )

    assert message_id == 123
    adapter._download_file_bytes.assert_awaited_once_with("https://example.com/audio")  # type: ignore[attr-defined]
    bot.send_audio.assert_awaited_once()
    send_call = bot.send_audio.await_args_list[0]
    assert send_call.kwargs["chat_id"] == 1
    assert send_call.kwargs["message_thread_id"] == 2
    assert send_call.kwargs["caption"] == "[Igor 1 22.03.26 22:30]"
    assert isinstance(send_call.kwargs["audio"], BufferedInputFile)


@pytest.mark.asyncio
async def test_send_audio_to_topic_reraises_when_download_fails_after_url_rejection() -> None:
    bot = MagicMock()
    bot.send_audio = AsyncMock()

    adapter = AiogramTelegramAdapter(bot)
    adapter._download_file_bytes = AsyncMock(side_effect=RuntimeError("download failed"))  # type: ignore[attr-defined]

    with pytest.raises(TelegramBadRequest, match="failed to get HTTP URL content"):
        await adapter.send_audio_to_topic(
            chat_id=1,
            topic_id=2,
            audio_url="https://example.com/audio",
            caption="[Igor 1 22.03.26 22:30]",
        )
    bot.send_audio.assert_not_awaited()


def test_download_header_profiles_prefers_opera_android_for_chrome_opera_mobile() -> None:
    adapter = AiogramTelegramAdapter(MagicMock())

    profiles = adapter._download_header_profiles(  # type: ignore[attr-defined]
        "https://example.com/audio?srcAg=CHROME_OPERA_MOBILE"
    )

    assert profiles[0]["User-Agent"].endswith("OPR/83.0.0.0")


def test_download_header_profiles_prefers_chrome_for_chrome_srcag() -> None:
    adapter = AiogramTelegramAdapter(MagicMock())

    profiles = adapter._download_header_profiles(  # type: ignore[attr-defined]
        "https://example.com/audio?srcAg=CHROME"
    )

    assert "Chrome/134.0.0.0 Safari/537.36" in profiles[0]["User-Agent"]
