"""
MAX client adapter wrapping pymax (maxapi-python).

pymax is a WebSocket client — it connects via phone auth and maintains
a persistent session per-user in work_dir.
"""

from __future__ import annotations

import asyncio
import logging
import os
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


class PymaxAdapter(MaxClientPort):
    """Adapter wrapping a live pymax MaxClient."""

    def __init__(self, client: MaxClient) -> None:
        self._client = client
        self._buffer: list[PymaxMessage] = []
        self._lock = asyncio.Lock()
        self._started = False
        self._registered = False

    async def authenticate(self, credentials: dict[str, str]) -> str:
        """Request SMS code. Returns the phone used."""
        phone = credentials.get("phone")
        if not phone:
            raise ValueError("phone is required for authentication")
        await self._client.request_code(phone)  # type: ignore[reportUnknownMemberType]
        return phone

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
        raise NotImplementedError("create_topic not needed for MAX personal chats")

    async def is_session_valid(self) -> bool:
        return self._started

    async def close(self) -> None:
        if self._started:
            await self._client.close()
            self._started = False

    async def start(self) -> None:
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
            self._buffer.append(PymaxMessage(
                chat_id=msg.chat_id,
                id=int(str(msg.id)),
                text=getattr(msg, "text", None) or "",
                sender_id=getattr(msg, "sender_id", None) or 0,
                sender=getattr(msg, "sender", None) or "",
                time=getattr(msg, "time", None) or 0,
            ))


def max_client_factory(work_dir: str) -> Callable[[int, str], MaxClientPort]:
    """Factory: given work_dir, returns a callable(phone, user_dir_name) -> MaxClientPort.

    Each user's session lives in work_dir/{telegram_user_id}/.
    Phone is read from Binding.max_session_data at call time.
    """

    def create(telegram_user_id: int, phone: str) -> MaxClientPort:
        user_dir = os.path.join(work_dir, str(telegram_user_id))
        headers = UserAgentPayload(device_type="WEB", app_version="25.12.13")
        client = MaxClient(
            phone=phone,
            work_dir=user_dir,
            headers=headers,
        )
        return PymaxAdapter(client)

    return create
