"""Telegram handlers — /start command, topic routing, and service messages."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from src.application.auth.authorization import AllowlistGate, AuthorizationFlowService
from src.application.auth.exceptions import AuthError
from src.application.ports.telegram_client import TelegramClient
from src.application.reconcile.service import RefreshReconcileService
from src.application.routing.outbound import OutboundSyncService

router = Router()


def register_handlers(
    router: Router,
    allowlist_gate: AllowlistGate,
    auth_service: AuthorizationFlowService,
    reconcile_service: RefreshReconcileService,
    outbound_service: OutboundSyncService,
    telegram_client: TelegramClient,
) -> None:
    """Register all handlers on the router."""

    @router.message(Command("start"))
    async def handle_start(message: Message) -> None:  # type: ignore[reportUnusedFunction]
        if message.from_user is None:
            return
        telegram_user_id = message.from_user.id

        if not allowlist_gate.is_allowed(telegram_user_id):
            return

        binding = await auth_service.get_active_binding(telegram_user_id)

        if binding is None or binding.requires_reauth():
            try:
                auth_start = await auth_service.begin_qr_auth(telegram_user_id)
                if auth_start.session_restored:
                    await auth_service.complete_qr_auth(auth_start.client, telegram_user_id)
                    await reconcile_service.reconcile(telegram_user_id)
                    await message.answer("Existing MAX session restored. Your chats are up to date.")
                    return

                await message.answer("Open MAX app → Settings → Linked devices → Scan QR")
                await message.answer_photo(
                    photo=BufferedInputFile(auth_start.qr_bytes or b"", filename="qr.png")
                )
                await auth_service.complete_qr_auth(auth_start.client, telegram_user_id)
                await message.answer("Authorized! Send /start to sync your chats.")
            except AuthError as e:
                await message.answer(f"QR auth failed: {e}")
            return

        try:
            await reconcile_service.reconcile(telegram_user_id)
            await message.answer("Sync complete. Your chats are up to date.")
        except AuthError:
            await message.answer("MAX session expired. Send /start to re-authorize.")
            await auth_service.mark_reauth_required(telegram_user_id)

    @router.message()
    async def handle_message(message: Message) -> None:  # type: ignore[reportUnusedFunction]
        """Route all text messages: topic messages or main chat."""
        if message.from_user is None:
            return
        telegram_user_id = message.from_user.id
        if not allowlist_gate.is_allowed(telegram_user_id):
            return
        text = message.text
        if not text:
            return

        # Topic message → deliver to MAX
        if message.message_thread_id:
            try:
                await outbound_service.deliver(
                    telegram_user_id=telegram_user_id,
                    telegram_topic_id=message.message_thread_id or 0,
                    text=text,
                )
            except AuthError:
                await message.answer("MAX session invalid. Send /start to re-authorize.")
            return

        # Plain text in main chat
        await message.answer("Send /start to sync chats.")
