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
    await db.commit()
