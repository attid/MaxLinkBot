"""Telegram client adapter using aiogram."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile

from src.application.ports.telegram_client import TelegramClient

logger = logging.getLogger(__name__)


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
