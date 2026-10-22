"""Shared selection of MAX media items that Telegram can render as one media group."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from src.application.ports.telegram_client import TelegramMediaItem

TELEGRAM_MEDIA_TYPE_BY_MAX_TYPE: dict[str, str] = {
    "photo": "photo",
    "image": "photo",
    "picture": "photo",
    "video": "video",
    "document": "document",
    "file": "document",
}

# Bot API groups documents only with documents; photos and videos may be mixed.
TELEGRAM_MEDIA_FAMILY_BY_TYPE: dict[str, str] = {
    "photo": "visual",
    "video": "visual",
    "document": "document",
}


def collect_media_group_items(msg: Mapping[str, Any]) -> list[TelegramMediaItem]:
    """Return media group items for a MAX message.

    The list is returned only when the message carries at least two renderable
    media items that Telegram accepts inside one album. Any other shape (single
    media, audio/voice, unresolved URLs, documents mixed with photos) returns an
    empty list so the caller keeps the existing single-media delivery path.
    """
    raw_media = msg.get("media")
    if not isinstance(raw_media, list):
        return []

    items: list[TelegramMediaItem] = []
    for raw_item in cast(list[Any], raw_media):
        if not isinstance(raw_item, Mapping):
            return []
        item = cast(Mapping[str, Any], raw_item)
        item_type = TELEGRAM_MEDIA_TYPE_BY_MAX_TYPE.get(str(item.get("type") or "").strip().lower())
        url = str(item.get("url") or "").strip()
        if item_type is None or not url:
            return []
        file_name = str(item.get("file_name") or "").strip()
        items.append(
            TelegramMediaItem(
                type=item_type,
                url=url,
                file_name=file_name or _default_file_name(item_type),
            )
        )
    if len(items) < 2 or len(_media_families(items)) > 1:
        return []
    return items


def _media_families(items: list[TelegramMediaItem]) -> set[str]:
    return {TELEGRAM_MEDIA_FAMILY_BY_TYPE.get(item["type"], item["type"]) for item in items}


def _default_file_name(media_type: str) -> str:
    if media_type == "video":
        return "video.mp4"
    if media_type == "document":
        return "file.bin"
    return "photo.jpg"
