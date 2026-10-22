"""Backlink audits run by a ``backlink_audit`` agent.

One audit row per agent -- the latest run. Starting a new audit replaces the
previous results, because the CSV is meant to be pasted back into the sheet
and only the current state of each page is useful there.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.types import UtcDateTime

BACKLINK_RESULTS: tuple[str, ...] = ("dofollow", "nofollow", "not_found", "error")


class BacklinkAudit(Base):
    __tablename__ = "backlink_audits"

    agent_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    id: Mapped[str] = mapped_column(
        String(36), nullable=False, default=lambda: str(uuid.uuid4())
    )
    # running | completed | failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime(), nullable=True, default=lambda: datetime.now(UTC)
    )
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)


class BacklinkCheck(Base):
    __tablename__ = "backlink_checks"
    __table_args__ = (Index("ix_backlink_checks_agent_row", "agent_id", "row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("backlink_audits.agent_id", ondelete="CASCADE"),
        nullable=False,
    )
    row: Mapped[int] = mapped_column(Integer, nullable=False)
    page_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    rel: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    link_href: Mapped[str] = mapped_column(Text, nullable=False, default="")
    anchor_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    checked_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
