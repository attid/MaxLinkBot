"""Database initialization."""

from src.infrastructure.persistence.connection import Database
from src.infrastructure.persistence.schema import SCHEMA_SQL


async def init_schema(db: Database) -> None:
    """Run all CREATE statements. Safe to call on existing DB."""
    if db._conn is None:  # type: ignore[reportPrivateUsage]
        raise RuntimeError("Database not connected")
    raw_conn = db._conn  # type: ignore[reportPrivateUsage]
    cursor = await raw_conn.cursor()
    await cursor.executescript(SCHEMA_SQL)
    topic_columns = await db.fetchall("PRAGMA table_info(telegram_topics)")
    if "inbound_enabled" not in {str(column["name"]) for column in topic_columns}:
        await db.execute(
            "ALTER TABLE telegram_topics "
            "ADD COLUMN inbound_enabled INTEGER NOT NULL DEFAULT 1 "
            "CHECK (inbound_enabled IN (0, 1))"
        )
    if "inbound_since_ms" not in {str(column["name"]) for column in topic_columns}:
        await db.execute("ALTER TABLE telegram_topics ADD COLUMN inbound_since_ms INTEGER")
    await db.commit()
