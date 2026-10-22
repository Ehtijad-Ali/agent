"""Versioned tuning config (spec §4).

Every PUT /api/tuning writes a new row rather than mutating one, so a scoring
change is attributable and reversible. The highest version is active.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.types import UtcDateTime


class ConfigurationVersion(Base):
    __tablename__ = "configuration_versions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, autoincrement=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
