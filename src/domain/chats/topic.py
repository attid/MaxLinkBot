from pydantic import BaseModel


class TelegramTopic(BaseModel):
    """A Telegram topic within a user's private chat with the bot."""

    telegram_topic_id: int
    telegram_user_id: int
    max_chat_id: str  # references MaxChat.max_chat_id
