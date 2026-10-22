"""Tracking links and click events.

The brief asks for analytics on "how many users clicked on our own tracking
links". That cannot be answered by looking at the reply we sent -- a sent
message proves only that we spoke, not that anyone listened. So every outbound
reply carries a short link unique to that conversation, and a hit on it is
recorded here.

One link per conversation, not per send: the redirect must keep working for as
long as the message exists, and reusing the slug makes a click attributable to
exactly one reply.

On privacy: no IP address is stored. The project pseudonymises authors at the
connector boundary, and keeping raw IPs here would undo that for the one group
of people we have least right to profile -- those who merely clicked. A salted
hash is kept instead, purely so repeat hits from one device can be collapsed
into a unique count.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.types import UtcDateTime


class TrackingLink(Base):
    __tablename__ = "tracking_links"
    __table_args__ = (Index("ix_tracking_links_conversation", "conversation_id"),)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # Short, URL-safe, and unique -- this is the whole public surface.
    slug: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    conversation_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )


class LinkClick(Base):
    __tablename__ = "link_clicks"
    __table_args__ = (
        Index("ix_link_clicks_link", "link_id"),
        Index("ix_link_clicks_at", "clicked_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    link_id: Mapped[str] = mapped_column(String(36), nullable=False)
    clicked_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    # Salted hash only -- never the address itself. See the module docstring.
    visitor_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    referer: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Platforms fetch links to build previews. Those hits are recorded but kept
    # out of the headline numbers, or every send would look like a click.
    is_bot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
