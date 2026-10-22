"""Conversation wire schemas.

Mirrors ``conversationSchema`` in src/lib/types.ts field for field. The enum
strings are exact and must not be renamed -- ``not_relevant``,
``manually_posted``, ``real_money``, ``negative_keyword``, ``off_topic`` are
rendered and compared by the frontend.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.base import CamelModel

Platform = Literal["discord", "telegram", "facebook", "reddit", "youtube"]
Intent = Literal["high", "medium", "low", "not_relevant"]
Confidence = Literal["low", "medium", "high"]
Status = Literal[
    "new",
    "awaiting",
    "approved",
    "rejected",
    "snoozed",
    "manually_posted",
    "blocked",
    # Posted by the bot through /api/replies/{id}/send. Distinct from
    # manually_posted, which means a human posted it by hand -- collapsing the
    # two would make the audit log claim a person did what the bot did.
    "sent",
]
RiskFlag = Literal["underage", "real_money", "spam", "negative_keyword", "off_topic"]

# Once a reply is posted it cannot be unposted, and the one-reply-per-person
# rule means the author is finished. Moving a row out of "sent" would make the
# Inbox offer a Send button for a conversation already replied to, so the
# transition is refused server-side rather than only hidden in the UI.
TERMINAL_STATUSES: frozenset[str] = frozenset({"sent"})

# Spec §18. Each verb is its own endpoint rather than a generic PATCH, so the
# audit log records intent and not just a field change.
#
# "reset" and "mark-awaiting" are not in §18. They exist because the bulk-action
# bar and Triage both offer undo, which has to be able to restore a row to
# whatever it was before -- including "new". Without them an undone approval
# would have nowhere to go.
ACTION_TO_STATUS: dict[str, Status] = {
    "approve": "approved",
    "reject": "rejected",
    "snooze": "snoozed",
    "mark-posted": "manually_posted",
    "block": "blocked",
    "reset": "new",
    "mark-awaiting": "awaiting",
}


class ScoreContributionOut(CamelModel):
    rule_id: str
    label: str
    points: float


class ReplyVariantOut(CamelModel):
    tone: str
    text: str


class HistoryEntryOut(CamelModel):
    at: str
    actor: str
    action: str


class ConversationOut(CamelModel):
    id: str
    platform: Platform
    country: str
    community: str
    source_url: str | None = None
    author_pseudonym: str
    message: str
    posted_at: datetime
    language: str
    score: int = Field(ge=0, le=100)
    intent: Intent
    confidence: Confidence
    matched_keywords: list[str] = Field(default_factory=list)
    contributions: list[ScoreContributionOut] = Field(default_factory=list)
    summary: str
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    status: Status
    reply_variants: list[ReplyVariantOut] = Field(default_factory=list)
    selected_variant: int = 0
    edited_reply: str | None = None
    history: list[HistoryEntryOut] = Field(default_factory=list)


class ConversationPage(CamelModel):
    """Paginated list envelope (spec §5).

    Aggregates are NOT derived from this page -- Insights reads
    /api/insights/overview instead, or every KPI would silently become "stats
    for the first 20 rows" (docs/frontend-api-mapping.md finding b).
    """

    items: list[ConversationOut]
    total: int
    page: int
    per_page: int


class EditReplyRequest(CamelModel):
    edited_reply: str | None = None
    selected_variant: int | None = None


class BulkActionRequest(CamelModel):
    ids: list[str]
    action: str


class BulkActionResult(CamelModel):
    id: str
    ok: bool
    error: str | None = None


class BulkActionResponse(CamelModel):
    """Per-id results so a partial failure is visible rather than swallowed."""

    results: list[BulkActionResult]
    updated: int
