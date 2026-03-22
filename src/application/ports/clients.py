"""Port for the MAX client (Pumax)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MaxClient(ABC):
    """Interface to MAX via Pumax. All Pumax interaction goes through this port."""

    @abstractmethod
    async def authenticate(self, credentials: dict[str, str]) -> str:
        """Authenticate and return serialized session data.

        Raises:
            AuthError: if credentials are invalid.
        """
        ...

    @abstractmethod
    async def restore_session(self, session_data: str) -> None:
        """Restore a session from serialized data.

        Raises:
            SessionExpiredError: if session cannot be restored.
        """
        ...

    @abstractmethod
    async def list_personal_chats(self) -> list[dict[str, Any]]:
        """Return list of personal chats for the current session.

        Returns:
            list of dicts with 'max_chat_id' and 'title'.
        """
        ...

    @abstractmethod
    async def get_messages(
        self, max_chat_id: str, since_message_id: str | None, limit: int
    ) -> list[dict[str, Any]]:
        """Fetch messages from a MAX chat.

        Args:
            max_chat_id: the chat to fetch from.
            since_message_id: fetch after this message (for cursor-based polling).
            limit: maximum number of messages.

        Returns:
            list of dicts with message data.
        """
        ...

    @abstractmethod
    async def send_message(self, max_chat_id: str, text: str) -> str:
        """Send a text message to a MAX chat.

        Returns:
            The sent message's MAX message ID.
        """
        ...

    @abstractmethod
    async def create_topic(self, title: str) -> str:
        """Create a new personal MAX chat and return its max_chat_id."""
        ...

    @abstractmethod
    async def is_session_valid(self) -> bool:
        """Check if the current session is still valid."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources."""
        ...
