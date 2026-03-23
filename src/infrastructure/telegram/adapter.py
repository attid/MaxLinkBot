"""Telegram client adapter using aiogram."""

from __future__ import annotations

import logging
from urllib.parse import parse_qs, urlparse

import aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile

from src.application.ports.telegram_client import TelegramClient

logger = logging.getLogger(__name__)

CHROME_DESKTOP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/134.0.0.0 Safari/537.36"
    ),
    "Referer": "https://max.ru/",
}

OPERA_ANDROID_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/134.0.0.0 Mobile Safari/537.36 OPR/83.0.0.0"
    ),
    "Referer": "https://max.ru/",
}

FIREFOX_ANDROID_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Android 14; Mobile; rv:136.0) Gecko/136.0 Firefox/136.0",
    "Referer": "https://max.ru/",
}


class AiogramTelegramAdapter(TelegramClient):
    """Adapter wrapping aiogram Bot into the TelegramClient port."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_text(self, chat_id: int, text: str) -> int:
        msg = await self._bot.send_message(chat_id=chat_id, text=text)
        return msg.message_id  # type: ignore[return-value]

    async def send_text_to_topic(self, chat_id: int, topic_id: int, text: str) -> int:
        logger.info(
            "telegram send_text_to_topic chat_id=%s topic_id=%s text_len=%s",
            chat_id,
            topic_id,
            len(text),
        )
        msg = await self._bot.send_message(
            chat_id=chat_id,
            message_thread_id=topic_id,
            text=text,
        )
        return msg.message_id  # type: ignore[return-value]

    async def send_photo_to_topic(
        self,
        chat_id: int,
        topic_id: int,
        photo_url: str,
        caption: str,
    ) -> int:
        logger.info(
            "telegram send_photo_to_topic chat_id=%s topic_id=%s url_len=%s caption_len=%s",
            chat_id,
            topic_id,
            len(photo_url),
            len(caption),
        )
        msg = await self._bot.send_photo(
            chat_id=chat_id,
            message_thread_id=topic_id,
            photo=photo_url,
            caption=caption,
        )
        return msg.message_id  # type: ignore[return-value]

    async def send_audio_to_topic(
        self,
        chat_id: int,
        topic_id: int,
        audio_url: str,
        caption: str,
    ) -> int:
        logger.info(
            "telegram send_audio_to_topic chat_id=%s topic_id=%s url_len=%s caption_len=%s",
            chat_id,
            topic_id,
            len(audio_url),
            len(caption),
        )
        try:
            audio_bytes = await self._download_file_bytes(audio_url)
            msg = await self._bot.send_audio(
                chat_id=chat_id,
                message_thread_id=topic_id,
                audio=BufferedInputFile(audio_bytes, filename="audio.mp3"),
                caption=caption,
            )
        except Exception as exc:
            logger.warning(
                "telegram send_audio_to_topic file upload preparation failed chat_id=%s topic_id=%s",
                chat_id,
                topic_id,
                exc_info=True,
            )
            raise TelegramBadRequest(
                method=self._bot.send_audio,
                message="failed to get HTTP URL content",
            ) from exc
        return msg.message_id  # type: ignore[return-value]

    async def send_photo(self, chat_id: int, image_bytes: bytes) -> int:
        msg = await self._bot.send_photo(
            chat_id=chat_id,
            photo=BufferedInputFile(image_bytes, filename="qr.png"),
        )
        return msg.message_id  # type: ignore[return-value]

    async def create_topic(self, chat_id: int, title: str) -> int:
        # aiogram 3.x uses create_forum_topic
        logger.info("telegram create_topic chat_id=%s title=%r", chat_id, title)
        forum = await self._bot.create_forum_topic(chat_id=chat_id, name=title)
        logger.info(
            "telegram create_topic success chat_id=%s title=%r topic_id=%s",
            chat_id,
            title,
            forum.message_thread_id,
        )
        return forum.message_thread_id  # type: ignore[return-value]

    async def topic_exists(self, chat_id: int, topic_id: int) -> bool:
        logger.info("telegram topic_exists probe chat_id=%s topic_id=%s", chat_id, topic_id)
        try:
            probe = await self._bot.send_message(
                chat_id=chat_id,
                message_thread_id=topic_id,
                text=".",
            )
        except TelegramBadRequest as exc:
            logger.info(
                "telegram topic_exists missing chat_id=%s topic_id=%s error=%s",
                chat_id,
                topic_id,
                exc,
            )
            return False

        try:
            await self._bot.delete_message(chat_id=chat_id, message_id=probe.message_id)
        except TelegramBadRequest as exc:
            logger.warning(
                "telegram topic_exists delete probe failed chat_id=%s topic_id=%s message_id=%s error=%s",
                chat_id,
                topic_id,
                probe.message_id,
                exc,
            )

        logger.info("telegram topic_exists confirmed chat_id=%s topic_id=%s", chat_id, topic_id)
        return True

    async def delete_topic(self, chat_id: int, topic_id: int) -> None:
        await self._bot.delete_forum_topic(chat_id=chat_id, message_thread_id=topic_id)

    async def close(self) -> None:
        await self._bot.session.close()

    async def _download_file_bytes(self, url: str) -> bytes:
        last_error: Exception | None = None
        for headers in self._download_header_profiles(url):
            try:
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.get(url) as response:
                        response.raise_for_status()
                        return await response.read()
            except aiohttp.ClientResponseError as exc:
                last_error = exc
                logger.info(
                    "telegram download failed status=%s url=%s ua=%s",
                    exc.status,
                    url,
                    headers.get("User-Agent", ""),
                )
                continue
        if last_error is not None:
            raise last_error
        raise RuntimeError("download failed without attempts")

    def _download_header_profiles(self, url: str) -> list[dict[str, str]]:
        src_ag = parse_qs(urlparse(url).query).get("srcAg", [""])[0].upper()
        profiles: list[dict[str, str]] = []

        def add(headers: dict[str, str]) -> None:
            if headers not in profiles:
                profiles.append(headers)

        if "OPERA_MOBILE" in src_ag:
            add(OPERA_ANDROID_HEADERS)
        elif "GECKO" in src_ag:
            add(FIREFOX_ANDROID_HEADERS)
        else:
            add(CHROME_DESKTOP_HEADERS)

        add(CHROME_DESKTOP_HEADERS)
        add(OPERA_ANDROID_HEADERS)
        add(FIREFOX_ANDROID_HEADERS)
        return profiles
