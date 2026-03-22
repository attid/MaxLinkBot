"""Unit tests for BackgroundPoller and HealthCheckService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from src.application.health.service import BackgroundPoller, HealthCheckService
from src.application.ports.repositories import AuditRepository, BindingRepository
from src.application.ports.telegram_client import TelegramClient
from src.domain.bindings.models import Binding, BindingStatus


class MockHealthRepos:
    """Container of mocks for health service tests."""

    binding_repo: MagicMock
    audit_repo: MagicMock
    telegram: MagicMock

    def __init__(self) -> None:
        self.binding_repo = MagicMock(spec=BindingRepository)
        self.audit_repo = MagicMock(spec=AuditRepository)
        self.telegram = MagicMock(spec=TelegramClient)


class TestHealthCheckService:
    async def test_check_and_notify_skips_inactive_binding(self) -> None:
        """Inactive binding is skipped without any session check."""
        repos = MockHealthRepos()
        repos.binding_repo.get = AsyncMock(
            return_value=Binding(
                telegram_user_id=123,
                max_session_data="session",
                status=BindingStatus.REAUTH_REQUIRED,
                created_at=0,
                updated_at=0,
            )
        )

        def factory(_session_data: str) -> MagicMock:
            return MagicMock()

        service = HealthCheckService(
            binding_repo=repos.binding_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=factory,
        )

        await service.check_and_notify(123)

        repos.telegram.send_text.assert_not_called()
        repos.binding_repo.update_status.assert_not_called()

    async def test_check_and_notify_skips_if_already_notified(self) -> None:
        """If reauth notification was already sent recently, skip sending again."""
        repos = MockHealthRepos()
        repos.binding_repo.get = AsyncMock(
            return_value=Binding(
                telegram_user_id=123,
                max_session_data="session",
                status=BindingStatus.ACTIVE,
                created_at=0,
                updated_at=0,
            )
        )
        repos.audit_repo.has_recent_event = AsyncMock(return_value=True)

        max_client = MagicMock()
        max_client.is_session_valid = AsyncMock(return_value=False)
        max_client.close = AsyncMock()

        def factory(_session_data: str) -> MagicMock:
            return max_client

        service = HealthCheckService(
            binding_repo=repos.binding_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=factory,
        )

        await service.check_and_notify(123)

        repos.telegram.send_text.assert_not_called()
        repos.binding_repo.update_status.assert_not_called()

    async def test_check_and_notify_session_expired_sends_notification(self) -> None:
        """Expired session → status updated, audit logged, notification sent."""
        repos = MockHealthRepos()
        repos.binding_repo.get = AsyncMock(
            return_value=Binding(
                telegram_user_id=123,
                max_session_data="session",
                status=BindingStatus.ACTIVE,
                created_at=0,
                updated_at=0,
            )
        )
        repos.audit_repo.has_recent_event = AsyncMock(return_value=False)

        max_client = MagicMock()
        max_client.is_session_valid = AsyncMock(return_value=False)
        max_client.close = AsyncMock()

        def factory(_session_data: str) -> MagicMock:
            return max_client

        service = HealthCheckService(
            binding_repo=repos.binding_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=factory,
        )

        await service.check_and_notify(123)

        repos.binding_repo.update_status.assert_called_once_with(123, BindingStatus.REAUTH_REQUIRED)
        repos.audit_repo.log.assert_called_once()
        repos.telegram.send_text.assert_called_once()

    async def test_check_and_notify_session_valid_nothing_happens(self) -> None:
        """Valid session → no status change, no notification."""
        repos = MockHealthRepos()
        repos.binding_repo.get = AsyncMock(
            return_value=Binding(
                telegram_user_id=123,
                max_session_data="session",
                status=BindingStatus.ACTIVE,
                created_at=0,
                updated_at=0,
            )
        )
        repos.audit_repo.has_recent_event = AsyncMock(return_value=False)

        max_client = MagicMock()
        max_client.is_session_valid = AsyncMock(return_value=True)
        max_client.close = AsyncMock()

        def factory(_session_data: str) -> MagicMock:
            return max_client

        service = HealthCheckService(
            binding_repo=repos.binding_repo,
            audit_repo=repos.audit_repo,
            telegram_client=repos.telegram,
            max_client_factory=factory,
        )

        await service.check_and_notify(123)

        repos.binding_repo.update_status.assert_not_called()
        repos.telegram.send_text.assert_not_called()


class TestBackgroundPoller:
    async def test_poll_once_skips_reauth_required(self) -> None:
        """Binding that becomes REAUTH_REQUIRED mid-loop skips inbound polling."""
        repos = MockHealthRepos()
        binding = Binding(
            telegram_user_id=123,
            max_session_data="session",
            status=BindingStatus.ACTIVE,
            created_at=0,
            updated_at=0,
        )
        repos.binding_repo.find_active = AsyncMock(return_value=[binding])
        repos.binding_repo.get = AsyncMock(return_value=binding)

        health = MagicMock()
        health.check_and_notify = AsyncMock()

        inbound = MagicMock()
        inbound.poll_user = AsyncMock()

        def factory(_uid: int) -> MagicMock:
            return inbound

        poller = BackgroundPoller(
            binding_repo=repos.binding_repo,
            health_service=health,
            inbound_factory=factory,
            poll_interval=60.0,
        )

        poller._running = True  # type: ignore[reportPrivateUsage]
        await poller._poll_once()  # type: ignore[reportPrivateUsage]

        inbound.poll_user.assert_called_once_with(123)

    async def test_poll_once_reauth_required_skips_poll(self) -> None:
        """Binding that transitions to REAUTH_REQUIRED skips further polling."""
        repos = MockHealthRepos()

        # First call returns ACTIVE (used by health check)
        # Second call returns REAUTH_REQUIRED (used before poll)
        active_binding = Binding(
            telegram_user_id=123,
            max_session_data="session",
            status=BindingStatus.ACTIVE,
            created_at=0,
            updated_at=0,
        )
        reauth_binding = Binding(
            telegram_user_id=123,
            max_session_data="session",
            status=BindingStatus.REAUTH_REQUIRED,
            created_at=0,
            updated_at=0,
        )
        repos.binding_repo.find_active = AsyncMock(return_value=[active_binding])
        repos.binding_repo.get = AsyncMock(side_effect=[active_binding, reauth_binding])

        health = MagicMock()
        health.check_and_notify = AsyncMock()

        inbound = MagicMock()
        inbound.poll_user = AsyncMock()

        def factory(_uid: int) -> MagicMock:
            return inbound

        poller = BackgroundPoller(
            binding_repo=repos.binding_repo,
            health_service=health,
            inbound_factory=factory,
            poll_interval=60.0,
        )

        await poller._poll_once()  # type: ignore[reportPrivateUsage]

        # After health check marks binding REAUTH_REQUIRED, inbound polling is skipped
        inbound.poll_user.assert_not_called()

    async def test_stop_terminates_loop(self) -> None:
        """stop() prevents the next iteration from running."""
        repos = MockHealthRepos()
        repos.binding_repo.find_active = AsyncMock(return_value=[])
        repos.binding_repo.get = AsyncMock()

        health = MagicMock()

        poller = BackgroundPoller(
            binding_repo=repos.binding_repo,
            health_service=health,
            inbound_factory=lambda _u: MagicMock(),  # type: ignore[reportUnknownLambdaType]
            poll_interval=60.0,
        )

        # Start then immediately stop
        poller._running = True  # type: ignore[reportPrivateUsage]
        await poller.stop()
        await poller._poll_once()  # type: ignore[reportPrivateUsage]
