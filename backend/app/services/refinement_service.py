"""Agent Refinement Index (brief §8, and the "optimise with learnings" ask).

One number per agent, so an operator can tell whether tuning is helping. It is
built from three things the system actually observes, not from a model's
opinion of itself:

  precision        -- of everything discovered, how much was relevant at all.
                      Low precision means the keywords are too broad.
  approval rate    -- of the leads a human looked at, how many they approved.
                      Low approval means the scoring disagrees with the human.
  click-through    -- of the replies sent, how many got a click.
                      Low CTR means the copy is not landing.

Deliberately refuses to grade on thin data. A single reply that got a click is
not a 100% click-through rate, and presenting it as one would invite tuning
against noise. Below MIN_SAMPLE the score is still returned but flagged
``confident=False`` with a note saying why.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Agent, Conversation, LinkClick, ReplySend, TrackingLink

# Below this many discovered conversations, the components are too noisy to
# tune against.
MIN_SAMPLE = 20

# Weights sum to 1. Click-through carries the most because it is the only
# component measuring a real person's reaction rather than our own judgement.
_WEIGHT_PRECISION = 0.25
_WEIGHT_APPROVAL = 0.3
_WEIGHT_CTR = 0.45

_RELEVANT = ("high", "medium", "low")
_REVIEWED = ("approved", "rejected", "sent", "manually_posted")


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 3) if denominator else 0.0


def compute(db: Session, agent: Agent | None = None, days: int = 30) -> dict:
    """The index over the window. ``agent`` is advisory until conversations
    carry an agent id; today the figures are system-wide and the agent is
    reported alongside them for context."""
    since = datetime.now(UTC) - timedelta(days=days)
    in_window = Conversation.posted_at >= since

    discovered = db.execute(
        select(func.count(Conversation.id)).where(in_window)
    ).scalar_one()
    relevant = db.execute(
        select(func.count(Conversation.id)).where(
            in_window, Conversation.intent.in_(_RELEVANT)
        )
    ).scalar_one()
    reviewed = db.execute(
        select(func.count(Conversation.id)).where(
            in_window, Conversation.status.in_(_REVIEWED)
        )
    ).scalar_one()
    approved = db.execute(
        select(func.count(Conversation.id)).where(
            in_window, Conversation.status.in_(("approved", "sent", "manually_posted"))
        )
    ).scalar_one()

    sent = db.execute(
        select(func.count(ReplySend.id)).where(ReplySend.sent_at >= since)
    ).scalar_one()
    clicked = db.execute(
        select(func.count(func.distinct(TrackingLink.conversation_id)))
        .join(LinkClick, LinkClick.link_id == TrackingLink.id)
        .where(LinkClick.is_bot == 0, LinkClick.clicked_at >= since)
    ).scalar_one()

    precision = _rate(relevant, discovered)
    approval_rate = _rate(approved, reviewed)
    ctr = _rate(clicked, sent)

    score = round(
        (
            precision * _WEIGHT_PRECISION
            + approval_rate * _WEIGHT_APPROVAL
            + ctr * _WEIGHT_CTR
        )
        * 100,
        1,
    )

    notes: list[str] = []
    confident = discovered >= MIN_SAMPLE and sent > 0

    if discovered < MIN_SAMPLE:
        notes.append(
            f"Only {discovered} conversation(s) discovered in {days} days; "
            f"at least {MIN_SAMPLE} are needed before this score means anything."
        )
    if sent == 0:
        notes.append(
            "No replies sent in the window, so click-through is 0 by absence "
            "rather than by failure. It is still weighted, which drags the "
            "score down until outreach starts."
        )
    if discovered and precision < 0.3:
        notes.append(
            f"Only {precision:.0%} of discovered messages were relevant. The "
            "keywords are matching too broadly -- tighten the phrase rules."
        )
    if reviewed and approval_rate < 0.3:
        notes.append(
            f"You approved {approval_rate:.0%} of what you reviewed. The "
            "scoring is surfacing leads you do not want; raise the thresholds."
        )
    if sent and ctr < 0.1:
        notes.append(
            f"{ctr:.0%} of sent replies got a click. The copy or the targeting "
            "is not landing -- try a different tone preset."
        )

    return {
        "agentId": agent.id if agent else None,
        "agentName": agent.name if agent else None,
        "sampleSize": discovered,
        "confident": confident,
        "score": score,
        "approvalRate": approval_rate,
        "clickThroughRate": ctr,
        "precision": precision,
        "notes": notes,
    }
