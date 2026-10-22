"""Public redirect for tracking links.

Deliberately *not* under /api: this URL is pasted into public messages, so it
has to be short and it is hit by strangers' browsers rather than by the app.

It must be forgiving. A person who clicks a link from a message we sent should
land on the product even if our own bookkeeping fails, so a recording error is
logged and swallowed rather than turned into an error page.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import TrackingLink
from app.services.reply_service import PRODUCT_URL
from app.services.tracking_service import record_click

router = APIRouter(tags=["tracking"])
logger = logging.getLogger("signal.tracking")


@router.get("/r/{slug}", include_in_schema=False)
def follow(
    slug: str, request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    link = db.execute(
        select(TrackingLink).where(TrackingLink.slug == slug)
    ).scalar_one_or_none()

    if link is None:
        # An unknown slug still goes to the product rather than a 404: a
        # dead-end would be a worse experience than a slightly wrong landing.
        logger.info("Unknown tracking slug %r", slug)
        return RedirectResponse(url=PRODUCT_URL, status_code=302)

    try:
        record_click(
            db,
            link,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            referer=request.headers.get("referer"),
        )
    except Exception:  # noqa: BLE001 -- never fail a real visitor over analytics
        logger.exception("Could not record click for %r", slug)

    # 302, not 301: a permanent redirect would be cached by the browser and
    # every later click would skip the server entirely, losing the count.
    return RedirectResponse(url=link.target_url, status_code=302)
