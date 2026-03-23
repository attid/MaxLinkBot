"""Telegram handlers — /start command, topic routing, and service messages."""

from __future__ import annotations

import io
import logging
from pathlib import Path

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from src.application.auth.authorization import AllowlistGate, AuthorizationFlowService
from src.application.auth.exceptions import AuthError
from src.application.ports.telegram_client import TelegramClient
from src.application.reconcile.service import RefreshReconcileService
from src.application.routing.outbound import OutboundSyncService

router = Router()
logger = logging.getLogger(__name__)


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
        logger.info("/start received from telegram_user_id=%s", telegram_user_id)

        if not allowlist_gate.is_allowed(telegram_user_id):
            logger.info("/start ignored for non-allowlisted telegram_user_id=%s", telegram_user_id)
            return

        binding = await auth_service.get_active_binding(telegram_user_id)
        logger.info(
            "/start binding lookup telegram_user_id=%s binding_exists=%s",
            telegram_user_id,
            binding is not None,
        )

        if binding is None or binding.requires_reauth():
            try:
                logger.info("/start entering auth flow telegram_user_id=%s", telegram_user_id)
                auth_start = await auth_service.begin_qr_auth(telegram_user_id)
                if auth_start.session_restored:
                    logger.info(
                        "/start restored MAX session telegram_user_id=%s; starting reconcile",
                        telegram_user_id,
                    )
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
                logger.exception(
                    "/start auth flow failed telegram_user_id=%s error=%s",
                    telegram_user_id,
                    e,
                )
                await message.answer(f"QR auth failed: {e}")
            return

        try:
            logger.info("/start running reconcile telegram_user_id=%s", telegram_user_id)
            await reconcile_service.reconcile(telegram_user_id)
            logger.info("/start reconcile finished telegram_user_id=%s", telegram_user_id)
            await message.answer("Sync complete. Your chats are up to date.")
        except AuthError:
            logger.exception("/start reconcile auth error telegram_user_id=%s", telegram_user_id)
            await message.answer("MAX session expired. Send /start to re-authorize.")
            await auth_service.mark_reauth_required(telegram_user_id)
        except Exception:
            logger.exception("/start reconcile unexpected error telegram_user_id=%s", telegram_user_id)
            await message.answer("Sync failed. Check logs and try /start again.")

    @router.message(Command("resync"))
    async def handle_resync(message: Message) -> None:  # type: ignore[reportUnusedFunction]
        if message.from_user is None:
            return
        telegram_user_id = message.from_user.id
        logger.info("/resync received from telegram_user_id=%s", telegram_user_id)

        if not allowlist_gate.is_allowed(telegram_user_id):
            logger.info("/resync ignored for non-allowlisted telegram_user_id=%s", telegram_user_id)
            return

        binding = await auth_service.get_active_binding(telegram_user_id)
        if binding is None or binding.requires_reauth():
            await message.answer("MAX session invalid. Send /start to authorize first.")
            return

        raw_text = (message.text or "").strip()
        parts = raw_text.split(maxsplit=1)
        target_max_chat_id = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None

        try:
            logger.info(
                "/resync running telegram_user_id=%s target_max_chat_id=%s",
                telegram_user_id,
                target_max_chat_id,
            )
            await reconcile_service.reconcile(
                telegram_user_id,
                force_recreate=True,
                target_max_chat_id=target_max_chat_id,
            )
            logger.info(
                "/resync finished telegram_user_id=%s target_max_chat_id=%s",
                telegram_user_id,
                target_max_chat_id,
            )
            if target_max_chat_id is None:
                await message.answer("Full topic rebuild complete.")
            else:
                await message.answer(f"Topic rebuild complete for MAX chat {target_max_chat_id}.")
        except ValueError as exc:
            logger.exception(
                "/resync invalid target telegram_user_id=%s target_max_chat_id=%s",
                telegram_user_id,
                target_max_chat_id,
            )
            await message.answer(str(exc))
        except AuthError:
            logger.exception("/resync auth error telegram_user_id=%s", telegram_user_id)
            await message.answer("MAX session expired. Send /start to re-authorize.")
            await auth_service.mark_reauth_required(telegram_user_id)
        except Exception:
            logger.exception("/resync unexpected error telegram_user_id=%s", telegram_user_id)
            await message.answer("Resync failed. Check logs and try /resync again.")

    @router.message()
    async def handle_message(message: Message) -> None:  # type: ignore[reportUnusedFunction]
        """Route all text messages: topic messages or main chat."""
        if message.from_user is None:
            return
        telegram_user_id = message.from_user.id
        if not allowlist_gate.is_allowed(telegram_user_id):
            return

        # Topic message → deliver to MAX
        if message.message_thread_id:
            if message.photo:
                largest_photo = message.photo[-1]
                file = await message.bot.get_file(largest_photo.file_id)
                buffer = io.BytesIO()
                await message.bot.download_file(file.file_path, destination=buffer)
                filename = Path(file.file_path or largest_photo.file_id).name or f"{largest_photo.file_id}.jpg"
                try:
                    await outbound_service.deliver_photo(
                        telegram_user_id=telegram_user_id,
                        telegram_topic_id=message.message_thread_id or 0,
                        image_bytes=buffer.getvalue(),
                        filename=filename,
                        caption=message.caption or "",
                    )
                except AuthError:
                    await message.answer("MAX session invalid. Send /start to re-authorize.")
                return

            text = message.text
            if not text:
                return
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
        text = message.text
        if not text:
            return
        await message.answer("Send /start to sync chats or /resync [max_chat_id] to rebuild topics.")
