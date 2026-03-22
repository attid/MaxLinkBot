from enum import StrEnum

from pydantic import BaseModel


class Direction(StrEnum):
    MAX_TO_TELEGRAM = "max_to_telegram"
    TELEGRAM_TO_MAX = "telegram_to_max"


class MessageLink(BaseModel):
    """Record of a delivered message pair."""

    max_message_id: str | None
    telegram_message_id: int | None
    telegram_user_id: int  # owner of this link
    max_chat_id: str
    direction: Direction
    delivered_at: int  # Unix timestamp
