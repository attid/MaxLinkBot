from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pymax.files import File

from src.application.auth.exceptions import AuthError
from src.infrastructure.max.adapter import PymaxAdapter


@pytest.mark.asyncio
async def test_start_returns_after_on_start_and_keeps_client_running() -> None:
    client = MagicMock()
    client._stop_event = asyncio.Event()  # type: ignore[attr-defined]
    client.close = AsyncMock()

    on_start_handler: Callable[[], object] | None = None

    def add_on_start_handler(
        handler: Callable[[], object | Awaitable[object]],
    ) -> Callable[[], object | Awaitable[object]]:
        nonlocal on_start_handler
        on_start_handler = handler
        return handler

    client.add_on_start_handler.side_effect = add_on_start_handler
    client.add_message_handler = MagicMock()

    async def start_side_effect() -> None:
        if on_start_handler is not None:
            result = on_start_handler()
            if asyncio.iscoroutine(result):
                await result
        await client._stop_event.wait()  # type: ignore[attr-defined]

    client.start = AsyncMock(side_effect=start_side_effect)

    adapter = PymaxAdapter(client)

    await asyncio.wait_for(adapter.start(), timeout=0.5)

    assert adapter._started is True
    assert adapter._client_task is not None
    assert not adapter._client_task.done()
    client.start.assert_awaited_once()
    client.add_message_handler.assert_called_once()
    client.add_on_start_handler.assert_called_once()

    await adapter.close()

    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_messages_returns_max_message_id_key() -> None:
    raw_message = MagicMock()
    raw_message.id = 42
    raw_message.text = "hello"
    raw_message.sender_id = 7
    raw_message.sender = "alice"
    raw_message.time = 123

    client = MagicMock()
    client.fetch_history = AsyncMock(return_value=[raw_message])
    client.get_cached_user = MagicMock(return_value=None)
    client.fetch_users = AsyncMock(return_value=[])

    adapter = PymaxAdapter(client)

    messages = await adapter.get_messages("100", since_message_id=None, limit=5)

    assert messages == [
        {
            "max_message_id": "42",
            "chat_id": "100",
            "text": "hello",
            "sender_id": 7,
            "sender_name": "alice",
            "time": 123,
            "type": "text",
            "description": "",
            "media_url": None,
            "file_name": None,
        }
    ]


@pytest.mark.asyncio
async def test_list_personal_chats_uses_other_participant_name_for_dialog_title() -> None:
    chat = MagicMock()
    chat.id = 100
    chat.title = None
    chat.type = "DIALOG"
    chat.owner = 1
    chat.participants = {1: 0, 2: 0}

    user = SimpleNamespace(
        names=[SimpleNamespace(name="Vasya", first_name="Vasya", last_name="")]
    )

    client = MagicMock()
    client.fetch_chats = AsyncMock(return_value=[chat])
    client.get_cached_user = MagicMock(return_value=user)
    client.fetch_users = AsyncMock(return_value=[])

    adapter = PymaxAdapter(client)

    chats = await adapter.list_personal_chats()

    assert chats == [{"max_chat_id": "100", "title": "Vasya", "participant_ids": ["1", "2"]}]
    client.fetch_users.assert_not_called()


@pytest.mark.asyncio
async def test_get_messages_uses_cached_sender_name_when_available() -> None:
    raw_message = MagicMock()
    raw_message.id = 42
    raw_message.text = "hello"
    raw_message.sender = 7
    raw_message.time = 123

    user = SimpleNamespace(
        names=[SimpleNamespace(name="Petya", first_name="Petya", last_name="")]
    )

    client = MagicMock()
    client.fetch_history = AsyncMock(return_value=[raw_message])
    client.get_cached_user = MagicMock(return_value=user)
    client.fetch_users = AsyncMock(return_value=[])

    adapter = PymaxAdapter(client)

    messages = await adapter.get_messages("100", since_message_id=None, limit=5)

    assert messages[0]["sender_name"] == "Petya"
    assert messages[0]["sender_id"] == 7


@pytest.mark.asyncio
async def test_get_messages_falls_back_to_sender_field_for_sender_id() -> None:
    raw_message = MagicMock()
    raw_message.id = 42
    raw_message.text = "hello"
    raw_message.sender = 147493423
    raw_message.sender_id = None
    raw_message.time = 123

    user = SimpleNamespace(
        names=[SimpleNamespace(name="Виктор Григорьевич", first_name="Виктор", last_name="Григорьевич")]
    )

    client = MagicMock()
    client.fetch_history = AsyncMock(return_value=[raw_message])
    client.get_cached_user = MagicMock(return_value=user)
    client.fetch_users = AsyncMock(return_value=[])

    adapter = PymaxAdapter(client)

    messages = await adapter.get_messages("100", since_message_id=None, limit=5)

    assert messages[0]["sender_id"] == 147493423
    assert messages[0]["sender_name"] == "Виктор Григорьевич"


@pytest.mark.asyncio
async def test_get_messages_includes_type_and_description_from_history() -> None:
    raw_message = MagicMock()
    raw_message.id = 42
    raw_message.text = ""
    raw_message.sender = "alice"
    raw_message.sender_id = 7
    raw_message.time = 123
    raw_message.type = "image"
    raw_message.description = "Sunset photo"

    client = MagicMock()
    client.fetch_history = AsyncMock(return_value=[raw_message])
    client.get_cached_user = MagicMock(return_value=None)
    client.fetch_users = AsyncMock(return_value=[])

    adapter = PymaxAdapter(client)

    messages = await adapter.get_messages("100", since_message_id=None, limit=5)

    assert messages[0]["type"] == "image"
    assert messages[0]["description"] == "Sunset photo"


@pytest.mark.asyncio
async def test_get_messages_extracts_photo_attach_url_from_history() -> None:
    raw_message = MagicMock()
    raw_message.id = 42
    raw_message.text = ""
    raw_message.sender = 7
    raw_message.sender_id = None
    raw_message.time = 123
    raw_message.type = "USER"
    raw_message.description = None
    raw_message.attaches = [
        SimpleNamespace(
            type=SimpleNamespace(name="PHOTO", value="PHOTO"),
            base_url="https://example.com/image.jpg",
        )
    ]

    user = SimpleNamespace(
        names=[SimpleNamespace(name="Petya", first_name="Petya", last_name="")]
    )

    client = MagicMock()
    client.fetch_history = AsyncMock(return_value=[raw_message])
    client.get_cached_user = MagicMock(return_value=user)
    client.fetch_users = AsyncMock(return_value=[])

    adapter = PymaxAdapter(client)

    messages = await adapter.get_messages("100", since_message_id=None, limit=5)

    assert messages[0]["type"] == "photo"
    assert messages[0]["media_url"] == "https://example.com/image.jpg"


@pytest.mark.asyncio
async def test_get_messages_extracts_audio_attach_url_from_history() -> None:
    raw_message = MagicMock()
    raw_message.id = 42
    raw_message.text = ""
    raw_message.sender = 7
    raw_message.sender_id = None
    raw_message.time = 123
    raw_message.type = "USER"
    raw_message.description = None
    raw_message.attaches = [
        SimpleNamespace(
            type=SimpleNamespace(name="AUDIO", value="AUDIO"),
            url="https://example.com/audio.mp3",
        )
    ]

    user = SimpleNamespace(
        names=[SimpleNamespace(name="Petya", first_name="Petya", last_name="")]
    )

    client = MagicMock()
    client.fetch_history = AsyncMock(return_value=[raw_message])
    client.get_cached_user = MagicMock(return_value=user)
    client.fetch_users = AsyncMock(return_value=[])

    adapter = PymaxAdapter(client)

    messages = await adapter.get_messages("100", since_message_id=None, limit=5)

    assert messages[0]["type"] == "audio"
    assert messages[0]["media_url"] == "https://example.com/audio.mp3"


@pytest.mark.asyncio
async def test_get_messages_extracts_file_attach_name_without_url_from_history() -> None:
    raw_message = MagicMock()
    raw_message.id = 42
    raw_message.text = ""
    raw_message.sender = 7
    raw_message.sender_id = None
    raw_message.time = 123
    raw_message.type = "USER"
    raw_message.description = None
    raw_message.attaches = [
        SimpleNamespace(
            type=SimpleNamespace(name="FILE", value="FILE"),
            name="crash.txt",
            token="abc-token",
            size=1234,
        )
    ]

    user = SimpleNamespace(
        names=[SimpleNamespace(name="Petya", first_name="Petya", last_name="")]
    )

    client = MagicMock()
    client.fetch_history = AsyncMock(return_value=[raw_message])
    client.get_cached_user = MagicMock(return_value=user)
    client.fetch_users = AsyncMock(return_value=[])

    adapter = PymaxAdapter(client)

    messages = await adapter.get_messages("0", since_message_id=None, limit=5)

    assert messages[0]["type"] == "document"
    assert messages[0]["media_url"] is None
    assert messages[0]["file_name"] == "crash.txt"


@pytest.mark.asyncio
async def test_get_messages_extracts_document_attach_url_and_filename_from_history() -> None:
    raw_message = MagicMock()
    raw_message.id = 42
    raw_message.text = ""
    raw_message.sender = 7
    raw_message.sender_id = None
    raw_message.time = 123
    raw_message.type = "USER"
    raw_message.description = None
    raw_message.attaches = [
        SimpleNamespace(
            type=SimpleNamespace(name="DOCUMENT", value="DOCUMENT"),
            url="https://example.com/spec.pdf",
            file_name="spec.pdf",
        )
    ]

    user = SimpleNamespace(
        names=[SimpleNamespace(name="Petya", first_name="Petya", last_name="")]
    )

    client = MagicMock()
    client.fetch_history = AsyncMock(return_value=[raw_message])
    client.get_cached_user = MagicMock(return_value=user)
    client.fetch_users = AsyncMock(return_value=[])

    adapter = PymaxAdapter(client)

    messages = await adapter.get_messages("100", since_message_id=None, limit=5)

    assert messages[0]["type"] == "document"
    assert messages[0]["media_url"] == "https://example.com/spec.pdf"
    assert messages[0]["file_name"] == "spec.pdf"


@pytest.mark.asyncio
async def test_send_photo_uses_temp_file_attachment() -> None:
    sent_message = SimpleNamespace(id=99)
    client = MagicMock()
    client.send_message = AsyncMock(return_value=sent_message)

    adapter = PymaxAdapter(client)

    result = await adapter.send_photo(
        "100",
        b"image-bytes",
        "telegram-image.png",
        "Caption",
    )

    assert result == "99"
    send_call = client.send_message.await_args
    assert send_call.kwargs["text"] == "Caption"
    assert send_call.kwargs["chat_id"] == 100
    attachment = send_call.kwargs["attachment"]
    assert attachment.file_name.endswith(".png")
    assert not os.path.exists(attachment.path)


@pytest.mark.asyncio
async def test_send_file_uses_temp_file_attachment() -> None:
    sent_message = SimpleNamespace(id=100)
    client = MagicMock()
    client.send_message = AsyncMock(return_value=sent_message)

    adapter = PymaxAdapter(client)

    result = await adapter.send_file(
        "100",
        b"file-bytes",
        "spec.pdf",
        "Spec caption",
    )

    assert result == "100"
    send_call = client.send_message.await_args
    assert send_call.kwargs["text"] == "Spec caption"
    assert send_call.kwargs["chat_id"] == 100
    attachment = send_call.kwargs["attachment"]
    assert isinstance(attachment, File)
    assert attachment.path.endswith(".pdf")
    assert not os.path.exists(attachment.path)


@pytest.mark.asyncio
async def test_resolve_user_display_name_caches_fetch_users_result() -> None:
    user = SimpleNamespace(
        names=[SimpleNamespace(name="Roman", first_name="Roman", last_name="")]
    )

    client = MagicMock()
    client.get_cached_user = MagicMock(return_value=None)
    client.fetch_users = AsyncMock(return_value=[user])

    adapter = PymaxAdapter(client)

    first = await adapter._resolve_user_display_name(7)  # type: ignore[reportPrivateUsage]
    second = await adapter._resolve_user_display_name(7)  # type: ignore[reportPrivateUsage]

    assert first == "Roman"
    assert second == "Roman"
    client.fetch_users.assert_awaited_once_with([7])


@pytest.mark.asyncio
async def test_get_messages_filters_since_id_without_dropping_newer_messages() -> None:
    older = MagicMock()
    older.id = 40
    older.text = "older"
    older.sender = "alice"
    older.sender_id = 7
    older.time = 100

    newer = MagicMock()
    newer.id = 41
    newer.text = "newer"
    newer.sender = "alice"
    newer.sender_id = 7
    newer.time = 101

    newest = MagicMock()
    newest.id = 42
    newest.text = "newest"
    newest.sender = "alice"
    newest.sender_id = 7
    newest.time = 102

    client = MagicMock()
    client.fetch_history = AsyncMock(return_value=[older, newer, newest])
    client.get_cached_user = MagicMock(return_value=None)
    client.fetch_users = AsyncMock(return_value=[])

    adapter = PymaxAdapter(client)

    messages = await adapter.get_messages("100", since_message_id="40", limit=50)

    assert [message["max_message_id"] for message in messages] == ["41", "42"]


@pytest.mark.asyncio
async def test_consume_reconnect_event_returns_true_after_second_on_start() -> None:
    client = MagicMock()
    client._stop_event = asyncio.Event()  # type: ignore[attr-defined]
    client.close = AsyncMock()

    on_start_handler: Callable[[], object] | None = None

    def add_on_start_handler(
        handler: Callable[[], object | Awaitable[object]],
    ) -> Callable[[], object | Awaitable[object]]:
        nonlocal on_start_handler
        on_start_handler = handler
        return handler

    client.add_on_start_handler.side_effect = add_on_start_handler
    client.add_message_handler = MagicMock()

    async def start_side_effect() -> None:
        if on_start_handler is not None:
            result = on_start_handler()
            if asyncio.iscoroutine(result):
                await result
        await client._stop_event.wait()  # type: ignore[attr-defined]

    client.start = AsyncMock(side_effect=start_side_effect)

    adapter = PymaxAdapter(client)

    await asyncio.wait_for(adapter.start(), timeout=0.5)
    assert await adapter.consume_reconnect_event() is False

    assert on_start_handler is not None
    result = on_start_handler()
    if asyncio.iscoroutine(result):
        await result

    assert await adapter.consume_reconnect_event() is True
    assert await adapter.consume_reconnect_event() is False

    await adapter.close()


@pytest.mark.asyncio
async def test_start_raises_auth_error_when_session_db_missing(tmp_path) -> None:
    client = MagicMock()
    client.add_message_handler = MagicMock()
    client.add_on_start_handler = MagicMock()
    client.start = AsyncMock()

    adapter = PymaxAdapter(client, session_db_path=tmp_path / "session.db")

    with pytest.raises(AuthError, match="Persisted MAX session not found"):
        await adapter.start()

    client.start.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_raises_auth_error_when_session_db_has_empty_token(tmp_path) -> None:
    session_db_path = tmp_path / "session.db"
    import sqlite3

    with sqlite3.connect(session_db_path) as conn:
        conn.execute("CREATE TABLE auth (token VARCHAR, device_id CHAR(32) NOT NULL, PRIMARY KEY (device_id))")
        conn.execute(
            "INSERT INTO auth(token, device_id) VALUES (?, ?)",
            ("", "device-1"),
        )
        conn.commit()

    client = MagicMock()
    client.add_message_handler = MagicMock()
    client.add_on_start_handler = MagicMock()
    client.start = AsyncMock()

    adapter = PymaxAdapter(client, session_db_path=session_db_path)

    with pytest.raises(AuthError, match="Persisted MAX session is not authorized"):
        await adapter.start()

    client.start.assert_not_awaited()
