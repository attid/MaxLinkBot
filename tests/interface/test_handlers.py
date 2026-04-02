from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from aiogram import Router

from src.interface.telegram_handlers.handlers import register_handlers


def _get_message_handler(router: Router):
    for handler in router.observers["message"].handlers:
        if handler.callback.__name__ == "handle_message":
            return handler.callback
    raise AssertionError("handle_message callback not found")


async def test_handle_message_forwards_topic_photo_to_max() -> None:
    router = Router()
    allowlist_gate = MagicMock()
    allowlist_gate.is_allowed.return_value = True
    auth_service = MagicMock()
    reconcile_service = MagicMock()
    outbound_service = MagicMock()
    outbound_service.deliver = AsyncMock()
    outbound_service.deliver_photo = AsyncMock(return_value="max-photo-id")
    telegram_client = MagicMock()

    register_handlers(
        router,
        allowlist_gate,
        auth_service,
        reconcile_service,
        outbound_service,
        telegram_client,
    )

    callback = _get_message_handler(router)

    bot = MagicMock()
    bot.get_file = AsyncMock(return_value=SimpleNamespace(file_path="photos/max-topic.jpg"))

    async def download_file(file_path: str, destination: io.BytesIO) -> None:
        assert file_path == "photos/max-topic.jpg"
        destination.write(b"photo-bytes")

    bot.download_file = AsyncMock(side_effect=download_file)

    message = MagicMock()
    message.from_user = SimpleNamespace(id=123)
    message.message_thread_id = 50
    message.text = None
    message.caption = "Photo from Telegram"
    message.photo = [SimpleNamespace(file_id="file-123")]
    message.bot = bot
    message.answer = AsyncMock()

    await callback(message)

    outbound_service.deliver.assert_not_called()
    outbound_service.deliver_photo.assert_awaited_once_with(
        telegram_user_id=123,
        telegram_topic_id=50,
        image_bytes=b"photo-bytes",
        filename="max-topic.jpg",
        caption="Photo from Telegram",
    )


async def test_handle_message_forwards_topic_document_to_max() -> None:
    router = Router()
    allowlist_gate = MagicMock()
    allowlist_gate.is_allowed.return_value = True
    auth_service = MagicMock()
    reconcile_service = MagicMock()
    outbound_service = MagicMock()
    outbound_service.deliver = AsyncMock()
    outbound_service.deliver_file = AsyncMock(return_value="max-file-id")
    telegram_client = MagicMock()

    register_handlers(
        router,
        allowlist_gate,
        auth_service,
        reconcile_service,
        outbound_service,
        telegram_client,
    )

    callback = _get_message_handler(router)

    bot = MagicMock()
    bot.get_file = AsyncMock(return_value=SimpleNamespace(file_path="docs/spec.pdf"))

    async def download_file(file_path: str, destination: io.BytesIO) -> None:
        assert file_path == "docs/spec.pdf"
        destination.write(b"pdf-bytes")

    bot.download_file = AsyncMock(side_effect=download_file)

    message = MagicMock()
    message.from_user = SimpleNamespace(id=123)
    message.message_thread_id = 50
    message.text = None
    message.caption = "Spec file"
    message.photo = None
    message.document = SimpleNamespace(file_id="file-doc-1", file_name="spec.pdf")
    message.bot = bot
    message.answer = AsyncMock()

    await callback(message)

    outbound_service.deliver.assert_not_called()
    outbound_service.deliver_file.assert_awaited_once_with(
        telegram_user_id=123,
        telegram_topic_id=50,
        file_bytes=b"pdf-bytes",
        filename="spec.pdf",
        caption="Spec file",
    )
