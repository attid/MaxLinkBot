"""Port for the Telegram client (aiogram)."""

from abc import ABC, abstractmethod


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
    async def create_topic(self, chat_id: int, title: str) -> int:
        """Create a new topic in a chat.

        Returns:
            The new topic's Telegram topic ID.
        """
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
