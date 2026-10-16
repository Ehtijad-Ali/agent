"""Activity log endpoints (spec §27).

Read and export only. There is no write endpoint: ``logActivity`` was removed
from the client surface because an audit trail the client can forge is not an
audit trail (docs/frontend-api-mapping.md operation 12). Rows are written by
the server as a side effect of the action being audited.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import ActivityEntry
from app.schemas.activity import ActivityEntryOut, ActivityPage

router = APIRouter(prefix="/activity", tags=["activity"])


def _filtered(
    stmt,
    actor: str | None,
    action: str | None,
    search: str | None,
    agent: str | None = None,
    platform: str | None = None,
    after: datetime | None = None,
    before: datetime | None = None,
):
    """Brief §7: filter by agent, platform, type and date.

    ``agent`` and ``platform`` match against ``item``, which is where the
    subject of each entry is recorded ("<agent name> / <city>", "<community> /
    <pseudonym>"). That is a substring match rather than a foreign key: the log
    is deliberately denormalised so a row still reads correctly after the agent
    or conversation it refers to has been deleted.
    """
    if actor:
        stmt = stmt.where(ActivityEntry.actor == actor)
    if action:
        stmt = stmt.where(ActivityEntry.action == action)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            or_(ActivityEntry.item.ilike(like), ActivityEntry.action.ilike(like))
        )
    if agent:
        stmt = stmt.where(ActivityEntry.item.ilike(f"%{agent}%"))
    if platform:
        stmt = stmt.where(
            or_(
                ActivityEntry.item.ilike(f"%{platform}%"),
                ActivityEntry.after.ilike(f"%{platform}%"),
            )
        )
    if after is not None:
        stmt = stmt.where(ActivityEntry.timestamp >= after)
    if before is not None:
        stmt = stmt.where(ActivityEntry.timestamp <= before)
    return stmt


@router.get("", response_model=ActivityPage)
def list_activity(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500, alias="perPage"),
    actor: str | None = Query(None),
    action: str | None = Query(None),
    search: str | None = Query(None),
    agent: str | None = Query(None),
    platform: str | None = Query(None),
    after: datetime | None = Query(None),
    before: datetime | None = Query(None),
) -> ActivityPage:
    extra = {"agent": agent, "platform": platform, "after": after, "before": before}
    total = db.execute(
        _filtered(select(func.count(ActivityEntry.id)), actor, action, search, **extra)
    ).scalar_one()

    rows = (
        db.execute(
            _filtered(select(ActivityEntry), actor, action, search, **extra)
            .order_by(ActivityEntry.timestamp.desc(), ActivityEntry.id)
            .limit(per_page)
            .offset((page - 1) * per_page)
        )
        .scalars()
        .all()
    )

    return ActivityPage(
        items=[ActivityEntryOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/export")
def export_activity(
    db: Session = Depends(get_db),
    actor: str | None = Query(None),
    action: str | None = Query(None),
    search: str | None = Query(None),
    agent: str | None = Query(None),
    platform: str | None = Query(None),
    after: datetime | None = Query(None),
    before: datetime | None = Query(None),
) -> StreamingResponse:
    """CSV export of the filtered log (spec §27)."""
    rows = (
        db.execute(
            _filtered(
                select(ActivityEntry),
                actor,
                action,
                search,
                agent=agent,
                platform=platform,
                after=after,
                before=before,
            ).order_by(
                ActivityEntry.timestamp.desc()
            )
        )
        .scalars()
        .all()
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["timestamp", "actor", "action", "item", "before", "after"])
    for row in rows:
        writer.writerow(
            [
                row.timestamp.isoformat(),
                row.actor,
                row.action,
                row.item,
                row.before or "",
                row.after or "",
            ]
        )
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="signal-activity.csv"'},
    )
