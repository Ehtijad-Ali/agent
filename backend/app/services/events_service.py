"""Outgoing events to n8n (self-hosted automation).

Signal posts a small JSON event to the n8n webhook whenever something happens
that a workflow might act on -- alert the team about a hot lead, log sends to a
Google Sheet, post a daily digest. Delivery is fire-and-forget: n8n being down
must never slow down or fail a scan or a review action.

Payloads carry pseudonymised authors only, the same data the Inbox shows.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import get_settings
from app.utils.background import spawn

logger = logging.getLogger("signal.events")

EVENTS = (
    "lead.discovered",
    "lead.status_changed",
    "reply.sent",
    "scan.completed",
)


def enabled() -> bool:
    return bool(get_settings().n8n_events_webhook_url)


def lead_payload(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "platform": row.platform,
        "community": row.community,
        "author": row.author_pseudonym,
        "message": (row.message or "")[:1000],
        "score": row.score,
        "intent": row.intent,
        "status": row.status,
        "summary": row.summary,
        "sourceUrl": row.source_url,
        "postedAt": row.posted_at.isoformat() if row.posted_at else None,
    }


async def _deliver(body: dict[str, Any]) -> None:
    s = get_settings()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                s.n8n_events_webhook_url,
                json=body,
                headers={"X-Signal-Secret": s.n8n_webhook_secret} if s.n8n_webhook_secret else {},
            )
        if response.status_code >= 400:
            logger.warning("n8n rejected %s: HTTP %s", body["event"], response.status_code)
    except httpx.HTTPError as exc:
        logger.warning("n8n unreachable for %s: %s", body["event"], exc)


def emit(event: str, data: dict[str, Any]) -> None:
    """Queue an event for n8n. Never raises, never blocks."""
    if not enabled():
        return
    body = {"event": event, "at": datetime.now(UTC).isoformat(), "data": data}
    try:
        spawn(_deliver(body))
    except RuntimeError:
        logger.debug("No event loop yet; dropped %s", event)


async def n8n_status() -> str:
    s = get_settings()
    if not s.n8n_base_url:
        return "not_configured"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{s.n8n_base_url.rstrip('/')}/healthz")
        return "ok" if response.status_code == 200 else f"http_{response.status_code}"
    except httpx.HTTPError:
        return "unreachable"
