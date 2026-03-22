from enum import StrEnum

from pydantic import BaseModel


class AuditEventType(StrEnum):
    BINDING_CREATED = "binding_created"
    BINDING_REAUTH_REQUIRED = "binding_reauth_required"
    BINDING_DISABLED = "binding_disabled"
    TOPIC_CREATED = "topic_created"
    TOPIC_RESTORED = "topic_restored"
    DELIVERY_SUCCESS = "delivery_success"
    DELIVERY_FAILED = "delivery_failed"
    SESSION_EXPIRED = "session_expired"
    UNKNOWN_ERROR = "unknown_error"


class SyncCursor(BaseModel):
    """Cursor for tracking last synced position per max_chat."""

    max_chat_id: str
    binding_telegram_user_id: int
    last_max_message_id: str
    updated_at: int  # Unix timestamp


class AuditEvent(BaseModel):
    """Audit log entry."""

    id: int | None
    telegram_user_id: int
    event_type: AuditEventType
    detail: str
    created_at: int  # Unix timestamp
