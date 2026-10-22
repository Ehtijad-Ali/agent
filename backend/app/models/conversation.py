"""Conversation table -- one discovered message, scored (spec §4, §10).

The unique constraint on (platform, external_id) is what makes ingestion
idempotent: polling the same channel every 60s re-sees the same messages, and
re-inserting them would otherwise fill the Inbox with duplicates.

Note what is *not* here: no author handle, no user id, no token. The connector
hashes the handle before the message reaches this layer, and that boundary is
the whole point -- see ``PlatformConnector`` in app/integrations/base.py.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.types import UtcDateTime


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("platform", "external_id", name="uq_conversation_external"),
        Index("ix_conversations_status", "status"),
        Index("ix_conversations_posted_at", "posted_at"),
        Index("ix_conversations_score", "score"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    # --- provenance ---
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    community: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_pseudonym: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    posted_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="US")
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")

    # --- scoring (spec §13) ---
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    intent: Mapped[str] = mapped_column(String(16), nullable=False, default="not_relevant")
    confidence: Mapped[str] = mapped_column(String(8), nullable=False, default="low")
    matched_keywords: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    contributions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    risk_flags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # --- triage (spec §18) ---
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="new")
    reply_variants: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    selected_variant: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edited_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    history: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=_now, onupdate=_now
    )
