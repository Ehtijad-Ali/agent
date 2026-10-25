"""Endpoints for n8n workflows (machine-to-machine).

A workflow has no browser session, so these authenticate with the shared
N8N_WEBHOOK_SECRET in the ``X-Signal-Secret`` header instead. They expose only
what an automation needs: start a scan, and read leads. Nothing here approves,
edits or sends -- those stay with a signed-in human (spec §18).
"""

from __future__ import annotations

import hmac
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models import Conversation, ScanRun
from app.services.events_service import lead_payload


def require_secret(x_signal_secret: str = Header(default="")) -> None:
    expected = get_settings().n8n_webhook_secret
    if not expected:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Automation is disabled: set N8N_WEBHOOK_SECRET on the server.",
        )
    if not hmac.compare_digest(x_signal_secret.encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or wrong X-Signal-Secret.")


router = APIRouter(prefix="/automation", tags=["automation"], dependencies=[Depends(require_secret)])


@router.post("/scan", status_code=status.HTTP_202_ACCEPTED)
def start_scan(background: BackgroundTasks, db: Session = Depends(get_db)) -> dict:
    """Start a scan, e.g. from an n8n Schedule node. Poll /api/scans/{id}
    with a session, or wait for the scan.completed event."""
    from app.api.routes.scans import _execute

    scan = ScanRun(status="running", trigger="automation")
    db.add(scan)
    db.commit()
    db.refresh(scan)
    background.add_task(_execute, scan.id)
    return {"scanId": scan.id, "status": scan.status}


@router.get("/leads")
def leads(
    db: Session = Depends(get_db),
    min_score: int = Query(60, ge=0, le=100, alias="minScore"),
    hours: int = Query(24, ge=1, le=24 * 30),
    lead_status: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """Recent leads above a score, newest first -- for digests and alerts."""
    since = datetime.now(UTC) - timedelta(hours=hours)
    stmt = select(Conversation).where(
        Conversation.score >= min_score, Conversation.posted_at >= since
    )
    if lead_status:
        stmt = stmt.where(Conversation.status == lead_status)
    rows = db.execute(stmt.order_by(Conversation.posted_at.desc()).limit(limit)).scalars().all()
    return {"count": len(rows), "leads": [lead_payload(r) for r in rows]}
