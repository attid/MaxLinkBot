"""SQLite repository implementations."""

from __future__ import annotations

import time

from src.application.ports.repositories import (
    AuditRepository,
    BindingRepository,
    MaxChatRepository,
    MessageLinkRepository,
    SyncCursorRepository,
    TelegramTopicRepository,
)
from src.domain.bindings.models import Binding, BindingStatus
from src.domain.chats.models import MaxChat
from src.domain.chats.topic import TelegramTopic
from src.domain.messages.models import MessageLink
from src.domain.sync.models import AuditEvent, AuditEventType, SyncCursor
from src.infrastructure.persistence.connection import Database


class SqliteBindingRepository(BindingRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def get(self, telegram_user_id: int) -> Binding | None:
        row = await self._db.fetchone(
            "SELECT telegram_user_id, max_session_data, status, created_at, updated_at "
            "FROM user_bindings WHERE telegram_user_id = ?",
            telegram_user_id,
        )
        if row is None:
            return None
        return Binding(
            telegram_user_id=row["telegram_user_id"],
            max_session_data=row["max_session_data"],
            status=BindingStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def find_active(self) -> list[Binding]:
        rows = await self._db.fetchall(
            "SELECT telegram_user_id, max_session_data, status, created_at, updated_at "
            "FROM user_bindings WHERE status = 'active'",
        )
        return [
            Binding(
                telegram_user_id=row["telegram_user_id"],
                max_session_data=row["max_session_data"],
                status=BindingStatus(row["status"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    async def save(self, binding: Binding) -> None:
        await self._db.execute(  # type: ignore[reportAttributeAccessIssue]
            "INSERT OR REPLACE INTO user_bindings "
            "(telegram_user_id, max_session_data, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            binding.telegram_user_id,
            binding.max_session_data,
            binding.status.value,
            binding.created_at,
            binding.updated_at,
        )
        await self._db.commit()

    async def update_status(self, telegram_user_id: int, status: BindingStatus) -> None:
        await self._db.execute(  # type: ignore[reportAttributeAccessIssue]
            "UPDATE user_bindings SET status = ?, updated_at = ? WHERE telegram_user_id = ?",
            status.value,
            int(time.time()),
            telegram_user_id,
        )
        await self._db.commit()


class SqliteMaxChatRepository(MaxChatRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def get(self, max_chat_id: str) -> MaxChat | None:
        row = await self._db.fetchone(
            "SELECT max_chat_id, binding_telegram_user_id, title, chat_type "
            "FROM max_chats WHERE max_chat_id = ?",
            max_chat_id,
        )
        if row is None:
            return None
        return MaxChat(
            max_chat_id=row["max_chat_id"],
            binding_telegram_user_id=row["binding_telegram_user_id"],
            title=row["title"] or "",
            chat_type=row["chat_type"],
        )

    async def find_by_binding(self, binding_telegram_user_id: int) -> list[MaxChat]:
        rows = await self._db.fetchall(
            "SELECT max_chat_id, binding_telegram_user_id, title, chat_type "
            "FROM max_chats WHERE binding_telegram_user_id = ?",
            binding_telegram_user_id,
        )
        return [
            MaxChat(
                max_chat_id=r["max_chat_id"],
                binding_telegram_user_id=r["binding_telegram_user_id"],
                title=r["title"] or "",
                chat_type=r["chat_type"],
            )
            for r in rows
        ]

    async def save(self, chat: MaxChat) -> None:
        await self._db.execute(  # type: ignore[reportAttributeAccessIssue]
            "INSERT OR IGNORE INTO max_chats "
            "(max_chat_id, binding_telegram_user_id, title, chat_type) "
            "VALUES (?, ?, ?, ?)",
            chat.max_chat_id,
            chat.binding_telegram_user_id,
            chat.title,
            chat.chat_type.value,
        )
        await self._db.commit()


class SqliteTelegramTopicRepository(TelegramTopicRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def get_by_user_and_chat(
        self, telegram_user_id: int, max_chat_id: str
    ) -> TelegramTopic | None:
        row = await self._db.fetchone(
            "SELECT telegram_topic_id, telegram_user_id, max_chat_id "
            "FROM telegram_topics "
            "WHERE telegram_user_id = ? AND max_chat_id = ?",
            telegram_user_id,
            max_chat_id,
        )
        if row is None:
            return None
        return TelegramTopic(
            telegram_topic_id=row["telegram_topic_id"],
            telegram_user_id=row["telegram_user_id"],
            max_chat_id=row["max_chat_id"],
        )

    async def get_by_user_and_topic(
        self, telegram_user_id: int, telegram_topic_id: int
    ) -> TelegramTopic | None:
        row = await self._db.fetchone(
            "SELECT telegram_topic_id, telegram_user_id, max_chat_id "
            "FROM telegram_topics "
            "WHERE telegram_user_id = ? AND telegram_topic_id = ?",
            telegram_user_id,
            telegram_topic_id,
        )
        if row is None:
            return None
        return TelegramTopic(
            telegram_topic_id=row["telegram_topic_id"],
            telegram_user_id=row["telegram_user_id"],
            max_chat_id=row["max_chat_id"],
        )

    async def find_by_user(self, telegram_user_id: int) -> list[TelegramTopic]:
        rows = await self._db.fetchall(
            "SELECT telegram_topic_id, telegram_user_id, max_chat_id "
            "FROM telegram_topics WHERE telegram_user_id = ?",
            telegram_user_id,
        )
        return [
            TelegramTopic(
                telegram_topic_id=r["telegram_topic_id"],
                telegram_user_id=r["telegram_user_id"],
                max_chat_id=r["max_chat_id"],
            )
            for r in rows
        ]

    async def save(self, topic: TelegramTopic) -> None:
        await self._db.execute(  # type: ignore[reportAttributeAccessIssue]
            "INSERT OR REPLACE INTO telegram_topics "
            "(telegram_topic_id, telegram_user_id, max_chat_id) "
            "VALUES (?, ?, ?)",
            topic.telegram_topic_id,
            topic.telegram_user_id,
            topic.max_chat_id,
        )
        await self._db.commit()


class SqliteMessageLinkRepository(MessageLinkRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def save(self, link: MessageLink) -> None:
        await self._db.execute(  # type: ignore[reportAttributeAccessIssue]
            "INSERT OR IGNORE INTO message_links "
            "(max_message_id, telegram_message_id, telegram_user_id, max_chat_id, direction, delivered_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            link.max_message_id,
            link.telegram_message_id,
            link.telegram_user_id,
            link.max_chat_id,
            link.direction.value,
            link.delivered_at,
        )
        await self._db.commit()

    async def exists_max_message(self, max_message_id: str, max_chat_id: str) -> bool:
        row = await self._db.fetchone(
            "SELECT 1 FROM message_links WHERE max_message_id = ? AND max_chat_id = ? "
            "AND direction = 'max_to_telegram'",
            max_message_id,
            max_chat_id,
        )
        return row is not None


class SqliteSyncCursorRepository(SyncCursorRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def get(self, max_chat_id: str, binding_telegram_user_id: int) -> SyncCursor | None:
        row = await self._db.fetchone(
            "SELECT max_chat_id, binding_telegram_user_id, last_max_message_id, updated_at "
            "FROM sync_cursors WHERE max_chat_id = ? AND binding_telegram_user_id = ?",
            max_chat_id,
            binding_telegram_user_id,
        )
        if row is None:
            return None
        return SyncCursor(
            max_chat_id=row["max_chat_id"],
            binding_telegram_user_id=row["binding_telegram_user_id"],
            last_max_message_id=row["last_max_message_id"],
            updated_at=row["updated_at"],
        )

    async def upsert(self, cursor: SyncCursor) -> None:
        await self._db.execute(  # type: ignore[reportAttributeAccessIssue]
            "INSERT OR REPLACE INTO sync_cursors "
            "(max_chat_id, binding_telegram_user_id, last_max_message_id, updated_at) "
            "VALUES (?, ?, ?, ?)",
            cursor.max_chat_id,
            cursor.binding_telegram_user_id,
            cursor.last_max_message_id,
            cursor.updated_at,
        )
        await self._db.commit()


class SqliteAuditRepository(AuditRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def log(
        self, telegram_user_id: int, event_type: AuditEventType, detail: str
    ) -> AuditEvent:
        now = int(time.time())
        cursor = await self._db.execute(  # type: ignore[reportAttributeAccessIssue]
            "INSERT INTO audit_events (telegram_user_id, event_type, detail, created_at) "
            "VALUES (?, ?, ?, ?)",
            telegram_user_id,
            event_type.value,
            detail,
            now,
        )
        await self._db.commit()
        return AuditEvent(
            id=cursor.lastrowid,  # type: ignore[reportUnknownMemberType]
            telegram_user_id=telegram_user_id,
            event_type=event_type,
            detail=detail,
            created_at=now,
        )

    async def has_recent_event(
        self, telegram_user_id: int, event_type: AuditEventType, since: int
    ) -> bool:
        row = await self._db.fetchone(
            "SELECT 1 FROM audit_events "
            "WHERE telegram_user_id = ? AND event_type = ? AND created_at >= ?",
            telegram_user_id,
            event_type.value,
            since,
        )
        return row is not None
