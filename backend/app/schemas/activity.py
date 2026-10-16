"""Activity log wire schemas (spec §27). Mirrors ``activityEntrySchema``."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.base import CamelModel


class ActivityEntryOut(CamelModel):
    id: str
    timestamp: datetime
    actor: str
    action: str
    item: str
    before: str | None = None
    after: str | None = None


class ActivityPage(CamelModel):
    items: list[ActivityEntryOut] = Field(default_factory=list)
    total: int
    page: int
    per_page: int
