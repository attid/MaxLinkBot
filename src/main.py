"""MaxLinkBot entrypoint."""

from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.application.auth.authorization import AllowlistGate, AuthorizationFlowService
from src.application.health.service import (
    BackgroundPoller,
    HealthCheckService,
    RuntimeHealthTracker,
)
from src.application.polling.max_runtime import MaxClientRuntimeRegistry
from src.application.reconcile.service import RefreshReconcileService
from src.application.routing.outbound import OutboundSyncService
from src.infrastructure.max.adapter import max_client_factory
from src.infrastructure.persistence.connection import Database, DatabaseSettings
from src.infrastructure.persistence.init import init_schema
from src.infrastructure.persistence.repositories import (
    SqliteAuditRepository,
    SqliteBindingRepository,
    SqliteMaxChatRepository,
    SqliteMessageLinkRepository,
    SqliteSyncCursorRepository,
    SqliteTelegramTopicRepository,
)
from src.infrastructure.telegram.adapter import AiogramTelegramAdapter
from src.interface.telegram_handlers.handlers import register_handlers

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings from environment."""

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    telegram_bot_token: str
    allowed_telegram_user_ids: str = ""
    max_work_dir: str = "/data/max_sessions"
    database_url: str = "sqlite+aiosqlite:////data/maxlinkbot.db"
    poll_interval_seconds: float = 1.0
    health_check_interval_seconds: int = 300
    catchup_interval_seconds: int = 3600
    reconnect_storm_threshold: int = 5
    reconnect_storm_window_seconds: int = 300
    backfill_message_count: int = 5
    log_level: str = "INFO"
    runtime_unhealthy_marker_path: str = "/tmp/maxlinkbot.unhealthy"

    @property
    def allowed_ids_set(self) -> set[int]:
        return {int(x.strip()) for x in self.allowed_telegram_user_ids.split(",") if x.strip()}


async def configure_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(
                command="start",
                description="Sync chats and create missing topics",
            ),
            BotCommand(
                command="resync",
                description="Rebuild all topics from MAX chats",
            ),
        ]
    )


async def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = Settings()  # type: ignore[call-args]
    logger.info("MaxLinkBot starting...")

    # Database
    db = Database(DatabaseSettings(database_url=settings.database_url))
    await db.connect()
    await init_schema(db)
    logger.info("Database initialized")

    # Repositories
    binding_repo = SqliteBindingRepository(db)
    max_chat_repo = SqliteMaxChatRepository(db)
    topic_repo = SqliteTelegramTopicRepository(db)
    message_link_repo = SqliteMessageLinkRepository(db)
    cursor_repo = SqliteSyncCursorRepository(db)
    audit_repo = SqliteAuditRepository(db)

    # MAX client factory
    live_max_factory = max_client_factory(settings.max_work_dir, reconnect=True)
    oneshot_max_factory = max_client_factory(settings.max_work_dir, reconnect=False)
    shared_max_runtime = MaxClientRuntimeRegistry(live_max_factory)

    # Telegram client + bot
    bot = Bot(token=settings.telegram_bot_token)
    await configure_bot_commands(bot)
    tg_client = AiogramTelegramAdapter(bot)

    # Services
    allowlist_gate = AllowlistGate(settings.allowed_ids_set)

    auth_service = AuthorizationFlowService(
        binding_repo=binding_repo,
        audit_repo=audit_repo,
        max_client_factory=oneshot_max_factory,
        work_dir=settings.max_work_dir,
    )

    reconcile_service = RefreshReconcileService(
        binding_repo=binding_repo,
        max_chat_repo=max_chat_repo,
        topic_repo=topic_repo,
        cursor_repo=cursor_repo,
        audit_repo=audit_repo,
        telegram_client=tg_client,
        max_client_factory=oneshot_max_factory,
        backfill_count=settings.backfill_message_count,
    )

    outbound_service = OutboundSyncService(
        binding_repo=binding_repo,
        topic_repo=topic_repo,
        message_link_repo=message_link_repo,
        audit_repo=audit_repo,
        max_client_factory=oneshot_max_factory,
        shared_runtime=shared_max_runtime,
    )

    health_service = HealthCheckService(
        binding_repo=binding_repo,
        audit_repo=audit_repo,
        telegram_client=tg_client,
        max_client_factory=oneshot_max_factory,
    )
    runtime_health_tracker = RuntimeHealthTracker(settings.runtime_unhealthy_marker_path)

    # Inbound factory for background poller
    async def reconcile_user(telegram_user_id: int) -> None:
        await reconcile_service.reconcile(telegram_user_id)

    def inbound_factory(telegram_user_id: int):
        from src.application.routing.inbound import InboundSyncService

        return InboundSyncService(
            binding_repo=binding_repo,
            max_chat_repo=max_chat_repo,
            topic_repo=topic_repo,
            message_link_repo=message_link_repo,
            cursor_repo=cursor_repo,
            audit_repo=audit_repo,
            telegram_client=tg_client,
            max_client_factory=live_max_factory,
            catchup_interval_seconds=float(settings.catchup_interval_seconds),
            reconcile_user=reconcile_user,
            shared_runtime=shared_max_runtime,
            reconnect_storm_threshold=int(settings.reconnect_storm_threshold),
            reconnect_storm_window_seconds=float(settings.reconnect_storm_window_seconds),
        )

    poller = BackgroundPoller(
        binding_repo=binding_repo,
        health_service=health_service,
        inbound_factory=inbound_factory,
        poll_interval=float(settings.poll_interval_seconds),
        health_check_interval=float(settings.health_check_interval_seconds),
        runtime_health_tracker=runtime_health_tracker,
    )

    # Register Telegram handlers
    dp = Dispatcher(bot=bot)
    register_handlers(dp, allowlist_gate, auth_service, reconcile_service, outbound_service, tg_client)

    # Start background poller
    asyncio.create_task(poller.start())

    logger.info("Bot starting...")
    await dp.start_polling(bot)  # type: ignore[reportUnknownMemberType]

    await poller.stop()
    await shared_max_runtime.close_all()
    await bot.session.close()
    await db.close()
    logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
