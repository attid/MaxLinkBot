"""Refresh/Reconcile service — full implementation for MLB-004."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from collections.abc import Callable

from aiogram.exceptions import TelegramBadRequest

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

    async def reconcile(
        self,
        telegram_user_id: int,
        force_recreate: bool = False,
        target_max_chat_id: str | None = None,
    ) -> None:
        return await self._reconcile(
            telegram_user_id=telegram_user_id,
            force_recreate=force_recreate,
            target_max_chat_id=target_max_chat_id,
        )

    async def _reconcile(
        self,
        telegram_user_id: int,
        force_recreate: bool = False,
        target_max_chat_id: str | None = None,
    ) -> None:
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
            if target_max_chat_id is not None:
                max_chats_raw = self._resolve_target_chats(max_chats_raw, target_max_chat_id)
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

    def _resolve_target_chats(
        self, max_chats_raw: list[dict[str, object]], target_max_chat_id: str
    ) -> list[dict[str, object]]:
        exact_matches = [
            chat for chat in max_chats_raw if str(chat.get("max_chat_id") or "") == target_max_chat_id
        ]
        if exact_matches:
            return exact_matches

        participant_matches = [
            chat
            for chat in max_chats_raw
            if target_max_chat_id
            in [str(participant_id) for participant_id in chat.get("participant_ids", []) or []]
        ]
        if not participant_matches:
            raise ValueError(f"MAX chat not found for resync: {target_max_chat_id}")

        direct_matches = [
            chat
            for chat in participant_matches
            if len(chat.get("participant_ids", []) or []) <= 2
        ]
        if len(direct_matches) == 1:
            return direct_matches
        if len(participant_matches) == 1:
            return participant_matches

        matched_chat_ids = ", ".join(
            sorted(str(chat.get("max_chat_id") or "") for chat in participant_matches)
        )
        raise ValueError(
            f"MAX user {target_max_chat_id} matched multiple chats. Use one of chat IDs: {matched_chat_ids}"
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
            logger.info(
                "reconcile backfill deliver telegram_user_id=%s max_chat_id=%s topic_id=%s message_keys=%s",
                telegram_user_id,
                max_chat_id,
                topic_id,
                sorted(msg.keys()),
            )
            await self._send_backfill_message(
                telegram_user_id=telegram_user_id,
                topic_id=topic_id,
                msg=msg,
            )

    async def _send_backfill_message(
        self,
        telegram_user_id: int,
        topic_id: int,
        msg: dict[str, object],
    ) -> int:
        msg_type = self._normalize_rendered_message_type(
            msg.get("type"),
            msg.get("description"),
            msg.get("text"),
            msg.get("chat_id"),
        )
        media_url = str(msg.get("media_url") or "").strip()
        prefix = self._render_backfill_prefix(msg)

        if msg_type in {"photo", "image"} and media_url:
            try:
                return await self._telegram.send_photo_to_topic(
                    chat_id=telegram_user_id,
                    topic_id=topic_id,
                    photo_url=media_url,
                    caption=prefix,
                )
            except TelegramBadRequest as exc:
                if self._should_fallback_from_media_url(exc):
                    return await self._telegram.send_text_to_topic(
                        chat_id=telegram_user_id,
                        topic_id=topic_id,
                        text=f"{prefix}\n[photo]: {media_url}",
                    )
                raise
        if msg_type == "audio" and media_url:
            try:
                return await self._telegram.send_audio_to_topic(
                    chat_id=telegram_user_id,
                    topic_id=topic_id,
                    audio_url=media_url,
                    caption=prefix,
                )
            except TelegramBadRequest as exc:
                if self._should_fallback_from_media_url(exc):
                    return await self._telegram.send_text_to_topic(
                        chat_id=telegram_user_id,
                        topic_id=topic_id,
                        text=f"{prefix}\n[audio]: {media_url}",
                    )
                raise

        text = self._render_backfill_message(msg)
        return await self._telegram.send_text_to_topic(
            chat_id=telegram_user_id,
            topic_id=topic_id,
            text=text,
        )

    def _render_backfill_message(self, msg: dict[str, object]) -> str:
        prefix = self._render_backfill_prefix(msg)
        msg_type = self._normalize_rendered_message_type(
            msg.get("type"),
            msg.get("description"),
            msg.get("text"),
            msg.get("chat_id"),
        )
        if msg_type == "text":
            body = str(msg.get("text") or "")
        else:
            description = self._normalize_rendered_description(msg_type, msg.get("description"))
            body = f"[{msg_type}]: {description}"
        return f"{prefix}\n{body}".strip()

    def _render_backfill_prefix(self, msg: dict[str, object]) -> str:
        sender_name = str(msg.get("sender_name") or "Unknown").strip()
        sender_id = str(msg.get("sender_id") or "UnknownID").strip()
        raw_time = msg.get("time")
        if raw_time:
            timestamp = datetime.fromtimestamp(int(raw_time) / 1000, tz=UTC)
            formatted_time = timestamp.strftime("%d.%m.%y %H:%M")
        else:
            formatted_time = "??.??.?? ??:??"
        return f"[{sender_name} {sender_id} {formatted_time}]"

    def _normalize_rendered_message_type(
        self,
        raw_type: object,
        raw_description: object,
        raw_text: object,
        raw_chat_id: object,
    ) -> str:
        normalized_type = str(raw_type or "unknown").strip().lower()
        normalized_description = str(raw_description or "").strip().lower()
        text_body = str(raw_text or "").strip()
        chat_id = str(raw_chat_id or "").strip()

        if text_body:
            return "text"
        if chat_id == "0" and normalized_type == "user":
            return "media"

        if normalized_type in {"photo", "image", "picture"}:
            return "image"
        if normalized_type in {"video", "gif", "sticker", "file", "audio", "voice", "document"}:
            return normalized_type
        if normalized_type != "unknown":
            return normalized_type

        if normalized_description in {"photo", "image", "picture"}:
            return "image"
        if normalized_description in {"video", "gif", "sticker", "file", "audio", "voice", "document"}:
            return normalized_description
        return normalized_type

    def _normalize_rendered_description(self, msg_type: str, raw_description: object) -> str:
        description = str(raw_description or "").strip()
        if description:
            return description
        if msg_type == "media":
            return "Media message"
        return "Unsupported content"

    def _should_fallback_from_media_url(self, exc: TelegramBadRequest) -> bool:
        return "failed to get http url content" in str(exc).lower()
