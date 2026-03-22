"""Telegram client adapter using aiogram."""

from __future__ import annotations

from aiogram import Bot

from src.application.ports.telegram_client import TelegramClient


class AiogramTelegramAdapter(TelegramClient):
    """Adapter wrapping aiogram Bot into the TelegramClient port."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_text(self, chat_id: int, text: str) -> int:
        msg = await self._bot.send_message(chat_id=chat_id, text=text)
        return msg.message_id  # type: ignore[return-value]

    async def send_text_to_topic(self, chat_id: int, topic_id: int, text: str) -> int:
        msg = await self._bot.send_message(
            chat_id=chat_id,
            message_thread_id=topic_id,
            text=text,
        )
        return msg.message_id  # type: ignore[return-value]

    async def create_topic(self, chat_id: int, title: str) -> int:
        # aiogram 3.x uses create_forum_topic
        forum = await self._bot.create_forum_topic(chat_id=chat_id, name=title)
        return forum.message_thread_id  # type: ignore[return-value]

    async def delete_topic(self, chat_id: int, topic_id: int) -> None:
        await self._bot.delete_forum_topic(chat_id=chat_id, message_thread_id=topic_id)

    async def close(self) -> None:
        await self._bot.session.close()
