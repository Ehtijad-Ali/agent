"""Reply safety check (spec §15, §17, §30).

Until now the five non-negotiable rules in ``core/defaults.py`` were strings in
a tuple, displayed as locked toggles and enforced by nothing. This module is
what enforces them, and it is the only thing standing between an edited draft
and a real post.

It runs server-side and returns *every* violation rather than the first, so a
rejected send explains itself completely instead of one problem at a time. The
caller must treat a non-empty result as a hard refusal -- never a warning.

Two rules are structural rather than checked here:
  - "Never post autonomously" is enforced by requiring status ``approved``,
    which only a human action can set.
  - "Never DM authors" is enforced by construction: the connectors post to the
    channel the message came from and have no DM path at all.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Conversation, ReplySend
from app.schemas.tuning import TuningConfig
from app.services.reply_service import DISCLOSURE, FREE_TO_PLAY

# Matched loosely so an operator may re-punctuate or re-case the mandatory
# wording while editing, but not drop it. Whitespace is collapsed first because
# a textarea readily introduces line breaks mid-sentence.
_DISCLOSURE_PATTERN = re.compile(
    r"full disclosure.*i work on join all bettors", re.IGNORECASE
)
# "free to play" / "free-to-play", then the no-deposit and 18+ assurances.
_FREE_TO_PLAY_PATTERN = re.compile(r"free[\s-]?to[\s-]?play", re.IGNORECASE)
_NO_DEPOSIT_PATTERN = re.compile(r"no deposit", re.IGNORECASE)
_AGE_PATTERN = re.compile(r"18\s*\+", re.IGNORECASE)


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def outgoing_text(conversation: Conversation) -> str:
    """What would actually be posted: the edit if there is one, else the
    selected variant."""
    if conversation.edited_reply:
        return conversation.edited_reply
    variants = conversation.reply_variants or []
    index = conversation.selected_variant or 0
    if 0 <= index < len(variants):
        return variants[index].get("text", "")
    return ""


def check_reply(
    db: Session, conversation: Conversation, config: TuningConfig
) -> list[str]:
    """Every reason this reply must not be sent. Empty means it may be."""
    problems: list[str] = []
    text = _collapse(outgoing_text(conversation))

    # --- "Never post autonomously" ---
    if conversation.status == "sent":
        problems.append("This conversation has already been replied to.")
    elif conversation.status != "approved":
        problems.append(
            f"Status is '{conversation.status}'. A reply can only be sent from "
            "'approved', which requires a human to approve it first."
        )

    # --- risk flags are blocking (spec §15) ---
    if conversation.risk_flags:
        problems.append(
            "Conversation carries risk flags "
            f"({', '.join(conversation.risk_flags)}); no reply may be sent."
        )

    # --- the reply text itself ---
    if not text:
        problems.append("There is no reply text to send.")
    else:
        if not _DISCLOSURE_PATTERN.search(text):
            problems.append(
                "Reply is missing the brand disclosure. It must state: "
                f'"{DISCLOSURE}"'
            )
        if not _FREE_TO_PLAY_PATTERN.search(text):
            problems.append(
                'Reply is missing the free-to-play statement. It must include: '
                f'"{FREE_TO_PLAY}"'
            )
        if not _NO_DEPOSIT_PATTERN.search(text):
            problems.append('Reply must state that there are no deposits.')
        if not _AGE_PATTERN.search(text):
            problems.append('Reply must carry the "18+" notice.')

        limit = config.voice.max_length
        if len(text) > limit:
            problems.append(
                f"Reply is {len(text)} characters, over the {limit}-character limit."
            )

    # --- "One reply per person, ever" ---
    already = db.execute(
        select(func.count(ReplySend.id)).where(
            ReplySend.platform == conversation.platform,
            ReplySend.author_pseudonym == conversation.author_pseudonym,
        )
    ).scalar_one()
    if already:
        problems.append(
            f"{conversation.author_pseudonym} has already received a reply on "
            f"{conversation.platform}. The limit is one per person, ever."
        )

    problems.extend(_rate_cap_problems(db, conversation.platform, config))
    return problems


def _rate_cap_problems(db: Session, platform: str, config: TuningConfig) -> list[str]:
    """Spec §30. Counted from sends, not approvals."""
    problems: list[str] = []
    now = datetime.now(UTC)

    per_hour = config.rate_caps.per_platform_per_hour
    sent_this_hour = db.execute(
        select(func.count(ReplySend.id)).where(
            ReplySend.platform == platform,
            ReplySend.sent_at >= now - timedelta(hours=1),
        )
    ).scalar_one()
    if sent_this_hour >= per_hour:
        problems.append(
            f"Hourly cap reached for {platform}: {sent_this_hour}/{per_hour} "
            "sent in the last hour."
        )

    ceiling = config.rate_caps.daily_approved_ceiling
    sent_today = db.execute(
        select(func.count(ReplySend.id)).where(
            ReplySend.sent_at >= now - timedelta(days=1)
        )
    ).scalar_one()
    if sent_today >= ceiling:
        problems.append(
            f"Daily cap reached: {sent_today}/{ceiling} replies sent in the "
            "last 24 hours."
        )

    return problems


def usage(db: Session, config: TuningConfig) -> dict:
    """Current consumption against the caps, for the Safety screen."""
    now = datetime.now(UTC)
    rows = db.execute(
        select(ReplySend.platform, func.count(ReplySend.id))
        .where(ReplySend.sent_at >= now - timedelta(hours=1))
        .group_by(ReplySend.platform)
    ).all()
    sent_today = db.execute(
        select(func.count(ReplySend.id)).where(
            ReplySend.sent_at >= now - timedelta(days=1)
        )
    ).scalar_one()

    return {
        "perPlatformPerHour": config.rate_caps.per_platform_per_hour,
        "dailyApprovedCeiling": config.rate_caps.daily_approved_ceiling,
        "sentLastHour": {platform: count for platform, count in rows},
        "sentToday": sent_today,
    }
