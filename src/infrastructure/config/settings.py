"""Application settings from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class AppSettings(BaseSettings):
    telegram_bot_token: str
    allowed_telegram_user_ids: str  # comma-separated
    max_phone: str
    max_work_dir: str
    database_url: str = "sqlite+aiosqlite:///data/maxlinkbot.db"
    poll_interval_seconds: int = 30
    backfill_message_count: int = 5
    log_level: str = "INFO"

    @property
    def allowed_user_ids(self) -> set[int]:
        return {
            int(uid.strip()) for uid in self.allowed_telegram_user_ids.split(",") if uid.strip()
        }
