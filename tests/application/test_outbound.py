"""Unit tests for OutboundSyncService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from src.application.auth.exceptions import AuthError
from src.application.ports.repositories import (
    AuditRepository,
    BindingRepository,
    MessageLinkRepository,
    TelegramTopicRepository,
)
from src.application.routing.outbound import OutboundSyncService


class MockRepos:
    """Container of repository mocks for OutboundSyncService tests."""

    binding_repo: MagicMock
    topic_repo: MagicMock
    message_link_repo: MagicMock
    audit_repo: MagicMock

    def __init__(self) -> None:
        self.binding_repo = MagicMock(spec=BindingRepository)
        self.topic_repo = MagicMock(spec=TelegramTopicRepository)
        self.message_link_repo = MagicMock(spec=MessageLinkRepository)
        self.audit_repo = MagicMock(spec=AuditRepository)


class TestOutboundSyncService:
    async def test_deliver_no_binding_raises(self) -> None:
        """No binding → raises AuthError."""
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock(return_value=None)

        max_client = MagicMock()
        max_client.close = AsyncMock()

        def factory() -> MagicMock:
            return max_client

        service = OutboundSyncService(
            binding_repo=repos.binding_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            audit_repo=repos.audit_repo,
            max_client_factory=factory,
        )

        try:
            await service.deliver(telegram_user_id=123, telegram_topic_id=50, text="Hi")
            raise AssertionError("Expected AuthError")
        except AuthError:
            pass

    async def test_deliver_no_topic_mapping_raises(self) -> None:
        """No topic mapping → raises AuthError."""
        repos = MockRepos()
        mock_binding = MagicMock()
        repos.binding_repo.get = AsyncMock(return_value=mock_binding)
        repos.topic_repo.get_by_user_and_topic = AsyncMock(return_value=None)

        max_client = MagicMock()
        max_client.close = AsyncMock()

        def factory() -> MagicMock:
            return max_client

        service = OutboundSyncService(
            binding_repo=repos.binding_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            audit_repo=repos.audit_repo,
            max_client_factory=factory,
        )

        try:
            await service.deliver(telegram_user_id=123, telegram_topic_id=50, text="Hi")
            raise AssertionError("Expected AuthError")
        except AuthError:
            pass

    async def test_deliver_success_sends_and_records(self) -> None:
        """Successful delivery sends to MAX and records link."""
        repos = MockRepos()
        mock_binding = MagicMock()
        repos.binding_repo.get = AsyncMock(return_value=mock_binding)

        mock_topic = MagicMock()
        mock_topic.max_chat_id = "max_chat_abc"
        repos.topic_repo.get_by_user_and_topic = AsyncMock(return_value=mock_topic)

        repos.message_link_repo.save = AsyncMock()
        repos.audit_repo.log = AsyncMock()

        max_client = MagicMock()
        max_client.send_message = AsyncMock(return_value="max_msg_xyz")
        max_client.close = AsyncMock()

        def factory() -> MagicMock:
            return max_client

        service = OutboundSyncService(
            binding_repo=repos.binding_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            audit_repo=repos.audit_repo,
            max_client_factory=factory,
        )

        result = await service.deliver(
            telegram_user_id=123,
            telegram_topic_id=50,
            text="Hello MAX",
        )

        assert result == "max_msg_xyz"
        max_client.send_message.assert_called_once_with("max_chat_abc", "Hello MAX")
        max_client.close.assert_called_once()
        repos.message_link_repo.save.assert_called_once()
        repos.audit_repo.log.assert_called_once()

    async def test_deliver_failure_logs_audit(self) -> None:
        """Delivery failure logs audit and re-raises."""
        repos = MockRepos()
        mock_binding = MagicMock()
        repos.binding_repo.get = AsyncMock(return_value=mock_binding)

        mock_topic = MagicMock()
        mock_topic.max_chat_id = "max_chat_abc"
        repos.topic_repo.get_by_user_and_topic = AsyncMock(return_value=mock_topic)

        repos.audit_repo.log = AsyncMock()

        max_client = MagicMock()
        max_client.send_message = AsyncMock(side_effect=Exception("Network error"))
        max_client.close = AsyncMock()

        def factory() -> MagicMock:
            return max_client

        service = OutboundSyncService(
            binding_repo=repos.binding_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            audit_repo=repos.audit_repo,
            max_client_factory=factory,
        )

        try:
            await service.deliver(
                telegram_user_id=123,
                telegram_topic_id=50,
                text="Hi",
            )
            raise AssertionError("Expected exception")
        except Exception:
            pass

        repos.audit_repo.log.assert_called_once()
