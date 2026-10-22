"""Port for the Telegram client (aiogram)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import NotRequired, TypedDict


class TelegramMediaItem(TypedDict):
    """One media element of a Telegram media group.

    Attributes:
        type: Telegram media kind: ``photo``, ``video`` or ``document``.
        url: MAX download URL of the media element.
        file_name: File name used for document/video uploads.
    """

    type: str
    url: str
    file_name: NotRequired[str]


class TelegramClient(ABC):
    """Interface to Telegram via aiogram. All Telegram interaction goes through this port."""

    @abstractmethod
    async def send_text(self, chat_id: int, text: str) -> int:
        """Send a text message.

        Returns:
            The sent message's Telegram message ID.
        """
        ...

    @abstractmethod
    async def send_text_to_topic(self, chat_id: int, topic_id: int, text: str) -> int:
        """Send a text message to a specific topic.

        Returns:
            The sent message's Telegram message ID.
        """
        ...

    @abstractmethod
    async def send_photo_to_topic(
        self,
        chat_id: int,
        topic_id: int,
        photo_url: str,
        caption: str,
    ) -> int:
        """Send a photo to a specific topic."""
        ...

    @abstractmethod
    async def send_media_group_to_topic(
        self,
        chat_id: int,
        topic_id: int,
        media: Sequence[TelegramMediaItem],
        caption: str,
    ) -> int:
        """Send several MAX media elements as one Telegram album.

        Returns:
            The Telegram message ID of the first element of the album.
        """
        ...

    @abstractmethod
    async def send_audio_to_topic(
        self,
        chat_id: int,
        topic_id: int,
        audio_url: str,
        caption: str,
    ) -> int:
        """Send an audio file to a specific topic."""
        ...

    @abstractmethod
    async def send_video_to_topic(
        self,
        chat_id: int,
        topic_id: int,
        video_url: str,
        caption: str,
    ) -> int:
        """Send a video file to a specific topic."""
        ...

    @abstractmethod
    async def create_topic(self, chat_id: int, title: str) -> int:
        """Create a new topic in a chat.

        Returns:
            The new topic's Telegram topic ID.
        """
        ...

    @abstractmethod
    async def send_document_to_topic(
        self,
        chat_id: int,
        topic_id: int,
        document_url: str,
        filename: str,
        caption: str,
    ) -> int:
        """Send a generic document/file to a specific topic."""
        ...

    @abstractmethod
    async def topic_exists(self, chat_id: int, topic_id: int) -> bool:
        """Check whether a topic is still writable."""
        ...

    @abstractmethod
    async def delete_topic(self, chat_id: int, topic_id: int) -> None:
        """Delete a topic from a chat."""
        ...

    @abstractmethod
    async def send_photo(self, chat_id: int, image_bytes: bytes) -> int:
        """Send a photo from bytes.

        Returns:
            The sent message's Telegram message ID.
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources."""
        ...
