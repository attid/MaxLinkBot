from enum import StrEnum

from pydantic import BaseModel


class BindingStatus(StrEnum):
    ACTIVE = "active"
    REAUTH_REQUIRED = "reauth_required"
    DISABLED = "disabled"


class Binding(BaseModel):
    """Binding links a Telegram user to a MAX session."""

    telegram_user_id: int
    max_session_data: str = ""  # kept for DB migration compat; session data persists to disk
    status: BindingStatus = BindingStatus.ACTIVE
    created_at: int  # Unix timestamp
    updated_at: int  # Unix timestamp

    def can_route(self) -> bool:
        return self.status == BindingStatus.ACTIVE

    def requires_reauth(self) -> bool:
        return self.status == BindingStatus.REAUTH_REQUIRED
