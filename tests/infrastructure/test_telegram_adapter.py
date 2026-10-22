from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.enums import InputMediaType
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile

from src.infrastructure.telegram.adapter import (
    TELEGRAM_MEDIA_CAPTION_LIMIT,
    TELEGRAM_VIDEO_LIMIT_BYTES,
    AiogramTelegramAdapter,
)


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


@pytest.mark.asyncio
async def test_send_video_to_topic_downloads_small_video_and_uploads() -> None:
    bot = MagicMock()
    bot.send_video = AsyncMock(return_value=MagicMock(message_id=456))

    adapter = AiogramTelegramAdapter(bot)
    adapter._probe_remote_file_size = AsyncMock(return_value=1_215_665)  # type: ignore[attr-defined]
    adapter._download_file_bytes = AsyncMock(return_value=b"video-bytes")  # type: ignore[attr-defined]

    message_id = await adapter.send_video_to_topic(
        chat_id=1,
        topic_id=2,
        video_url="https://example.com/circle.mp4",
        caption="[Igor 1 22.03.26 22:30]",
    )

    assert message_id == 456
    adapter._probe_remote_file_size.assert_awaited_once_with(  # type: ignore[attr-defined]
        "https://example.com/circle.mp4"
    )
    adapter._download_file_bytes.assert_awaited_once_with(  # type: ignore[attr-defined]
        "https://example.com/circle.mp4"
    )
    send_call = bot.send_video.await_args_list[0]
    assert send_call.kwargs["chat_id"] == 1
    assert send_call.kwargs["message_thread_id"] == 2
    assert send_call.kwargs["caption"] == "[Igor 1 22.03.26 22:30]"
    assert send_call.kwargs["supports_streaming"] is True
    assert isinstance(send_call.kwargs["video"], BufferedInputFile)


@pytest.mark.asyncio
async def test_send_video_to_topic_splits_long_caption_without_losing_text() -> None:
    bot = MagicMock()
    bot.send_video = AsyncMock(return_value=MagicMock(message_id=456))
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=457))
    caption = "x" * 1617

    adapter = AiogramTelegramAdapter(bot)
    adapter._probe_remote_file_size = AsyncMock(return_value=1_215_665)  # type: ignore[attr-defined]
    adapter._download_file_bytes = AsyncMock(return_value=b"video-bytes")  # type: ignore[attr-defined]

    message_id = await adapter.send_video_to_topic(
        chat_id=1,
        topic_id=2,
        video_url="https://example.com/circle.mp4",
        caption=caption,
    )

    assert message_id == 456
    assert bot.send_video.await_args.kwargs["caption"] == caption[:1024]
    bot.send_message.assert_awaited_once_with(
        chat_id=1,
        message_thread_id=2,
        text=caption[1024:],
    )


@pytest.mark.asyncio
async def test_send_photo_to_topic_chunks_caption_remainder_by_text_limit() -> None:
    bot = MagicMock()
    bot.send_photo = AsyncMock(return_value=MagicMock(message_id=123))
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=124))
    caption = "x" * (1024 + 4096 + 1)

    adapter = AiogramTelegramAdapter(bot)

    message_id = await adapter.send_photo_to_topic(
        chat_id=1,
        topic_id=2,
        photo_url="https://example.com/photo.jpg",
        caption=caption,
    )

    assert message_id == 123
    assert bot.send_photo.await_args.kwargs["caption"] == caption[:1024]
    assert [call.kwargs["text"] for call in bot.send_message.await_args_list] == [
        caption[1024 : 1024 + 4096],
        caption[1024 + 4096 :],
    ]


@pytest.mark.asyncio
async def test_send_video_to_topic_preserves_telegram_api_error() -> None:
    bot = MagicMock()
    telegram_error = TelegramBadRequest(
        method=bot.send_video,  # type: ignore[reportArgumentType]
        message="message caption is too long",
    )
    bot.send_video = AsyncMock(side_effect=telegram_error)

    adapter = AiogramTelegramAdapter(bot)
    adapter._probe_remote_file_size = AsyncMock(return_value=1_215_665)  # type: ignore[attr-defined]
    adapter._download_file_bytes = AsyncMock(return_value=b"video-bytes")  # type: ignore[attr-defined]

    with pytest.raises(TelegramBadRequest) as raised:
        await adapter.send_video_to_topic(
            chat_id=1,
            topic_id=2,
            video_url="https://example.com/circle.mp4",
            caption="short caption",
        )

    assert raised.value is telegram_error


@pytest.mark.asyncio
async def test_send_video_to_topic_rejects_large_video_before_download() -> None:
    bot = MagicMock()
    bot.send_video = AsyncMock()

    adapter = AiogramTelegramAdapter(bot)
    adapter._probe_remote_file_size = AsyncMock(return_value=196_464_264)  # type: ignore[attr-defined]
    adapter._download_file_bytes = AsyncMock()  # type: ignore[attr-defined]

    with pytest.raises(TelegramBadRequest, match="failed to get HTTP URL content"):
        await adapter.send_video_to_topic(
            chat_id=1,
            topic_id=2,
            video_url="https://example.com/large.mp4",
            caption="[Igor 1 22.03.26 22:30]",
        )

    adapter._download_file_bytes.assert_not_awaited()  # type: ignore[attr-defined]
    bot.send_video.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_document_to_topic_downloads_and_uploads() -> None:
    bot = MagicMock()
    bot.send_document = AsyncMock(return_value=MagicMock(message_id=321))

    adapter = AiogramTelegramAdapter(bot)
    adapter._download_file_bytes = AsyncMock(return_value=b"document-bytes")  # type: ignore[attr-defined]

    message_id = await adapter.send_document_to_topic(
        chat_id=1,
        topic_id=2,
        document_url="https://example.com/spec.pdf",
        filename="spec.pdf",
        caption="[Igor 1 22.03.26 22:30]",
    )

    assert message_id == 321
    adapter._download_file_bytes.assert_awaited_once_with("https://example.com/spec.pdf")  # type: ignore[attr-defined]
    bot.send_document.assert_awaited_once()
    send_call = bot.send_document.await_args_list[0]
    assert send_call.kwargs["chat_id"] == 1
    assert send_call.kwargs["message_thread_id"] == 2
    assert send_call.kwargs["caption"] == "[Igor 1 22.03.26 22:30]"
    assert isinstance(send_call.kwargs["document"], BufferedInputFile)


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


@pytest.mark.asyncio
async def test_send_media_group_to_topic_sends_album_with_caption_on_first_item() -> None:
    bot = MagicMock()
    bot.send_media_group = AsyncMock(
        return_value=[MagicMock(message_id=11), MagicMock(message_id=12), MagicMock(message_id=13)]
    )

    adapter = AiogramTelegramAdapter(bot)

    message_id = await adapter.send_media_group_to_topic(
        chat_id=1,
        topic_id=2,
        media=[
            {"type": "photo", "url": "https://example.com/1.jpg", "file_name": "photo.jpg"},
            {"type": "photo", "url": "https://example.com/2.jpg", "file_name": "photo.jpg"},
            {"type": "photo", "url": "https://example.com/3.jpg", "file_name": "photo.jpg"},
        ],
        caption="[Igor 1 22.03.26 22:30]\nalbum caption",
    )

    assert message_id == 11
    bot.send_media_group.assert_awaited_once()
    send_call = bot.send_media_group.await_args_list[0]
    assert send_call.kwargs["chat_id"] == 1
    assert send_call.kwargs["message_thread_id"] == 2
    media = send_call.kwargs["media"]
    assert [item.type for item in media] == [InputMediaType.PHOTO] * 3
    assert [item.media for item in media] == [
        "https://example.com/1.jpg",
        "https://example.com/2.jpg",
        "https://example.com/3.jpg",
    ]
    assert [item.caption for item in media] == ["[Igor 1 22.03.26 22:30]\nalbum caption", "", ""]


@pytest.mark.asyncio
async def test_send_media_group_to_topic_chunks_more_than_ten_items() -> None:
    bot = MagicMock()
    bot.send_media_group = AsyncMock(
        side_effect=[[MagicMock(message_id=21)], [MagicMock(message_id=22)]]
    )

    adapter = AiogramTelegramAdapter(bot)

    message_id = await adapter.send_media_group_to_topic(
        chat_id=1,
        topic_id=2,
        media=[
            {"type": "photo", "url": f"https://example.com/{index}.jpg", "file_name": "photo.jpg"}
            for index in range(12)
        ],
        caption="album",
    )

    assert message_id == 21
    assert bot.send_media_group.await_count == 2
    first_chunk = bot.send_media_group.await_args_list[0].kwargs["media"]
    second_chunk = bot.send_media_group.await_args_list[1].kwargs["media"]
    assert len(first_chunk) == 10
    assert len(second_chunk) == 2
    assert first_chunk[0].caption == "album"
    assert second_chunk[0].caption == ""


@pytest.mark.asyncio
async def test_send_media_group_to_topic_uploads_video_as_buffered_file() -> None:
    bot = MagicMock()
    bot.send_media_group = AsyncMock(
        return_value=[MagicMock(message_id=31), MagicMock(message_id=32)]
    )

    adapter = AiogramTelegramAdapter(bot)
    adapter._download_file_bytes = AsyncMock(return_value=b"video-bytes")  # type: ignore[attr-defined]
    adapter._probe_remote_file_size = AsyncMock(return_value=1024)  # type: ignore[attr-defined]

    await adapter.send_media_group_to_topic(
        chat_id=1,
        topic_id=2,
        media=[
            {"type": "photo", "url": "https://example.com/1.jpg", "file_name": "photo.jpg"},
            {"type": "video", "url": "https://example.com/2.mp4", "file_name": "video.mp4"},
        ],
        caption="album",
    )

    media = bot.send_media_group.await_args_list[0].kwargs["media"]
    assert [item.type for item in media] == [InputMediaType.PHOTO, InputMediaType.VIDEO]
    assert isinstance(media[1].media, BufferedInputFile)


@pytest.mark.asyncio
async def test_send_media_group_to_topic_rejects_oversized_video() -> None:
    bot = MagicMock()
    bot.send_media_group = AsyncMock(return_value=[MagicMock(message_id=31)])

    adapter = AiogramTelegramAdapter(bot)
    adapter._probe_remote_file_size = AsyncMock(return_value=TELEGRAM_VIDEO_LIMIT_BYTES + 1)  # type: ignore[attr-defined]

    with pytest.raises(TelegramBadRequest, match="failed to get HTTP URL content"):
        await adapter.send_media_group_to_topic(
            chat_id=1,
            topic_id=2,
            media=[
                {"type": "photo", "url": "https://example.com/1.jpg", "file_name": "photo.jpg"},
                {"type": "video", "url": "https://example.com/2.mp4", "file_name": "video.mp4"},
            ],
            caption="album",
        )

    bot.send_media_group.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_media_group_to_topic_continues_long_caption_as_text() -> None:
    bot = MagicMock()
    bot.send_media_group = AsyncMock(
        return_value=[MagicMock(message_id=41), MagicMock(message_id=42)]
    )
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=43))

    adapter = AiogramTelegramAdapter(bot)

    await adapter.send_media_group_to_topic(
        chat_id=1,
        topic_id=2,
        media=[
            {"type": "photo", "url": "https://example.com/1.jpg", "file_name": "photo.jpg"},
            {"type": "photo", "url": "https://example.com/2.jpg", "file_name": "photo.jpg"},
        ],
        caption="x" * (TELEGRAM_MEDIA_CAPTION_LIMIT + 10),
    )

    media = bot.send_media_group.await_args_list[0].kwargs["media"]
    assert len(media[0].caption) == TELEGRAM_MEDIA_CAPTION_LIMIT
    bot.send_message.assert_awaited_once_with(
        chat_id=1,
        message_thread_id=2,
        text="x" * 10,
    )
