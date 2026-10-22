"""Outbound reply wire schemas (spec §17, §30)."""

from __future__ import annotations

from pydantic import Field

from app.schemas.base import CamelModel
from app.schemas.conversation import ConversationOut


class ReplyPreview(CamelModel):
    """What would be sent, and every reason it would be refused."""

    text: str
    can_send: bool
    problems: list[str] = Field(default_factory=list)


class SendResult(CamelModel):
    external_message_id: str
    text: str
    conversation: ConversationOut


class UsageOut(CamelModel):
    per_platform_per_hour: int
    daily_approved_ceiling: int
    sent_last_hour: dict[str, int] = Field(default_factory=dict)
    sent_today: int = 0
