"""
MAX client adapter wrapping `maxapi-python`.

The underlying client is WebSocket-based and connects via phone auth or QR code
and maintains a persistent session per-user in work_dir.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import time
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
    type: str
    description: str


class PymaxAdapter(MaxClientPort):
    """Adapter wrapping a live MAX WebSocket client."""

    USER_CACHE_TTL_SECONDS = 60 * 60 * 24

    def __init__(self, client: MaxClient) -> None:
        self._client = client
        self._buffer: list[PymaxMessage] = []
        self._lock = asyncio.Lock()
        self._started = False
        self._registered = False
        self._qr_bytes: bytes | None = None
        self._client_task: asyncio.Task[None] | None = None
        self._ready_event = asyncio.Event()
        self._user_cache: dict[int, tuple[float, str]] = {}
        self._reconnect_detected = False

    async def authenticate(self, credentials: dict[str, str]) -> str:
        """No-op: QR auth is handled via start()."""
        return credentials.get("phone", "")

    async def restore_session(self, session_data: str) -> None:
        pass

    async def list_personal_chats(self) -> list[dict[str, Any]]:
        raw = await self._client.fetch_chats()  # type: ignore[reportUnknownMemberType]
        chats = []
        for chat in raw:
            title = await self._resolve_chat_title(chat)
            logger.info(
                "max resolved chat title chat_id=%s chat_type=%r raw_title=%r owner=%r participants=%r resolved_title=%r",
                getattr(chat, "id", None),
                getattr(chat, "type", None),
                getattr(chat, "title", None),
                getattr(chat, "owner", None),
                list((getattr(chat, "participants", {}) or {}).keys()),
                title,
            )
            chats.append({"max_chat_id": str(chat.id), "title": title})
        logger.info(
            "max list_personal_chats fetched count=%s ids=%s",
            len(chats),
            [chat["max_chat_id"] for chat in chats],
        )
        return chats

    async def get_messages(
        self, max_chat_id: str, since_message_id: str | None, limit: int
    ) -> list[dict[str, Any]]:
        chat_id = int(max_chat_id)
        since = int(since_message_id) if since_message_id else None
        raw = await self._client.fetch_history(chat_id, backward=limit)  # type: ignore[reportUnknownMemberType]
        if raw is None:
            logger.info(
                "max get_messages no history max_chat_id=%s since_message_id=%s limit=%s",
                max_chat_id,
                since_message_id,
                limit,
            )
            return []
        result: list[dict[str, Any]] = []
        raw_ids: list[str] = []
        for m in raw:
            mid = int(str(m.id))
            raw_ids.append(str(m.id))
            if since is not None and mid <= since:
                continue
            result.append(
                {
                    "max_message_id": str(m.id),
                    "chat_id": max_chat_id,
                    "text": getattr(m, "text", None) or "",
                    "sender_id": getattr(m, "sender_id", None) or 0,
                    "sender_name": await self._resolve_sender_name(m),
                    "time": getattr(m, "time", None) or 0,
                }
            )
        logger.info(
            "max get_messages fetched max_chat_id=%s since_message_id=%s limit=%s raw_ids=%s filtered_ids=%s count=%s",
            max_chat_id,
            since_message_id,
            limit,
            raw_ids,
            [message["max_message_id"] for message in result],
            len(result),
        )
        return result

    async def _resolve_chat_title(self, chat: Any) -> str:
        title = self._normalize_text_field(getattr(chat, "title", None))
        if title:
            return title

        title = self._normalize_text_field(getattr(chat, "name", None))
        if title:
            return title

        if not self._is_dialog_chat(chat):
            return ""

        owner = getattr(chat, "owner", None)
        participants = getattr(chat, "participants", {}) or {}
        participant_ids = [int(uid) for uid in participants.keys()]
        other_participant_id = next((uid for uid in participant_ids if uid != owner), None)
        if other_participant_id is None:
            logger.info(
                "max resolve chat title no other participant chat_id=%s owner=%r participants=%r",
                getattr(chat, "id", None),
                owner,
                participant_ids,
            )
            return ""

        display_name = await self._resolve_user_display_name(other_participant_id)
        logger.info(
            "max resolve chat title dialog chat_id=%s other_participant_id=%s display_name=%r",
            getattr(chat, "id", None),
            other_participant_id,
            display_name,
        )
        return display_name or ""

    async def _resolve_sender_name(self, message: Any) -> str:
        sender = getattr(message, "sender", None)
        if isinstance(sender, str):
            return sender

        sender_id = sender
        if sender_id is None:
            sender_id = getattr(message, "sender_id", None)
        if sender_id is None:
            return ""

        display_name = await self._resolve_user_display_name(int(sender_id))
        if display_name:
            return display_name

        return str(sender_id)

    async def _resolve_user_display_name(self, user_id: int) -> str | None:
        cached = self._user_cache.get(user_id)
        now = time.time()
        if cached is not None and cached[0] > now:
            return cached[1]

        user = None
        with suppress(Exception):
            user = self._client.get_cached_user(user_id)  # type: ignore[reportUnknownMemberType]

        if user is None:
            with suppress(Exception):
                users = await self._client.fetch_users([user_id])  # type: ignore[reportUnknownMemberType]
                user = users[0] if users else None

        display_name = self._extract_user_display_name(user)
        if display_name:
            self._user_cache[user_id] = (now + self.USER_CACHE_TTL_SECONDS, display_name)
            logger.info("max user display name resolved user_id=%s display_name=%r", user_id, display_name)
        else:
            logger.info("max user display name missing user_id=%s", user_id)
        return display_name

    def _extract_user_display_name(self, user: Any) -> str | None:
        if user is None:
            return None

        for name in getattr(user, "names", []) or []:
            display_name = self._normalize_text_field(getattr(name, "name", None))
            if display_name:
                return display_name

            first_name = getattr(name, "first_name", None) or ""
            last_name = getattr(name, "last_name", None) or ""
            combined = f"{first_name} {last_name}".strip()
            if combined:
                return combined

        return None

    def _normalize_text_field(self, value: Any) -> str:
        if not isinstance(value, str):
            return ""
        return value.strip()

    def _is_dialog_chat(self, chat: Any) -> bool:
        chat_type = getattr(chat, "type", None)
        if isinstance(chat_type, str):
            return chat_type.upper() == "DIALOG"
        name = getattr(chat_type, "name", None)
        if isinstance(name, str):
            return name.upper() == "DIALOG"
        value = getattr(chat_type, "value", None)
        if isinstance(value, str):
            return value.upper() == "DIALOG"
        return str(chat_type).upper().endswith("DIALOG")

    async def send_message(self, max_chat_id: str, text: str) -> str:
        msg = await self._client.send_message(text=text, chat_id=int(max_chat_id))
        return str(msg.id) if msg else ""

    async def drain_buffered_messages(self) -> list[dict[str, Any]]:
        async with self._lock:
            buffered = list(self._buffer)
            self._buffer.clear()

        result: list[dict[str, Any]] = []
        for message in buffered:
            sender_name = message.sender
            if not sender_name and message.sender_id:
                sender_name = (await self._resolve_user_display_name(message.sender_id)) or str(
                    message.sender_id
                )
            result.append(
                {
                    "max_message_id": str(message.id),
                    "chat_id": str(message.chat_id),
                    "text": message.text,
                    "sender_id": message.sender_id,
                    "sender_name": sender_name,
                    "time": message.time,
                    "type": message.type or "text",
                    "description": message.description,
                }
            )

        if result:
            logger.info(
                "max drain_buffered_messages count=%s ids=%s",
                len(result),
                [message["max_message_id"] for message in result],
            )
        return result

    async def consume_reconnect_event(self) -> bool:
        reconnect_detected = self._reconnect_detected
        self._reconnect_detected = False
        return reconnect_detected

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
        self._ready_event = asyncio.Event()

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
        """Start the client in background and wait until pymax signals readiness."""
        if self._started:
            return
        if not self._registered:
            self._client.add_message_handler(self._on_message)
            self._registered = True

        async def mark_ready() -> None:
            logger.info("max start on_start fired")
            if self._started:
                self._reconnect_detected = True
                logger.info("max reconnect detected")
            self._ready_event.set()

        self._client.add_on_start_handler(mark_ready)

        if self._client_task is None or self._client_task.done():
            logger.info("max start launching background client task")
            self._client_task = asyncio.create_task(self._client.start())

        logger.info("max start waiting for on_start readiness")
        await self._ready_event.wait()
        logger.info("max start ready")
        self._started = True

    def _on_message(self, msg: Any) -> None:
        asyncio.create_task(self._buffer_message(msg))

    async def _buffer_message(self, msg: Any) -> None:
        raw_type = getattr(msg, "type", None)
        normalized_type = self._normalize_live_message_type(raw_type, getattr(msg, "text", None))
        async with self._lock:
            self._buffer.append(
                PymaxMessage(
                    chat_id=msg.chat_id,
                    id=int(str(msg.id)),
                    text=getattr(msg, "text", None) or "",
                    sender_id=getattr(msg, "sender_id", None) or 0,
                    sender=getattr(msg, "sender", None) or "",
                    time=getattr(msg, "time", None) or 0,
                    type=normalized_type,
                    description=str(getattr(msg, "description", None) or ""),
                )
            )
        logger.info(
            "max buffered live message chat_id=%s message_id=%s raw_type=%r normalized_type=%s has_text=%s",
            getattr(msg, "chat_id", None),
            getattr(msg, "id", None),
            raw_type,
            normalized_type,
            bool(getattr(msg, "text", None)),
        )

    def _normalize_live_message_type(self, raw_type: Any, text: Any) -> str:
        if isinstance(raw_type, str):
            normalized = raw_type.strip().lower()
        else:
            name = getattr(raw_type, "name", None)
            value = getattr(raw_type, "value", None)
            normalized = ""
            if isinstance(name, str):
                normalized = name.strip().lower()
            elif isinstance(value, str):
                normalized = value.strip().lower()
            elif raw_type is not None:
                normalized = str(raw_type).strip().lower()

        if normalized.endswith(".text") or normalized == "text":
            return "text"
        if text:
            return "text"
        return normalized or "unknown"


def max_client_factory(
    work_dir: str,
    reconnect: bool = True,
) -> Callable[[int, str | None], MaxClientPort]:
    """Factory: given work_dir, returns a callable(telegram_user_id, phone?) -> MaxClientPort.

    Each user's session lives in work_dir/{telegram_user_id}/.
    For QR auth, phone can be None (placeholder is used internally).
    """

    def create(telegram_user_id: int, phone: str | None = None) -> MaxClientPort:
        user_dir = os.path.join(work_dir, str(telegram_user_id))
        headers = UserAgentPayload(device_type="WEB", app_version="25.12.13")
        # For QR auth, the client requires a valid-format phone (regex: ^\+?\d{10,15}$).
        # Use a placeholder — the phone is not used during QR login.
        client_phone = phone if phone and phone != "qr_auth" else "+000000000000"
        client = MaxClient(
            phone=client_phone,
            work_dir=user_dir,
            headers=headers,
            reconnect=reconnect,
        )
        return PymaxAdapter(client)

    return create
