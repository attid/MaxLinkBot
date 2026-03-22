"""Refresh/Reconcile service — full implementation for MLB-004."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
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

logger = logging.getLogger(__name__)


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

    async def reconcile(self, telegram_user_id: int, force_recreate: bool = False) -> None:
        """Run full reconcile for a user.

        1. Verify binding is active.
        2. Fetch MAX personal chats.
        3. For each chat: save/update MAX chat record.
        4. Compare MAX chats with topic mappings.
        5. Create missing topics with backfill.
        6. Optionally force recreate all topics with backfill.
        """
        binding = await self._binding_repo.get(telegram_user_id)
        if binding is None:
            raise ValueError(f"No binding for user {telegram_user_id}")
        logger.info("reconcile started telegram_user_id=%s", telegram_user_id)

        max_client = self._max_client_factory(binding.telegram_user_id, binding.max_session_data)
        try:
            await max_client.start()  # type: ignore[attr-defined]
            max_chats_raw = await max_client.list_personal_chats()
            logger.info(
                "reconcile fetched MAX chats telegram_user_id=%s count=%s raw_ids=%s",
                telegram_user_id,
                len(max_chats_raw),
                [chat.get("max_chat_id") for chat in max_chats_raw],
            )
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
                logger.info(
                    "reconcile saved MAX chat telegram_user_id=%s max_chat_id=%s title=%r",
                    telegram_user_id,
                    max_chat_id,
                    chat.title,
                )

            # Get existing topics for this user
            existing_topics = await self._topic_repo.find_by_user(telegram_user_id)
            existing_by_chat = {t.max_chat_id: t for t in existing_topics}
            logger.info(
                "reconcile existing topics telegram_user_id=%s count=%s existing_chat_ids=%s",
                telegram_user_id,
                len(existing_topics),
                list(existing_by_chat.keys()),
            )

            # Determine topics to create
            for max_chat_id in max_chat_ids:
                existing_topic = existing_by_chat.get(max_chat_id)
                if existing_topic is None or force_recreate:
                    logger.info(
                        "reconcile creating topic telegram_user_id=%s max_chat_id=%s force_recreate=%s",
                        telegram_user_id,
                        max_chat_id,
                        force_recreate,
                    )
                    await self._create_topic_with_backfill(
                        telegram_user_id, max_chat_id, max_client
                    )
                    continue

                logger.info(
                    "reconcile topic already exists telegram_user_id=%s max_chat_id=%s topic_id=%s",
                    telegram_user_id,
                    max_chat_id,
                    existing_topic.telegram_topic_id,
                )
        except AuthError:
            logger.exception("reconcile auth error telegram_user_id=%s", telegram_user_id)
            raise
        except Exception:
            logger.exception("reconcile unexpected error telegram_user_id=%s", telegram_user_id)
            raise
        finally:
            logger.info("reconcile closing MAX client telegram_user_id=%s", telegram_user_id)
            await max_client.close()

    async def _create_topic_with_backfill(
        self,
        telegram_user_id: int,
        max_chat_id: str,
        max_client: MaxClient,
    ) -> None:
        """Create a Telegram topic and backfill recent messages."""
        # Create topic in Telegram
        chat = await self._max_chat_repo.get(max_chat_id)
        raw_title = chat.title if chat else ""
        title = raw_title.strip() or f"Chat {max_chat_id}"
        logger.info(
            "reconcile create_topic start telegram_user_id=%s max_chat_id=%s title=%r",
            telegram_user_id,
            max_chat_id,
            title,
        )
        topic_id = await self._telegram.create_topic(chat_id=telegram_user_id, title=title)
        logger.info(
            "reconcile create_topic success telegram_user_id=%s max_chat_id=%s topic_id=%s",
            telegram_user_id,
            max_chat_id,
            topic_id,
        )

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
        logger.info(
            "reconcile cursor fetch telegram_user_id=%s max_chat_id=%s count=%s",
            telegram_user_id,
            max_chat_id,
            len(messages),
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
            logger.exception(
                "reconcile backfill auth error telegram_user_id=%s max_chat_id=%s",
                telegram_user_id,
                max_chat_id,
            )
            return
        except Exception:
            logger.exception(
                "reconcile backfill unexpected error telegram_user_id=%s max_chat_id=%s",
                telegram_user_id,
                max_chat_id,
            )
            raise

        logger.info(
            "reconcile backfill fetched telegram_user_id=%s max_chat_id=%s count=%s",
            telegram_user_id,
            max_chat_id,
            len(messages),
        )

        for msg in messages:
            text = self._render_backfill_message(msg)
            logger.info(
                "reconcile backfill deliver telegram_user_id=%s max_chat_id=%s topic_id=%s message_keys=%s",
                telegram_user_id,
                max_chat_id,
                topic_id,
                sorted(msg.keys()),
            )
            await self._telegram.send_text_to_topic(
                chat_id=telegram_user_id,
                topic_id=topic_id,
                text=text,
            )

    def _render_backfill_message(self, msg: dict[str, object]) -> str:
        sender_name = str(msg.get("sender_name") or "Unknown").strip()
        raw_time = msg.get("time")
        if raw_time:
            timestamp = datetime.fromtimestamp(int(raw_time) / 1000, tz=UTC)
            formatted_time = timestamp.strftime("%d.%m.%y %H:%M")
        else:
            formatted_time = "??.??.?? ??:??"

        prefix = f"[{sender_name} {formatted_time}]"
        msg_type = str(msg.get("type") or "text")
        if msg_type == "text":
            body = str(msg.get("text") or "")
        else:
            body = f"[{msg_type}]: {msg.get('description', 'Unsupported content')}"
        return f"{prefix}\n{body}".strip()
