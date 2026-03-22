"""Authorization flow service — orchestrates MAX auth and binding lifecycle."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from src.application.auth.exceptions import AuthError
from src.application.ports.clients import MaxClient
from src.application.ports.repositories import AuditRepository, BindingRepository
from src.domain.bindings.models import Binding, BindingStatus
from src.domain.sync.models import AuditEventType


@dataclass(frozen=True)
class AuthStartResult:
    client: MaxClient
    qr_bytes: bytes | None
    session_restored: bool


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
        max_client_factory: Callable[[int, str | None], MaxClient],
        work_dir: str,
    ) -> None:
        self._binding_repo = binding_repo
        self._audit_repo = audit_repo
        self._max_client_factory = max_client_factory
        self._work_dir = work_dir

    async def begin_qr_auth(self, telegram_user_id: int) -> AuthStartResult:
        """Start QR auth: connect to MAX, generate QR image, return client and bytes.

        The QR bytes are available immediately (within ~5s). The client's WebSocket
        stays open and waits for the scan — caller sends the QR photo to Telegram
        and then calls complete_qr_auth().
        """
        client = self._max_client_factory(telegram_user_id, None)
        try:
            qr_result = await client.start_for_qr()  # type: ignore[attr-defined]
        except Exception:
            await client.close()
            raise
        qr_payload = qr_result if isinstance(qr_result, bytes) and qr_result else None
        if qr_payload is None:
            if await client.is_session_valid():
                return AuthStartResult(
                    client=client,
                    qr_bytes=None,
                    session_restored=True,
                )
            await client.close()
            raise AuthError("Failed to generate QR code")
        return AuthStartResult(
            client=client,
            qr_bytes=qr_payload,
            session_restored=False,
        )

    async def complete_qr_auth(self, client: MaxClient, telegram_user_id: int) -> Binding:
        """Save binding after QR scan.

        The QR scan completed and token is saved in pymax's session DB.
        Client stays connected for inbound polling (do NOT close it here).
        """

        now = int(time.time())
        binding = Binding(
            telegram_user_id=telegram_user_id,
            max_session_data="qr_auth",
            status=BindingStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        await self._binding_repo.save(binding)
        await self._audit_repo.log(
            telegram_user_id,
            AuditEventType.BINDING_CREATED,
            f"Binding created via QR for user {telegram_user_id}",
        )
        return binding

    async def start_auth(self, telegram_user_id: int, phone: str) -> Binding:
        """Request SMS code and save binding with phone. Deprecated: use QR auth."""

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
        """Complete login with the SMS code. Deprecated: use QR auth."""

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
