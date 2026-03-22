"""Background polling and health check services for MLB-007."""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from typing import Any

from src.application.auth.exceptions import AuthError
from src.application.ports.repositories import (
    AuditRepository,
    BindingRepository,
)
from src.application.ports.telegram_client import TelegramClient
from src.domain.bindings.models import BindingStatus
from src.domain.sync.models import AuditEventType


class HealthCheckService:
    """Checks binding health and manages reauth notifications."""

    # How long (seconds) before sending another reauth notification
    REAUTH_NOTIFICATION_COOLDOWN = 60 * 60 * 24  # 24 hours

    def __init__(
        self,
        binding_repo: BindingRepository,
        audit_repo: AuditRepository,
        telegram_client: TelegramClient,
        max_client_factory: Any,  # (session_data: str) -> MaxClient
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
        max_client = self._max_client_factory(binding.max_session_data)
        try:
            is_valid = await max_client.is_session_valid()  # type: ignore[union-attr]
        except AuthError:
            is_valid = False
        finally:
            await max_client.close()  # type: ignore[union-attr]

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
    ) -> None:
        self._binding_repo = binding_repo
        self._health_service = health_service
        self._inbound_factory = inbound_factory
        self._poll_interval = poll_interval
        self._running = False

    async def start(self) -> None:
        """Start the background polling loop. Runs until stop() is called."""
        self._running = True
        while self._running:
            await self._poll_once()
            await asyncio.sleep(self._poll_interval)

    async def stop(self) -> None:
        """Stop the polling loop after the current iteration."""
        self._running = False

    async def _poll_once(self) -> None:
        """Poll all active bindings once."""
        bindings = await self._binding_repo.find_active()
        for binding in bindings:
            if not self._running:
                break
            await self._poll_user(binding.telegram_user_id)

    async def _poll_user(self, telegram_user_id: int) -> None:
        """Poll a single user, handling reauth transitions."""
        with suppress(Exception):  # non-fatal health check errors
            await self._health_service.check_and_notify(telegram_user_id)

        binding = await self._binding_repo.get(telegram_user_id)
        if binding is None or binding.status != BindingStatus.ACTIVE:
            return

        inbound = self._inbound_factory(telegram_user_id)
        with suppress(AuthError):
            await inbound.poll_user(telegram_user_id)
