"""Authorization flow service — orchestrates MAX auth and binding lifecycle."""

from __future__ import annotations

import time
from collections.abc import Callable

from src.application.auth.exceptions import AuthError
from src.application.ports.clients import MaxClient
from src.application.ports.repositories import AuditRepository, BindingRepository
from src.domain.bindings.models import Binding, BindingStatus
from src.domain.sync.models import AuditEventType


class AllowlistGate:
    """Rejects non-allowlisted users before any business logic."""

    def __init__(self, allowed_user_ids: set[int]) -> None:
        self._allowed = allowed_user_ids

    def is_allowed(self, telegram_user_id: int) -> bool:
        return telegram_user_id in self._allowed

    def assert_allowed(self, telegram_user_id: int) -> None:
        if not self.is_allowed(telegram_user_id):
            raise PermissionError(f"User {telegram_user_id} is not in allowlist.")


class AuthorizationFlowService:
    """Handles MAX authentication and binding lifecycle.

    pymax persists sessions to work_dir/{telegram_user_id}/.
    The binding stores the phone number in max_session_data.
    """

    def __init__(
        self,
        binding_repo: BindingRepository,
        audit_repo: AuditRepository,
        max_client_factory: Callable[[int, str], MaxClient],
        work_dir: str,
    ) -> None:
        self._binding_repo = binding_repo
        self._audit_repo = audit_repo
        self._max_client_factory = max_client_factory
        self._work_dir = work_dir

    async def start_auth(self, telegram_user_id: int, phone: str) -> Binding:
        """Request SMS code and save binding with phone.

        Raises:
            AuthError: if pymax fails to request the code.
        """
        client = self._max_client_factory(telegram_user_id, phone)
        try:
            await client.authenticate({"phone": phone})
        except AuthError:
            await self._audit_repo.log(
                telegram_user_id,
                AuditEventType.UNKNOWN_ERROR,
                f"Auth failed for user {telegram_user_id}",
            )
            raise
        finally:
            await client.close()

        now = int(time.time())
        binding = Binding(
            telegram_user_id=telegram_user_id,
            max_session_data=phone,
            status=BindingStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        await self._binding_repo.save(binding)
        await self._audit_repo.log(
            telegram_user_id,
            AuditEventType.BINDING_CREATED,
            f"Binding created for user {telegram_user_id}",
        )
        return binding

    async def complete_login(self, telegram_user_id: int, code: str) -> None:
        """Complete login with the SMS code.

        Raises:
            AuthError: if the code is invalid or expired.
        """
        binding = await self._binding_repo.get(telegram_user_id)
        if binding is None:
            raise AuthError("No binding found for user")
        phone = binding.max_session_data
        client = self._max_client_factory(telegram_user_id, phone)
        try:
            await client.authenticate({"code": code})
        except Exception as e:
            raise AuthError(f"Login failed: {e}") from e
        finally:
            await client.close()

    async def get_active_binding(self, telegram_user_id: int) -> Binding | None:
        """Return the binding if it exists and is active."""
        binding = await self._binding_repo.get(telegram_user_id)
        if binding is None:
            return None
        if binding.status == BindingStatus.REAUTH_REQUIRED:
            return binding
        return binding

    async def mark_reauth_required(self, telegram_user_id: int) -> None:
        """Mark binding as requiring re-authorization."""
        await self._binding_repo.update_status(telegram_user_id, BindingStatus.REAUTH_REQUIRED)
        await self._audit_repo.log(
            telegram_user_id,
            AuditEventType.BINDING_REAUTH_REQUIRED,
            f"Session expired for user {telegram_user_id}",
        )
