"""Unit tests for RefreshReconcileService."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest

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

        max_client = MagicMock(start=AsyncMock())
        max_client.list_personal_chats = AsyncMock(
            return_value=[
                {"max_chat_id": "chat1", "title": "Alice", "participant_ids": ["1", "101"]},
                {"max_chat_id": "chat2", "title": "Bob", "participant_ids": ["1", "202"]},
            ]
        )
        max_client.get_messages = AsyncMock(return_value=[])
        max_client.close = AsyncMock()

        def factory(_uid: int, _phone: str) -> MagicMock:
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

        max_client = MagicMock(start=AsyncMock())
        max_client.list_personal_chats = AsyncMock(
            return_value=[{"max_chat_id": "chat1", "title": "Alice"}]
        )
        max_client.close = AsyncMock()

        def factory(_uid: int, _phone: str) -> MagicMock:
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
        repos.telegram.topic_exists.assert_not_called()

    async def test_reconcile_force_recreates_existing_topic(self) -> None:
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock()
        repos.topic_repo.find_by_user = AsyncMock(
            return_value=[MagicMock(max_chat_id="chat1", telegram_topic_id=10)]
        )
        repos.topic_repo.save = AsyncMock()
        repos.audit_repo.log = AsyncMock()
        repos.cursor_repo.upsert = AsyncMock()
        repos.max_chat_repo.get = AsyncMock(
            return_value=MaxChat(
                max_chat_id="chat1",
                binding_telegram_user_id=123,
                title="Alice",
                chat_type=ChatType.PERSONAL,
            )
        )
        repos.telegram.create_topic = AsyncMock(return_value=200)
        repos.telegram.send_text_to_topic = AsyncMock(return_value=500)

        max_client = MagicMock(start=AsyncMock())
        max_client.list_personal_chats = AsyncMock(
            return_value=[{"max_chat_id": "chat1", "title": "Alice"}]
        )
        max_client.get_messages = AsyncMock(return_value=[])
        max_client.close = AsyncMock()

        def factory(_uid: int, _phone: str) -> MagicMock:
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

        await service.reconcile(telegram_user_id=123, force_recreate=True)

        repos.telegram.create_topic.assert_called_once_with(chat_id=123, title="Alice")
        repos.topic_repo.save.assert_called_once()

    async def test_reconcile_force_recreates_only_target_chat(self) -> None:
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock()
        repos.topic_repo.find_by_user = AsyncMock(
            return_value=[
                MagicMock(max_chat_id="chat1", telegram_topic_id=10),
                MagicMock(max_chat_id="chat2", telegram_topic_id=11),
            ]
        )
        repos.topic_repo.save = AsyncMock()
        repos.audit_repo.log = AsyncMock()
        repos.cursor_repo.upsert = AsyncMock()
        repos.max_chat_repo.get = AsyncMock(
            side_effect=[
                MaxChat(
                    max_chat_id="chat1",
                    binding_telegram_user_id=123,
                    title="Alice",
                    chat_type=ChatType.PERSONAL,
                ),
            ]
        )
        repos.telegram.create_topic = AsyncMock(return_value=200)
        repos.telegram.send_text_to_topic = AsyncMock(return_value=500)

        max_client = MagicMock(start=AsyncMock())
        max_client.list_personal_chats = AsyncMock(
            return_value=[
                {"max_chat_id": "chat1", "title": "Alice"},
                {"max_chat_id": "chat2", "title": "Bob"},
            ]
        )
        max_client.get_messages = AsyncMock(return_value=[])
        max_client.close = AsyncMock()

        def factory(_uid: int, _phone: str) -> MagicMock:
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

        await service.reconcile(telegram_user_id=123, force_recreate=True, target_max_chat_id="chat1")

        repos.telegram.create_topic.assert_called_once_with(chat_id=123, title="Alice")
        repos.topic_repo.save.assert_called_once()

    async def test_reconcile_target_chat_raises_when_missing(self) -> None:
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock()
        repos.topic_repo.find_by_user = AsyncMock(return_value=[])

        max_client = MagicMock(start=AsyncMock())
        max_client.list_personal_chats = AsyncMock(
            return_value=[{"max_chat_id": "chat2", "title": "Bob", "participant_ids": ["1", "202"]}]
        )
        max_client.close = AsyncMock()

        def factory(_uid: int, _phone: str) -> MagicMock:
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

        try:
            await service.reconcile(
                telegram_user_id=123,
                force_recreate=True,
                target_max_chat_id="chat1",
            )
        except ValueError as exc:
            assert "chat1" in str(exc)
        else:
            raise AssertionError("Expected ValueError for missing target chat")

    async def test_reconcile_target_user_id_resolves_to_dialog_chat(self) -> None:
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock()
        repos.topic_repo.find_by_user = AsyncMock(return_value=[])
        repos.topic_repo.save = AsyncMock()
        repos.audit_repo.log = AsyncMock()
        repos.cursor_repo.upsert = AsyncMock()
        repos.max_chat_repo.get = AsyncMock(
            return_value=MaxChat(
                max_chat_id="chat234",
                binding_telegram_user_id=123,
                title="Irina",
                chat_type=ChatType.PERSONAL,
            )
        )
        repos.telegram.create_topic = AsyncMock(return_value=200)
        repos.telegram.send_text_to_topic = AsyncMock(return_value=500)

        max_client = MagicMock(start=AsyncMock())
        max_client.list_personal_chats = AsyncMock(
            return_value=[
                {"max_chat_id": "chat234", "title": "Irina", "participant_ids": ["192875451", "109283159"]},
                {"max_chat_id": "chat999", "title": "Other", "participant_ids": ["192875451", "222"]},
            ]
        )
        max_client.get_messages = AsyncMock(return_value=[])
        max_client.close = AsyncMock()

        def factory(_uid: int, _phone: str) -> MagicMock:
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

        await service.reconcile(
            telegram_user_id=123,
            force_recreate=True,
            target_max_chat_id="109283159",
        )

        repos.telegram.create_topic.assert_called_once_with(chat_id=123, title="Irina")

    async def test_reconcile_target_user_id_raises_when_ambiguous(self) -> None:
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock()
        repos.topic_repo.find_by_user = AsyncMock(return_value=[])

        max_client = MagicMock(start=AsyncMock())
        max_client.list_personal_chats = AsyncMock(
            return_value=[
                {"max_chat_id": "chat1", "title": "A", "participant_ids": ["10", "109283159"]},
                {"max_chat_id": "chat2", "title": "B", "participant_ids": ["11", "109283159"]},
            ]
        )
        max_client.close = AsyncMock()

        def factory(_uid: int, _phone: str) -> MagicMock:
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

        with pytest.raises(ValueError, match="matched multiple chats"):
            await service.reconcile(
                telegram_user_id=123,
                force_recreate=True,
                target_max_chat_id="109283159",
            )

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

        max_client = MagicMock(start=AsyncMock())
        max_client.list_personal_chats = AsyncMock(
            return_value=[{"max_chat_id": "chat_new", "title": "New Chat"}]
        )
        max_client.get_messages = AsyncMock(return_value=[])
        max_client.close = AsyncMock()

        def factory(_uid: int, _phone: str) -> MagicMock:
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

    async def test_reconcile_keeps_max_client_open_during_backfill(self) -> None:
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock()
        repos.topic_repo.find_by_user = AsyncMock(return_value=[])
        repos.topic_repo.save = AsyncMock()
        repos.audit_repo.log = AsyncMock()
        repos.cursor_repo.upsert = AsyncMock()
        repos.max_chat_repo.get = AsyncMock(
            return_value=MaxChat(
                max_chat_id="chat_new",
                binding_telegram_user_id=123,
                title="New Chat",
                chat_type=ChatType.PERSONAL,
            )
        )
        repos.telegram.create_topic = AsyncMock(return_value=200)
        repos.telegram.send_text_to_topic = AsyncMock(return_value=500)

        max_client = MagicMock(start=AsyncMock())
        max_client.list_personal_chats = AsyncMock(
            return_value=[{"max_chat_id": "chat_new", "title": "New Chat"}]
        )
        max_client.close = AsyncMock()

        async def get_messages(*_args: object, **_kwargs: object) -> list[dict[str, str]]:
            assert max_client.close.await_count == 0
            return [{"max_message_id": "42", "text": "hello"}]

        max_client.get_messages = AsyncMock(side_effect=get_messages)

        def factory(_uid: int, _phone: str) -> MagicMock:
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

        assert max_client.get_messages.await_count == 2
        max_client.close.assert_awaited_once()
        repos.telegram.send_text_to_topic.assert_awaited_once_with(
            chat_id=123,
            topic_id=200,
            text="[Unknown UnknownID ??.??.?? ??:??]\nhello",
        )

    async def test_send_backfill_message_falls_back_to_text_when_audio_url_is_rejected(self) -> None:
        repos = MockRepos()
        repos.telegram.send_audio_to_topic = AsyncMock(
            side_effect=TelegramBadRequest(
                method=MagicMock(),
                message="failed to get HTTP URL content",
            )
        )
        repos.telegram.send_text_to_topic = AsyncMock(return_value=500)

        service = RefreshReconcileService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda _uid, _phone: MagicMock(),
            backfill_count=5,
        )

        await service._send_backfill_message(  # type: ignore[reportPrivateUsage]
            telegram_user_id=123,
            topic_id=200,
            msg={
                "chat_id": "0",
                "type": "audio",
                "media_url": "https://example.com/audio.mp3",
                "sender_name": "Igor",
                "sender_id": 192875451,
                "time": int(datetime(2026, 3, 22, 22, 30, tzinfo=UTC).timestamp() * 1000),
            },
        )

        repos.telegram.send_text_to_topic.assert_awaited_once_with(
            chat_id=123,
            topic_id=200,
            text="[Igor 192875451 22.03.26 22:30]\n[audio]: https://example.com/audio.mp3",
        )

    async def test_backfill_continues_after_single_message_failure(self) -> None:
        repos = MockRepos()
        sleep = AsyncMock()
        repos.telegram.send_text_to_topic = AsyncMock(
            side_effect=[
                TelegramBadRequest(method=MagicMock(), message="message thread not found"),
                500,
                501,
            ]
        )

        first = {
            "max_message_id": "1",
            "chat_id": "chat1",
            "type": "text",
            "text": "first",
            "sender_name": "Alice",
            "sender_id": 101,
            "time": int(datetime(2026, 3, 22, 22, 30, tzinfo=UTC).timestamp() * 1000),
        }
        second = {
            "max_message_id": "2",
            "chat_id": "chat1",
            "type": "text",
            "text": "second",
            "sender_name": "Alice",
            "sender_id": 101,
            "time": int(datetime(2026, 3, 22, 22, 31, tzinfo=UTC).timestamp() * 1000),
        }

        max_client = MagicMock()
        max_client.get_messages = AsyncMock(return_value=[first, second])

        service = RefreshReconcileService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda _uid, _phone: MagicMock(),
            backfill_count=5,
            sleep_func=sleep,
        )

        await service._backfill(  # type: ignore[reportPrivateUsage]
            telegram_user_id=123,
            max_chat_id="chat1",
            topic_id=200,
            max_client=max_client,
        )

        assert repos.telegram.send_text_to_topic.await_count == 3
        sleep.assert_awaited()

    async def test_send_backfill_message_retries_message_thread_not_found(self) -> None:
        repos = MockRepos()
        sleep = AsyncMock()
        repos.telegram.send_text_to_topic = AsyncMock(
            side_effect=[
                TelegramBadRequest(method=MagicMock(), message="message thread not found"),
                500,
            ]
        )

        service = RefreshReconcileService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda _uid, _phone: MagicMock(),
            backfill_count=5,
            sleep_func=sleep,
        )

        result = await service._send_backfill_message(  # type: ignore[reportPrivateUsage]
            telegram_user_id=123,
            topic_id=200,
            msg={
                "chat_id": "chat1",
                "type": "text",
                "text": "hello",
                "sender_name": "Alice",
                "sender_id": 101,
                "time": int(datetime(2026, 3, 22, 22, 30, tzinfo=UTC).timestamp() * 1000),
            },
        )

        assert result == 500
        assert repos.telegram.send_text_to_topic.await_count == 2
        sleep.assert_awaited()

    async def test_create_topic_with_backfill_skips_cursor_update_when_backfill_has_failures(self) -> None:
        repos = MockRepos()
        sleep = AsyncMock()
        repos.max_chat_repo.get = AsyncMock(
            return_value=MaxChat(
                max_chat_id="chat1",
                binding_telegram_user_id=123,
                title="Alice",
                chat_type=ChatType.PERSONAL,
            )
        )
        repos.topic_repo.save = AsyncMock()
        repos.audit_repo.log = AsyncMock()
        repos.telegram.create_topic = AsyncMock(return_value=200)
        repos.telegram.send_text_to_topic = AsyncMock(
            side_effect=TelegramBadRequest(method=MagicMock(), message="message thread not found")
        )
        repos.cursor_repo.upsert = AsyncMock()

        message = {
            "max_message_id": "1",
            "chat_id": "chat1",
            "type": "text",
            "text": "first",
            "sender_name": "Alice",
            "sender_id": 101,
            "time": int(datetime(2026, 3, 22, 22, 30, tzinfo=UTC).timestamp() * 1000),
        }

        max_client = MagicMock()
        max_client.get_messages = AsyncMock(return_value=[message])

        service = RefreshReconcileService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda _uid, _phone: MagicMock(),
            backfill_count=5,
            sleep_func=sleep,
        )

        await service._create_topic_with_backfill(  # type: ignore[reportPrivateUsage]
            telegram_user_id=123,
            max_chat_id="chat1",
            max_client=max_client,
        )

        repos.cursor_repo.upsert.assert_not_awaited()

    async def test_reconcile_continues_when_one_chat_create_topic_fails(self) -> None:
        repos = MockRepos()
        sleep = AsyncMock()
        repos.binding_repo.get = AsyncMock()
        repos.max_chat_repo.save = AsyncMock()
        repos.topic_repo.find_by_user = AsyncMock(return_value=[])
        repos.max_chat_repo.get = AsyncMock(
            side_effect=[
                MaxChat(
                    max_chat_id="chat1",
                    binding_telegram_user_id=123,
                    title="Alice",
                    chat_type=ChatType.PERSONAL,
                ),
                MaxChat(
                    max_chat_id="chat2",
                    binding_telegram_user_id=123,
                    title="Bob",
                    chat_type=ChatType.PERSONAL,
                ),
            ]
        )
        repos.topic_repo.save = AsyncMock()
        repos.audit_repo.log = AsyncMock()
        repos.cursor_repo.upsert = AsyncMock()
        repos.telegram.create_topic = AsyncMock(side_effect=[RuntimeError("boom"), 201])
        repos.telegram.send_text_to_topic = AsyncMock(return_value=500)

        max_client = MagicMock(start=AsyncMock())
        max_client.list_personal_chats = AsyncMock(
            return_value=[
                {"max_chat_id": "chat1", "title": "Alice", "participant_ids": ["1", "101"]},
                {"max_chat_id": "chat2", "title": "Bob", "participant_ids": ["1", "202"]},
            ]
        )
        max_client.get_messages = AsyncMock(return_value=[])
        max_client.close = AsyncMock()

        service = RefreshReconcileService(
            binding_repo=repos.binding_repo,
            max_chat_repo=repos.max_chat_repo,
            topic_repo=repos.topic_repo,
            cursor_repo=repos.cursor_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=lambda _uid, _phone: max_client,
            backfill_count=5,
            sleep_func=sleep,
        )

        await service.reconcile(telegram_user_id=123)

        assert repos.telegram.create_topic.await_count == 2
        repos.topic_repo.save.assert_awaited()

    async def test_reconcile_uses_fallback_title_for_empty_chat_name(self) -> None:
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock()
        repos.topic_repo.find_by_user = AsyncMock(return_value=[])
        repos.topic_repo.save = AsyncMock()
        repos.audit_repo.log = AsyncMock()
        repos.cursor_repo.upsert = AsyncMock()
        repos.max_chat_repo.get = AsyncMock(
            return_value=MaxChat(
                max_chat_id="chat_empty",
                binding_telegram_user_id=123,
                title="",
                chat_type=ChatType.PERSONAL,
            )
        )
        repos.telegram.create_topic = AsyncMock(return_value=200)
        repos.telegram.send_text_to_topic = AsyncMock(return_value=500)

        max_client = MagicMock(start=AsyncMock())
        max_client.list_personal_chats = AsyncMock(
            return_value=[{"max_chat_id": "chat_empty", "title": ""}]
        )
        max_client.get_messages = AsyncMock(return_value=[])
        max_client.close = AsyncMock()

        def factory(_uid: int, _phone: str) -> MagicMock:
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

        repos.telegram.create_topic.assert_called_once_with(
            chat_id=123,
            title="Chat chat_empty",
        )

    async def test_reconcile_saves_cursor_from_max_message_id(self) -> None:
        repos = MockRepos()
        repos.binding_repo.get = AsyncMock()
        repos.topic_repo.find_by_user = AsyncMock(return_value=[])
        repos.topic_repo.save = AsyncMock()
        repos.audit_repo.log = AsyncMock()
        repos.cursor_repo.upsert = AsyncMock()
        repos.max_chat_repo.get = AsyncMock(
            return_value=MaxChat(
                max_chat_id="chat_new",
                binding_telegram_user_id=123,
                title="New Chat",
                chat_type=ChatType.PERSONAL,
            )
        )
        repos.telegram.create_topic = AsyncMock(return_value=200)
        repos.telegram.send_text_to_topic = AsyncMock(return_value=500)

        max_client = MagicMock(start=AsyncMock())
        max_client.list_personal_chats = AsyncMock(
            return_value=[{"max_chat_id": "chat_new", "title": "New Chat"}]
        )
        max_client.get_messages = AsyncMock(
            return_value=[
                {"max_message_id": "41", "text": "first"},
                {"max_message_id": "42", "text": "second"},
            ]
        )
        max_client.close = AsyncMock()

        def factory(_uid: int, _phone: str) -> MagicMock:
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

        saved_cursor = repos.cursor_repo.upsert.await_args.args[0]
        assert saved_cursor.last_max_message_id == "42"
