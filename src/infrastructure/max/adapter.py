"""
MAX client adapter wrapping pymax (maxapi-python).

pymax is a WebSocket client — it connects via phone auth and maintains
a persistent session in work_dir. No base_url needed.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

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


@dataclass
class PymaxChat:
    """Chat data extracted from pymax Chat type."""

    id: int
    name: str
    type: str


class PymaxAdapter(MaxClientPort):
    """Adapter wrapping a live pymax MaxClient.

    Receives messages via WebSocket and buffers them for poll-based access.
    """

    def __init__(self, client: MaxClient) -> None:
        self._client = client
        self._buffer: list[PymaxMessage] = []
        self._lock = asyncio.Lock()
        self._started = False
        self._on_start_handlers: list[Callable[[], Any]] = []
        self._registered = False

    # ---- MaxClient port implementation ----

    async def authenticate(self, credentials: dict[str, str]) -> str:
        """Request SMS code. Returns the phone used (session persists in work_dir)."""
        phone = credentials.get("phone")
        if not phone:
            raise ValueError("phone is required for authentication")
        await self._client.request_code(phone)  # type: ignore[reportUnknownMemberType]
        return phone  # pymax persists session to disk; no session_data needed

    async def restore_session(self, session_data: str) -> None:
        """Session is managed by pymax internally in work_dir. No-op."""
        # pymax auto-restores from session.db in work_dir on start()
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
            result.append({
                "message_id": str(m.id),
                "chat_id": max_chat_id,
                "text": getattr(m, "text", None) or "",
                "sender_id": getattr(m, "sender_id", None) or 0,
                "sender": getattr(m, "sender", None) or "",
                "time": getattr(m, "time", None) or 0,
            })
        return result

    async def send_message(self, max_chat_id: str, text: str) -> str:
        msg = await self._client.send_message(text=text, chat_id=int(max_chat_id))
        return str(msg.id) if msg else ""

    async def create_topic(self, title: str) -> str:
        # MAX personal chats are created implicitly; no explicit create needed
        raise NotImplementedError("create_topic not needed for MAX personal chats")

    async def is_session_valid(self) -> bool:
        # pymax manages session internally; assume valid if connected
        return self._started

    async def close(self) -> None:
        if self._started:
            await self._client.close()
            self._started = False

    # ---- Internal helpers ----

    async def start(self) -> None:
        """Connect and register message handlers once."""
        if self._started:
            return
        if not self._registered:
            self._client.add_message_handler(self._on_message)
            self._registered = True
        await self._client.start()
        self._started = True

    def _on_message(self, msg: Any) -> None:
        """Called by pymax WebSocket thread — buffer the message."""
        asyncio.create_task(self._buffer_message(msg))

    async def _buffer_message(self, msg: Any) -> None:
        async with self._lock:
            self._buffer.append(PymaxMessage(
                chat_id=msg.chat_id,
                id=int(str(msg.id)),
                text=msg.text or "",
                sender_id=msg.sender_id or 0,
                sender=msg.sender or "",
                time=msg.time or 0,
            ))


def max_client_factory(phone: str, work_dir: str) -> Callable[[], MaxClientPort]:
    """Create a PymaxAdapter backed by a pymax MaxClient.

    The client is created once and reused.
    """

    def create() -> MaxClientPort:
        headers = UserAgentPayload(device_type="WEB", app_version="25.12.13")
        client = MaxClient(
            phone=phone,
            work_dir=work_dir,
            headers=headers,
        )
        return PymaxAdapter(client)

    return create
