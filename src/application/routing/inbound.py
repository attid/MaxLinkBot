"""Inbound sync service — MAX messages delivered to Telegram topics."""

from __future__ import annotations

import time
from typing import Any

from src.application.auth.exceptions import AuthError
from src.application.ports.repositories import (
    AuditRepository,
    BindingRepository,
    MaxChatRepository,
    MessageLinkRepository,
    SyncCursorRepository,
    TelegramTopicRepository,
)
from src.application.ports.telegram_client import TelegramClient
from src.domain.messages.models import Direction, MessageLink
from src.domain.sync.models import AuditEventType, SyncCursor


class InboundSyncService:
    """Polls MAX for new messages and delivers them to Telegram topics."""

    def __init__(
        self,
        binding_repo: BindingRepository,
        max_chat_repo: MaxChatRepository,
        topic_repo: TelegramTopicRepository,
        message_link_repo: MessageLinkRepository,
        cursor_repo: SyncCursorRepository,
        audit_repo: AuditRepository,
        telegram_client: TelegramClient,
        max_client_factory: Any,  # (session_data: str) -> MaxClient
    ) -> None:
        self._binding_repo = binding_repo
        self._max_chat_repo = max_chat_repo
        self._topic_repo = topic_repo
        self._message_link_repo = message_link_repo
        self._cursor_repo = cursor_repo
        self._audit_repo = audit_repo
        self._telegram = telegram_client
        self._max_client_factory = max_client_factory

    async def poll_user(self, telegram_user_id: int) -> None:
        """Poll all MAX chats for a user and deliver new messages to Telegram."""
        binding = await self._binding_repo.get(telegram_user_id)
        if binding is None:
            return

        max_client = self._max_client_factory(binding.max_session_data)
        try:
            await max_client.list_personal_chats()
        except AuthError:
            raise
        finally:
            await max_client.close()

    async def poll_chat(self, telegram_user_id: int, max_chat_id: str) -> None:
        """Poll a specific chat for new messages and deliver to Telegram."""
        # Get topic mapping
        topic = await self._topic_repo.get_by_user_and_chat(telegram_user_id, max_chat_id)
        if topic is None:
            return

        # Get sync cursor
        cursor = await self._cursor_repo.get(max_chat_id, telegram_user_id)
        since_id = cursor.last_max_message_id if cursor else None

        # Fetch new messages from MAX
        binding = await self._binding_repo.get(telegram_user_id)
        if binding is None:
            return

        max_client = self._max_client_factory(binding.max_session_data)
        try:
            messages = await max_client.get_messages(
                max_chat_id, since_message_id=since_id, limit=50
            )
        except AuthError:
            raise
        finally:
            await max_client.close()

        if not messages:
            return

        # Deliver each message
        for msg in messages:
            await self._deliver_message(telegram_user_id, max_chat_id, topic.telegram_topic_id, msg)

        # Update cursor
        latest_id = messages[-1]["max_message_id"]
        await self._cursor_repo.upsert(
            SyncCursor(
                max_chat_id=max_chat_id,
                binding_telegram_user_id=telegram_user_id,
                last_max_message_id=str(latest_id),
                updated_at=int(time.time()),
            )
        )

    async def _deliver_message(
        self,
        telegram_user_id: int,
        max_chat_id: str,
        topic_id: int,
        msg: dict[str, Any],
    ) -> None:
        """Deliver a single MAX message to Telegram topic."""
        max_msg_id = str(msg["max_message_id"])

        # Idempotency: skip already delivered
        if await self._message_link_repo.exists_max_message(max_msg_id, max_chat_id):
            return

        text = self._render_message(msg)
        try:
            tg_msg_id = await self._telegram.send_text_to_topic(
                chat_id=telegram_user_id,
                topic_id=topic_id,
                text=text,
            )
        except Exception as exc:
            await self._audit_repo.log(
                telegram_user_id,
                AuditEventType.DELIVERY_FAILED,
                f"Failed to deliver {max_msg_id}: {exc}",
            )
            return

        # Record delivery
        await self._message_link_repo.save(
            MessageLink(
                max_message_id=max_msg_id,
                telegram_message_id=tg_msg_id,
                telegram_user_id=telegram_user_id,
                max_chat_id=max_chat_id,
                direction=Direction.MAX_TO_TELEGRAM,
                delivered_at=int(time.time()),
            )
        )

    def _render_message(self, msg: dict[str, Any]) -> str:
        """Render a MAX message to Telegram text. Fallback for unsupported types."""
        msg_type = msg.get("type", "unknown")

        if msg_type == "text":
            return msg.get("text", "")

        # Fallback for unsupported media types
        return f"[{msg_type}]: {msg.get('description', 'Unsupported content')}"
