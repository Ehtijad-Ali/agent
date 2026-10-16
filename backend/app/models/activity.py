"""Audit log (spec §27).

Written server-side only. ``logActivity`` was removed from the client surface
deliberately -- an audit trail the client can forge is not an audit trail. See
docs/frontend-api-mapping.md operation 12.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.types import UtcDateTime

# The frontend's Activity table renders this verbatim for system-level rows
# with no resource. An empty string would render a blank cell instead.
NO_ITEM = "—"


class ActivityEntry(Base):
    __tablename__ = "activity_entries"
    __table_args__ = (Index("ix_activity_timestamp", "timestamp"),)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    timestamp: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    actor: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    item: Mapped[str] = mapped_column(Text, nullable=False, default=NO_ITEM)
    before: Mapped[str | None] = mapped_column(Text, nullable=True)
    after: Mapped[str | None] = mapped_column(Text, nullable=True)
