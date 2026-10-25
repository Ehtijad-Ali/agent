"""Backlink audit results (one row per URL checked by a backlink-audit agent).

A run replaces the agent's previous results rather than appending to them: the
question an operator asks is "what is the state of my backlinks now", and a
history of every past run would bury that answer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.types import UtcDateTime

# What a check can conclude. "nofollow" covers rel=nofollow, sponsored and ugc,
# and a page-level robots nofollow -- all of them stop the link passing value.
BACKLINK_RESULTS: tuple[str, ...] = ("dofollow", "nofollow", "not_found", "error")


class BacklinkCheck(Base):
    __tablename__ = "backlink_checks"
    __table_args__ = (Index("ix_backlink_checks_agent", "agent_id"),)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # Row in the source sheet (1-based), so a result can be matched back to it.
    row: Mapped[int] = mapped_column(Integer, nullable=False)
    page_url: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    # The rel attribute as found, e.g. "nofollow noopener". Empty for dofollow.
    rel: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    link_href: Mapped[str] = mapped_column(Text, nullable=False, default="")
    anchor_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    checked_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
