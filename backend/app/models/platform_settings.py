"""What each discovery platform searches for, editable from the Platforms page.

Credentials are not here -- they stay in the server environment (spec §29).
This holds only the non-secret part: search terms, and the subreddits,
YouTube channels or Telegram chats to watch.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.types import UtcDateTime

# Searches that find people looking for a free prediction game without
# pulling in gambling chatter. Real-money talk is flagged by scoring anyway.
DEFAULT_QUERIES = [
    "free prediction game",
    "sports prediction app",
    "free sports predictions",
    "prediction league friends",
    "free fantasy football game",
]

DEFAULTS: dict[str, dict] = {
    "reddit": {"queries": DEFAULT_QUERIES, "subreddits": []},
    "youtube": {"queries": DEFAULT_QUERIES[:3], "channel_ids": []},
    "telegram_account": {"queries": ["sports predictions", "football tips free"], "chats": []},
}


class PlatformSettings(Base):
    __tablename__ = "platform_settings"

    platform: Mapped[str] = mapped_column(String(32), primary_key=True)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
