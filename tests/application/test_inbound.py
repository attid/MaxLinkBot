"""Unit tests for InboundSyncService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from src.application.ports.repositories import (
    AuditRepository,
    BindingRepository,
    MaxChatRepository,
    MessageLinkRepository,
    SyncCursorRepository,
    TelegramTopicRepository,
)
from src.application.ports.telegram_client import TelegramClient
from src.application.routing.inbound import InboundSyncService


class MockRepos:
    """Container of repository mocks for InboundSyncService tests."""

    binding_repo: MagicMock
    max_chat_repo: MagicMock
    topic_repo: MagicMock
    message_link_repo: MagicMock
    cursor_repo: MagicMock
    audit_repo: MagicMock
    telegram: MagicMock

    def __init__(self) -> None:
        self.binding_repo = MagicMock(spec=BindingRepository)
        self.max_chat_repo = MagicMock(spec=MaxChatRepository)
        self.topic_repo = MagicMock(spec=TelegramTopicRepository)
        self.message_link_repo = MagicMock(spec=MessageLinkRepository)
        self.cursor_repo = MagicMock(spec=SyncCursorRepository)
        self.audit_repo = MagicMock(spec=AuditRepository)
        self.telegram = MagicMock(spec=TelegramClient)


class TestInboundSyncService:
    async def test_poll_user_no_binding(self) -> None:
        """No binding → nothing to do."""
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock(return_value=None)

        max_client = MagicMock()
        max_client.close = AsyncMock()

        def factory() -> MagicMock:
            return max_client

        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=factory,
        )

        await service.poll_user(telegram_user_id=123)

        repos.binding_repo.get.assert_called_once_with(123)
        max_client.list_personal_chats.assert_not_called()

    async def test_poll_chat_no_topic_mapping(self) -> None:
        """No topic for user+chat → nothing to do."""
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock()
        repos.topic_repo.get_by_user_and_chat = AsyncMock(return_value=None)

        max_client = MagicMock()
        max_client.close = AsyncMock()

        def factory() -> MagicMock:
            return max_client

        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=factory,
        )

        await service.poll_chat(telegram_user_id=123, max_chat_id="chat1")

        repos.topic_repo.get_by_user_and_chat.assert_called_once_with(123, "chat1")
        max_client.get_messages.assert_not_called()

    async def test_poll_chat_delivers_new_messages(self) -> None:
        """New messages are fetched, delivered, and cursor is updated."""
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock()
        repos.topic_repo.get_by_user_and_chat = AsyncMock(
            return_value=MagicMock(telegram_topic_id=50)
        )
        repos.cursor_repo.get = AsyncMock(return_value=None)
        repos.message_link_repo.exists_max_message = AsyncMock(return_value=False)
        repos.message_link_repo.save = AsyncMock()
        repos.cursor_repo.upsert = AsyncMock()

        max_client = MagicMock()
        max_client.get_messages = AsyncMock(
            return_value=[
                {"max_message_id": 10, "type": "text", "text": "Hello"},
                {"max_message_id": 11, "type": "text", "text": "World"},
            ]
        )
        max_client.close = AsyncMock()

        repos.telegram.send_text_to_topic = AsyncMock(side_effect=[100, 101])

        def factory() -> MagicMock:
            return max_client

        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=factory,
        )

        await service.poll_chat(telegram_user_id=123, max_chat_id="chat1")

        assert repos.telegram.send_text_to_topic.call_count == 2
        assert repos.message_link_repo.save.call_count == 2
        repos.cursor_repo.upsert.assert_called_once()
        max_client.close.assert_called_once()

    async def test_poll_chat_idempotency_skips_already_delivered(self) -> None:
        """Already-delivered messages are skipped."""
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock()
        repos.topic_repo.get_by_user_and_chat = AsyncMock(
            return_value=MagicMock(telegram_topic_id=50)
        )
        repos.cursor_repo.get = AsyncMock(return_value=None)
        repos.message_link_repo.exists_max_message = AsyncMock(return_value=True)
        repos.message_link_repo.save = AsyncMock()
        repos.cursor_repo.upsert = AsyncMock()

        max_client = MagicMock()
        max_client.get_messages = AsyncMock(
            return_value=[{"max_message_id": 10, "type": "text", "text": "Old"}]
        )
        max_client.close = AsyncMock()

        def factory() -> MagicMock:
            return max_client

        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=factory,
        )

        await service.poll_chat(telegram_user_id=123, max_chat_id="chat1")

        repos.telegram.send_text_to_topic.assert_not_called()
        repos.message_link_repo.save.assert_not_called()

    async def test_deliver_message_telegram_error_logs_audit(self) -> None:
        """Telegram delivery failure is logged and does not raise."""
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock()
        repos.topic_repo.get_by_user_and_chat = AsyncMock(
            return_value=MagicMock(telegram_topic_id=50)
        )
        repos.cursor_repo.get = AsyncMock(return_value=None)
        repos.message_link_repo.exists_max_message = AsyncMock(return_value=False)
        repos.audit_repo.log = AsyncMock()
        repos.message_link_repo.save = AsyncMock()
        repos.cursor_repo.upsert = AsyncMock()

        max_client = MagicMock()
        max_client.get_messages = AsyncMock(
            return_value=[{"max_message_id": 10, "type": "text", "text": "Hi"}]
        )
        max_client.close = AsyncMock()

        repos.telegram.send_text_to_topic = AsyncMock(side_effect=Exception("Telegram timeout"))

        def factory() -> MagicMock:
            return max_client

        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=factory,
        )

        # Should not raise
        await service.poll_chat(telegram_user_id=123, max_chat_id="chat1")

        repos.audit_repo.log.assert_called_once()

    async def test_render_message_text(self) -> None:
        """Text messages are rendered as-is."""
        repos = MockRepos()
        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda: MagicMock(),
        )

        # pyright: ignore — testing private method directly
        assert service._render_message({"type": "text", "text": "Hello!"}) == "Hello!"  # type: ignore[reportPrivateUsage]

    async def test_render_message_unsupported_fallback(self) -> None:
        """Unsupported message types render with type and description."""
        repos = MockRepos()
        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda: MagicMock(),
        )

        result = service._render_message({"type": "image", "description": "Sunset photo"})  # type: ignore[reportPrivateUsage]
        assert result == "[image]: Sunset photo"

    async def test_render_message_unknown_type(self) -> None:
        """Unknown type without description uses default fallback."""
        repos = MockRepos()
        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda: MagicMock(),
        )

        result = service._render_message({})  # type: ignore[reportPrivateUsage]
        assert result == "[unknown]: Unsupported content"
