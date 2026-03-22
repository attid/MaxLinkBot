"""Async SQLite connection manager using aiosqlite 0.22."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite
from pydantic_settings import BaseSettings


class DatabaseSettings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///data/maxlinkbot.db"


class Database:
    _conn: aiosqlite.Connection | None = None
    _settings: DatabaseSettings

    def __init__(self, settings: DatabaseSettings) -> None:
        self._settings = settings

    @property
    def _db_path(self) -> Path:
        url = self._settings.database_url
        # sqlite+aiosqlite:///file.db   → file.db   (3 slashes = relative)
        # sqlite+aiosqlite:///:memory:  → :memory:   (3 slashes = memory)
        # sqlite+aiosqlite:////file.db  → /file.db   (4 slashes = absolute)
        if "+aiosqlite://" in url:
            raw = url.split("+aiosqlite://", 1)[1]
        else:
            raw = url.split("://", 1)[1]
        # Count leading slashes: /// = 2, //// = 3
        leading_slashes = len(raw) - len(raw.lstrip("/"))
        stripped = raw.lstrip("/")
        if leading_slashes >= 2:
            # 4 slashes in URL → 3 after split → 2 leading → absolute path
            return Path("/" + stripped)
        return Path(stripped)

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(str(self._db_path))
        self._conn.row_factory = aiosqlite.Row

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def execute(self, sql: str, *args: Any) -> aiosqlite.Cursor:
        """Execute SQL, return cursor. Use for INSERT/UPDATE. Caller must close cursor."""
        if self._conn is None:
            raise RuntimeError("Database not connected")
        result = self._conn.execute(sql, args)
        return await result.__aenter__()

    async def script_cursor(self) -> aiosqlite.Cursor:
        """Return a cursor for executing scripts (internal use)."""
        if self._conn is None:
            raise RuntimeError("Database not connected")
        return self._conn.cursor()  # type: ignore[return-value]

    async def commit(self) -> None:
        if self._conn is None:
            raise RuntimeError("Database not connected")
        await self._conn.commit()

    async def fetchone(self, sql: str, *args: Any) -> aiosqlite.Row | None:
        """Execute SQL and fetch one row."""
        if self._conn is None:
            raise RuntimeError("Database not connected")
        async with self._conn.execute(sql, args) as cursor:
            return await cursor.fetchone()  # type: ignore[return-value]

    async def fetchall(self, sql: str, *args: Any) -> list[aiosqlite.Row]:
        """Execute SQL and fetch all rows."""
        if self._conn is None:
            raise RuntimeError("Database not connected")
        async with self._conn.execute(sql, args) as cursor:
            result: Any = await cursor.fetchall()  # type: ignore[return-value]
            return list(result)


# Module-level singleton
_db: Database | None = None


def get_database() -> Database:
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_database first.")
    return _db


def init_database(settings: DatabaseSettings) -> Database:
    global _db
    _db = Database(settings)
    return _db
