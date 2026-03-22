"""Domain tests for binding state transitions."""

from __future__ import annotations

from src.domain.bindings.models import Binding, BindingStatus


class TestBindingStateTransitions:
    def test_active_can_route(self) -> None:
        b = Binding(
            telegram_user_id=1,
            max_session_data="token",
            status=BindingStatus.ACTIVE,
            created_at=0,
            updated_at=0,
        )
        assert b.can_route() is True
        assert b.requires_reauth() is False

    def test_reauth_required_cannot_route(self) -> None:
        b = Binding(
            telegram_user_id=1,
            max_session_data="token",
            status=BindingStatus.REAUTH_REQUIRED,
            created_at=0,
            updated_at=0,
        )
        assert b.can_route() is False
        assert b.requires_reauth() is True

    def test_disabled_cannot_route(self) -> None:
        b = Binding(
            telegram_user_id=1,
            max_session_data="token",
            status=BindingStatus.DISABLED,
            created_at=0,
            updated_at=0,
        )
        assert b.can_route() is False
        assert b.requires_reauth() is False
