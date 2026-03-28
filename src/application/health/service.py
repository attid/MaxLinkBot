"""Background polling and health check services for MLB-007."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from src.application.auth.exceptions import AuthError
from src.application.ports.clients import MaxClient
from src.application.ports.repositories import (
    AuditRepository,
    BindingRepository,
)
from src.application.ports.telegram_client import TelegramClient
from src.domain.bindings.models import BindingStatus
from src.domain.sync.models import AuditEventType

logger = logging.getLogger(__name__)


class RuntimeHealthTracker:
    """Tracks runtime health through a filesystem marker."""

    def __init__(self, marker_path: str | Path = "/tmp/maxlinkbot.unhealthy") -> None:
        self._marker_path = Path(marker_path)

    def mark_healthy(self) -> None:
        with suppress(FileNotFoundError):
            self._marker_path.unlink()

    def mark_unhealthy(self, reason: str) -> None:
        self._marker_path.parent.mkdir(parents=True, exist_ok=True)
        self._marker_path.write_text(reason, encoding="utf-8")

    def is_healthy(self) -> bool:
        return not self._marker_path.exists()


class HealthCheckService:
    """Checks binding health and manages reauth notifications."""

    # How long (seconds) before sending another reauth notification
    REAUTH_NOTIFICATION_COOLDOWN = 60 * 60 * 24  # 24 hours

    def __init__(
        self,
        binding_repo: BindingRepository,
        audit_repo: AuditRepository,
        telegram_client: TelegramClient,
        max_client_factory: Callable[[int, str], MaxClient],
    ) -> None:
        self._binding_repo = binding_repo
        self._audit_repo = audit_repo
        self._telegram = telegram_client
        self._max_client_factory = max_client_factory

    async def check_and_notify(self, telegram_user_id: int) -> None:
        """Check session validity; send reauth notification if expired and not already sent."""
        binding = await self._binding_repo.get(telegram_user_id)
        if binding is None or binding.status != BindingStatus.ACTIVE:
            return

        # Already notified recently
        since = int(time.time()) - self.REAUTH_NOTIFICATION_COOLDOWN
        if await self._audit_repo.has_recent_event(
            telegram_user_id, AuditEventType.BINDING_REAUTH_REQUIRED, since
        ):
            return

        # Validate session
        max_client = self._max_client_factory(binding.telegram_user_id, binding.max_session_data)
        try:
            await max_client.start()  # type: ignore[attr-defined]
            is_valid = await max_client.is_session_valid()
        except AuthError:
            is_valid = False
        finally:
            await max_client.close()

        if not is_valid:
            await self._binding_repo.update_status(telegram_user_id, BindingStatus.REAUTH_REQUIRED)
            await self._audit_repo.log(
                telegram_user_id,
                AuditEventType.BINDING_REAUTH_REQUIRED,
                f"Session expired for user {telegram_user_id}",
            )
            await self._telegram.send_text(
                chat_id=telegram_user_id,
                text="Your MAX session has expired. Please re-authorize by sending /start.",
            )


class BackgroundPoller:
    """Background loop that polls all active bindings."""

    def __init__(
        self,
        binding_repo: BindingRepository,
        health_service: HealthCheckService,
        inbound_factory: Any,  # (telegram_user_id) -> InboundSyncService per-user
        poll_interval: float = 60.0,
        health_check_interval: float = 300.0,
        runtime_health_tracker: RuntimeHealthTracker | None = None,
    ) -> None:
        self._binding_repo = binding_repo
        self._health_service = health_service
        self._inbound_factory = inbound_factory
        self._poll_interval = poll_interval
        self._health_check_interval = health_check_interval
        self._runtime_health_tracker = runtime_health_tracker or RuntimeHealthTracker()
        self._running = False
        self._inbound_services: dict[int, Any] = {}
        self._last_health_check_at: dict[int, float] = {}

    async def start(self) -> None:
        """Start the background polling loop. Runs until stop() is called."""
        self._running = True
        self._runtime_health_tracker.mark_healthy()
        while self._running:
            await self._poll_once()
            await asyncio.sleep(self._poll_interval)

    async def stop(self) -> None:
        """Stop the polling loop after the current iteration."""
        self._running = False
        for inbound in self._inbound_services.values():
            close = getattr(inbound, "close", None)
            if close is not None:
                await close()
        self._inbound_services.clear()

    async def _poll_once(self) -> None:
        """Poll all active bindings once."""
        bindings = await self._binding_repo.find_active()
        had_runtime_failure = False
        for binding in bindings:
            if not self._running:
                break
            poll_ok = await self._poll_user(binding.telegram_user_id)
            had_runtime_failure = had_runtime_failure or not poll_ok

        if had_runtime_failure:
            self._runtime_health_tracker.mark_unhealthy(
                f"Background poll failed at {int(time.time())}"
            )
        else:
            self._runtime_health_tracker.mark_healthy()

    async def _poll_user(self, telegram_user_id: int) -> bool:
        """Poll a single user, handling reauth transitions."""
        now = time.time()
        last_health_check_at = self._last_health_check_at.get(telegram_user_id)
        if last_health_check_at is None or (
            now - last_health_check_at >= self._health_check_interval
        ):
            with suppress(Exception):  # non-fatal health check errors
                await self._health_service.check_and_notify(telegram_user_id)
            self._last_health_check_at[telegram_user_id] = now

        binding = await self._binding_repo.get(telegram_user_id)
        if binding is None or binding.status != BindingStatus.ACTIVE:
            inbound = self._inbound_services.pop(telegram_user_id, None)
            if inbound is not None:
                close = getattr(inbound, "close", None)
                if close is not None:
                    await close()
            return True

        inbound = self._inbound_services.get(telegram_user_id)
        if inbound is None:
            inbound = self._inbound_factory(telegram_user_id)
            self._inbound_services[telegram_user_id] = inbound
        try:
            await inbound.poll_user(telegram_user_id)
        except AuthError:
            return True
        except Exception:
            logger.exception(
                "background inbound poll failed telegram_user_id=%s",
                telegram_user_id,
            )
            return False
        return True
