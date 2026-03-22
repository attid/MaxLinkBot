"""Outbound sync service — Telegram messages delivered to MAX topics."""

from __future__ import annotations

import time
from typing import Any

from src.application.auth.exceptions import AuthError
from src.application.ports.repositories import (
    AuditRepository,
    BindingRepository,
    MessageLinkRepository,
    TelegramTopicRepository,
)
from src.domain.messages.models import Direction, MessageLink
from src.domain.sync.models import AuditEventType


class OutboundSyncService:
    """Delivers Telegram topic messages to MAX chats."""

    def __init__(
        self,
        binding_repo: BindingRepository,
        topic_repo: TelegramTopicRepository,
        message_link_repo: MessageLinkRepository,
        audit_repo: AuditRepository,
        max_client_factory: Any,  # (session_data: str) -> MaxClient
    ) -> None:
        self._binding_repo = binding_repo
        self._topic_repo = topic_repo
        self._message_link_repo = message_link_repo
        self._audit_repo = audit_repo
        self._max_client_factory = max_client_factory

    async def deliver(
        self,
        telegram_user_id: int,
        telegram_topic_id: int,
        text: str,
        reply_to_max_message_id: str | None = None,
    ) -> str:
        """Deliver a Telegram message to its mapped MAX chat.

        Returns:
            The sent message's MAX message ID.

        Raises:
            AuthError: if the user's MAX session is invalid.
        """
        binding = await self._binding_repo.get(telegram_user_id)
        if binding is None:
            raise AuthError("No binding for user")

        topic = await self._topic_repo.get_by_user_and_topic(telegram_user_id, telegram_topic_id)
        if topic is None:
            raise AuthError("No topic mapping")

        max_client = self._max_client_factory(binding.max_session_data)
        try:
            max_msg_id = await max_client.send_message(topic.max_chat_id, text)
        except AuthError:
            raise
        except Exception as exc:
            await self._audit_repo.log(
                telegram_user_id,
                AuditEventType.DELIVERY_FAILED,
                f"Outbound delivery failed: {exc}",
            )
            raise
        finally:
            await max_client.close()

        # Record delivery
        await self._message_link_repo.save(
            MessageLink(
                max_message_id=max_msg_id,
                telegram_message_id=None,  # telegram_message_id not tracked for outbound
                telegram_user_id=telegram_user_id,
                max_chat_id=topic.max_chat_id,
                direction=Direction.TELEGRAM_TO_MAX,
                delivered_at=int(time.time()),
            )
        )

        await self._audit_repo.log(
            telegram_user_id,
            AuditEventType.DELIVERY_SUCCESS,
            f"Outbound delivered to {topic.max_chat_id}",
        )

        return max_msg_id
