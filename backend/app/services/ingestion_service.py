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
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.base import NormalisedMessage, PlatformConnector
from app.integrations.discord import DiscordConnector, DiscordError
from app.integrations.telegram import TelegramConnector, TelegramError
from app.models import ActivityEntry, Conversation, ScanRun
from app.schemas.tuning import TuningConfig
from app.services.reply_service import detect_language, draft_all_variants
from app.services.scoring_service import ScoreResult, score_message

if TYPE_CHECKING:
    from app.services.ai_service import AIDraft

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
    msg: NormalisedMessage, config: TuningConfig, ai: "AIDraft | None" = None
) -> Conversation:
    """Score one normalised message into an unsaved Conversation row.

    ``ai`` replaces the template summary and drafts when the model produced
    them; risk-flagged messages never get a draft either way.
    """
    country = msg.country or None
    result = score_message(msg.message, config, country, msg.posted_at)

    blocked = bool(result.risk_flags)
    variants = [] if blocked else draft_all_variants(msg.community, config.voice)
    summary = build_summary(msg.message, result.matched_keywords, result.risk_flags)
    language = msg.language or detect_language(msg.message)
    history = [
        {"at": datetime.now(UTC).isoformat(), "actor": "system", "action": "discovered by scan"}
    ]
    if ai is not None and not blocked:
        variants, language = ai.variants, ai.language
        summary = ai.summary or summary
        history.append(
            {"at": datetime.now(UTC).isoformat(), "actor": "system", "action": "AI drafted summary and replies"}
        )

    return Conversation(
        platform=msg.platform,
        external_id=msg.external_id,
        community=msg.community,
        source_url=msg.source_url,
        author_pseudonym=msg.author_pseudonym,
        message=msg.message,
        posted_at=msg.posted_at,
        country=country or UNKNOWN_COUNTRY,
        language=language,
        score=result.score,
        intent=result.intent,
        confidence=result.confidence,
        matched_keywords=list(result.matched_keywords),
        contributions=[
            {"ruleId": c.rule_id, "label": c.label, "points": c.points}
            for c in result.contributions
        ],
        risk_flags=list(result.risk_flags),
        summary=summary,
        status=initial_status(result),
        reply_variants=variants,
        selected_variant=0,
        edited_reply=None,
        history=history,
    )


def build_connectors() -> list[tuple[str, PlatformConnector]]:
    """Only platforms with complete credentials.

    A missing token is not an error here -- it is a platform that is not
    connected yet, which the caller reports as such.
    """
    settings = get_settings()
    out: list[tuple[str, PlatformConnector]] = []
    if not settings.pseudonym_salt:
        logger.warning("PSEUDONYM_SALT is unset; ingestion disabled.")
        return out
    if settings.discord_bot_token:
        out.append(
            (
                "discord",
                DiscordConnector(settings.discord_bot_token, settings.pseudonym_salt),
            )
        )
    if settings.telegram_bot_token:
        out.append(
            (
                "telegram",
                TelegramConnector(settings.telegram_bot_token, settings.pseudonym_salt),
            )
        )
    return out


def build_discovery_connectors(db: Session) -> list[tuple[str, PlatformConnector]]:
    """Reddit, YouTube and the Telegram account, when each is set up.

    The first element is the label recorded in the scan outcome; messages carry
    their own platform, which is what de-duplication keys on.
    """
    from app.services import sources_service

    out: list[tuple[str, PlatformConnector]] = []
    for name in sources_service.DISCOVERY_PLATFORMS:
        connector = sources_service.build_connector(db, name)
        if connector is not None:
            out.append((name, connector))
    return out


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


async def ai_drafts_for(
    db: Session, platform: str, messages: list[NormalisedMessage], config: TuningConfig
) -> dict[str, "AIDraft"]:
    """AI summaries and replies for the new, relevant messages in a batch.

    Only messages that are not stored yet, carry no risk flag and reach the
    "low intent" threshold, and at most AI_MAX_PER_SCAN of them: each draft
    is a model call, which on a CPU server is tens of seconds.
    """
    from app.services import ai_service

    if not ai_service.enabled():
        return {}
    settings = get_settings()
    seen = _existing_external_ids(db, platform, [m.external_id for m in messages])
    candidates: list[tuple[int, NormalisedMessage]] = []
    for msg in messages:
        if msg.external_id in seen:
            continue
        result = score_message(msg.message, config, msg.country or None, msg.posted_at)
        if result.risk_flags or result.score < config.thresholds.low:
            continue
        candidates.append((result.score, msg))
    candidates.sort(key=lambda pair: pair[0], reverse=True)

    drafts: dict[str, ai_service.AIDraft] = {}
    for _, msg in candidates[: settings.ai_max_per_scan]:
        draft = await ai_service.draft(
            msg.message, msg.community, config.voice, msg.language or detect_language(msg.message)
        )
        if draft is None:
            break  # the model is down or misbehaving; templates for the rest
        drafts[msg.external_id] = draft
    return drafts


def persist_messages(
    db: Session,
    platform: str,
    messages: list[NormalisedMessage],
    config: TuningConfig,
    ai: dict[str, "AIDraft"] | None = None,
) -> int:
    """Insert only messages not already stored. Returns the number added."""
    if not messages:
        return 0

    seen = _existing_external_ids(db, platform, [m.external_id for m in messages])
    added = 0
    new_leads: list[Conversation] = []

    for msg in messages:
        if msg.external_id in seen:
            continue
        seen.add(msg.external_id)
        row = normalise_to_conversation(msg, config, (ai or {}).get(msg.external_id))
        db.add(row)
        try:
            # Flush per row: one row violating a constraint must not discard
            # the whole batch.
            db.flush()
        except IntegrityError:
            db.rollback()
            logger.info("Skipping duplicate %s:%s", platform, msg.external_id)
            continue
        added += 1
        if row.intent in ("high", "medium") and not row.risk_flags:
            new_leads.append(row)

    db.commit()
    if new_leads:
        from app.services import events_service

        for row in new_leads:
            events_service.emit("lead.discovered", events_service.lead_payload(row))
    return added


async def run_scan(db: Session, scan: ScanRun) -> ScanRun:
    """Poll every connected platform once and record the outcome.

    A connector that fails is recorded against its own platform and does not
    abort the others: partial success has to be visible, or a dead token looks
    identical to a quiet channel.
    """
    from app.core.redis import scan_lock

    with scan_lock() as acquired:
        if not acquired:
            scan.status = "failed"
            scan.error = "Another scan is already running. Try again when it finishes."
            scan.finished_at = datetime.now(UTC)
            db.commit()
            return scan
        await _run_scan_locked(db, scan)
    from app.services import events_service

    events_service.emit(
        "scan.completed",
        {"scanId": scan.id, "status": scan.status, "trigger": scan.trigger,
         "examined": scan.examined, "discovered": scan.discovered,
         "platforms": scan.platforms, "error": scan.error},
    )
    return scan


async def _run_scan_locked(db: Session, scan: ScanRun) -> ScanRun:
    config = active_config()
    connectors = build_connectors() + build_discovery_connectors(db)
    outcomes: list[dict] = []
    total_examined = 0
    total_added = 0

    if not connectors:
        scan.status = "failed"
        scan.error = (
            "No platform is connected. Set DISCORD_BOT_TOKEN, "
            "TELEGRAM_BOT_TOKEN, REDDIT_CLIENT_ID/SECRET or YOUTUBE_API_KEY, "
            "and PSEUDONYM_SALT in backend/.env."
        )
        scan.finished_at = datetime.now(UTC)
        db.commit()
        return scan

    for name, connector in connectors:
        try:
            messages = await connector.fetch_messages(limit=50)
        except (DiscordError, TelegramError) as exc:
            logger.warning("%s ingestion failed: %s", name, exc)
            outcomes.append(
                {"platform": name, "examined": 0, "discovered": 0, "error": str(exc)}
            )
            continue
        except Exception as exc:  # noqa: BLE001 -- one connector must not kill the scan
            logger.exception("%s ingestion crashed", name)
            outcomes.append(
                {
                    "platform": name,
                    "examined": 0,
                    "discovered": 0,
                    "error": repr(exc)[:200],
                }
            )
            continue

        drafts = await ai_drafts_for(db, connector.platform, messages, config)
        added = persist_messages(db, connector.platform, messages, config, drafts)
        total_examined += len(messages)
        total_added += added
        outcomes.append(
            {
                "platform": name,
                "examined": len(messages),
                "discovered": added,
                "error": None,
            }
        )

    scan.status = "completed"
    scan.examined = total_examined
    scan.discovered = total_added
    scan.platforms = outcomes
    scan.finished_at = datetime.now(UTC)

    if total_added:
        db.add(
            ActivityEntry(
                actor="system",
                action="scan completed",
                item=f"{total_added} new conversation(s)",
                after=f"examined {total_examined}",
            )
        )
    db.commit()
    return scan
