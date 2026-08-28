"""Application service for per-topic inbound synchronization state."""

from src.application.ports.repositories import TelegramTopicRepository


class TopicMuteService:
    def __init__(self, topic_repo: TelegramTopicRepository) -> None:
        self._topic_repo = topic_repo

    async def mute(self, telegram_user_id: int, telegram_topic_id: int) -> bool:
        return await self._topic_repo.set_inbound_enabled(
            telegram_user_id,
            telegram_topic_id,
            False,
        )

    async def unmute(self, telegram_user_id: int, telegram_topic_id: int) -> bool:
        return await self._topic_repo.set_inbound_enabled(
            telegram_user_id,
            telegram_topic_id,
            True,
        )
