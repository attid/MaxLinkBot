"""Shared per-user MAX client runtime for steady-state messaging."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from src.application.ports.clients import MaxClient


class MaxClientRuntimeRegistry:
    """Caches started MAX clients keyed by binding owner and session data."""

    def __init__(
        self,
        max_client_factory: Callable[[int, str], MaxClient],
        dirty_chat_ttl_seconds: float = 120.0,
    ) -> None:
        self._max_client_factory = max_client_factory
        self._dirty_chat_ttl_seconds = dirty_chat_ttl_seconds
        self._clients: dict[int, tuple[str, MaxClient]] = {}
        self._dirty_chats: dict[int, dict[str, float]] = {}
        self._last_active_chat: dict[int, str] = {}
        self._lock = asyncio.Lock()

    async def get_client(self, session_owner_id: int, session_data: str) -> MaxClient:
        async with self._lock:
            cached = self._clients.get(session_owner_id)
            if cached is not None and cached[0] == session_data:
                return cached[1]

            if cached is not None:
                await cached[1].close()

            client = self._max_client_factory(session_owner_id, session_data)
            await client.start()  # type: ignore[attr-defined]
            self._clients[session_owner_id] = (session_data, client)
            return client

    async def close_user(self, session_owner_id: int) -> None:
        async with self._lock:
            cached = self._clients.pop(session_owner_id, None)
            self._dirty_chats.pop(session_owner_id, None)
            self._last_active_chat.pop(session_owner_id, None)
        if cached is not None:
            await cached[1].close()

    async def close_all(self) -> None:
        async with self._lock:
            cached = list(self._clients.values())
            self._clients.clear()
            self._dirty_chats.clear()
            self._last_active_chat.clear()
        for _, client in cached:
            await client.close()

    async def mark_chat_dirty(self, session_owner_id: int, max_chat_id: str) -> None:
        async with self._lock:
            dirty_for_user = self._dirty_chats.setdefault(session_owner_id, {})
            dirty_for_user[max_chat_id] = time.time() + self._dirty_chat_ttl_seconds
            self._last_active_chat[session_owner_id] = max_chat_id

    async def clear_dirty_chat(self, session_owner_id: int, max_chat_id: str) -> None:
        async with self._lock:
            dirty_for_user = self._dirty_chats.get(session_owner_id)
            if dirty_for_user is None:
                return
            dirty_for_user.pop(max_chat_id, None)
            if not dirty_for_user:
                self._dirty_chats.pop(session_owner_id, None)

    async def get_dirty_chats(self, session_owner_id: int) -> list[str]:
        now = time.time()
        async with self._lock:
            dirty_for_user = self._dirty_chats.get(session_owner_id, {})
            active = {
                max_chat_id: expires_at
                for max_chat_id, expires_at in dirty_for_user.items()
                if expires_at > now
            }
            if active:
                self._dirty_chats[session_owner_id] = active
            else:
                self._dirty_chats.pop(session_owner_id, None)
            return list(active.keys())

    async def get_last_active_chat(self, session_owner_id: int) -> str | None:
        async with self._lock:
            return self._last_active_chat.get(session_owner_id)
