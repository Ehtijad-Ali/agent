"""Tracking links: minting, substitution, click recording and attribution.

This is what makes "did the outreach work?" answerable. The reply drafts carry
a plain product URL; at send time it is swapped for a short link unique to that
conversation, so a later click is attributable to one reply on one platform.

The substitution happens *before* the safety check runs, so the text that is
checked is the text that is posted -- and the preview shows the real link
rather than a placeholder the operator never sees.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Conversation, LinkClick, ReplySend, TrackingLink
from app.services.reply_service import PRODUCT_URL

logger = logging.getLogger("signal.tracking")

# Public path for the redirect. Short on purpose: it is pasted into messages
# where length counts against the reply limit.
REDIRECT_PREFIX = "/r"

# Substrings that identify a platform's own link-preview fetcher rather than a
# person. Counting these would make every send look like a click, because
# Discord and Telegram both unfurl links the moment a message is posted.
_BOT_MARKERS = (
    "bot",
    "crawler",
    "spider",
    "preview",
    "facebookexternalhit",
    "telegrambot",
    "discordbot",
    "slackbot",
    "whatsapp",
    "curl",
    "wget",
    "python-requests",
    "httpx",
    "headless",
)


def _slug() -> str:
    """Short, URL-safe and unguessable.

    Unguessable matters: a sequential id would let anyone enumerate every link
    the system has ever sent.
    """
    return secrets.token_urlsafe(6)[:8]


def visitor_hash(ip: str | None, salt: str) -> str:
    """Salted hash of the caller's address, for de-duplicating repeat hits.

    Never the address itself -- see the note in models/tracking.py. With no
    salt configured this returns an empty string rather than a bare digest,
    which would be reversible for an address space this small.
    """
    if not ip or not salt:
        return ""
    return hmac.new(salt.encode(), ip.encode(), hashlib.sha256).hexdigest()[:32]


def looks_like_bot(user_agent: str | None) -> bool:
    if not user_agent:
        # No user agent at all is far more likely a fetcher than a browser.
        return True
    lowered = user_agent.lower()
    return any(marker in lowered for marker in _BOT_MARKERS)


def public_url(slug: str) -> str:
    base = get_settings().public_base_url.rstrip("/")
    return f"{base}{REDIRECT_PREFIX}/{slug}"


def ensure_link(db: Session, conversation: Conversation) -> TrackingLink:
    """The tracking link for this conversation, creating it if needed.

    One per conversation and reused, so a click maps to exactly one reply and
    the redirect keeps resolving for as long as the message exists.
    """
    existing = db.execute(
        select(TrackingLink).where(
            TrackingLink.conversation_id == conversation.id
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    # Retry on the astronomically unlikely slug collision rather than 500.
    for _ in range(5):
        candidate = _slug()
        clash = db.execute(
            select(TrackingLink.id).where(TrackingLink.slug == candidate)
        ).scalar_one_or_none()
        if clash is None:
            break
    else:  # pragma: no cover - requires five consecutive collisions
        raise RuntimeError("Could not mint a unique tracking slug")

    link = TrackingLink(
        slug=candidate,
        conversation_id=conversation.id,
        platform=conversation.platform,
        target_url=PRODUCT_URL,
    )
    db.add(link)
    db.flush()
    return link


def apply_tracking(text: str, link: TrackingLink) -> str:
    """Swap the plain product URL for the tracking link.

    If the operator edited the URL out entirely there is nothing to replace;
    the text is returned untouched rather than having a link appended, because
    silently adding a URL to someone's edited message would be worse than
    losing the attribution.
    """
    if not text or PRODUCT_URL not in text:
        return text
    return text.replace(PRODUCT_URL, public_url(link.slug))


def record_click(
    db: Session,
    link: TrackingLink,
    *,
    ip: str | None,
    user_agent: str | None,
    referer: str | None,
) -> LinkClick:
    click = LinkClick(
        link_id=link.id,
        visitor_hash=visitor_hash(ip, get_settings().pseudonym_salt),
        user_agent=(user_agent or "")[:500] or None,
        referer=(referer or "")[:500] or None,
        is_bot=1 if looks_like_bot(user_agent) else 0,
    )
    db.add(click)
    db.commit()
    return click


def engagement(db: Session, hours: int = 24 * 7) -> dict:
    """Reply-and-click funnel for the window (brief §1 analytics).

    Human clicks only. Link-preview fetchers are counted separately so the
    headline click-through rate is not inflated by the platform unfurling the
    link we just posted.
    """
    since = datetime.now(UTC) - timedelta(hours=hours)

    sent = db.execute(
        select(func.count(ReplySend.id)).where(ReplySend.sent_at >= since)
    ).scalar_one()

    human = (LinkClick.is_bot == 0) & (LinkClick.clicked_at >= since)
    clicks = db.execute(select(func.count(LinkClick.id)).where(human)).scalar_one()
    unique_clicks = db.execute(
        select(func.count(func.distinct(LinkClick.visitor_hash))).where(
            human, LinkClick.visitor_hash != ""
        )
    ).scalar_one()
    bot_hits = db.execute(
        select(func.count(LinkClick.id)).where(
            LinkClick.is_bot == 1, LinkClick.clicked_at >= since
        )
    ).scalar_one()

    per_platform = db.execute(
        select(TrackingLink.platform, func.count(LinkClick.id))
        .join(LinkClick, LinkClick.link_id == TrackingLink.id)
        .where(human)
        .group_by(TrackingLink.platform)
    ).all()

    sent_per_platform = db.execute(
        select(ReplySend.platform, func.count(ReplySend.id))
        .where(ReplySend.sent_at >= since)
        .group_by(ReplySend.platform)
    ).all()

    # Conversations whose link was clicked at least once -- the closest thing
    # to "this reply worked" that a click alone can tell us.
    converted = db.execute(
        select(func.count(func.distinct(TrackingLink.conversation_id)))
        .join(LinkClick, LinkClick.link_id == TrackingLink.id)
        .where(human)
    ).scalar_one()

    return {
        "windowHours": hours,
        "repliesSent": sent,
        "clicks": clicks,
        "uniqueClicks": unique_clicks,
        "botHits": bot_hits,
        "conversationsClicked": converted,
        "clickThroughRate": round(clicks / sent, 3) if sent else 0.0,
        "clicksByPlatform": {platform: count for platform, count in per_platform},
        "repliesByPlatform": {platform: count for platform, count in sent_per_platform},
    }
