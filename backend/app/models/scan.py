"""Scan runs (spec §23).

``POST /api/scans/run`` returns immediately with an id; the work happens in the
background and the client polls. A scan row is the only place a partial failure
is visible -- one platform erroring must not look like "no new leads".
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.types import UtcDateTime


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    trigger: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    started_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime(), nullable=True
    )
    discovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    examined: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Per-platform outcome, so one dead connector is distinguishable from an
    # empty channel.
    platforms: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
