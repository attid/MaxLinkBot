"""Unit tests for RefreshReconcileService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from src.application.ports.repositories import (
    AuditRepository,
    BindingRepository,
    MaxChatRepository,
    SyncCursorRepository,
    TelegramTopicRepository,
)
from src.application.ports.telegram_client import TelegramClient
from src.application.reconcile.service import RefreshReconcileService
from src.domain.chats.models import ChatType, MaxChat


class MockRepos:
    """Container of repository mocks for RefreshReconcileService tests."""

    binding_repo: MagicMock
    max_chat_repo: MagicMock
    topic_repo: MagicMock
    cursor_repo: MagicMock
    audit_repo: MagicMock
    telegram: MagicMock

    def __init__(self) -> None:
        self.binding_repo = MagicMock(spec=BindingRepository)
        self.max_chat_repo = MagicMock(spec=MaxChatRepository)
        self.topic_repo = MagicMock(spec=TelegramTopicRepository)
        self.cursor_repo = MagicMock(spec=SyncCursorRepository)
        self.audit_repo = MagicMock(spec=AuditRepository)
        self.telegram = MagicMock(spec=TelegramClient)


class TestReconcileService:
    async def test_reconcile_saves_max_chats(self) -> None:
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock()
        repos.max_chat_repo.save = AsyncMock()
        repos.topic_repo.find_by_user = AsyncMock(return_value=[])
        repos.telegram.create_topic = AsyncMock(return_value=100)
        repos.max_chat_repo.get = AsyncMock(return_value=None)

        max_client = MagicMock()
        max_client.list_personal_chats = AsyncMock(
            return_value=[
                {"max_chat_id": "chat1", "title": "Alice"},
                {"max_chat_id": "chat2", "title": "Bob"},
            ]
        )
        max_client.get_messages = AsyncMock(return_value=[])
        max_client.close = AsyncMock()

        def factory() -> MagicMock:
            return max_client

        service = RefreshReconcileService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=factory,
            backfill_count=5,
        )

        await service.reconcile(telegram_user_id=123)

        max_client.list_personal_chats.assert_called_once()
        assert repos.max_chat_repo.save.call_count == 2

    async def test_reconcile_skips_existing_topics(self) -> None:
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock()
        repos.topic_repo.find_by_user = AsyncMock(
            return_value=[MagicMock(max_chat_id="chat1", telegram_topic_id=10)]
        )

        max_client = MagicMock()
        max_client.list_personal_chats = AsyncMock(
            return_value=[{"max_chat_id": "chat1", "title": "Alice"}]
        )
        max_client.close = AsyncMock()

        def factory() -> MagicMock:
            return max_client

        service = RefreshReconcileService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=factory,
            backfill_count=5,
        )

        await service.reconcile(telegram_user_id=123)

        repos.telegram.create_topic.assert_not_called()

    async def test_reconcile_creates_topic_for_new_chat(self) -> None:
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock()
        repos.topic_repo.find_by_user = AsyncMock(return_value=[])
        repos.topic_repo.save = AsyncMock()
        repos.max_chat_repo.get = AsyncMock(
            return_value=MaxChat(
                max_chat_id="chat_new",
                binding_telegram_user_id=123,
                title="New Chat",
                chat_type=ChatType.PERSONAL,
            )
        )
        repos.telegram.create_topic = AsyncMock(return_value=200)

        max_client = MagicMock()
        max_client.list_personal_chats = AsyncMock(
            return_value=[{"max_chat_id": "chat_new", "title": "New Chat"}]
        )
        max_client.get_messages = AsyncMock(return_value=[])
        max_client.close = AsyncMock()

        def factory() -> MagicMock:
            return max_client

        service = RefreshReconcileService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=factory,
            backfill_count=5,
        )

        await service.reconcile(telegram_user_id=123)

        repos.telegram.create_topic.assert_called_once_with(chat_id=123, title="New Chat")
        repos.topic_repo.save.assert_called_once()
