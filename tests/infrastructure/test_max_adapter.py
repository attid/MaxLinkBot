from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Awaitable, Callable
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError
from pymax import File, Photo
from pymax.exceptions import ApiError
from pymax.types.domain.attachments.video import VideoRequest

from src.application.auth.exceptions import AuthError
from src.infrastructure.max import adapter as adapter_module
from src.infrastructure.max.adapter import PymaxAdapter


@pytest.mark.asyncio
async def test_close_cancels_running_client_without_concurrent_direct_close() -> None:
    client = MagicMock()
    stop_event = asyncio.Event()

    on_start_handler: Callable[[object], object] | None = None

    def on_start() -> Callable[
        [Callable[[object], object | Awaitable[object]]],
        Callable[[object], object | Awaitable[object]],
    ]:
        def register(
            handler: Callable[[object], object | Awaitable[object]],
        ) -> Callable[[object], object | Awaitable[object]]:
            nonlocal on_start_handler
            on_start_handler = handler
            return handler

        return register

    client.on_start.side_effect = on_start
    client.on_message.return_value = lambda handler: handler  # type: ignore[reportUnknownLambdaType]

    async def start_side_effect() -> None:
        if on_start_handler is not None:
            result = on_start_handler(client)
            if asyncio.iscoroutine(result):
                await result
        await stop_event.wait()

    client.start = AsyncMock(side_effect=start_side_effect)
    client.close = AsyncMock(side_effect=lambda: stop_event.set())

    adapter = PymaxAdapter(client)

    await asyncio.wait_for(adapter.start(), timeout=0.5)

    assert adapter._started is True  # type: ignore[reportPrivateUsage]
    assert adapter._client_task is not None  # type: ignore[reportPrivateUsage]
    assert not adapter._client_task.done()  # type: ignore[reportPrivateUsage]
    client.start.assert_awaited_once()
    client.on_message.assert_called_once_with()
    client.on_start.assert_called_once_with()

    await adapter.close()

    client.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_propagates_client_failure_before_ready() -> None:
    client = MagicMock()
    client.on_start.return_value = lambda handler: handler  # type: ignore[reportUnknownLambdaType]
    client.on_message.return_value = lambda handler: handler  # type: ignore[reportUnknownLambdaType]
    client.start = AsyncMock(side_effect=RuntimeError("login rejected"))

    adapter = PymaxAdapter(client)

    with pytest.raises(RuntimeError, match="login rejected"):
        await asyncio.wait_for(adapter.start(), timeout=0.5)


@pytest.mark.asyncio
async def test_start_maps_login_api_error_to_auth_error() -> None:
    client = MagicMock()
    client.on_start.return_value = lambda handler: handler  # type: ignore[reportUnknownLambdaType]
    client.on_message.return_value = lambda handler: handler  # type: ignore[reportUnknownLambdaType]
    client.start = AsyncMock(
        side_effect=ApiError(opcode=19, error="auth.token", message="Token rejected")
    )

    adapter = PymaxAdapter(client)

    with pytest.raises(AuthError, match="MAX session login failed"):
        await adapter.start()


@pytest.mark.asyncio
async def test_start_for_qr_maps_client_failure_to_auth_error() -> None:
    client = MagicMock()
    client.on_start.return_value = lambda handler: handler  # type: ignore[reportUnknownLambdaType]
    client.on_message.return_value = lambda handler: handler  # type: ignore[reportUnknownLambdaType]
    client.start = AsyncMock(side_effect=RuntimeError("QR startup failed"))

    adapter = PymaxAdapter(client)

    with pytest.raises(AuthError, match="MAX QR startup failed: QR startup failed"):
        await asyncio.wait_for(adapter.start_for_qr(), timeout=0.5)


@pytest.mark.asyncio
async def test_wait_until_authorized_waits_for_on_start() -> None:
    client = MagicMock()
    stop_event = asyncio.Event()
    on_start_handler: Callable[[object], object] | None = None

    def on_start() -> Callable[
        [Callable[[object], object | Awaitable[object]]],
        Callable[[object], object | Awaitable[object]],
    ]:
        def register(
            handler: Callable[[object], object | Awaitable[object]],
        ) -> Callable[[object], object | Awaitable[object]]:
            nonlocal on_start_handler
            on_start_handler = handler
            return handler

        return register

    client.on_start.side_effect = on_start
    client.on_message.return_value = lambda handler: handler  # type: ignore[reportUnknownLambdaType]

    async def start_side_effect() -> None:
        await stop_event.wait()

    client.start = AsyncMock(side_effect=start_side_effect)
    client.close = AsyncMock(side_effect=lambda: stop_event.set())
    provider = MagicMock()
    provider.wait_for_qr = AsyncMock(return_value=b"qr-png")
    adapter = PymaxAdapter(client, qr_provider=provider)

    assert await adapter.start_for_qr() == b"qr-png"
    wait_task = asyncio.create_task(adapter.wait_until_authorized())
    await asyncio.sleep(0)
    assert not wait_task.done()

    assert on_start_handler is not None
    result = on_start_handler(client)
    if asyncio.iscoroutine(result):
        await result

    await asyncio.wait_for(wait_task, timeout=0.5)
    assert await adapter.is_session_valid() is True
    await adapter.close()


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
            "media": [],
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

    user = SimpleNamespace(names=[SimpleNamespace(name="Vasya", first_name="Vasya", last_name="")])

    client = MagicMock()
    client.fetch_chats = AsyncMock(return_value=[chat])
    client.get_cached_user = MagicMock(return_value=user)
    client.fetch_users = AsyncMock(return_value=[])

    adapter = PymaxAdapter(client)

    chats = await adapter.list_personal_chats()

    assert chats == [{"max_chat_id": "100", "title": "Vasya", "participant_ids": ["1", "2"]}]
    client.fetch_users.assert_not_called()


@pytest.mark.asyncio
async def test_get_chat_state_reports_unsubscribed_channel_membership() -> None:
    stale_chat = SimpleNamespace(
        id=-75032416815636,
        title="Новокриницкие от 0 до года",
        type="CHANNEL",
        owner=0,
        participants={192875451: 0},
    )
    fresh_chat = SimpleNamespace(
        id=-75032416815636,
        title="Новокриницкие от 0 до года",
        type="CHANNEL",
        owner=0,
        participants={},
    )
    client = MagicMock()
    client.me = SimpleNamespace(contact=SimpleNamespace(id=192875451))
    client.chats = [stale_chat]

    async def get_chat(chat_id: int):
        assert chat_id == -75032416815636
        assert all(chat.id != chat_id for chat in client.chats)
        return fresh_chat

    client.get_chat = AsyncMock(side_effect=get_chat)

    state = await PymaxAdapter(client).get_chat_state("-75032416815636")

    assert state == {
        "max_chat_id": "-75032416815636",
        "title": "Новокриницкие от 0 до года",
        "participant_ids": [],
        "chat_type": "CHANNEL",
        "is_current_user_member": False,
    }
    client.get_chat.assert_awaited_once_with(-75032416815636)


@pytest.mark.asyncio
async def test_get_chat_state_reports_subscribed_channel_membership() -> None:
    chat = SimpleNamespace(
        id=-69679794189655,
        title="Аттракционы Ривьера Сочи.",
        type="CHANNEL",
        owner=0,
        participants={192875451: 0},
    )
    client = MagicMock()
    client.me = SimpleNamespace(contact=SimpleNamespace(id=192875451))
    client.get_chat = AsyncMock(return_value=chat)

    state = await PymaxAdapter(client).get_chat_state("-69679794189655")

    assert state is not None
    assert state.get("is_current_user_member") is True


@pytest.mark.asyncio
async def test_get_messages_uses_cached_sender_name_when_available() -> None:
    raw_message = MagicMock()
    raw_message.id = 42
    raw_message.text = "hello"
    raw_message.sender = 7
    raw_message.time = 123

    user = SimpleNamespace(names=[SimpleNamespace(name="Petya", first_name="Petya", last_name="")])

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
        names=[
            SimpleNamespace(name="Виктор Григорьевич", first_name="Виктор", last_name="Григорьевич")
        ]
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

    user = SimpleNamespace(names=[SimpleNamespace(name="Petya", first_name="Petya", last_name="")])

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

    user = SimpleNamespace(names=[SimpleNamespace(name="Petya", first_name="Petya", last_name="")])

    client = MagicMock()
    client.fetch_history = AsyncMock(return_value=[raw_message])
    client.get_cached_user = MagicMock(return_value=user)
    client.fetch_users = AsyncMock(return_value=[])

    adapter = PymaxAdapter(client)

    messages = await adapter.get_messages("100", since_message_id=None, limit=5)

    assert messages[0]["type"] == "audio"
    assert messages[0]["media_url"] == "https://example.com/audio.mp3"


@pytest.mark.asyncio
async def test_get_messages_resolves_direct_video_attach_url() -> None:
    raw_message = SimpleNamespace(
        id=42,
        text="Video caption",
        sender="Petya",
        sender_id=None,
        time=123,
        type="USER",
        description=None,
        attaches=[
            SimpleNamespace(
                type=SimpleNamespace(name="VIDEO", value="VIDEO"),
                video_id=777,
                duration=18000,
                width=480,
                height=480,
            )
        ],
    )
    client = MagicMock()
    client.fetch_history = AsyncMock(return_value=[raw_message])
    client.get_video_by_id = AsyncMock(
        return_value=SimpleNamespace(url="https://example.com/video.mp4")
    )
    adapter = PymaxAdapter(client)

    messages = await adapter.get_messages("0", since_message_id=None, limit=5)

    assert messages[0]["type"] == "video"
    assert messages[0]["media_url"] == "https://example.com/video.mp4"
    assert messages[0]["file_name"] == "video.mp4"
    assert messages[0]["text"] == "Video caption"
    client.get_video_by_id.assert_awaited_once_with(0, 42, 777)


@pytest.mark.asyncio
async def test_get_messages_recovers_dynamic_video_url_from_pymax_validation_error() -> None:
    raw_message = SimpleNamespace(
        id=117110862086738596,
        text="",
        sender=5079376,
        sender_id=None,
        time=1786969941509,
        type="USER",
        description=None,
        attaches=[
            SimpleNamespace(
                type=SimpleNamespace(name="VIDEO", value="VIDEO"),
                video_id=3112890335312,
                duration=48045,
                width=480,
                height=480,
            )
        ],
    )
    with pytest.raises(ValidationError) as exc_info:
        VideoRequest.model_validate(
            {
                "MP4_360": "https://example.com/video-360.mp4",
                "MP4_480": "https://example.com/video-480.mp4",
            }
        )

    client = MagicMock()
    client.fetch_history = AsyncMock(return_value=[raw_message])
    client.get_cached_user = MagicMock(return_value=None)
    client.fetch_users = AsyncMock(return_value=[])
    client.get_video_by_id = AsyncMock(side_effect=exc_info.value)
    adapter = PymaxAdapter(client)

    messages = await adapter.get_messages("187861739", since_message_id=None, limit=5)

    assert messages[0]["type"] == "video"
    assert messages[0]["media_url"] == "https://example.com/video-480.mp4"
    assert messages[0]["file_name"] == "video.mp4"


@pytest.mark.asyncio
async def test_get_messages_resolves_file_attach_url_from_history() -> None:
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
            file_id=555,
            name="crash.txt",
            token="abc-token",
            size=1234,
        )
    ]

    user = SimpleNamespace(names=[SimpleNamespace(name="Petya", first_name="Petya", last_name="")])

    client = MagicMock()
    client.fetch_history = AsyncMock(return_value=[raw_message])
    client.get_cached_user = MagicMock(return_value=user)
    client.fetch_users = AsyncMock(return_value=[])
    client.get_file_by_id = AsyncMock(
        return_value=SimpleNamespace(url="https://example.com/crash.txt")
    )

    adapter = PymaxAdapter(client)

    messages = await adapter.get_messages("0", since_message_id=None, limit=5)

    assert messages[0]["type"] == "document"
    assert messages[0]["media_url"] == "https://example.com/crash.txt"
    assert messages[0]["file_name"] == "crash.txt"
    client.get_file_by_id.assert_awaited_once_with(0, 42, 555)


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

    user = SimpleNamespace(names=[SimpleNamespace(name="Petya", first_name="Petya", last_name="")])

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
async def test_get_messages_uses_linked_forward_text_when_top_level_message_is_empty() -> None:
    forwarded = SimpleNamespace(
        text="Пересланный текст",
        type="TEXT",
        description=None,
        attaches=[],
    )
    raw_message = MagicMock()
    raw_message.id = 42
    raw_message.text = ""
    raw_message.sender = 7
    raw_message.sender_id = None
    raw_message.time = 123
    raw_message.type = "USER"
    raw_message.description = None
    raw_message.attaches = []
    raw_message.link = SimpleNamespace(type="FORWARD", message=forwarded)

    user = SimpleNamespace(names=[SimpleNamespace(name="Petya", first_name="Petya", last_name="")])

    client = MagicMock()
    client.fetch_history = AsyncMock(return_value=[raw_message])
    client.get_cached_user = MagicMock(return_value=user)
    client.fetch_users = AsyncMock(return_value=[])

    adapter = PymaxAdapter(client)

    messages = await adapter.get_messages("100", since_message_id=None, limit=5)

    assert messages[0]["type"] == "text"
    assert messages[0]["text"] == "Пересланный текст"


@pytest.mark.asyncio
async def test_get_messages_resolves_dict_linked_video_using_top_level_message_id() -> None:
    raw_message = SimpleNamespace(
        id=99,
        text="",
        sender="Petya",
        sender_id=None,
        time=123,
        type="USER",
        description=None,
        attaches=[],
        link={
            "type": "FORWARD",
            "message": {
                "id": "77",
                "text": "Circle caption",
                "type": "USER",
                "attaches": [
                    {
                        "_type": "VIDEO",
                        "videoId": 888,
                        "duration": 18000,
                        "width": 480,
                        "height": 480,
                    }
                ],
            },
        },
    )
    client = MagicMock()
    client.fetch_history = AsyncMock(return_value=[raw_message])
    client.get_video_by_id = AsyncMock(
        return_value=SimpleNamespace(url="https://example.com/circle.mp4")
    )
    adapter = PymaxAdapter(client)

    messages = await adapter.get_messages("0", since_message_id=None, limit=5)

    assert messages[0]["type"] == "video"
    assert messages[0]["media_url"] == "https://example.com/circle.mp4"
    assert messages[0]["file_name"] == "video.mp4"
    assert messages[0]["text"] == "Circle caption"
    client.get_video_by_id.assert_awaited_once_with(0, 99, 888)


@pytest.mark.asyncio
async def test_drain_buffered_messages_resolves_numeric_live_sender() -> None:
    raw_message = SimpleNamespace(
        chat_id=100,
        id=42,
        text="hello",
        sender=192875451,
        time=123,
        type="USER",
        description="",
        attaches=[],
        link=None,
    )
    user = SimpleNamespace(names=[SimpleNamespace(name="Igor", first_name="Igor", last_name="")])
    client = MagicMock()
    client.get_cached_user = MagicMock(return_value=user)
    client.fetch_users = AsyncMock(return_value=[])
    adapter = PymaxAdapter(client)

    await adapter._buffer_message(raw_message)  # type: ignore[reportPrivateUsage]
    messages = await adapter.drain_buffered_messages()

    assert messages[0]["sender_id"] == 192875451
    assert messages[0]["sender_name"] == "Igor"


@pytest.mark.asyncio
async def test_drain_buffered_messages_uses_linked_forward_photo_metadata_when_top_level_message_is_empty() -> (
    None
):
    forwarded = SimpleNamespace(
        text="",
        type="USER",
        description=None,
        attaches=[
            SimpleNamespace(
                type=SimpleNamespace(name="PHOTO", value="PHOTO"),
                base_url="https://example.com/forwarded.jpg",
            )
        ],
    )
    raw_message = SimpleNamespace(
        chat_id=100,
        id=42,
        text="",
        sender_id=7,
        sender="Petya",
        time=123,
        type="USER",
        description="",
        attaches=[],
        link=SimpleNamespace(type="FORWARD", message=forwarded),
    )

    client = MagicMock()
    adapter = PymaxAdapter(client)

    await adapter._buffer_message(raw_message)  # type: ignore[reportPrivateUsage]
    messages = await adapter.drain_buffered_messages()

    assert messages[0]["type"] == "photo"
    assert messages[0]["media_url"] == "https://example.com/forwarded.jpg"


@pytest.mark.asyncio
async def test_send_photo_uses_raw_attachment() -> None:
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
    attachments = send_call.kwargs["attachments"]
    assert len(attachments) == 1
    attachment = attachments[0]
    assert isinstance(attachment, Photo)
    assert attachment.raw == b"image-bytes"
    assert attachment.file_name == "telegram-image.png"


@pytest.mark.asyncio
async def test_send_file_uses_raw_attachment() -> None:
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
    attachments = send_call.kwargs["attachments"]
    assert len(attachments) == 1
    attachment = attachments[0]
    assert isinstance(attachment, File)
    assert attachment.raw == b"file-bytes"
    assert attachment.name == "spec.pdf"


@pytest.mark.asyncio
async def test_resolve_user_display_name_caches_fetch_users_result() -> None:
    user = SimpleNamespace(names=[SimpleNamespace(name="Roman", first_name="Roman", last_name="")])

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
    stop_event = asyncio.Event()

    on_start_handler: Callable[[object], object] | None = None

    def on_start() -> Callable[
        [Callable[[object], object | Awaitable[object]]],
        Callable[[object], object | Awaitable[object]],
    ]:
        def register(
            handler: Callable[[object], object | Awaitable[object]],
        ) -> Callable[[object], object | Awaitable[object]]:
            nonlocal on_start_handler
            on_start_handler = handler
            return handler

        return register

    client.on_start.side_effect = on_start
    client.on_message.return_value = lambda handler: handler  # type: ignore[reportUnknownLambdaType]

    async def start_side_effect() -> None:
        if on_start_handler is not None:
            result = on_start_handler(client)
            if asyncio.iscoroutine(result):
                await result
        await stop_event.wait()

    client.start = AsyncMock(side_effect=start_side_effect)
    client.close = AsyncMock(side_effect=lambda: stop_event.set())

    adapter = PymaxAdapter(client)

    await asyncio.wait_for(adapter.start(), timeout=0.5)
    assert await adapter.consume_reconnect_event() is False

    assert on_start_handler is not None
    result = on_start_handler(client)
    if asyncio.iscoroutine(result):
        await result

    assert await adapter.consume_reconnect_event() is True
    assert await adapter.consume_reconnect_event() is False

    await adapter.close()


@pytest.mark.asyncio
async def test_start_raises_auth_error_when_session_db_missing(tmp_path: Path) -> None:
    client = MagicMock()
    client.on_message = MagicMock()
    client.on_start = MagicMock()
    client.start = AsyncMock()

    adapter = PymaxAdapter(client, session_db_path=tmp_path / "session.db")

    with pytest.raises(AuthError, match="Persisted MAX session not found"):
        await adapter.start()

    client.start.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_raises_auth_error_when_session_db_has_empty_token(tmp_path: Path) -> None:
    session_db_path = tmp_path / "session.db"

    with sqlite3.connect(session_db_path) as conn:
        conn.execute(
            "CREATE TABLE auth (token VARCHAR, device_id CHAR(32) NOT NULL, PRIMARY KEY (device_id))"
        )
        conn.execute(
            "INSERT INTO auth(token, device_id) VALUES (?, ?)",
            ("", "device-1"),
        )
        conn.commit()

    client = MagicMock()
    client.on_message = MagicMock()
    client.on_start = MagicMock()
    client.start = AsyncMock()

    adapter = PymaxAdapter(client, session_db_path=session_db_path)

    with pytest.raises(AuthError, match="Persisted MAX session is not authorized"):
        await adapter.start()

    client.start.assert_not_awaited()


@pytest.mark.asyncio
async def test_qr_provider_returns_png_bytes() -> None:
    provider = adapter_module.TelegramQrProvider()

    await provider.show_qr("https://max.ru/qr/test")

    qr_bytes = await provider.wait_for_qr(timeout=0.1)
    assert qr_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_migrate_legacy_session_db_preserves_auth_and_creates_sessions(tmp_path: Path) -> None:
    session_db_path = tmp_path / "session.db"
    with sqlite3.connect(session_db_path) as conn:
        conn.execute(
            "CREATE TABLE auth (token VARCHAR, device_id CHAR(32) NOT NULL, "
            "PRIMARY KEY (device_id))"
        )
        conn.execute(
            "INSERT INTO auth(token, device_id) VALUES (?, ?)",
            ("legacy-token", "legacy-device"),
        )
        conn.commit()

    adapter_module.migrate_legacy_session_db(session_db_path)

    with sqlite3.connect(session_db_path) as conn:
        legacy_row = conn.execute("SELECT token, device_id FROM auth").fetchone()
        migrated_row = conn.execute(
            "SELECT token, device_id, phone, chats_sync FROM sessions"
        ).fetchone()

    assert legacy_row == ("legacy-token", "legacy-device")
    assert migrated_row == ("legacy-token", "legacy-device", "", -1)


def test_migrate_legacy_session_db_does_not_overwrite_new_session(tmp_path: Path) -> None:
    session_db_path = tmp_path / "session.db"
    with sqlite3.connect(session_db_path) as conn:
        conn.execute(
            "CREATE TABLE auth (token VARCHAR, device_id CHAR(32) NOT NULL, "
            "PRIMARY KEY (device_id))"
        )
        conn.execute(
            "INSERT INTO auth(token, device_id) VALUES (?, ?)",
            ("legacy-token", "legacy-device"),
        )
        conn.execute(
            """
            CREATE TABLE sessions (
                token TEXT NOT NULL PRIMARY KEY,
                device_id TEXT NOT NULL,
                phone TEXT NOT NULL,
                mt_instance_id TEXT NOT NULL DEFAULT '',
                chats_sync INTEGER NOT NULL DEFAULT -1,
                contacts_sync INTEGER NOT NULL DEFAULT -1,
                drafts_sync INTEGER NOT NULL DEFAULT -1,
                presence_sync INTEGER NOT NULL DEFAULT -1,
                config_hash TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            "INSERT INTO sessions(token, device_id, phone) VALUES (?, ?, ?)",
            ("new-token", "new-device", ""),
        )
        conn.commit()

    adapter_module.migrate_legacy_session_db(session_db_path)

    with sqlite3.connect(session_db_path) as conn:
        rows = conn.execute("SELECT token, device_id FROM sessions").fetchall()

    assert rows == [("new-token", "new-device")]


@pytest.mark.asyncio
async def test_get_messages_collects_all_photo_attaches_as_media_list() -> None:
    raw_message = SimpleNamespace(
        id=42,
        text="album caption",
        sender=7,
        sender_id=None,
        time=123,
        type="USER",
        description=None,
        attaches=[
            SimpleNamespace(
                type=SimpleNamespace(name="PHOTO", value="PHOTO"),
                base_url=f"https://example.com/image-{index}.jpg",
            )
            for index in range(1, 4)
        ],
        link=None,
    )

    user = SimpleNamespace(names=[SimpleNamespace(name="Petya", first_name="Petya", last_name="")])

    client = MagicMock()
    client.fetch_history = AsyncMock(return_value=[raw_message])
    client.get_cached_user = MagicMock(return_value=user)
    client.fetch_users = AsyncMock(return_value=[])

    adapter = PymaxAdapter(client)

    messages = await adapter.get_messages("100", since_message_id=None, limit=5)

    assert messages[0]["type"] == "photo"
    assert messages[0]["media_url"] == "https://example.com/image-1.jpg"
    assert messages[0]["media"] == [
        {"type": "photo", "url": "https://example.com/image-1.jpg", "file_name": None},
        {"type": "photo", "url": "https://example.com/image-2.jpg", "file_name": None},
        {"type": "photo", "url": "https://example.com/image-3.jpg", "file_name": None},
    ]


@pytest.mark.asyncio
async def test_get_messages_resolves_download_url_for_each_file_attach() -> None:
    raw_message = SimpleNamespace(
        id=42,
        text="",
        sender=7,
        sender_id=None,
        time=123,
        type="USER",
        description=None,
        attaches=[
            SimpleNamespace(
                type=SimpleNamespace(name="FILE", value="FILE"),
                file_id=1,
                name="first.pdf",
            ),
            SimpleNamespace(
                type=SimpleNamespace(name="FILE", value="FILE"),
                file_id=2,
                name="second.pdf",
            ),
        ],
        link=None,
    )

    user = SimpleNamespace(names=[SimpleNamespace(name="Petya", first_name="Petya", last_name="")])

    client = MagicMock()
    client.fetch_history = AsyncMock(return_value=[raw_message])
    client.get_cached_user = MagicMock(return_value=user)
    client.fetch_users = AsyncMock(return_value=[])
    client.get_file_by_id = AsyncMock(
        side_effect=[
            SimpleNamespace(url="https://example.com/first.pdf"),
            SimpleNamespace(url="https://example.com/second.pdf"),
        ]
    )

    adapter = PymaxAdapter(client)

    messages = await adapter.get_messages("100", since_message_id=None, limit=5)

    assert client.get_file_by_id.await_args_list == [
        ((100, 42, 1),),
        ((100, 42, 2),),
    ]
    assert messages[0]["media"] == [
        {"type": "document", "url": "https://example.com/first.pdf", "file_name": "first.pdf"},
        {"type": "document", "url": "https://example.com/second.pdf", "file_name": "second.pdf"},
    ]


@pytest.mark.asyncio
async def test_buffered_live_message_keeps_all_photo_attaches() -> None:
    raw_message = SimpleNamespace(
        id=42,
        chat_id=100,
        text="",
        sender="Petya",
        sender_id=None,
        time=123,
        type="USER",
        description=None,
        attaches=[
            SimpleNamespace(
                type=SimpleNamespace(name="PHOTO", value="PHOTO"),
                base_url=f"https://example.com/live-{index}.jpg",
            )
            for index in range(1, 3)
        ],
        link=None,
    )

    client = MagicMock()
    client.get_cached_user = MagicMock(return_value=None)
    client.fetch_users = AsyncMock(return_value=[])

    adapter = PymaxAdapter(client)

    await adapter._buffer_message(raw_message)  # type: ignore[reportPrivateUsage]
    messages = await adapter.drain_buffered_messages()

    assert messages[0]["media"] == [
        {"type": "photo", "url": "https://example.com/live-1.jpg", "file_name": None},
        {"type": "photo", "url": "https://example.com/live-2.jpg", "file_name": None},
    ]
