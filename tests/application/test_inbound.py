"""Unit tests for InboundSyncService."""

from __future__ import annotations

import time
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock

from aiogram.exceptions import TelegramBadRequest

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

        max_client = MagicMock(start=AsyncMock())
        max_client.close = AsyncMock()

        def factory(_uid: int, _phone: str) -> MagicMock:
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

    async def test_poll_user_drains_live_buffer_without_history_polling(self) -> None:
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock(
            return_value=MagicMock(telegram_user_id=123, max_session_data="token")
        )
        repos.topic_repo.get_by_user_and_chat = AsyncMock(return_value=MagicMock(telegram_topic_id=50))
        repos.message_link_repo.exists_max_message = AsyncMock(return_value=False)
        repos.message_link_repo.save = AsyncMock()
        repos.cursor_repo.upsert = AsyncMock()
        repos.telegram.send_text_to_topic = AsyncMock(return_value=100)

        max_client = MagicMock(start=AsyncMock())
        max_client.drain_buffered_messages = AsyncMock(
            return_value=[
                {
                    "max_message_id": "1",
                    "chat_id": "chat1",
                    "type": "text",
                    "text": "Hello",
                    "sender_name": "Alice",
                    "time": int(datetime(2026, 3, 22, 14, 35, tzinfo=UTC).timestamp() * 1000),
                }
            ]
        )
        max_client.list_personal_chats = AsyncMock(return_value=[])
        max_client.get_messages = AsyncMock(return_value=[])
        max_client.consume_reconnect_event = AsyncMock(return_value=False)
        max_client.close = AsyncMock()

        factory = MagicMock(return_value=max_client)

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

        max_client.start.assert_awaited_once()
        max_client.drain_buffered_messages.assert_awaited_once()
        max_client.get_messages.assert_not_called()
        max_client.close.assert_not_called()
        factory.assert_called_once_with(123, "token")
        repos.telegram.send_text_to_topic.assert_awaited_once()

    async def test_poll_user_ignores_service_live_event_for_regular_chat(self) -> None:
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock(
            return_value=MagicMock(telegram_user_id=123, max_session_data="token")
        )

        max_client = MagicMock(start=AsyncMock())
        max_client.drain_buffered_messages = AsyncMock(
            return_value=[
                {
                    "max_message_id": "1",
                    "chat_id": "12345",
                    "type": "user",
                    "sender_name": 192875451,
                    "time": int(datetime(2026, 3, 22, 22, 30, tzinfo=UTC).timestamp() * 1000),
                }
            ]
        )
        max_client.consume_reconnect_event = AsyncMock(return_value=False)
        max_client.get_messages = AsyncMock(return_value=[])
        max_client.close = AsyncMock()

        factory = MagicMock(return_value=max_client)

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

        repos.telegram.send_text_to_topic.assert_not_called()
        repos.message_link_repo.save.assert_not_called()
        repos.cursor_repo.upsert.assert_not_called()

    async def test_poll_user_keeps_self_chat_user_media_event(self) -> None:
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock(
            return_value=MagicMock(telegram_user_id=123, max_session_data="token")
        )
        repos.topic_repo.get_by_user_and_chat = AsyncMock(return_value=MagicMock(telegram_topic_id=50))
        repos.message_link_repo.exists_max_message = AsyncMock(return_value=False)
        repos.message_link_repo.save = AsyncMock()
        repos.cursor_repo.upsert = AsyncMock()
        repos.telegram.send_text_to_topic = AsyncMock(return_value=100)

        max_client = MagicMock(start=AsyncMock())
        max_client.drain_buffered_messages = AsyncMock(
            return_value=[
                {
                    "max_message_id": "1",
                    "chat_id": "0",
                    "type": "user",
                    "sender_name": 192875451,
                    "sender_id": 192875451,
                    "time": int(datetime(2026, 3, 22, 22, 30, tzinfo=UTC).timestamp() * 1000),
                }
            ]
        )
        max_client.consume_reconnect_event = AsyncMock(return_value=False)
        max_client.get_messages = AsyncMock(return_value=[])
        max_client.close = AsyncMock()

        factory = MagicMock(return_value=max_client)

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

        repos.telegram.send_text_to_topic.assert_awaited_once()
        repos.message_link_repo.save.assert_awaited_once()
        repos.cursor_repo.upsert.assert_awaited_once()

    async def test_deliver_message_sends_photo_to_topic_when_media_url_present(self) -> None:
        repos = MockRepos()
        repos.message_link_repo.exists_max_message = AsyncMock(return_value=False)
        repos.message_link_repo.save = AsyncMock()
        repos.telegram.send_photo_to_topic = AsyncMock(return_value=101)

        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda _u, _p: MagicMock(),
        )

        delivered = await service._deliver_message(  # type: ignore[reportPrivateUsage]
            telegram_user_id=123,
            max_chat_id="0",
            topic_id=50,
            msg={
                "max_message_id": "1",
                "chat_id": "0",
                "type": "photo",
                "media_url": "https://example.com/image.jpg",
                "sender_name": "Igor",
                "sender_id": 192875451,
                "time": int(datetime(2026, 3, 22, 22, 30, tzinfo=UTC).timestamp() * 1000),
            },
        )

        assert delivered is True
        repos.telegram.send_photo_to_topic.assert_awaited_once_with(
            chat_id=123,
            topic_id=50,
            photo_url="https://example.com/image.jpg",
            caption="[Igor 192875451 22.03.26 22:30]",
        )

    async def test_deliver_message_sends_audio_to_topic_when_media_url_present(self) -> None:
        repos = MockRepos()
        repos.message_link_repo.exists_max_message = AsyncMock(return_value=False)
        repos.message_link_repo.save = AsyncMock()
        repos.telegram.send_audio_to_topic = AsyncMock(return_value=101)

        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda _u, _p: MagicMock(),
        )

        delivered = await service._deliver_message(  # type: ignore[reportPrivateUsage]
            telegram_user_id=123,
            max_chat_id="0",
            topic_id=50,
            msg={
                "max_message_id": "1",
                "chat_id": "0",
                "type": "audio",
                "media_url": "https://example.com/audio.mp3",
                "sender_name": "Igor",
                "sender_id": 192875451,
                "time": int(datetime(2026, 3, 22, 22, 30, tzinfo=UTC).timestamp() * 1000),
            },
        )

        assert delivered is True
        repos.telegram.send_audio_to_topic.assert_awaited_once_with(
            chat_id=123,
            topic_id=50,
            audio_url="https://example.com/audio.mp3",
            caption="[Igor 192875451 22.03.26 22:30]",
        )

    async def test_deliver_message_sends_document_to_topic_when_media_url_present(self) -> None:
        repos = MockRepos()
        repos.message_link_repo.exists_max_message = AsyncMock(return_value=False)
        repos.message_link_repo.save = AsyncMock()
        repos.telegram.send_document_to_topic = AsyncMock(return_value=101)

        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda _u, _p: MagicMock(),
        )

        delivered = await service._deliver_message(  # type: ignore[reportPrivateUsage]
            telegram_user_id=123,
            max_chat_id="0",
            topic_id=50,
            msg={
                "max_message_id": "1",
                "chat_id": "0",
                "type": "document",
                "media_url": "https://example.com/spec.pdf",
                "file_name": "spec.pdf",
                "sender_name": "Igor",
                "sender_id": 192875451,
                "time": int(datetime(2026, 3, 22, 22, 30, tzinfo=UTC).timestamp() * 1000),
            },
        )

        assert delivered is True
        repos.telegram.send_document_to_topic.assert_awaited_once_with(
            chat_id=123,
            topic_id=50,
            document_url="https://example.com/spec.pdf",
            filename="spec.pdf",
            caption="[Igor 192875451 22.03.26 22:30]",
        )

    async def test_deliver_message_falls_back_to_text_when_audio_url_is_rejected(self) -> None:
        repos = MockRepos()
        repos.message_link_repo.exists_max_message = AsyncMock(return_value=False)
        repos.message_link_repo.save = AsyncMock()
        repos.telegram.send_audio_to_topic = AsyncMock(
            side_effect=TelegramBadRequest(
                method=MagicMock(),
                message="failed to get HTTP URL content",
            )
        )
        repos.telegram.send_text_to_topic = AsyncMock(return_value=101)

        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda _u, _p: MagicMock(),
        )

        delivered = await service._deliver_message(  # type: ignore[reportPrivateUsage]
            telegram_user_id=123,
            max_chat_id="0",
            topic_id=50,
            msg={
                "max_message_id": "1",
                "chat_id": "0",
                "type": "audio",
                "media_url": "https://example.com/audio.mp3",
                "sender_name": "Igor",
                "sender_id": 192875451,
                "time": int(datetime(2026, 3, 22, 22, 30, tzinfo=UTC).timestamp() * 1000),
            },
        )

        assert delivered is True
        repos.telegram.send_text_to_topic.assert_awaited_once_with(
            chat_id=123,
            topic_id=50,
            text="[Igor 192875451 22.03.26 22:30]\n[audio]: https://example.com/audio.mp3",
        )

    async def test_poll_user_reuses_live_client_between_ticks(self) -> None:
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock(
            return_value=MagicMock(telegram_user_id=123, max_session_data="token")
        )

        max_client = MagicMock(start=AsyncMock())
        max_client.drain_buffered_messages = AsyncMock(return_value=[])
        max_client.list_personal_chats = AsyncMock(return_value=[])
        max_client.get_messages = AsyncMock(return_value=[])
        max_client.consume_reconnect_event = AsyncMock(return_value=False)
        max_client.close = AsyncMock()

        factory = MagicMock(return_value=max_client)

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
        await service.poll_user(telegram_user_id=123)

        max_client.start.assert_awaited_once()
        assert max_client.drain_buffered_messages.await_count == 2
        max_client.close.assert_not_called()
        factory.assert_called_once_with(123, "token")

    async def test_poll_user_runs_catchup_for_existing_topics_on_interval(self) -> None:
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock(
            return_value=MagicMock(telegram_user_id=123, max_session_data="token")
        )
        repos.topic_repo.find_by_user = AsyncMock(
            return_value=[MagicMock(max_chat_id="chat1", telegram_topic_id=50)]
        )
        repos.topic_repo.get_by_user_and_chat = AsyncMock(return_value=MagicMock(telegram_topic_id=50))
        repos.cursor_repo.get = AsyncMock(return_value=None)
        repos.message_link_repo.exists_max_message = AsyncMock(return_value=False)
        repos.message_link_repo.save = AsyncMock()
        repos.cursor_repo.upsert = AsyncMock()
        repos.telegram.send_text_to_topic = AsyncMock(return_value=101)

        max_client = MagicMock(start=AsyncMock())
        max_client.drain_buffered_messages = AsyncMock(return_value=[])
        max_client.consume_reconnect_event = AsyncMock(return_value=False)
        max_client.get_messages = AsyncMock(
            return_value=[{"max_message_id": "2", "type": "text", "text": "Catchup"}]
        )
        max_client.close = AsyncMock()

        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda _uid, _phone: max_client,
            catchup_interval_seconds=0,
        )

        await service.poll_user(telegram_user_id=123)

        max_client.get_messages.assert_awaited_once_with("chat1", since_message_id=None, limit=50)

    async def test_poll_user_polls_only_dirty_chats_between_hourly_catchups(self) -> None:
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock(
            return_value=MagicMock(telegram_user_id=123, max_session_data="token")
        )
        repos.topic_repo.get_by_user_and_chat = AsyncMock(return_value=MagicMock(telegram_topic_id=50))
        repos.cursor_repo.get = AsyncMock(return_value=None)
        repos.message_link_repo.exists_max_message = AsyncMock(return_value=False)
        repos.message_link_repo.save = AsyncMock()
        repos.cursor_repo.upsert = AsyncMock()
        repos.telegram.send_text_to_topic = AsyncMock(return_value=101)

        max_client = MagicMock(start=AsyncMock())
        max_client.drain_buffered_messages = AsyncMock(return_value=[])
        max_client.consume_reconnect_event = AsyncMock(return_value=False)
        max_client.get_messages = AsyncMock(
            return_value=[{"max_message_id": "2", "type": "text", "text": "Dirty reply"}]
        )
        max_client.close = AsyncMock()

        shared_runtime = MagicMock()
        shared_runtime.get_client = AsyncMock(return_value=max_client)
        shared_runtime.get_dirty_chats = AsyncMock(return_value=["chat1"])
        shared_runtime.clear_dirty_chat = AsyncMock()

        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda _uid, _phone: max_client,
            catchup_interval_seconds=3600,
            shared_runtime=shared_runtime,
        )

        service._last_catchup_at = time.time()  # type: ignore[reportPrivateUsage]

        await service.poll_user(telegram_user_id=123)

        shared_runtime.get_dirty_chats.assert_awaited_once_with(123)
        max_client.get_messages.assert_awaited_once_with("chat1", since_message_id=None, limit=50)

    async def test_live_message_clears_dirty_chat_marker(self) -> None:
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock(
            return_value=MagicMock(telegram_user_id=123, max_session_data="token")
        )
        repos.topic_repo.get_by_user_and_chat = AsyncMock(return_value=MagicMock(telegram_topic_id=50))
        repos.message_link_repo.exists_max_message = AsyncMock(return_value=False)
        repos.message_link_repo.save = AsyncMock()
        repos.cursor_repo.upsert = AsyncMock()
        repos.telegram.send_text_to_topic = AsyncMock(return_value=100)

        max_client = MagicMock(start=AsyncMock())
        max_client.drain_buffered_messages = AsyncMock(
            return_value=[
                {
                    "max_message_id": "1",
                    "chat_id": "chat1",
                    "type": "text",
                    "text": "Hello",
                    "sender_name": "Alice",
                    "time": int(datetime(2026, 3, 22, 14, 35, tzinfo=UTC).timestamp() * 1000),
                }
            ]
        )
        max_client.consume_reconnect_event = AsyncMock(return_value=False)
        max_client.get_messages = AsyncMock(return_value=[])
        max_client.close = AsyncMock()

        shared_runtime = MagicMock()
        shared_runtime.get_client = AsyncMock(return_value=max_client)
        shared_runtime.get_dirty_chats = AsyncMock(return_value=[])
        shared_runtime.clear_dirty_chat = AsyncMock()

        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda _uid, _phone: max_client,
            shared_runtime=shared_runtime,
        )

        await service.poll_user(telegram_user_id=123)

        shared_runtime.clear_dirty_chat.assert_awaited_once_with(123, "chat1")

    async def test_poll_user_forces_full_catchup_after_reconnect(self) -> None:
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock(
            return_value=MagicMock(telegram_user_id=123, max_session_data="token")
        )
        repos.topic_repo.find_by_user = AsyncMock(
            return_value=[MagicMock(max_chat_id="chat1", telegram_topic_id=50)]
        )
        repos.topic_repo.get_by_user_and_chat = AsyncMock(return_value=MagicMock(telegram_topic_id=50))
        repos.cursor_repo.get = AsyncMock(return_value=None)
        repos.message_link_repo.exists_max_message = AsyncMock(return_value=False)
        repos.message_link_repo.save = AsyncMock()
        repos.cursor_repo.upsert = AsyncMock()
        repos.telegram.send_text_to_topic = AsyncMock(return_value=101)

        max_client = MagicMock(start=AsyncMock())
        max_client.drain_buffered_messages = AsyncMock(return_value=[])
        max_client.consume_reconnect_event = AsyncMock(return_value=True)
        max_client.get_messages = AsyncMock(
            return_value=[{"max_message_id": "2", "type": "text", "text": "Reconnect catchup"}]
        )
        max_client.close = AsyncMock()

        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda _uid, _phone: max_client,
            catchup_interval_seconds=3600,
        )

        service._last_catchup_at = time.time()  # type: ignore[reportPrivateUsage]

        await service.poll_user(telegram_user_id=123)

        repos.topic_repo.find_by_user.assert_awaited_once_with(123)
        max_client.get_messages.assert_awaited_once_with("chat1", since_message_id=None, limit=50)

    async def test_reconnect_recovery_skips_reconcile_and_only_catches_up_topics(self) -> None:
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock(
            return_value=MagicMock(telegram_user_id=123, max_session_data="token")
        )
        repos.topic_repo.find_by_user = AsyncMock(
            return_value=[MagicMock(max_chat_id="chat1", telegram_topic_id=50)]
        )
        repos.topic_repo.get_by_user_and_chat = AsyncMock(return_value=MagicMock(telegram_topic_id=50))
        repos.cursor_repo.get = AsyncMock(return_value=None)
        repos.message_link_repo.exists_max_message = AsyncMock(return_value=False)
        repos.message_link_repo.save = AsyncMock()
        repos.cursor_repo.upsert = AsyncMock()
        repos.telegram.send_text_to_topic = AsyncMock(return_value=101)

        max_client = MagicMock(start=AsyncMock())
        max_client.drain_buffered_messages = AsyncMock(return_value=[])
        max_client.consume_reconnect_event = AsyncMock(return_value=True)
        max_client.get_messages = AsyncMock(
            return_value=[{"max_message_id": "2", "type": "text", "text": "Reconnect catchup"}]
        )
        max_client.close = AsyncMock()

        reconcile_user = AsyncMock()

        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda _uid, _phone: max_client,
            catchup_interval_seconds=3600,
            reconcile_user=reconcile_user,
        )

        service._last_catchup_at = time.time()  # type: ignore[reportPrivateUsage]

        await service.poll_user(telegram_user_id=123)

        reconcile_user.assert_not_awaited()
        repos.topic_repo.find_by_user.assert_awaited_once_with(123)

    async def test_reconnect_recovery_checks_dirty_chat_first_and_skips_broad_scan_when_found(self) -> None:
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock(
            return_value=MagicMock(telegram_user_id=123, max_session_data="token")
        )
        repos.topic_repo.get_by_user_and_chat = AsyncMock(return_value=MagicMock(telegram_topic_id=50))
        repos.topic_repo.find_by_user = AsyncMock(
            return_value=[MagicMock(max_chat_id="chat1", telegram_topic_id=50)]
        )
        repos.cursor_repo.get = AsyncMock(return_value=None)
        repos.message_link_repo.exists_max_message = AsyncMock(return_value=False)
        repos.message_link_repo.save = AsyncMock()
        repos.cursor_repo.upsert = AsyncMock()
        repos.telegram.send_text_to_topic = AsyncMock(return_value=101)

        max_client = MagicMock(start=AsyncMock())
        max_client.drain_buffered_messages = AsyncMock(return_value=[])
        max_client.consume_reconnect_event = AsyncMock(return_value=True)
        max_client.get_messages = AsyncMock(
            return_value=[{"max_message_id": "2", "type": "text", "text": "Reconnect catchup"}]
        )
        max_client.close = AsyncMock()

        shared_runtime = MagicMock()
        shared_runtime.get_client = AsyncMock(return_value=max_client)
        shared_runtime.get_dirty_chats = AsyncMock(return_value=["chat1"])
        shared_runtime.get_last_active_chat = AsyncMock(return_value=None)
        shared_runtime.clear_dirty_chat = AsyncMock()

        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda _uid, _phone: max_client,
            catchup_interval_seconds=3600,
            shared_runtime=shared_runtime,
        )

        await service.poll_user(telegram_user_id=123)

        shared_runtime.get_dirty_chats.assert_awaited_once_with(123)
        repos.topic_repo.find_by_user.assert_not_awaited()

    async def test_poll_user_raises_on_reconnect_storm_and_closes_live_client(self) -> None:
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock(
            return_value=MagicMock(telegram_user_id=123, max_session_data="token")
        )
        repos.topic_repo.find_by_user = AsyncMock(return_value=[])

        max_client = MagicMock(start=AsyncMock())
        max_client.drain_buffered_messages = AsyncMock(return_value=[])
        max_client.consume_reconnect_event = AsyncMock(return_value=True)
        max_client.get_messages = AsyncMock(return_value=[])
        max_client.close = AsyncMock()

        shared_runtime = MagicMock()
        shared_runtime.get_client = AsyncMock(return_value=max_client)
        shared_runtime.get_dirty_chats = AsyncMock(return_value=[])
        shared_runtime.get_last_active_chat = AsyncMock(return_value=None)
        shared_runtime.close_user = AsyncMock()

        now = 1000.0
        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda _uid, _phone: max_client,
            catchup_interval_seconds=3600,
            shared_runtime=shared_runtime,
            reconnect_storm_threshold=3,
            reconnect_storm_window_seconds=60.0,
            time_func=lambda: now,
        )

        await service.poll_user(telegram_user_id=123)
        now += 5
        await service.poll_user(telegram_user_id=123)
        now += 5

        try:
            await service.poll_user(telegram_user_id=123)
        except RuntimeError as exc:
            assert "reconnect storm" in str(exc).lower()
        else:
            raise AssertionError("Expected reconnect storm RuntimeError")

        shared_runtime.close_user.assert_awaited_once_with(123)

    async def test_poll_chat_no_topic_mapping(self) -> None:
        """No topic for user+chat → nothing to do."""
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock()
        repos.topic_repo.get_by_user_and_chat = AsyncMock(return_value=None)

        max_client = MagicMock(start=AsyncMock())
        max_client.close = AsyncMock()

        def factory(_uid: int, _phone: str) -> MagicMock:
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

        max_client = MagicMock(start=AsyncMock())
        max_client.get_messages = AsyncMock(
            return_value=[
                {"max_message_id": 10, "type": "text", "text": "Hello"},
                {"max_message_id": 11, "type": "text", "text": "World"},
            ]
        )
        max_client.close = AsyncMock()

        repos.telegram.send_text_to_topic = AsyncMock(side_effect=[100, 101])

        def factory(_uid: int, _phone: str) -> MagicMock:
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
        max_client.close.assert_not_called()

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

        max_client = MagicMock(start=AsyncMock())
        max_client.get_messages = AsyncMock(
            return_value=[{"max_message_id": 10, "type": "text", "text": "Old"}]
        )
        max_client.close = AsyncMock()

        def factory(_uid: int, _phone: str) -> MagicMock:
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

        max_client = MagicMock(start=AsyncMock())
        max_client.get_messages = AsyncMock(
            return_value=[{"max_message_id": 10, "type": "text", "text": "Hi"}]
        )
        max_client.close = AsyncMock()

        repos.telegram.send_text_to_topic = AsyncMock(side_effect=Exception("Telegram timeout"))

        def factory(_uid: int, _phone: str) -> MagicMock:
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
        """Text messages are rendered with sender and timestamp prefix."""
        repos = MockRepos()
        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda _u, _p: MagicMock(),
        )

        # pyright: ignore — testing private method directly
        rendered = service._render_message(  # type: ignore[reportPrivateUsage]
            {
                "type": "text",
                "text": "Hello!",
                "sender_name": "Vasya",
                "sender_id": 7,
                "time": int(datetime(2026, 3, 22, 14, 35, tzinfo=UTC).timestamp() * 1000),
            }
        )
        assert rendered == "[Vasya 7 22.03.26 14:35]\nHello!"

    async def test_render_message_coerces_non_string_sender_name(self) -> None:
        repos = MockRepos()
        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda _u, _p: MagicMock(),
        )

        rendered = service._render_message(  # type: ignore[reportPrivateUsage]
            {
                "type": "text",
                "text": "Hello!",
                "sender_name": 192875451,
                "sender_id": 192875451,
                "time": int(datetime(2026, 3, 22, 14, 35, tzinfo=UTC).timestamp() * 1000),
            }
        )
        assert rendered == "[192875451 192875451 22.03.26 14:35]\nHello!"

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
            max_client_factory=lambda _u, _p: MagicMock(),
        )

        result = service._render_message(  # type: ignore[reportPrivateUsage]
            {
                "type": "image",
                "description": "Sunset photo",
                "sender_name": "Vasya",
                "time": int(datetime(2026, 3, 22, 14, 35, tzinfo=UTC).timestamp() * 1000),
            }
        )
        assert result == "[Vasya UnknownID 22.03.26 14:35]\n[image]: Sunset photo"

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
            max_client_factory=lambda _u, _p: MagicMock(),
        )

        result = service._render_message(  # type: ignore[reportPrivateUsage]
            {
                "sender_name": "Unknown",
                "time": int(datetime(2026, 3, 22, 14, 35, tzinfo=UTC).timestamp() * 1000),
            }
        )
        assert result == "[Unknown UnknownID 22.03.26 14:35]\n[unknown]: Unsupported content"

    async def test_render_message_unknown_media_fallback(self) -> None:
        repos = MockRepos()
        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda _u, _p: MagicMock(),
        )

        result = service._render_message(  # type: ignore[reportPrivateUsage]
            {
                "type": "unknown",
                "description": "photo",
                "sender_name": "Igor",
                "time": int(datetime(2026, 3, 22, 22, 29, tzinfo=UTC).timestamp() * 1000),
            }
        )
        assert result == "[Igor UnknownID 22.03.26 22:29]\n[image]: photo"

    async def test_render_message_media_without_description_uses_media_message(self) -> None:
        repos = MockRepos()
        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda _u, _p: MagicMock(),
        )

        result = service._render_message(  # type: ignore[reportPrivateUsage]
            {
                "type": "media",
                "sender_name": "Igor",
                "time": int(datetime(2026, 3, 22, 22, 29, tzinfo=UTC).timestamp() * 1000),
            }
        )
        assert result == "[Igor UnknownID 22.03.26 22:29]\n[media]: Media message"

    async def test_render_message_self_chat_user_type_uses_media_placeholder(self) -> None:
        repos = MockRepos()
        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda _u, _p: MagicMock(),
        )

        result = service._render_message(  # type: ignore[reportPrivateUsage]
            {
                "chat_id": "0",
                "type": "user",
                "sender_name": "Igor",
                "sender_id": 192875451,
                "time": int(datetime(2026, 3, 22, 22, 29, tzinfo=UTC).timestamp() * 1000),
            }
        )
        assert result == "[Igor 192875451 22.03.26 22:29]\n[media]: Media message"

    async def test_render_message_prefers_text_body_when_type_is_unknown(self) -> None:
        repos = MockRepos()
        service = InboundSyncService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            message_link_repo=repos.message_link_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda _u, _p: MagicMock(),
        )

        result = service._render_message(  # type: ignore[reportPrivateUsage]
            {
                "type": "messagetype.text",
                "text": "Черновой план",
                "sender_name": "Аттракционы Ривьера Сочи",
                "time": int(datetime(2026, 3, 22, 21, 28, tzinfo=UTC).timestamp() * 1000),
            }
        )
        assert result == "[Аттракционы Ривьера Сочи UnknownID 22.03.26 21:28]\nЧерновой план"
