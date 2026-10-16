"""Column types shared by the models.

SQLite has no timezone-aware timestamp type: a tz-aware datetime goes in and a
naive one comes back. Serialised naive, ``postedAt`` reaches the browser without
an offset, and ``new Date(...)`` reads it as *local* time -- so every timestamp
in the Inbox silently shifts by the viewer's UTC offset.

``UtcDateTime`` closes that: everything is normalised to UTC on the way in and
re-tagged as UTC on the way out, on every dialect.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator):
    """A DateTime that is always tz-aware UTC in Python."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:  # noqa: ANN001
        if value is None:
            return None
        if value.tzinfo is None:
            # A naive value from a connector is documented as UTC.
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:  # noqa: ANN001
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
