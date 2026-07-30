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
import sqlite3
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import qrcode
from pymax import ExtraConfig, File, Photo, WebClient
from pymax.exceptions import ApiError
from pymax.protocol.enums import Opcode

from src.application.auth.exceptions import AuthError
from src.application.ports.clients import MaxClient as MaxClientPort

logger = logging.getLogger(__name__)


class TelegramQrProvider:
    """Captures a PyMax QR URL as PNG bytes for delivery through Telegram."""

    def __init__(self) -> None:
        self._qr_bytes: bytes | None = None
        self._ready = asyncio.Event()

    async def show_qr(self, qr_url: str) -> None:
        image = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,  # type: ignore[attr-defined]
            box_size=10,
            border=4,
        )
        image.add_data(qr_url)
        image.make(fit=True)
        buffer = io.BytesIO()
        image.make_image(fill_color="black", back_color="white").save(buffer)  # type: ignore[call-arg]
        self._qr_bytes = buffer.getvalue()
        self._ready.set()

    async def wait_for_qr(self, timeout: float = 5.0) -> bytes:
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=timeout)
        except TimeoutError:
            return b""
        return self._qr_bytes or b""


def migrate_legacy_session_db(session_db_path: Path) -> None:
    """Copy a PyMax 1.2.5 auth row into the 2.3 session table.

    The legacy table is intentionally preserved so a rollback can still use it.
    Existing 2.3 sessions always win and are never overwritten.
    """
    with sqlite3.connect(session_db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
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
        session_exists = conn.execute("SELECT 1 FROM sessions LIMIT 1").fetchone()
        legacy_table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'auth'"
        ).fetchone()
        if session_exists is None and legacy_table_exists is not None:
            legacy_row = conn.execute(
                "SELECT token, device_id FROM auth WHERE COALESCE(token, '') != '' LIMIT 1"
            ).fetchone()
            if legacy_row is not None:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO sessions(token, device_id, phone)
                    VALUES (?, ?, '')
                    """,
                    legacy_row,
                )
        conn.commit()


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
    media_url: str | None = None
    file_name: str | None = None


class PymaxAdapter(MaxClientPort):
    """Adapter wrapping a live MAX WebSocket client."""

    USER_CACHE_TTL_SECONDS = 60 * 60 * 24

    def __init__(
        self,
        client: WebClient,
        session_db_path: Path | None = None,
        qr_provider: TelegramQrProvider | None = None,
    ) -> None:
        self._client = client
        self._session_db_path = session_db_path
        self._qr_provider = qr_provider or TelegramQrProvider()
        self._buffer: list[PymaxMessage] = []
        self._lock = asyncio.Lock()
        self._started = False
        self._registered = False
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
        chats: list[dict[str, Any]] = []
        for chat in raw:
            title = await self._resolve_chat_title(chat)
            participants = getattr(chat, "participants", {}) or {}
            participant_ids = [str(uid) for uid in participants]
            logger.info(
                "max resolved chat title chat_id=%s chat_type=%r raw_title=%r owner=%r participants=%r resolved_title=%r",
                getattr(chat, "id", None),
                getattr(chat, "type", None),
                getattr(chat, "title", None),
                getattr(chat, "owner", None),
                list((getattr(chat, "participants", {}) or {}).keys()),
                title,
            )
            chats.append(
                {
                    "max_chat_id": str(chat.id),
                    "title": title,
                    "participant_ids": participant_ids,
                }
            )
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
            content = self._select_content_source_message(m)
            sender_id = self._extract_sender_id(m)
            media_type, media_url, file_name = self._extract_media_metadata(content)
            if media_type == "document" and media_url is None:
                media_url = await self._resolve_document_url(
                    content,
                    chat_id=chat_id,
                    message_id=m.id,
                )
            if media_type == "video" and media_url is None:
                media_url = await self._resolve_video_url(
                    content,
                    chat_id=chat_id,
                    message_id=m.id,
                )
            raw_description = self._field(content, "description")
            description = raw_description.strip() if isinstance(raw_description, str) else ""
            text = self._field(content, "text") or ""
            result.append(
                {
                    "max_message_id": str(m.id),
                    "chat_id": max_chat_id,
                    "text": text,
                    "sender_id": sender_id,
                    "sender_name": await self._resolve_sender_name(m),
                    "time": getattr(m, "time", None) or 0,
                    "type": media_type
                    or self._normalize_live_message_type(
                        self._field(content, "type"),
                        text,
                    ),
                    "description": description,
                    "media_url": media_url,
                    "file_name": file_name,
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
        participant_ids = [int(uid) for uid in participants]
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

        sender_id = self._extract_sender_id(message)
        display_name = await self._resolve_user_display_name(int(sender_id))
        if display_name:
            return display_name

        return str(sender_id)

    def _extract_sender_id(self, message: Any) -> int:
        sender_id = getattr(message, "sender_id", None)
        if not isinstance(sender_id, (int, str)):
            sender_id = getattr(message, "sender", None)
        if sender_id is None:
            return 0
        if isinstance(sender_id, str) and not sender_id.strip().lstrip("-").isdigit():
            return 0
        try:
            return int(sender_id)
        except (TypeError, ValueError):
            return 0

    def _select_content_source_message(self, message: Any) -> Any:
        if self._message_has_renderable_content(message):
            return message

        link = self._field(message, "link")
        linked_message = self._field(link, "message")
        if linked_message is not None and self._message_has_renderable_content(linked_message):
            return linked_message
        return message

    def _message_has_renderable_content(self, message: Any) -> bool:
        text = self._field(message, "text")
        if isinstance(text, str) and text.strip():
            return True

        description = self._field(message, "description")
        if isinstance(description, str) and description.strip():
            return True

        raw_attaches = self._field(message, "attaches")
        if not isinstance(raw_attaches, (list, tuple)):
            return False
        attaches = cast(list[Any] | tuple[Any, ...], raw_attaches)
        return bool(attaches)

    def _extract_media_metadata(self, message: Any) -> tuple[str | None, str | None, str | None]:
        raw_attaches = self._field(message, "attaches")
        if isinstance(raw_attaches, (list, tuple)):
            attaches = list(cast(list[Any] | tuple[Any, ...], raw_attaches))
        else:
            attaches = []
        for attach in attaches:
            attach_type = self._field(attach, "type", "_type")
            type_name = ""
            if isinstance(attach_type, str):
                type_name = attach_type.strip().lower()
            else:
                name = getattr(attach_type, "name", None)
                value = getattr(attach_type, "value", None)
                if isinstance(name, str):
                    type_name = name.strip().lower()
                elif isinstance(value, str):
                    type_name = value.strip().lower()

            if type_name == "photo":
                base_url = self._field(attach, "base_url", "baseUrl")
                if isinstance(base_url, str) and base_url.strip():
                    return "photo", base_url.strip(), None
            if type_name in {"audio", "voice"}:
                url = self._field(attach, "url")
                if isinstance(url, str) and url.strip():
                    return "audio", url.strip(), self._extract_attach_filename(attach)
            if type_name == "video":
                url = self._field(attach, "url")
                if isinstance(url, str) and url.strip():
                    return "video", url.strip(), self._extract_attach_filename(attach)
                return "video", None, "video.mp4"
            if type_name in {"file", "document"}:
                url = self._field(attach, "url")
                file_name = self._extract_attach_filename(attach)
                if isinstance(url, str) and url.strip():
                    return "document", url.strip(), file_name
                if file_name:
                    return "document", None, file_name
        return None, None, None

    def _extract_attach_filename(self, attach: Any) -> str | None:
        for attr_name in ("file_name", "fileName", "filename", "name", "title"):
            value = self._field(attach, attr_name)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    async def _resolve_document_url(
        self,
        message: Any,
        chat_id: int,
        message_id: int | str,
    ) -> str | None:
        raw_attaches = self._field(message, "attaches")
        if not isinstance(raw_attaches, (list, tuple)):
            return None

        for attach in cast(list[Any] | tuple[Any, ...], raw_attaches):
            attach_type = self._field(attach, "type", "_type")
            type_name = getattr(attach_type, "value", attach_type)
            if not isinstance(type_name, str) or type_name.strip().lower() not in {
                "file",
                "document",
            }:
                continue
            file_id = self._field(attach, "file_id", "fileId")
            if not isinstance(file_id, int):
                return None
            with suppress(Exception):
                file_request = await self._client.get_file_by_id(
                    chat_id,
                    message_id,
                    file_id,
                )
                url = getattr(file_request, "url", None)
                if isinstance(url, str) and url.strip():
                    return url.strip()
            return None
        return None

    async def _resolve_video_url(
        self,
        message: Any,
        chat_id: int,
        message_id: int | str,
    ) -> str | None:
        raw_attaches = self._field(message, "attaches")
        if not isinstance(raw_attaches, (list, tuple)):
            return None

        for attach in cast(list[Any] | tuple[Any, ...], raw_attaches):
            attach_type = self._field(attach, "type", "_type")
            type_name = getattr(attach_type, "value", attach_type)
            if not isinstance(type_name, str) or type_name.strip().lower() != "video":
                continue
            video_id = self._field(attach, "video_id", "videoId")
            if not isinstance(video_id, int):
                return None
            with suppress(Exception):
                video_request = await self._client.get_video_by_id(
                    chat_id,
                    message_id,
                    video_id,
                )
                url = getattr(video_request, "url", None)
                if isinstance(url, str) and url.strip():
                    return url.strip()
            return None
        return None

    def _field(self, value: Any, name: str, *aliases: str) -> Any:
        if isinstance(value, dict):
            mapping = cast(dict[str, Any], value)
            for key in (name, *aliases):
                if key in mapping:
                    return mapping[key]
            return None
        return getattr(value, name, None)

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
            logger.info(
                "max user display name resolved user_id=%s display_name=%r", user_id, display_name
            )
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

    async def send_photo(
        self,
        max_chat_id: str,
        image_bytes: bytes,
        filename: str,
        caption: str,
    ) -> str:
        normalized_name = f"{Path(filename).stem}{self._normalize_photo_suffix(filename)}"
        msg = await self._client.send_message(
            text=caption,
            chat_id=int(max_chat_id),
            attachments=[Photo(raw=image_bytes, name=normalized_name)],
        )
        return str(msg.id) if msg else ""

    async def send_file(
        self,
        max_chat_id: str,
        file_bytes: bytes,
        filename: str,
        caption: str,
    ) -> str:
        msg = await self._client.send_message(
            text=caption,
            chat_id=int(max_chat_id),
            attachments=[File(raw=file_bytes, name=filename)],
        )
        return str(msg.id) if msg else ""

    def _normalize_photo_suffix(self, filename: str) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
            return suffix
        return ".jpg"

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
                    "media_url": message.media_url,
                    "file_name": message.file_name,
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
        if self._client_task is None:
            with suppress(Exception):
                await self._client.close()
        else:
            if not self._client_task.done():
                self._client_task.cancel()
            try:
                await asyncio.wait_for(self._client_task, timeout=5.0)
            except TimeoutError:
                logger.warning("max client task did not stop within timeout")
            except asyncio.CancelledError:
                pass
            self._client_task = None
        self._started = False
        self._ready_event = asyncio.Event()

    async def start_for_qr(self) -> bytes:
        """Start the client in a background task and return QR bytes immediately.

        The client runs in the background, polling for QR scan confirmation.
        Caller sends the QR photo to Telegram and then calls close().
        """
        if self._started:
            return b""
        self._register_handlers()
        self._launch_client()
        try:
            return await self._wait_for_qr_or_failure()
        except AuthError:
            raise
        except Exception as exc:
            raise AuthError(f"MAX QR startup failed: {exc}") from exc

    async def wait_until_authorized(self) -> None:
        """Wait for QR confirmation or restored-session readiness."""
        try:
            await self._wait_until_ready()
        except AuthError:
            raise
        except Exception as exc:
            raise AuthError(f"MAX QR authorization failed: {exc}") from exc
        self._started = True

    async def start(self) -> None:
        """Start the client in background and wait until pymax signals readiness."""
        if self._started:
            return
        self._assert_persisted_session_ready()
        self._register_handlers()
        self._launch_client()

        logger.info("max start waiting for on_start readiness")
        await self._wait_until_ready()
        logger.info("max start ready")
        self._started = True

    def _register_handlers(self) -> None:
        if self._registered:
            return

        @self._client.on_message()
        async def on_message(  # type: ignore[reportUnusedFunction]
            msg: Any, _client: WebClient
        ) -> None:
            await self._buffer_message(msg)

        @self._client.on_start()
        async def on_start(  # type: ignore[reportUnusedFunction]
            _client: WebClient,
        ) -> None:
            logger.info("max start on_start fired")
            if self._started:
                self._reconnect_detected = True
                logger.info("max reconnect detected")
            self._started = True
            self._ready_event.set()

        self._registered = True

    def _launch_client(self) -> None:
        if self._client_task is None or self._client_task.done():
            logger.info("max start launching background client task")
            self._client_task = asyncio.create_task(self._client.start())

    async def _wait_until_ready(self) -> None:
        if self._client_task is None:
            raise RuntimeError("MAX client task was not started")

        ready_task = asyncio.create_task(self._ready_event.wait())
        try:
            await asyncio.wait(
                {ready_task, self._client_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if self._ready_event.is_set():
                return
            try:
                await self._client_task
            except ApiError as exc:
                if exc.opcode == Opcode.LOGIN:
                    raise AuthError(f"MAX session login failed: {exc}") from exc
                raise
            raise RuntimeError("MAX client stopped before startup completed")
        finally:
            if not ready_task.done():
                ready_task.cancel()
                with suppress(asyncio.CancelledError):
                    await ready_task

    async def _wait_for_qr_or_failure(self) -> bytes:
        if self._client_task is None:
            raise RuntimeError("MAX client task was not started")

        qr_task = asyncio.create_task(self._qr_provider.wait_for_qr(timeout=5.0))
        try:
            done, _ = await asyncio.wait(
                {qr_task, self._client_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if qr_task in done:
                return await qr_task
            await self._client_task
            return b""
        finally:
            if not qr_task.done():
                qr_task.cancel()
                with suppress(asyncio.CancelledError):
                    await qr_task

    async def _buffer_message(self, msg: Any) -> None:
        content = self._select_content_source_message(msg)
        raw_type = self._field(content, "type")
        text = self._field(content, "text") or ""
        normalized_type = self._normalize_live_message_type(raw_type, text)
        media_type, media_url, file_name = self._extract_media_metadata(content)
        if media_type == "document" and media_url is None:
            media_url = await self._resolve_document_url(
                content,
                chat_id=int(msg.chat_id),
                message_id=msg.id,
            )
        if media_type == "video" and media_url is None:
            media_url = await self._resolve_video_url(
                content,
                chat_id=int(msg.chat_id),
                message_id=msg.id,
            )
        async with self._lock:
            self._buffer.append(
                PymaxMessage(
                    chat_id=msg.chat_id,
                    id=int(str(msg.id)),
                    text=text,
                    sender_id=getattr(msg, "sender_id", None) or 0,
                    sender=getattr(msg, "sender", None) or "",
                    time=getattr(msg, "time", None) or 0,
                    type=media_type or normalized_type,
                    description=str(self._field(content, "description") or ""),
                    media_url=media_url,
                    file_name=file_name,
                )
            )
        logger.info(
            "max buffered live message chat_id=%s message_id=%s raw_type=%r normalized_type=%s has_text=%s",
            getattr(msg, "chat_id", None),
            getattr(msg, "id", None),
            raw_type,
            normalized_type,
            bool(text),
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

    def _assert_persisted_session_ready(self) -> None:
        if self._session_db_path is None:
            return
        if not self._session_db_path.exists():
            raise AuthError(f"Persisted MAX session not found at {self._session_db_path}")

        try:
            migrate_legacy_session_db(self._session_db_path)
            with sqlite3.connect(self._session_db_path) as conn:
                row = conn.execute(
                    "SELECT token FROM sessions WHERE COALESCE(token, '') != '' LIMIT 1"
                ).fetchone()
        except sqlite3.Error as exc:
            raise AuthError(
                f"Persisted MAX session is unreadable at {self._session_db_path}: {exc}"
            ) from exc

        if row is None:
            raise AuthError(f"Persisted MAX session is not authorized at {self._session_db_path}")


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
        session_db_path = Path(user_dir) / "session.db"
        qr_provider = TelegramQrProvider()
        client = WebClient(
            session_name="session.db",
            work_dir=user_dir,
            extra_config=ExtraConfig(reconnect=reconnect),
            qr_provider=qr_provider,
        )
        return PymaxAdapter(
            client,
            session_db_path=session_db_path,
            qr_provider=qr_provider,
        )

    return create
