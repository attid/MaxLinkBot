"""Integration tests for MaxChat and TelegramTopic repositories — user isolation."""

from __future__ import annotations

import pytest_asyncio

from src.domain.bindings.models import Binding, BindingStatus
from src.domain.chats.models import ChatType, MaxChat
from src.domain.chats.topic import TelegramTopic
from src.infrastructure.persistence.connection import Database, DatabaseSettings
from src.infrastructure.persistence.init import init_schema
from src.infrastructure.persistence.repositories import (
    SqliteBindingRepository,
    SqliteMaxChatRepository,
    SqliteTelegramTopicRepository,
)


@pytest_asyncio.fixture
async def db_with_bindings():
    db_instance = Database(DatabaseSettings(database_url="sqlite+aiosqlite:///:memory:"))
    await db_instance.connect()
    await init_schema(db_instance)

    binding_repo = SqliteBindingRepository(db_instance)
    for uid in (100, 200):
        await binding_repo.save(
            Binding(
                telegram_user_id=uid,
                max_session_data=f"token_{uid}",
                status=BindingStatus.ACTIVE,
                created_at=0,
                updated_at=0,
            )
        )
    yield db_instance
    await db_instance.close()


class TestMaxChatRepositoryIsolation:
    async def test_user_a_cannot_see_user_b_chats(self, db_with_bindings: Database) -> None:
        chat_repo = SqliteMaxChatRepository(db_with_bindings)

        await chat_repo.save(
            MaxChat(
                max_chat_id="chat_X",
                binding_telegram_user_id=100,
                title="User 100 Chat",
                chat_type=ChatType.PERSONAL,
            )
        )
        await chat_repo.save(
            MaxChat(
                max_chat_id="chat_Y",
                binding_telegram_user_id=200,
                title="User 200 Chat",
                chat_type=ChatType.PERSONAL,
            )
        )

        user_100_chats = await chat_repo.find_by_binding(100)
        user_200_chats = await chat_repo.find_by_binding(200)

        assert {c.max_chat_id for c in user_100_chats} == {"chat_X"}
        assert {c.max_chat_id for c in user_200_chats} == {"chat_Y"}


class TestTelegramTopicRepositoryIsolation:
    async def test_topic_unique_per_user_and_chat(self, db_with_bindings: Database) -> None:
        topic_repo = SqliteTelegramTopicRepository(db_with_bindings)

        await topic_repo.save(
            TelegramTopic(
                telegram_topic_id=10,
                telegram_user_id=100,
                max_chat_id="chat_X",
            )
        )
        await topic_repo.save(
            TelegramTopic(
                telegram_topic_id=20,
                telegram_user_id=200,
                max_chat_id="chat_X",
            )
        )

        t10 = await topic_repo.get_by_user_and_chat(100, "chat_X")
        t20 = await topic_repo.get_by_user_and_chat(200, "chat_X")

        assert t10 is not None
        assert t10.telegram_topic_id == 10
        assert t20 is not None
        assert t20.telegram_topic_id == 20

        # User 100 cannot resolve user 200's topic
        t_wrong = await topic_repo.get_by_user_and_chat(100, "chat_Y")
        assert t_wrong is None
