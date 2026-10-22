"""Scan endpoints (spec §23).

``POST /api/scans/run`` returns an id immediately and does the polling in a
background task, because a Discord fetch across several channels takes longer
than a request should block for. The caller polls ``GET /api/scans/{id}``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db, session_scope
from app.models import ScanRun
from app.schemas.scan import ScanOut
from app.services.ingestion_service import run_scan

router = APIRouter(prefix="/scans", tags=["scans"])
logger = logging.getLogger("signal.scans")


def _to_out(row: ScanRun) -> ScanOut:
    return ScanOut(
        scan_id=row.id,
        status=row.status,
        trigger=row.trigger,
        started_at=row.started_at,
        finished_at=row.finished_at,
        discovered=row.discovered,
        examined=row.examined,
        error=row.error,
        platforms=row.platforms or [],
    )


async def _execute(scan_id: str) -> None:
    """Run the scan on its own session.

    The request's session is closed by the time this runs, so the background
    task opens its own and reloads the row.
    """
    db = session_scope()
    try:
        scan = db.get(ScanRun, scan_id)
        if scan is None:
            logger.warning("Scan %s vanished before it ran", scan_id)
            return
        await run_scan(db, scan)
    except Exception as exc:  # noqa: BLE001 -- a failed scan must be recorded, not lost
        logger.exception("Scan %s failed", scan_id)
        db.rollback()
        scan = db.get(ScanRun, scan_id)
        if scan is not None:
            scan.status = "failed"
            scan.error = repr(exc)[:500]
            db.commit()
    finally:
        db.close()


@router.post("/run", response_model=ScanOut, status_code=status.HTTP_202_ACCEPTED)
def run(
    background: BackgroundTasks, db: Session = Depends(get_db)
) -> ScanOut:
    scan = ScanRun(status="running", trigger="manual")
    db.add(scan)
    db.commit()
    db.refresh(scan)

    background.add_task(_execute, scan.id)
    return _to_out(scan)


@router.get("/{scan_id}", response_model=ScanOut)
def get_scan(scan_id: str, db: Session = Depends(get_db)) -> ScanOut:
    row = db.get(ScanRun, scan_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No scan with id {scan_id}."
        )
    return _to_out(row)


@router.get("", response_model=list[ScanOut])
def list_scans(db: Session = Depends(get_db), limit: int = 20) -> list[ScanOut]:
    rows = (
        db.execute(select(ScanRun).order_by(ScanRun.started_at.desc()).limit(limit))
        .scalars()
        .all()
    )
    return [_to_out(r) for r in rows]
