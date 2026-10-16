"""Scheduled ingestion.

The brief specifies scans **twice a day plus manual runs**, so this sleeps
until the next configured clock time rather than polling on a short interval. A
fixed interval is still available via ``SCAN_INTERVAL_SECONDS`` because waiting
hours for the next slot makes development impossible -- but it is off by
default, and the scheduled path is what production uses.

It is an asyncio task rather than Celery because there is exactly one recurring
job and Redis is optional. The Celery dependency stays for when there are many.

The loop never raises. A connector outage must degrade to "no new rows this
cycle", not kill the task and silently stop all ingestion.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, time, timedelta

from app.core.config import get_settings
from app.db.session import session_scope
from app.models import ScanRun
from app.services.ingestion_service import build_connectors, run_scan

logger = logging.getLogger("signal.poller")

_task: asyncio.Task | None = None

# Reported by /api/scans so the UI can show when the next scan is due.
_next_run_at: datetime | None = None


def parse_times(values: list[str]) -> list[time]:
    """Parse "HH:MM" strings into UTC times, skipping anything malformed.

    A typo must not stop ingestion entirely, so bad entries are logged and
    dropped; if none survive the caller falls back to the defaults.
    """
    parsed: list[time] = []
    for raw in values:
        try:
            hour, _, minute = raw.partition(":")
            parsed.append(time(hour=int(hour), minute=int(minute), tzinfo=UTC))
        except (TypeError, ValueError):
            logger.warning("Ignoring malformed scan time %r (expected HH:MM)", raw)
    return sorted(set(parsed))


def next_due(now: datetime, times: list[time]) -> datetime:
    """The soonest configured slot strictly after ``now``.

    Strictly after, so finishing a scan at exactly its slot time does not
    immediately qualify to run again.
    """
    candidates = [
        datetime.combine(now.date(), slot, tzinfo=UTC) for slot in times
    ]
    future = [c for c in candidates if c > now]
    if future:
        return min(future)
    # Everything today has passed; take the first slot tomorrow.
    return datetime.combine(now.date() + timedelta(days=1), times[0], tzinfo=UTC)


def next_run_at() -> datetime | None:
    """When the next scheduled scan is due, or None if nothing is scheduled."""
    return _next_run_at


async def _cycle(trigger: str) -> None:
    db = session_scope()
    try:
        scan = ScanRun(status="running", trigger=trigger)
        db.add(scan)
        db.commit()
        db.refresh(scan)
        await run_scan(db, scan)
        logger.info(
            "Scheduled scan examined %s message(s), discovered %s",
            scan.examined,
            scan.discovered,
        )
    finally:
        db.close()


async def _interval_loop(interval: int) -> None:
    logger.info("Ingestion poller started (development interval: every %ss)", interval)
    global _next_run_at
    while True:
        _next_run_at = datetime.now(UTC) + timedelta(seconds=interval)
        try:
            await _cycle("scheduled")
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 -- one bad cycle is not fatal
            logger.exception("Scan cycle failed; continuing")
        await asyncio.sleep(interval)


async def _scheduled_loop(times: list[time]) -> None:
    global _next_run_at
    logger.info(
        "Ingestion scheduled at %s UTC daily",
        ", ".join(slot.strftime("%H:%M") for slot in times),
    )
    while True:
        now = datetime.now(UTC)
        due = next_due(now, times)
        _next_run_at = due
        wait = (due - now).total_seconds()
        logger.info("Next scan at %s UTC (in %.1f min)", due.isoformat(), wait / 60)

        try:
            await asyncio.sleep(wait)
        except asyncio.CancelledError:
            raise

        try:
            await _cycle("scheduled")
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 -- one bad cycle is not fatal
            logger.exception("Scan cycle failed; continuing")


def start() -> bool:
    """Start the scanner unless it is already running or nothing is connected."""
    global _task
    if _task is not None and not _task.done():
        return True
    if not build_connectors():
        logger.info("No platform connected; scanner not started.")
        return False

    settings = get_settings()
    if settings.scan_interval_seconds > 0:
        coro = _interval_loop(settings.scan_interval_seconds)
    else:
        times = parse_times(settings.scan_time_list) or parse_times(["09:00", "21:00"])
        coro = _scheduled_loop(times)

    _task = asyncio.create_task(coro, name="signal-scanner")
    return True


async def stop() -> None:
    global _task, _next_run_at
    if _task is None:
        return
    _task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await _task
    _task = None
    _next_run_at = None
    logger.info("Scanner stopped")
