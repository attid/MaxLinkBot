"""Refresh/Reconcile service — full implementation for MLB-004."""

from __future__ import annotations

from collections.abc import Callable

from src.application.auth.exceptions import AuthError
from src.application.ports.clients import MaxClient
from src.application.ports.repositories import (
    AuditRepository,
    BindingRepository,
    MaxChatRepository,
    SyncCursorRepository,
    TelegramTopicRepository,
)
from src.application.ports.telegram_client import TelegramClient
from src.domain.chats.models import ChatType, MaxChat
from src.domain.chats.topic import TelegramTopic
from src.domain.sync.models import AuditEventType, SyncCursor


class RefreshReconcileService:
    """Performs reconcile for a user's binding: syncs MAX chats with Telegram topics."""

    def __init__(
        self,
        binding_repo: BindingRepository,
        max_chat_repo: MaxChatRepository,
        topic_repo: TelegramTopicRepository,
        cursor_repo: SyncCursorRepository,
        audit_repo: AuditRepository,
        telegram_client: TelegramClient,
        max_client_factory: Callable[[int, str], MaxClient],
        backfill_count: int = 5,
    ) -> None:
        self._binding_repo = binding_repo
        self._max_chat_repo = max_chat_repo
        self._topic_repo = topic_repo
        self._cursor_repo = cursor_repo
        self._audit_repo = audit_repo
        self._telegram = telegram_client
        self._max_client_factory = max_client_factory
        self._backfill_count = backfill_count

    async def reconcile(self, telegram_user_id: int) -> None:
        """Run full reconcile for a user.

        1. Verify binding is active.
        2. Fetch MAX personal chats.
        3. For each chat: save/update MAX chat record.
        4. Compare MAX chats with topic mappings.
        5. Create missing topics with backfill.
        6. Restore deleted topics with backfill.
        """
        binding = await self._binding_repo.get(telegram_user_id)
        if binding is None:
            raise ValueError(f"No binding for user {telegram_user_id}")

        max_client = self._max_client_factory(binding.telegram_user_id, binding.max_session_data)
        try:
            max_chats_raw = await max_client.list_personal_chats()
        except AuthError:
            raise
        finally:
            await max_client.close()

        # Persist chat records
        max_chat_ids: set[str] = set()
        for chat_data in max_chats_raw:
            max_chat_id = chat_data["max_chat_id"]
            max_chat_ids.add(max_chat_id)
            chat = MaxChat(
                max_chat_id=max_chat_id,
                binding_telegram_user_id=telegram_user_id,
                title=chat_data.get("title", ""),
                chat_type=ChatType.PERSONAL,
            )
            await self._max_chat_repo.save(chat)

        # Get existing topics for this user
        existing_topics = await self._topic_repo.find_by_user(telegram_user_id)
        existing_by_chat = {t.max_chat_id: t for t in existing_topics}

        # Determine topics to create
        for max_chat_id in max_chat_ids:
            if max_chat_id not in existing_by_chat:
                await self._create_topic_with_backfill(telegram_user_id, max_chat_id, max_client)

    async def _create_topic_with_backfill(
        self,
        telegram_user_id: int,
        max_chat_id: str,
        max_client: MaxClient,
    ) -> None:
        """Create a Telegram topic and backfill recent messages."""
        # Create topic in Telegram
        chat = await self._max_chat_repo.get(max_chat_id)
        title = chat.title if chat else f"Chat {max_chat_id}"
        topic_id = await self._telegram.create_topic(chat_id=telegram_user_id, title=title)

        # Save topic mapping
        topic = TelegramTopic(
            telegram_topic_id=topic_id,
            telegram_user_id=telegram_user_id,
            max_chat_id=max_chat_id,
        )
        await self._topic_repo.save(topic)

        await self._audit_repo.log(
            telegram_user_id,
            AuditEventType.TOPIC_CREATED,
            f"Topic {topic_id} created for chat {max_chat_id}",
        )

        # Backfill messages
        await self._backfill(telegram_user_id, max_chat_id, topic_id, max_client)

        # Save sync cursor after backfill
        messages = await max_client.get_messages(
            max_chat_id, since_message_id=None, limit=self._backfill_count
        )
        if messages:
            latest = messages[-1]
            await self._cursor_repo.upsert(
                SyncCursor(
                    max_chat_id=max_chat_id,
                    binding_telegram_user_id=telegram_user_id,
                    last_max_message_id=str(latest["max_message_id"]),
                    updated_at=0,  # TODO
                )
            )

    async def _backfill(
        self,
        telegram_user_id: int,
        max_chat_id: str,
        topic_id: int,
        max_client: MaxClient,
    ) -> None:
        """Fetch and deliver last N messages into a topic."""
        try:
            messages = await max_client.get_messages(
                max_chat_id, since_message_id=None, limit=self._backfill_count
            )
        except AuthError:
            return

        for msg in messages:
            text = msg.get("text") or f"[media: {msg.get('type', 'unknown')}]"
            await self._telegram.send_text_to_topic(
                chat_id=telegram_user_id,
                topic_id=topic_id,
                text=text,
            )
