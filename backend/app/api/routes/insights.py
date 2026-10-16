"""Insights endpoints (spec §26).

The server owns aggregation. The frontend used to compute KPIs and charts by
folding over the entire conversation array, which silently becomes "stats for
the first page" the moment the list is paginated -- see
docs/frontend-api-mapping.md finding (b). These endpoints exist to replace that.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Conversation
from app.schemas.insights import (
    BreakdownResponse,
    CountRow,
    EngagementOut,
    FunnelResponse,
    KpiSnapshot,
    SeriesPoint,
)
from app.schemas.agent import RefinementIndex
from app.services.refinement_service import compute as compute_refinement
from app.services.tracking_service import engagement as engagement_stats

router = APIRouter(prefix="/insights", tags=["insights"])

RangeKey = Literal["24h", "7d", "30d"]

_WINDOWS: dict[str, timedelta] = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}

# "Relevant" is anything the engine did not rule out. It is the complement of
# not_relevant rather than a score threshold, so it stays consistent if the
# thresholds are retuned.
_RELEVANT_INTENTS = ("high", "medium", "low")


def _count(db: Session, *conditions) -> int:
    stmt = select(func.count(Conversation.id))
    for condition in conditions:
        stmt = stmt.where(condition)
    return db.execute(stmt).scalar_one()


def _delta(current: int, previous: int) -> float:
    """Percent change against the preceding window of equal length.

    A jump from zero has no defined percentage, so it reports 100% when
    something appeared and 0% when both periods were empty -- never a division
    by zero, and never the mock's ``Math.random()``.
    """
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100, 1)


def _series(
    db: Session, since: datetime, buckets: int, step: timedelta, *conditions
) -> list[SeriesPoint]:
    """Bucketed counts, computed in Python.

    Date bucketing in SQL is dialect-specific (``strftime`` on SQLite,
    ``date_trunc`` on Postgres); at these row counts one pass over the
    timestamps is cheaper than making the query portable.
    """
    stmt = select(Conversation.posted_at).where(Conversation.posted_at >= since)
    for condition in conditions:
        stmt = stmt.where(condition)
    stamps = db.execute(stmt).scalars().all()

    edges = [since + step * i for i in range(buckets + 1)]
    counts = [0] * buckets
    for stamp in stamps:
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        for i in range(buckets):
            if edges[i] <= stamp < edges[i + 1]:
                counts[i] += 1
                break
    return [
        SeriesPoint(t=edges[i].isoformat(), v=counts[i]) for i in range(buckets)
    ]


@router.get("/overview", response_model=KpiSnapshot)
def overview(
    db: Session = Depends(get_db), range: RangeKey = Query("7d")
) -> KpiSnapshot:
    window = _WINDOWS[range]
    now = datetime.now(UTC)
    since = now - window
    prev_since = since - window

    in_window = Conversation.posted_at >= since
    in_previous = (Conversation.posted_at >= prev_since) & (
        Conversation.posted_at < since
    )
    relevant = Conversation.intent.in_(_RELEVANT_INTENTS)
    high = Conversation.intent == "high"
    awaiting = Conversation.status.in_(("new", "awaiting"))

    buckets = 24 if range == "24h" else (7 if range == "7d" else 30)
    step = window / buckets

    return KpiSnapshot(
        range=range,
        discovered=_count(db, in_window),
        relevant=_count(db, in_window, relevant),
        high_intent=_count(db, in_window, high),
        awaiting_review=_count(db, in_window, awaiting),
        delta_discovered=_delta(_count(db, in_window), _count(db, in_previous)),
        delta_relevant=_delta(
            _count(db, in_window, relevant), _count(db, in_previous, relevant)
        ),
        delta_high_intent=_delta(
            _count(db, in_window, high), _count(db, in_previous, high)
        ),
        delta_awaiting_review=_delta(
            _count(db, in_window, awaiting), _count(db, in_previous, awaiting)
        ),
        discovered_series=_series(db, since, buckets, step),
        relevant_series=_series(db, since, buckets, step, relevant),
    )


def _breakdown(db: Session, column, since: datetime | None) -> BreakdownResponse:
    stmt = select(column, func.count(Conversation.id)).group_by(column)
    if since is not None:
        stmt = stmt.where(Conversation.posted_at >= since)
    stmt = stmt.order_by(func.count(Conversation.id).desc())
    return BreakdownResponse(
        rows=[CountRow(label=str(label), count=count) for label, count in db.execute(stmt)]
    )


@router.get("/platforms", response_model=BreakdownResponse)
def by_platform(
    db: Session = Depends(get_db), range: RangeKey = Query("7d")
) -> BreakdownResponse:
    return _breakdown(db, Conversation.platform, datetime.now(UTC) - _WINDOWS[range])


@router.get("/countries", response_model=BreakdownResponse)
def by_country(
    db: Session = Depends(get_db), range: RangeKey = Query("7d")
) -> BreakdownResponse:
    return _breakdown(db, Conversation.country, datetime.now(UTC) - _WINDOWS[range])


@router.get("/keywords", response_model=BreakdownResponse)
def by_keyword(
    db: Session = Depends(get_db), range: RangeKey = Query("7d")
) -> BreakdownResponse:
    """Counted in Python because matched keywords are a JSON array.

    Postgres could unnest it, SQLite cannot, and the portable option is one
    pass over the rows in the window.
    """
    since = datetime.now(UTC) - _WINDOWS[range]
    rows = db.execute(
        select(Conversation.matched_keywords).where(Conversation.posted_at >= since)
    ).scalars()

    tally: dict[str, int] = {}
    for keywords in rows:
        for keyword in keywords or []:
            tally[keyword] = tally.get(keyword, 0) + 1

    ordered = sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))
    return BreakdownResponse(rows=[CountRow(label=k, count=v) for k, v in ordered])


@router.get("/funnel", response_model=FunnelResponse)
def funnel(db: Session = Depends(get_db), range: RangeKey = Query("7d")) -> FunnelResponse:
    since = datetime.now(UTC) - _WINDOWS[range]
    in_window = Conversation.posted_at >= since
    return FunnelResponse(
        discovered=_count(db, in_window),
        relevant=_count(db, in_window, Conversation.intent.in_(_RELEVANT_INTENTS)),
        awaiting=_count(db, in_window, Conversation.status.in_(("new", "awaiting"))),
        approved=_count(db, in_window, Conversation.status == "approved"),
        rejected=_count(db, in_window, Conversation.status == "rejected"),
        posted=_count(db, in_window, Conversation.status == "manually_posted"),
    )


@router.get("/engagement", response_model=EngagementOut)
def engagement(
    db: Session = Depends(get_db), range: RangeKey = Query("7d")
) -> EngagementOut:
    """Replies sent versus links actually clicked (brief §1)."""
    hours = int(_WINDOWS[range].total_seconds() // 3600)
    return EngagementOut.model_validate(engagement_stats(db, hours))


@router.get("/refinement", response_model=RefinementIndex)
def refinement(
    db: Session = Depends(get_db), days: int = Query(30, ge=1, le=365)
) -> RefinementIndex:
    """System-wide Agent Refinement Index (brief §8).

    Per-agent figures live at /api/agents/{id}/refinement.
    """
    return RefinementIndex.model_validate(compute_refinement(db, None, days))
