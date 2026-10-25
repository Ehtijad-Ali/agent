"""Ingestion: poll connectors, score, persist (spec §10, §23).

This is the path that was missing in Phase 1. The test scripts in
backend/scripts proved a connector can read and score a message; this turns
that into something the Inbox can show.

Idempotence is the design constraint. Polling re-sees the same messages every
cycle, so insertion is guarded by the unique index on
(platform, external_id) plus a pre-check. Re-running a scan must never
duplicate a row or a reply draft.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.base import NormalisedMessage, PlatformConnector
from app.integrations.discord import DiscordConnector, DiscordError
from app.integrations.telegram import TelegramConnector, TelegramError
from app.models import ActivityEntry, Agent, Conversation, ScanRun
from app.schemas.tuning import TuningConfig
from app.services.reply_service import detect_language, draft_all_variants
from app.services.scoring_service import ScoreResult, score_message

logger = logging.getLogger("signal.ingestion")

# ISO 3166-1 user-assigned code for "unknown". Neither Discord nor Telegram
# exposes user location, and inferring one from a server region would be wrong
# more often than right -- so it is recorded as unknown rather than invented.
UNKNOWN_COUNTRY = "ZZ"

_ASKING = re.compile(r"\b(recommend|suggestion|any good|looking for|anyone know)\b")
_NO_DEPOSIT = re.compile(r"\b(no\s*deposit|without\s*depositing)\b")


def build_summary(message: str, matched: list[str], risk_flags: list[str]) -> str:
    """Port of ``buildSummary`` in src/lib/seed.ts.

    Kept identical so a conversation reads the same however it was produced.
    These strings are user-visible in the Inspector.
    """
    lower = message.lower()
    if "underage" in risk_flags:
        return "Author says they are under 18, so no reply can be drafted for this one."
    if "real_money" in risk_flags:
        return (
            "Author wants real-money gambling. Rejected: Join All Bettors is "
            "free-to-play only."
        )
    if "spam" in risk_flags:
        return "Promotional links and referral codes. Rejected as spam."
    if not matched:
        return "No keywords matched, and the message is not asking for a recommendation."

    pieces: list[str] = []
    if _ASKING.search(lower):
        pieces.append("Author is asking for a recommendation")
    if _NO_DEPOSIT.search(lower):
        pieces.append("explicitly mentions no deposit")
    if any("free" in m for m in matched):
        pieces.append("interested in free-to-play")
    if any("social" in m or "friend" in m for m in matched):
        pieces.append("wants a social/community experience")
    if not pieces:
        pieces.append(f"Matched {len(matched)} configured keywords")
    return ", ".join(pieces) + "."


def initial_status(result: ScoreResult) -> str:
    """Spec §15-18: risk flags are blocking, and nothing is auto-approved.

    A flagged message goes straight to ``blocked`` with no draft. Everything
    else lands in ``new`` for a human -- the ceiling on automation is that a
    person approves before anything is sent.
    """
    if result.risk_flags:
        return "blocked"
    return "new"


def active_config() -> TuningConfig:
    """The config ingestion scores against.

    Read through the engine route so a manual tuning edit and ingestion cannot
    drift apart while the active config still lives in process memory.
    """
    from app.api.routes import engine

    return engine.get_active_config()


def normalise_to_conversation(
    msg: NormalisedMessage, config: TuningConfig
) -> Conversation:
    """Score one normalised message into an unsaved Conversation row."""
    country = msg.country or None
    result = score_message(msg.message, config, country, msg.posted_at)

    blocked = bool(result.risk_flags)
    variants = [] if blocked else draft_all_variants(msg.community, config.voice)

    return Conversation(
        platform=msg.platform,
        external_id=msg.external_id,
        community=msg.community,
        source_url=msg.source_url,
        author_pseudonym=msg.author_pseudonym,
        message=msg.message,
        posted_at=msg.posted_at,
        country=country or UNKNOWN_COUNTRY,
        language=msg.language or detect_language(msg.message),
        score=result.score,
        intent=result.intent,
        confidence=result.confidence,
        matched_keywords=list(result.matched_keywords),
        contributions=[
            {"ruleId": c.rule_id, "label": c.label, "points": c.points}
            for c in result.contributions
        ],
        risk_flags=list(result.risk_flags),
        summary=build_summary(msg.message, result.matched_keywords, result.risk_flags),
        status=initial_status(result),
        reply_variants=variants,
        selected_variant=0,
        edited_reply=None,
        history=[
            {
                "at": datetime.now(UTC).isoformat(),
                "actor": "system",
                "action": "discovered by scan",
            }
        ],
    )


def source_settings(db: Session | None = None) -> dict[str, dict]:
    """Search terms and sources per discovery platform, with defaults filled in."""
    from app.models.platform_settings import DEFAULTS, PlatformSettings

    out = {k: dict(v) for k, v in DEFAULTS.items()}
    own = db is None
    if own:
        from app.db.session import session_scope

        try:
            db = session_scope()
        except RuntimeError:  # no database configured (tests, engine-only mode)
            return out
    try:
        for row in db.execute(select(PlatformSettings)).scalars():
            out[row.platform] = {**out.get(row.platform, {}), **(row.config or {})}
    except Exception:  # noqa: BLE001 -- table missing on first boot; defaults apply
        logger.debug("platform_settings unavailable; using defaults")
    finally:
        if own:
            db.close()
    return out


def build_connectors(db: Session | None = None) -> list[tuple[str, PlatformConnector]]:
    """Only platforms with complete credentials.

    A missing token is not an error here -- it is a platform that is not
    connected yet, which the caller reports as such. The first element of each
    pair is the platform the messages are stored under; the Telegram bot and
    the Telegram account both store under "telegram", so a message either can
    see is kept once.
    """
    settings = get_settings()
    out: list[tuple[str, PlatformConnector]] = []
    if not settings.pseudonym_salt:
        logger.warning("PSEUDONYM_SALT is unset; ingestion disabled.")
        return out
    salt = settings.pseudonym_salt
    if settings.discord_bot_token:
        out.append(("discord", DiscordConnector(settings.discord_bot_token, salt)))
    if settings.telegram_bot_token:
        out.append(("telegram", TelegramConnector(settings.telegram_bot_token, salt)))

    has_reddit = bool(settings.reddit_client_id and settings.reddit_client_secret)
    has_youtube = bool(settings.youtube_api_key)
    has_tg_account = bool(
        settings.telegram_api_id and settings.telegram_api_hash and settings.telegram_session
    )
    if not (has_reddit or has_youtube or has_tg_account):
        return out
    sources = source_settings(db)
    if has_reddit:
        from app.integrations.reddit import RedditConnector

        cfg = sources["reddit"]
        out.append(("reddit", RedditConnector(
            settings.reddit_client_id, settings.reddit_client_secret,
            settings.reddit_user_agent, salt, cfg.get("queries"), cfg.get("subreddits"),
        )))
    if has_youtube:
        from app.integrations.youtube import YouTubeConnector

        cfg = sources["youtube"]
        out.append(("youtube", YouTubeConnector(
            settings.youtube_api_key, salt, cfg.get("queries"), cfg.get("channel_ids"),
        )))
    if has_tg_account:
        from app.integrations.telegram_account import TelegramAccountConnector

        cfg = sources["telegram_account"]
        out.append(("telegram", TelegramAccountConnector(
            settings.telegram_api_id, settings.telegram_api_hash, settings.telegram_session,
            salt, cfg.get("queries"), cfg.get("chats"),
        )))
    return out


def sender_for(platform: str) -> PlatformConnector | None:
    """The connector that may post replies on a platform: the bots only.

    Discovery connectors (Reddit, YouTube, the Telegram account) are read-only;
    replies found through them are posted by a person.
    """
    settings = get_settings()
    if not settings.pseudonym_salt:
        return None
    if platform == "discord" and settings.discord_bot_token:
        return DiscordConnector(settings.discord_bot_token, settings.pseudonym_salt)
    if platform == "telegram" and settings.telegram_bot_token:
        return TelegramConnector(settings.telegram_bot_token, settings.pseudonym_salt)
    return None


def _existing_external_ids(db: Session, platform: str, ids: list[str]) -> set[str]:
    if not ids:
        return set()
    rows = db.execute(
        select(Conversation.external_id).where(
            Conversation.platform == platform,
            Conversation.external_id.in_(ids),
        )
    ).scalars()
    return set(rows)


def enabled_engagement_agents(db: Session) -> list[Agent]:
    return list(
        db.execute(
            select(Agent).where(Agent.agent_type == "engagement", Agent.enabled == 1)
        ).scalars()
    )


def agent_accepts(agent: Agent, conv: Conversation) -> bool:
    """Whether a conversation falls inside an engagement agent's rules."""
    rules = agent.rules or {}
    if conv.platform not in rules.get("platforms", ["discord", "telegram"]):
        return False
    if conv.score < int(rules.get("minScore", 0)):
        return False
    if conv.risk_flags and rules.get("skipRiskFlagged", True):
        return False
    return True


def assign_agents(
    conversations: list[Conversation], agents: list[Agent]
) -> dict[str, int]:
    """Record on each new conversation which agents picked it up.

    Returns the count per agent name so the scan can report it. An agent that
    matched nothing still appears with 0 -- "ran and found nothing" and "never
    ran" must not look the same.
    """
    counts = {a.name: 0 for a in agents}
    now = datetime.now(UTC).isoformat()
    for conv in conversations:
        picked = [a for a in agents if agent_accepts(a, conv)]
        if not picked:
            continue
        conv.history = [
            *conv.history,
            *(
                {"at": now, "actor": a.name, "action": "picked up by agent"}
                for a in picked
            ),
        ]
        for a in picked:
            counts[a.name] += 1
    return counts


def persist_messages(
    db: Session,
    platform: str,
    messages: list[NormalisedMessage],
    config: TuningConfig,
    agents: list[Agent] | None = None,
    agent_counts: dict[str, int] | None = None,
    added_ids: list[str] | None = None,
) -> int:
    """Insert only messages not already stored. Returns the number added."""
    if not messages:
        return 0

    seen = _existing_external_ids(db, platform, [m.external_id for m in messages])
    added = 0

    for msg in messages:
        if msg.external_id in seen:
            continue
        seen.add(msg.external_id)
        conv = normalise_to_conversation(msg, config)
        picked = assign_agents([conv], agents) if agents else {}
        db.add(conv)
        try:
            # Flush per row: one row violating a constraint must not discard
            # the whole batch.
            db.flush()
        except IntegrityError:
            db.rollback()
            logger.info("Skipping duplicate %s:%s", platform, msg.external_id)
            continue
        added += 1
        if added_ids is not None:
            added_ids.append(conv.id)
        if agent_counts is not None:
            for name, n in picked.items():
                agent_counts[name] = agent_counts.get(name, 0) + n

    db.commit()
    return added


async def run_scan(db: Session, scan: ScanRun) -> ScanRun:
    """Poll every connected platform once and record the outcome.

    A connector that fails is recorded against its own platform and does not
    abort the others: partial success has to be visible, or a dead token looks
    identical to a quiet channel.
    """
    config = active_config()
    connectors = build_connectors(db)
    agents = enabled_engagement_agents(db)
    agent_counts: dict[str, int] = {a.name: 0 for a in agents}
    outcomes: list[dict] = []
    total_examined = 0
    total_added = 0
    new_ids: list[str] = []

    if not connectors:
        scan.status = "failed"
        scan.error = (
            "No platform is connected. Set DISCORD_BOT_TOKEN or "
            "TELEGRAM_BOT_TOKEN and PSEUDONYM_SALT in backend/.env."
        )
        scan.finished_at = datetime.now(UTC)
        db.add(
            ActivityEntry(actor="system", action="scan failed", after=scan.error)
        )
        db.commit()
        return scan

    for name, connector in connectors:
        label = getattr(connector, "label", name)
        try:
            messages = await connector.fetch_messages(limit=50)
        except (DiscordError, TelegramError) as exc:
            logger.warning("%s ingestion failed: %s", label, exc)
            outcomes.append(
                {"platform": label, "examined": 0, "discovered": 0, "error": str(exc)}
            )
            continue
        except Exception as exc:  # noqa: BLE001 -- one connector must not kill the scan
            logger.exception("%s ingestion crashed", label)
            outcomes.append(
                {
                    "platform": label,
                    "examined": 0,
                    "discovered": 0,
                    "error": str(exc)[:200] or repr(exc)[:200],
                }
            )
            continue

        added = persist_messages(db, name, messages, config, agents, agent_counts, new_ids)
        total_examined += len(messages)
        total_added += added
        outcome = {
            "platform": label,
            "examined": len(messages),
            "discovered": added,
            "error": None,
        }
        poll = getattr(connector, "last_poll", None)
        if poll:
            outcome["received"] = poll
            for event in poll.get("events", []):
                db.add(
                    ActivityEntry(
                        actor=name, action=event["action"], item=event["chat"]
                    )
                )
        outcomes.append(outcome)

    scan.status = "completed"
    scan.examined = total_examined
    scan.discovered = total_added
    scan.platforms = outcomes
    scan.finished_at = datetime.now(UTC)

    # Every scan is recorded, including the ones that found nothing. A test
    # message that "did nothing" has to leave a trace saying what the scan
    # actually received, or there is no way to tell where it was lost.
    db.add(
        ActivityEntry(
            actor="system",
            action="scan completed",
            item=f"{total_added} new conversation(s)",
            after=scan_summary(outcomes, agent_counts),
        )
    )
    for agent_name, count in agent_counts.items():
        db.add(
            ActivityEntry(
                actor=agent_name[:64],
                action="agent run",
                item=f"{count} new conversation(s) picked up",
            )
        )
    db.commit()

    # AI summaries and replies are written after the scan has been recorded,
    # so a slow local model never holds the scan open.
    from app.services import ai_drafts

    ai_drafts.enrich_in_background(new_ids)
    await notify_new_leads(db, new_ids)
    return scan


async def notify_new_leads(db: Session, ids: list[str]) -> None:
    """Post strong new leads to n8n, which can alert by email, Slack, etc."""
    settings = get_settings()
    if not ids or not settings.n8n_lead_webhook_url:
        return
    rows = db.execute(
        select(Conversation).where(
            Conversation.id.in_(ids),
            Conversation.score >= settings.lead_alert_min_score,
            Conversation.status == "new",
        )
    ).scalars().all()
    if not rows:
        return
    payload = {
        "count": len(rows),
        "dashboard": f"{settings.public_base_url.rstrip('/')}/",
        "leads": [
            {
                "id": r.id, "platform": r.platform, "community": r.community,
                "score": r.score, "intent": r.intent, "summary": r.summary,
                "message": r.message[:500], "url": r.source_url,
            }
            for r in rows
        ],
    }
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                settings.n8n_lead_webhook_url, json=payload,
                headers={"X-Signal-Secret": settings.n8n_webhook_secret},
            )
    except httpx.HTTPError as exc:
        logger.warning("n8n lead webhook failed: %s", exc)


def scan_summary(outcomes: list[dict], agent_counts: dict[str, int]) -> str:
    """One line per scan that explains an empty result rather than hiding it."""
    parts: list[str] = []
    for o in outcomes:
        if o.get("error"):
            parts.append(f"{o['platform']}: ERROR {o['error']}")
            continue
        poll = o.get("received")
        if poll is None:
            parts.append(f"{o['platform']}: {o['examined']} message(s)")
            continue
        text = (
            f"{o['platform']}: {poll['updates']} update(s), "
            f"{poll['textMessages']} text message(s)"
        )
        if poll["skippedNoText"]:
            text += f", {poll['skippedNoText']} without text skipped"
        if poll["chats"]:
            text += f" from {', '.join(poll['chats'])}"
        if not poll["updates"]:
            text += (
                " -- Telegram delivered nothing since the last scan. If the bot "
                "is in a group, remove and re-add it so privacy-mode changes apply"
            )
        parts.append(text)
    if not agent_counts:
        parts.append("no engagement agent is enabled")
    return "; ".join(parts)
