"""Unit tests for shared MAX media group selection."""

from __future__ import annotations

from src.application.routing.media import collect_media_group_items


def test_collect_media_group_items_returns_album_elements() -> None:
    items = collect_media_group_items(
        {
            "media": [
                {"type": "photo", "url": "https://example.com/1.jpg", "file_name": None},
                {"type": "image", "url": "https://example.com/2.jpg", "file_name": None},
                {"type": "video", "url": "https://example.com/3.mp4", "file_name": None},
            ]
        }
    )

    assert items == [
        {"type": "photo", "url": "https://example.com/1.jpg", "file_name": "photo.jpg"},
        {"type": "photo", "url": "https://example.com/2.jpg", "file_name": "photo.jpg"},
        {"type": "video", "url": "https://example.com/3.mp4", "file_name": "video.mp4"},
    ]


def test_collect_media_group_items_skips_single_media_message() -> None:
    items = collect_media_group_items(
        {"media": [{"type": "photo", "url": "https://example.com/1.jpg", "file_name": None}]}
    )

    assert items == []


def test_collect_media_group_items_skips_message_without_media_list() -> None:
    items = collect_media_group_items({"type": "photo", "media_url": "https://example.com/1.jpg"})

    assert items == []


def test_collect_media_group_items_skips_unresolved_media() -> None:
    items = collect_media_group_items(
        {
            "media": [
                {"type": "photo", "url": "https://example.com/1.jpg", "file_name": None},
                {"type": "video", "url": None, "file_name": "video.mp4"},
            ]
        }
    )

    assert items == []


def test_collect_media_group_items_skips_documents_mixed_with_photos() -> None:
    items = collect_media_group_items(
        {
            "media": [
                {"type": "photo", "url": "https://example.com/1.jpg", "file_name": None},
                {"type": "document", "url": "https://example.com/report.pdf", "file_name": "r.pdf"},
            ]
        }
    )

    assert items == []


def test_collect_media_group_items_skips_audio_album() -> None:
    items = collect_media_group_items(
        {
            "media": [
                {"type": "audio", "url": "https://example.com/1.mp3", "file_name": "1.mp3"},
                {"type": "audio", "url": "https://example.com/2.mp3", "file_name": "2.mp3"},
            ]
        }
    )

    assert items == []
