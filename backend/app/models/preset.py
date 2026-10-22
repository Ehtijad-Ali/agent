"""Saved tuning presets (brief §5).

``presetSchema`` already existed in the frontend types but had no backend and
no storage, so presets could not survive a reload. A preset is a named,
complete TuningConfig snapshot -- not a diff -- because the value of "go back
to how it was on Tuesday" depends on getting every field back, including the
ones that were not being edited at the time.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.types import UtcDateTime


class TuningPreset(Base):
    __tablename__ = "tuning_presets"
    __table_args__ = (UniqueConstraint("name", name="uq_preset_name"),)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
