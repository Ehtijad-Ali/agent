"""Outbound reply ledger (spec §17, §30).

One row per message actually posted to a platform. It exists for two reasons
that cannot be answered from the conversations table:

1. **"One reply per person, ever"** is a non-negotiable rule. Enforcing it needs
   a record keyed on the author, and the author is only ever a pseudonym -- so
   the unique constraint on (platform, author_pseudonym) *is* the rule. A second
   reply to the same person fails at the database, not just in a check that
   could be bypassed.
2. **Rate caps** (per platform per hour, daily ceiling) are counted from real
   sends. Counting approvals instead would let a burst of approvals followed by
   sends sail past the cap.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.types import UtcDateTime


class ReplySend(Base):
    __tablename__ = "reply_sends"
    __table_args__ = (
        UniqueConstraint(
            "platform", "author_pseudonym", name="uq_reply_once_per_author"
        ),
        Index("ix_reply_sends_sent_at", "sent_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    conversation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    author_pseudonym: Mapped[str] = mapped_column(String(64), nullable=False)
    # The id the platform gave the message we posted, for later reference.
    external_message_id: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False, default="you")
    sent_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
