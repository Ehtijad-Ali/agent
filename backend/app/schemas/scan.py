"""Scan wire schemas (spec §23)."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.base import CamelModel


class PlatformOutcome(CamelModel):
    platform: str
    examined: int = 0
    discovered: int = 0
    error: str | None = None


class ScanOut(CamelModel):
    scan_id: str
    status: str
    trigger: str
    started_at: datetime
    finished_at: datetime | None = None
    discovered: int = 0
    examined: int = 0
    error: str | None = None
    platforms: list[PlatformOutcome] = Field(default_factory=list)
