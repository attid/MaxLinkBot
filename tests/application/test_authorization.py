"""Unit tests for AuthorizationFlowService and AllowlistGate."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.auth.authorization import (
    AllowlistGate,
    AuthorizationFlowService,
    AuthStartResult,
)
from src.application.auth.exceptions import AuthError
from src.domain.bindings.models import Binding, BindingStatus


class TestAllowlistGate:
    def test_allowed_user_passes(self) -> None:
        gate = AllowlistGate({123, 456})
        assert gate.is_allowed(123) is True
        assert gate.is_allowed(456) is True

    def test_unknown_user_rejected(self) -> None:
        gate = AllowlistGate({123})
        assert gate.is_allowed(999) is False

    def test_assert_allowed_raises_for_unknown(self) -> None:
        gate = AllowlistGate({123})
        with pytest.raises(PermissionError) as exc_info:
            gate.assert_allowed(999)
        assert "999" in str(exc_info.value)
        assert "not in allowlist" in str(exc_info.value)

    def test_empty_allowlist_rejects_all(self) -> None:
        gate = AllowlistGate(set())
        assert gate.is_allowed(1) is False


def make_auth_service(binding_repo: MagicMock, audit_repo: MagicMock) -> AuthorizationFlowService:
    """Factory that creates an AuthorizationFlowService with a working mock client."""

    def factory(_uid: int, _phone: str | None) -> MagicMock:
        client = MagicMock()
        client.authenticate = AsyncMock(return_value="+79112223344")
        client.is_session_valid = AsyncMock(return_value=True)
        client.close = AsyncMock()
        return client

    return AuthorizationFlowService(
        binding_repo=binding_repo,
        audit_repo=audit_repo,
        max_client_factory=factory,
        work_dir="/tmp/max",
    )


class TestAuthorizationFlowService:
    async def test_begin_qr_auth_uses_existing_session_without_qr(self) -> None:
        binding_repo = MagicMock()
        binding_repo.save = AsyncMock()
        audit_repo = MagicMock()
        audit_repo.log = AsyncMock()

        existing_client = MagicMock()
        existing_client.start_for_qr = AsyncMock(return_value=b"")
        existing_client.is_session_valid = AsyncMock(return_value=True)
        existing_client.close = AsyncMock()

        def existing_session_factory(_uid: int, _phone: str | None) -> MagicMock:
            return existing_client

        service = AuthorizationFlowService(
            binding_repo=binding_repo,
            audit_repo=audit_repo,
            max_client_factory=existing_session_factory,
            work_dir="/tmp/max",
        )

        result = await service.begin_qr_auth(telegram_user_id=123)

        assert result == AuthStartResult(
            client=existing_client,
            qr_bytes=None,
            session_restored=True,
        )
        existing_client.close.assert_not_called()

    async def test_start_auth_creates_binding(self) -> None:
        binding_repo = MagicMock()
        binding_repo.get = AsyncMock(return_value=None)
        binding_repo.save = AsyncMock()
        audit_repo = MagicMock()
        audit_repo.log = AsyncMock()

        service = make_auth_service(binding_repo, audit_repo)
        await service.start_auth(telegram_user_id=123, phone="+79112223344")

        binding_repo.save.assert_called_once()
        saved = binding_repo.save.call_args[0][0]
        assert saved.telegram_user_id == 123
        assert saved.max_session_data == "+79112223344"  # stores phone
        assert saved.status == BindingStatus.ACTIVE
        audit_repo.log.assert_called()

    async def test_start_auth_raises_on_auth_failure(self) -> None:
        binding_repo = MagicMock()
        binding_repo.get = AsyncMock(return_value=None)
        binding_repo.save = AsyncMock()
        audit_repo = MagicMock()
        audit_repo.log = AsyncMock()

        def failing_factory(_uid: int, _phone: str | None) -> MagicMock:
            client = MagicMock()
            client.authenticate = AsyncMock(side_effect=AuthError("Invalid"))
            client.close = AsyncMock()
            return client

        service = AuthorizationFlowService(
            binding_repo=binding_repo,
            audit_repo=audit_repo,
            max_client_factory=failing_factory,
            work_dir="/tmp/max",
        )

        with pytest.raises(AuthError):
            await service.start_auth(123, "+79112223344")

        audit_repo.log.assert_called()

    async def test_get_active_binding_returns_none_when_missing(self) -> None:
        binding_repo = MagicMock()
        binding_repo.get = AsyncMock(return_value=None)
        audit_repo = MagicMock()
        service = make_auth_service(binding_repo, audit_repo)

        result = await service.get_active_binding(123)
        assert result is None

    async def test_get_active_binding_returns_active_binding(self) -> None:
        binding_repo = MagicMock()
        binding = Binding(
            telegram_user_id=123,
            max_session_data="+79112223344",
            status=BindingStatus.ACTIVE,
            created_at=0,
            updated_at=0,
        )
        binding_repo.get = AsyncMock(return_value=binding)
        audit_repo = MagicMock()
        service = make_auth_service(binding_repo, audit_repo)

        result = await service.get_active_binding(123)
        assert result is not None
        assert result.telegram_user_id == 123
