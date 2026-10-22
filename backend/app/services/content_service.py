"""Content agents: per-city classified-ad copy (brief §2).

What this does and does not do matters, so it is stated plainly:

  - It generates the ad -- city, category, title, ZIP, body, contact email --
    and records it with a slot for the published URL (§2.1-2.7, §2.9).
  - It does NOT submit the ad. Automated posting to Craigslist is outside what
    this system does; see docs/feasibility.md. The operator copies the
    generated content, posts it, and pastes the live URL back.

"A US city different from any used before" is enforced by a unique constraint
on (agent_id, location_key), not by remembering to check. Asking for an ad when
every city is used returns an explicit error rather than silently repeating one.

The copy carries the same mandatory wording as a reply -- brand disclosure,
free-to-play, no deposits, 18+ -- because an ad is a public promotional
statement and the non-negotiable rules do not stop applying because the channel
changed.
"""

from __future__ import annotations

import logging
import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Agent, AgentOutput
from app.services.locations import US_CITIES, City
from app.services.reply_service import DISCLOSURE, FREE_TO_PLAY, PRODUCT_URL

logger = logging.getLogger("signal.content")

CATEGORIES: tuple[str, ...] = ("community", "events", "services")


class ContentError(RuntimeError):
    """The agent cannot produce an ad, and why."""


_TITLES = (
    "{city} prediction league - free to play, no deposit",
    "Free sports prediction game for {city} fans",
    "{city}: free-to-play prediction league, no money involved",
    "Looking for {city} sports fans - free prediction game",
    "Free prediction game, {city} leaderboard just opened",
)

_OPENERS = (
    "Starting a free prediction league for {city} sports fans.",
    "Setting up a {city} leaderboard for a free prediction game.",
    "Putting together a group of {city} sports fans for a free prediction league.",
    "Opening a {city} table on a free-to-play prediction game.",
)

_MIDDLES = (
    "You pick outcomes on upcoming games, earn points for the ones you call "
    "right, and climb a leaderboard against other people in {state}.",
    "It works on predictions only: call the result, collect points, see where "
    "you land against everyone else in {state}.",
    "Pick winners, rack up points, and compete on a {state} leaderboard. "
    "That's the whole game.",
)

_CLOSERS = (
    "No stake, no wallet, nothing to withdraw - the points have no cash value.",
    "There is no money in it at any point: no deposit, no payout, no cash value.",
    "Nothing financial is involved - no deposit to make and nothing to cash out.",
)


def available_cities(db: Session, agent_id: str) -> list[City]:
    """Cities this agent has not produced an ad for yet."""
    used = set(
        db.execute(
            select(AgentOutput.location_key).where(AgentOutput.agent_id == agent_id)
        ).scalars()
    )
    return [city for city in US_CITIES if city.key not in used]


def build_ad(city: City, category: str, email: str, seed: int | None = None) -> dict:
    """Compose the ad copy for one city.

    Seeded on the city by default, so the same city always yields the same ad
    (regenerating is idempotent) while different cities read differently rather
    than being one template with the name swapped.
    """
    rng = random.Random(seed if seed is not None else hash(city.key) & 0xFFFFFFFF)

    title = rng.choice(_TITLES).format(city=city.name)
    paragraphs = [
        rng.choice(_OPENERS).format(city=city.name, state=city.state),
        rng.choice(_MIDDLES).format(city=city.name, state=city.state),
        rng.choice(_CLOSERS),
        # Mandatory wording, same as an outbound reply.
        f"{DISCLOSURE} {FREE_TO_PLAY}",
        f"Have a look here: {PRODUCT_URL}",
    ]

    return {
        "city": city.name,
        "state": city.state,
        "zipcode": city.zipcode,
        "category": category,
        "title": title,
        "body": "\n\n".join(paragraphs),
        "contact_email": email,
    }


def _rules(agent: Agent) -> dict:
    return agent.rules or {}


def generate_output(db: Session, agent: Agent) -> AgentOutput:
    """Produce the next ad for this agent and record it.

    Raises ContentError when the agent is misconfigured or has exhausted the
    city list, so the caller can say which rather than returning an empty row.
    """
    if agent.agent_type != "content":
        raise ContentError(
            f"Agent '{agent.name}' is a {agent.agent_type} agent and cannot "
            "generate ad content."
        )

    rules = _rules(agent)
    email = (rules.get("contactEmail") or "").strip()
    if not email:
        raise ContentError(
            "This agent has no contactEmail in its rules; an ad with no contact "
            "address is not postable."
        )

    allowed = [c for c in (rules.get("categories") or CATEGORIES) if c in CATEGORIES]
    if not allowed:
        raise ContentError(
            "This agent has no valid categories configured. Choose from: "
            + ", ".join(CATEGORIES)
        )

    remaining = available_cities(db, agent.id)
    if not remaining:
        raise ContentError(
            f"Every one of the {len(US_CITIES)} available cities has already "
            "been used by this agent. Add cities or use a different agent."
        )

    rng = random.Random()
    city = rng.choice(remaining)
    category = rng.choice(allowed)

    ad = build_ad(city, category, email)
    output = AgentOutput(
        agent_id=agent.id,
        location_key=city.key,
        city=ad["city"],
        state=ad["state"],
        zipcode=ad["zipcode"],
        category=ad["category"],
        title=ad["title"],
        body=ad["body"],
        contact_email=ad["contact_email"],
        status="generated",
    )
    db.add(output)
    db.flush()
    return output
