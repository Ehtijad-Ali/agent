"""Insights wire schemas (spec §26).

These exist because the frontend aggregates over the whole conversation array
client-side. Once the list is paginated that aggregation is wrong, so the
server owns it -- see docs/frontend-api-mapping.md finding (b).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.base import CamelModel

Range = Literal["24h", "7d", "30d", "custom"]


class SeriesPoint(CamelModel):
    t: str
    v: int


class KpiSnapshot(CamelModel):
    """Mirrors ``kpiSnapshotSchema``. The deltas are real period-over-period
    comparisons; the mock used ``Math.random()``."""

    range: Range
    discovered: int
    relevant: int
    high_intent: int
    awaiting_review: int
    delta_discovered: float
    delta_relevant: float
    delta_high_intent: float
    delta_awaiting_review: float
    discovered_series: list[SeriesPoint] = Field(default_factory=list)
    relevant_series: list[SeriesPoint] = Field(default_factory=list)


class CountRow(CamelModel):
    label: str
    count: int


class BreakdownResponse(CamelModel):
    rows: list[CountRow] = Field(default_factory=list)


class FunnelResponse(CamelModel):
    discovered: int
    relevant: int
    awaiting: int
    approved: int
    rejected: int
    posted: int


class EngagementOut(CamelModel):
    """Brief §1: did the outreach actually work?

    ``clicks`` counts humans only. Discord and Telegram both fetch a link the
    moment it is posted to build a preview, so counting every hit would show a
    100% click-through rate on messages nobody opened. Those hits are reported
    separately as ``bot_hits`` rather than discarded, so the filtering is
    auditable.
    """

    window_hours: int
    replies_sent: int
    clicks: int
    unique_clicks: int
    bot_hits: int
    conversations_clicked: int
    click_through_rate: float
    clicks_by_platform: dict[str, int] = Field(default_factory=dict)
    replies_by_platform: dict[str, int] = Field(default_factory=dict)
