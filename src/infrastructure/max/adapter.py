"""
MAX client adapter wrapping pymax (maxapi-python).

pymax is a WebSocket client — it connects via phone auth or QR code
and maintains a persistent session per-user in work_dir.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

import qrcode
from pymax import MaxClient
from pymax.payloads import UserAgentPayload

from src.application.ports.clients import MaxClient as MaxClientPort

logger = logging.getLogger(__name__)


@dataclass
class PymaxMessage:
    """Message stored by the in-process buffer."""

    chat_id: int
    id: int
    text: str
    sender_id: int
    sender: str
    time: int


class PymaxAdapter(MaxClientPort):
    """Adapter wrapping a live pymax MaxClient."""

    def __init__(self, client: MaxClient) -> None:
        self._client = client
        self._buffer: list[PymaxMessage] = []
        self._lock = asyncio.Lock()
        self._started = False
        self._registered = False
        self._qr_bytes: bytes | None = None
        self._client_task: asyncio.Task[None] | None = None

    async def authenticate(self, credentials: dict[str, str]) -> str:
        """No-op: QR auth is handled via start()."""
        return credentials.get("phone", "")

    async def restore_session(self, session_data: str) -> None:
        pass

    async def list_personal_chats(self) -> list[dict[str, Any]]:
        raw = await self._client.fetch_chats()  # type: ignore[reportUnknownMemberType]
        return [{"max_chat_id": str(c.id), "title": getattr(c, "name", None) or ""} for c in raw]

    async def get_messages(
        self, max_chat_id: str, since_message_id: str | None, limit: int
    ) -> list[dict[str, Any]]:
        chat_id = int(max_chat_id)
        since = int(since_message_id) if since_message_id else None
        raw = await self._client.fetch_history(chat_id, backward=limit)  # type: ignore[reportUnknownMemberType]
        if raw is None:
            return []
        result: list[dict[str, Any]] = []
        for m in raw:
            mid = int(str(m.id))
            if since is not None and mid <= since:
                break
            result.append(
                {
                    "message_id": str(m.id),
                    "chat_id": max_chat_id,
                    "text": getattr(m, "text", None) or "",
                    "sender_id": getattr(m, "sender_id", None) or 0,
                    "sender": getattr(m, "sender", None) or "",
                    "time": getattr(m, "time", None) or 0,
                }
            )
        return result

    async def send_message(self, max_chat_id: str, text: str) -> str:
        msg = await self._client.send_message(text=text, chat_id=int(max_chat_id))
        return str(msg.id) if msg else ""

    async def create_topic(self, title: str) -> str:
        raise NotImplementedError("create_topic not needed for MAX personal chats")

    async def is_session_valid(self) -> bool:
        return self._started

    async def close(self) -> None:
        if self._client_task is not None and not self._client_task.done():
            self._client._stop_event.set()  # type: ignore[reportPrivateUsage]  # sync: signals start() to exit
            try:
                await asyncio.wait_for(self._client_task, timeout=5.0)
            except TimeoutError:
                self._client_task.cancel()
            except asyncio.CancelledError:
                pass
            self._client_task = None
        if self._started:
            with suppress(Exception):
                await self._client.close()
            self._started = False

    async def start_for_qr(self) -> bytes:
        """Start the client in a background task and return QR bytes immediately.

        The client runs in the background, polling for QR scan confirmation.
        Caller sends the QR photo to Telegram and then calls close().
        """
        if self._started:
            return self._qr_bytes or b""

        qr_event = asyncio.Event()

        def capture_qr(qr_link: str) -> None:
            """Generate QR image from link and signal readiness."""
            img = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,  # type: ignore[attr-defined]
                box_size=10,
                border=4,
            )
            img.add_data(qr_link)
            img.make(fit=True)
            buf = io.BytesIO()
            img.make_image(fill_color="black", back_color="white").save(buf)  # type: ignore[call-arg]
            self._qr_bytes = buf.getvalue()
            qr_event.set()

        # Patch _print_qr to capture QR image
        original_print_qr = self._client._print_qr  # type: ignore[reportPrivateUsage]
        self._client._print_qr = capture_qr  # type: ignore[method-assign]

        # Run client in a background task so we can return QR bytes immediately
        async def run_client() -> None:
            await self._client.start()

        self._client_task = asyncio.create_task(run_client())

        # Wait up to 5s for QR bytes to be generated
        try:
            await asyncio.wait_for(qr_event.wait(), timeout=5.0)
        except TimeoutError:
            pass
        finally:
            # Restore original _print_qr — client is running in background now
            self._client._print_qr = original_print_qr  # type: ignore[method-assign,assignment]

        self._started = True
        return self._qr_bytes or b""

    async def start(self) -> None:
        """Start the client: connect, authenticate, and keep the WebSocket alive."""
        if self._started:
            return
        if not self._registered:
            self._client.add_message_handler(self._on_message)
            self._registered = True
        await self._client.start()
        self._started = True

    def _on_message(self, msg: Any) -> None:
        asyncio.create_task(self._buffer_message(msg))

    async def _buffer_message(self, msg: Any) -> None:
        async with self._lock:
            self._buffer.append(
                PymaxMessage(
                    chat_id=msg.chat_id,
                    id=int(str(msg.id)),
                    text=getattr(msg, "text", None) or "",
                    sender_id=getattr(msg, "sender_id", None) or 0,
                    sender=getattr(msg, "sender", None) or "",
                    time=getattr(msg, "time", None) or 0,
                )
            )


def max_client_factory(work_dir: str) -> Callable[[int, str | None], MaxClientPort]:
    """Factory: given work_dir, returns a callable(telegram_user_id, phone?) -> MaxClientPort.

    Each user's session lives in work_dir/{telegram_user_id}/.
    For QR auth, phone can be None (placeholder is used internally).
    """

    def create(telegram_user_id: int, phone: str | None = None) -> MaxClientPort:
        user_dir = os.path.join(work_dir, str(telegram_user_id))
        headers = UserAgentPayload(device_type="WEB", app_version="25.12.13")
        # For QR auth, pymax requires a valid-format phone (regex: ^\+?\d{10,15}$).
        # Use a placeholder — the phone is not used during QR login.
        client_phone = phone if phone and phone != "qr_auth" else "+000000000000"
        client = MaxClient(
            phone=client_phone,
            work_dir=user_dir,
            headers=headers,
            reconnect=True,  # stay connected for inbound polling
        )
        return PymaxAdapter(client)

    return create
