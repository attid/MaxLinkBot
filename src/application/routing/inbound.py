"""Inbound sync service — MAX messages delivered to Telegram topics."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from collections.abc import Callable
from typing import Any

from src.application.auth.exceptions import AuthError
from src.application.ports.clients import MaxClient
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
        max_client_factory: Callable[[int, str], MaxClient],
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

        max_client = self._max_client_factory(binding.telegram_user_id, binding.max_session_data)
        try:
            await max_client.start()  # type: ignore[attr-defined]
            chats = await max_client.list_personal_chats()
            for chat in chats:
                await self._poll_chat_with_client(
                    telegram_user_id, str(chat["max_chat_id"]), max_client
                )
        except AuthError:
            raise
        finally:
            await max_client.close()

    async def poll_chat(self, telegram_user_id: int, max_chat_id: str) -> None:
        """Poll a specific chat for new messages and deliver to Telegram."""
        binding = await self._binding_repo.get(telegram_user_id)
        if binding is None:
            return

        max_client = self._max_client_factory(binding.telegram_user_id, binding.max_session_data)
        try:
            await max_client.start()  # type: ignore[attr-defined]
            await self._poll_chat_with_client(telegram_user_id, max_chat_id, max_client)
        except AuthError:
            raise
        finally:
            await max_client.close()

    async def _poll_chat_with_client(
        self, telegram_user_id: int, max_chat_id: str, max_client: MaxClient
    ) -> None:
        # Get topic mapping
        topic = await self._topic_repo.get_by_user_and_chat(telegram_user_id, max_chat_id)
        if topic is None:
            return

        # Get sync cursor
        cursor = await self._cursor_repo.get(max_chat_id, telegram_user_id)
        since_id = cursor.last_max_message_id if cursor else None

        # Fetch new messages from MAX
        messages = await max_client.get_messages(max_chat_id, since_message_id=since_id, limit=50)

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
        prefix = self._render_prefix(msg)

        if msg_type == "text":
            body = msg.get("text", "")
            return f"{prefix}\n{body}".strip()

        # Fallback for unsupported media types
        body = f"[{msg_type}]: {msg.get('description', 'Unsupported content')}"
        return f"{prefix}\n{body}".strip()

    def _render_prefix(self, msg: dict[str, Any]) -> str:
        sender_name = (msg.get("sender_name") or "Unknown").strip()
        raw_time = msg.get("time")
        if raw_time:
            timestamp = datetime.fromtimestamp(int(raw_time) / 1000, tz=UTC)
            formatted_time = timestamp.strftime("%d.%m.%y %H:%M")
        else:
            formatted_time = "??.??.?? ??:??"
        return f"[{sender_name} {formatted_time}]"
