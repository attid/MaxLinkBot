"""Integration tests for BindingRepository using in-memory SQLite."""

from __future__ import annotations

import time

import pytest_asyncio

from src.domain.bindings.models import Binding, BindingStatus
from src.infrastructure.persistence.connection import Database, DatabaseSettings
from src.infrastructure.persistence.init import init_schema
from src.infrastructure.persistence.repositories import SqliteBindingRepository


@pytest_asyncio.fixture
async def db():
    settings = DatabaseSettings(database_url="sqlite+aiosqlite:///:memory:")
    db_instance = Database(settings)
    await db_instance.connect()
    await init_schema(db_instance)
    yield db_instance
    await db_instance.close()


class TestBindingRepository:
    async def test_save_and_get_active(self, db: Database) -> None:
        repo = SqliteBindingRepository(db)
        binding = Binding(
            telegram_user_id=123,
            max_session_data="session_token_abc",
            status=BindingStatus.ACTIVE,
            created_at=int(time.time()),
            updated_at=int(time.time()),
        )
        await repo.save(binding)
        loaded = await repo.get(123)
        assert loaded is not None
        assert loaded.telegram_user_id == 123
        assert loaded.status == BindingStatus.ACTIVE
        assert loaded.max_session_data == "session_token_abc"

    async def test_get_nonexistent(self, db: Database) -> None:
        repo = SqliteBindingRepository(db)
        result = await repo.get(999)
        assert result is None

    async def test_update_status_to_reauth_required(self, db: Database) -> None:
        repo = SqliteBindingRepository(db)
        await repo.save(
            Binding(
                telegram_user_id=123,
                max_session_data="token",
                status=BindingStatus.ACTIVE,
                created_at=0,
                updated_at=0,
            )
        )
        await repo.update_status(123, BindingStatus.REAUTH_REQUIRED)
        loaded = await repo.get(123)
        assert loaded is not None
        assert loaded.status == BindingStatus.REAUTH_REQUIRED

    async def test_one_binding_per_user(self, db: Database) -> None:
        """Each telegram_user_id has exactly one binding (upsert semantics)."""
        repo = SqliteBindingRepository(db)
        await repo.save(
            Binding(
                telegram_user_id=123,
                max_session_data="token1",
                status=BindingStatus.ACTIVE,
                created_at=0,
                updated_at=0,
            )
        )
        await repo.save(
            Binding(
                telegram_user_id=123,
                max_session_data="token2",
                status=BindingStatus.ACTIVE,
                created_at=0,
                updated_at=int(time.time()),
            )
        )
        loaded = await repo.get(123)
        assert loaded is not None
        assert loaded.max_session_data == "token2"
