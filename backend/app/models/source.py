"""What each discovery connector searches for.

Discord and Telegram bots read the communities they were added to, so they
need no settings here. Reddit, YouTube and the Telegram account search public
content by keyword, and the operator edits those terms from the Platforms
screen -- one row per platform, ``settings`` shaped per platform.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.types import UtcDateTime


class PlatformSource(Base):
    __tablename__ = "platform_sources"

    platform: Mapped[str] = mapped_column(String(32), primary_key=True)
    settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
