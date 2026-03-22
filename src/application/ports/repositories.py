"""Repository ports for the application layer."""

from abc import ABC, abstractmethod

from src.domain.bindings.models import Binding, BindingStatus
from src.domain.chats.models import MaxChat
from src.domain.chats.topic import TelegramTopic
from src.domain.messages.models import MessageLink
from src.domain.sync.models import AuditEvent, AuditEventType, SyncCursor


class BindingRepository(ABC):
    @abstractmethod
    async def get(self, telegram_user_id: int) -> Binding | None: ...

    @abstractmethod
    async def find_active(self) -> list[Binding]: ...

    @abstractmethod
    async def save(self, binding: Binding) -> None: ...

    @abstractmethod
    async def update_status(self, telegram_user_id: int, status: BindingStatus) -> None: ...


class MaxChatRepository(ABC):
    @abstractmethod
    async def get(self, max_chat_id: str) -> MaxChat | None: ...

    @abstractmethod
    async def find_by_binding(self, binding_telegram_user_id: int) -> list[MaxChat]: ...

    @abstractmethod
    async def save(self, chat: MaxChat) -> None: ...


class TelegramTopicRepository(ABC):
    @abstractmethod
    async def get_by_user_and_chat(
        self, telegram_user_id: int, max_chat_id: str
    ) -> TelegramTopic | None: ...

    @abstractmethod
    async def get_by_user_and_topic(
        self, telegram_user_id: int, telegram_topic_id: int
    ) -> TelegramTopic | None: ...

    @abstractmethod
    async def find_by_user(self, telegram_user_id: int) -> list[TelegramTopic]: ...

    @abstractmethod
    async def save(self, topic: TelegramTopic) -> None: ...


class MessageLinkRepository(ABC):
    @abstractmethod
    async def save(self, link: MessageLink) -> None: ...

    @abstractmethod
    async def exists_max_message(self, max_message_id: str, max_chat_id: str) -> bool: ...


class SyncCursorRepository(ABC):
    @abstractmethod
    async def get(self, max_chat_id: str, binding_telegram_user_id: int) -> SyncCursor | None: ...

    @abstractmethod
    async def upsert(self, cursor: SyncCursor) -> None: ...


class AuditRepository(ABC):
    @abstractmethod
    async def log(
        self, telegram_user_id: int, event_type: AuditEventType, detail: str
    ) -> AuditEvent: ...

    @abstractmethod
    async def has_recent_event(
        self, telegram_user_id: int, event_type: AuditEventType, since: int
    ) -> bool: ...
