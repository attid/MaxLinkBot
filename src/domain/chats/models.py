from enum import StrEnum

from pydantic import BaseModel


class ChatType(StrEnum):
    PERSONAL = "personal"


class MaxChat(BaseModel):
    """A personal MAX chat belonging to a binding."""

    max_chat_id: str
    binding_telegram_user_id: int
    title: str
    chat_type: ChatType = ChatType.PERSONAL
