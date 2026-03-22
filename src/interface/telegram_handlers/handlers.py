"""Telegram handlers — /start command, topic routing, and service messages."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.application.auth.authorization import AllowlistGate, AuthorizationFlowService
from src.application.auth.exceptions import AuthError
from src.application.reconcile.service import RefreshReconcileService
from src.application.routing.outbound import OutboundSyncService


def _is_topic_message(message: Message) -> bool:
    """Return True for messages sent inside a Telegram topic."""
    return bool(message.message_thread_id)


router = Router()


def register_handlers(
    router: Router,
    allowlist_gate: AllowlistGate,
    auth_service: AuthorizationFlowService,
    reconcile_service: RefreshReconcileService,
    outbound_service: OutboundSyncService,
) -> None:
    """Register all handlers on the router. Call once at startup."""

    @router.message(Command("start"))
    async def handle_start(message: Message) -> None:  # type: ignore[reportUnusedFunction]
        if message.from_user is None:
            return
        telegram_user_id = message.from_user.id

        # Gate 1: allowlist — silent ignore
        if not allowlist_gate.is_allowed(telegram_user_id):
            return

        # Gate 2: binding status
        binding = await auth_service.get_active_binding(telegram_user_id)

        if binding is None:
            # No binding — start auth flow
            await _handle_auth_required(message)
            return

        if binding.requires_reauth():
            await message.answer(
                "Your MAX session has expired. Please re-authorize by sending /start again "
                "and following the instructions."
            )
            return

        # Active binding — run reconcile
        try:
            await reconcile_service.reconcile(telegram_user_id)
            await message.answer("Sync complete. Your chats are up to date.")
        except AuthError:
            await message.answer("Your MAX session has expired. Please re-authorize.")
            await auth_service.mark_reauth_required(telegram_user_id)

    @router.message(_is_topic_message)
    async def handle_topic_message(message: Message) -> None:  # type: ignore[reportUnusedFunction]
        """Route messages from Telegram topics to MAX chats."""
        if message.from_user is None:
            return
        telegram_user_id = message.from_user.id

        if not allowlist_gate.is_allowed(telegram_user_id):
            return

        if message.text is None:
            await message.answer("Only text messages are supported at this time.")
            return

        try:
            topic_id: int = message.message_thread_id or 0  # type: ignore[reportUnknownMemberType]
            await outbound_service.deliver(
                telegram_user_id=telegram_user_id,
                telegram_topic_id=topic_id,
                text=message.text,
            )
        except AuthError:
            await message.answer("Your MAX session is invalid. Please re-authorize with /start.")

    @router.message()
    async def handle_main_chat_text(message: Message) -> None:  # type: ignore[reportUnusedFunction]
        """Service reply for text sent in the main chat (outside topics)."""
        if message.from_user is None:
            return
        if not allowlist_gate.is_allowed(message.from_user.id):
            return
        # Only respond to actual text, not commands (commands are filtered above)
        if message.text:
            await message.answer(
                "Please send your messages from within a topic. "
                "Use /start to set up or sync your chats first."
            )


async def _handle_auth_required(message: Message) -> None:
    """Send auth instructions to the user."""
    await message.answer(
        "To get started, I need to link your MAX account.\n\n"
        "Please visit the MAX authorization page and send me the verification code, "
        "or follow the instructions provided by your MAX administrator."
    )
