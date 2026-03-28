"""Inbound sync service — MAX messages delivered to Telegram topics."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Awaitable
from datetime import UTC, datetime
from collections.abc import Callable
from typing import Any

from aiogram.exceptions import TelegramBadRequest

from src.application.auth.exceptions import AuthError
from src.application.polling.max_runtime import MaxClientRuntimeRegistry
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
        catchup_interval_seconds: float = 3600.0,
        reconcile_user: Callable[[int], Awaitable[None]] | None = None,
        shared_runtime: MaxClientRuntimeRegistry | None = None,
        reconnect_storm_threshold: int = 5,
        reconnect_storm_window_seconds: float = 300.0,
        time_func: Callable[[], float] | None = None,
    ) -> None:
        self._binding_repo = binding_repo
        self._max_chat_repo = max_chat_repo
        self._topic_repo = topic_repo
        self._message_link_repo = message_link_repo
        self._cursor_repo = cursor_repo
        self._audit_repo = audit_repo
        self._telegram = telegram_client
        self._max_client_factory = max_client_factory
        self._catchup_interval_seconds = catchup_interval_seconds
        self._reconcile_user = reconcile_user
        self._shared_runtime = shared_runtime
        self._reconnect_storm_threshold = reconnect_storm_threshold
        self._reconnect_storm_window_seconds = reconnect_storm_window_seconds
        self._time_func = time_func or time.time
        self._recent_reconnects: deque[float] = deque()
        self._live_client: MaxClient | None = None
        self._live_session_owner_id: int | None = None
        self._live_session_data: str | None = None
        self._last_catchup_at: float | None = None

    async def poll_user(self, telegram_user_id: int) -> None:
        """Poll all MAX chats for a user and deliver new messages to Telegram."""
        binding = await self._binding_repo.get(telegram_user_id)
        if binding is None:
            await self.close()
            return

        max_client = await self._ensure_live_client(
            binding.telegram_user_id,
            binding.max_session_data,
        )
        buffered_messages = await max_client.drain_buffered_messages()
        for msg in buffered_messages:
            await self._process_live_message(telegram_user_id, msg)

        reconnect_detected = await max_client.consume_reconnect_event()
        if reconnect_detected:
            await self._register_reconnect_event()
            recovered = await self._recover_after_reconnect(telegram_user_id, max_client)
            if not recovered:
                await self._catch_up_user(telegram_user_id, max_client, include_discovery=False)
            self._last_catchup_at = time.time()
            return

        if self._shared_runtime is not None:
            dirty_chat_ids = await self._shared_runtime.get_dirty_chats(telegram_user_id)
            for max_chat_id in dirty_chat_ids:
                await self._poll_chat_with_client(telegram_user_id, max_chat_id, max_client)

        now = time.time()
        if self._last_catchup_at is None or (
            now - self._last_catchup_at >= self._catchup_interval_seconds
        ):
            await self._catch_up_user(telegram_user_id, max_client, include_discovery=True)
            self._last_catchup_at = now

    async def poll_chat(self, telegram_user_id: int, max_chat_id: str) -> None:
        """Poll a specific chat for new messages and deliver to Telegram."""
        binding = await self._binding_repo.get(telegram_user_id)
        if binding is None:
            return

        max_client = await self._ensure_live_client(
            binding.telegram_user_id,
            binding.max_session_data,
        )
        await self._poll_chat_with_client(telegram_user_id, max_chat_id, max_client)

    async def close(self) -> None:
        if self._shared_runtime is not None and self._live_session_owner_id is not None:
            await self._shared_runtime.close_user(self._live_session_owner_id)
        elif self._live_client is not None:
            await self._live_client.close()
        self._live_client = None
        self._live_session_owner_id = None
        self._live_session_data = None
        self._last_catchup_at = None

    async def _ensure_live_client(self, session_owner_id: int, session_data: str) -> MaxClient:
        if self._shared_runtime is not None:
            client = await self._shared_runtime.get_client(session_owner_id, session_data)
            self._live_client = client
            self._live_session_owner_id = session_owner_id
            self._live_session_data = session_data
            return client

        if (
            self._live_client is not None
            and self._live_session_owner_id == session_owner_id
            and self._live_session_data == session_data
        ):
            return self._live_client

        if self._live_client is not None:
            await self._live_client.close()

        max_client = self._max_client_factory(session_owner_id, session_data)
        await max_client.start()  # type: ignore[attr-defined]
        self._live_client = max_client
        self._live_session_owner_id = session_owner_id
        self._live_session_data = session_data
        return max_client

    async def _catch_up_user(
        self,
        telegram_user_id: int,
        max_client: MaxClient,
        include_discovery: bool,
    ) -> None:
        if include_discovery and self._reconcile_user is not None:
            await self._reconcile_user(telegram_user_id)

        topics = await self._topic_repo.find_by_user(telegram_user_id)
        for topic in topics:
            await self._poll_chat_with_client(telegram_user_id, topic.max_chat_id, max_client)

    async def _recover_after_reconnect(self, telegram_user_id: int, max_client: MaxClient) -> bool:
        if self._shared_runtime is None:
            return False

        candidate_chat_ids: list[str] = []

        dirty_chat_ids = await self._shared_runtime.get_dirty_chats(telegram_user_id)
        candidate_chat_ids.extend(dirty_chat_ids)

        last_active_chat_id = await self._shared_runtime.get_last_active_chat(telegram_user_id)
        if last_active_chat_id and last_active_chat_id not in candidate_chat_ids:
            candidate_chat_ids.append(last_active_chat_id)

        if not candidate_chat_ids:
            return False

        delivered_any = False
        for max_chat_id in candidate_chat_ids:
            delivered = await self._poll_chat_with_client(
                telegram_user_id,
                max_chat_id,
                max_client,
            )
            delivered_any = delivered_any or delivered

        return delivered_any

    async def _register_reconnect_event(self) -> None:
        now = self._time_func()
        window_start = now - self._reconnect_storm_window_seconds
        self._recent_reconnects.append(now)
        while self._recent_reconnects and self._recent_reconnects[0] < window_start:
            self._recent_reconnects.popleft()

        if len(self._recent_reconnects) < self._reconnect_storm_threshold:
            return

        if self._shared_runtime is not None and self._live_session_owner_id is not None:
            await self._shared_runtime.close_user(self._live_session_owner_id)
        elif self._live_client is not None:
            await self._live_client.close()

        raise RuntimeError(
            "MAX reconnect storm detected; runtime closed for fresh restart"
        )

    async def _process_live_message(self, telegram_user_id: int, msg: dict[str, Any]) -> None:
        if self._should_ignore_live_message(msg):
            return

        max_chat_id = str(msg["chat_id"])
        topic = await self._topic_repo.get_by_user_and_chat(telegram_user_id, max_chat_id)
        if topic is None:
            if self._reconcile_user is not None:
                await self._reconcile_user(telegram_user_id)
            return

        delivered = await self._deliver_message(
            telegram_user_id,
            max_chat_id,
            topic.telegram_topic_id,
            msg,
        )
        if delivered:
            if self._shared_runtime is not None:
                await self._shared_runtime.clear_dirty_chat(telegram_user_id, max_chat_id)
            await self._cursor_repo.upsert(
                SyncCursor(
                    max_chat_id=max_chat_id,
                    binding_telegram_user_id=telegram_user_id,
                    last_max_message_id=str(msg["max_message_id"]),
                    updated_at=int(time.time()),
                )
            )

    async def _poll_chat_with_client(
        self, telegram_user_id: int, max_chat_id: str, max_client: MaxClient
    ) -> bool:
        # Get topic mapping
        topic = await self._topic_repo.get_by_user_and_chat(telegram_user_id, max_chat_id)
        if topic is None:
            return False

        # Get sync cursor
        cursor = await self._cursor_repo.get(max_chat_id, telegram_user_id)
        since_id = cursor.last_max_message_id if cursor else None

        # Fetch new messages from MAX
        messages = await max_client.get_messages(max_chat_id, since_message_id=since_id, limit=50)

        if not messages:
            return False

        latest_processed_id: str | None = None
        delivered_any = False
        for msg in messages:
            delivered = await self._deliver_message(
                telegram_user_id,
                max_chat_id,
                topic.telegram_topic_id,
                msg,
            )
            if delivered:
                latest_processed_id = str(msg["max_message_id"])
                delivered_any = True

        if latest_processed_id is not None:
            await self._cursor_repo.upsert(
                SyncCursor(
                    max_chat_id=max_chat_id,
                    binding_telegram_user_id=telegram_user_id,
                    last_max_message_id=latest_processed_id,
                    updated_at=int(time.time()),
                )
            )
        return delivered_any

    async def _deliver_message(
        self,
        telegram_user_id: int,
        max_chat_id: str,
        topic_id: int,
        msg: dict[str, Any],
    ) -> bool:
        """Deliver a single MAX message to Telegram topic."""
        max_msg_id = str(msg["max_message_id"])

        # Idempotency: skip already delivered
        if await self._message_link_repo.exists_max_message(max_msg_id, max_chat_id):
            return True

        try:
            tg_msg_id = await self._send_message_to_telegram(
                telegram_user_id=telegram_user_id,
                topic_id=topic_id,
                msg=msg,
            )
        except Exception as exc:
            await self._audit_repo.log(
                telegram_user_id,
                AuditEventType.DELIVERY_FAILED,
                f"Failed to deliver {max_msg_id}: {exc}",
            )
            return False

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
        return True

    async def _send_message_to_telegram(
        self,
        telegram_user_id: int,
        topic_id: int,
        msg: dict[str, Any],
    ) -> int:
        msg_type = self._normalize_rendered_message_type(
            msg.get("type"),
            msg.get("description"),
            msg.get("text"),
            msg.get("chat_id"),
        )
        media_url = str(msg.get("media_url") or "").strip()
        prefix = self._render_prefix(msg)

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

        text = self._render_message(msg)
        return await self._telegram.send_text_to_topic(
            chat_id=telegram_user_id,
            topic_id=topic_id,
            text=text,
        )

    def _render_message(self, msg: dict[str, Any]) -> str:
        """Render a MAX message to Telegram text. Fallback for unsupported types."""
        msg_type = self._normalize_rendered_message_type(
            msg.get("type"),
            msg.get("description"),
            msg.get("text"),
            msg.get("chat_id"),
        )
        prefix = self._render_prefix(msg)
        text_body = str(msg.get("text") or "").strip()

        if str(msg_type).lower() == "text" or text_body:
            body = text_body
            return f"{prefix}\n{body}".strip()

        # Fallback for unsupported media types
        description = self._normalize_rendered_description(msg_type, msg.get("description"))
        body = f"[{msg_type}]: {description}"
        return f"{prefix}\n{body}".strip()

    def _render_prefix(self, msg: dict[str, Any]) -> str:
        sender_name = str(msg.get("sender_name") or "Unknown").strip()
        sender_id = str(msg.get("sender_id") or "UnknownID").strip()
        raw_time = msg.get("time")
        if raw_time:
            timestamp = datetime.fromtimestamp(int(raw_time) / 1000, tz=UTC)
            formatted_time = timestamp.strftime("%d.%m.%y %H:%M")
        else:
            formatted_time = "??.??.?? ??:??"
        return f"[{sender_name} {sender_id} {formatted_time}]"

    def _should_ignore_live_message(self, msg: dict[str, Any]) -> bool:
        chat_id = str(msg.get("chat_id") or "").strip()
        msg_type = str(msg.get("type") or "").strip().lower()
        text_body = str(msg.get("text") or "").strip()

        if text_body:
            return False
        if chat_id == "0" and msg_type == "user":
            return False
        return msg_type in {"user", "system", "service"}

    def _normalize_rendered_message_type(
        self,
        raw_type: Any,
        raw_description: Any,
        raw_text: Any,
        raw_chat_id: Any,
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

    def _normalize_rendered_description(self, msg_type: str, raw_description: Any) -> str:
        description = str(raw_description or "").strip()
        if description:
            return description
        if msg_type == "media":
            return "Media message"
        return "Unsupported content"

    def _should_fallback_from_media_url(self, exc: TelegramBadRequest) -> bool:
        return "failed to get http url content" in str(exc).lower()
