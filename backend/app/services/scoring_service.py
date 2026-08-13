"""Deterministic scoring engine.

Port of ``scoreMessage`` from ``src/lib/scoring.ts``. The LLM never produces the
score (spec §13) -- it only supplies summary/intent commentary downstream. Given
the same message and config this function returns the same score every time.

``contributions`` labels are rendered verbatim by the frontend Inspector, so the
label strings are part of the wire contract, not an implementation detail.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from app.schemas.tuning import TuningConfig
from app.services.matching_service import match_keyword, normalise_text, tokenise

Intent = Literal["high", "medium", "low", "not_relevant"]
Confidence = Literal["low", "medium", "high"]
RiskFlag = Literal["underage", "real_money", "spam", "negative_keyword", "off_topic"]


def js_round(value: float) -> int:
    """Round half toward +infinity, matching JavaScript's ``Math.round``.

    Python's built-in ``round`` is banker's rounding: ``round(8.5) == 8``, while
    ``Math.round(8.5) === 9``. Partial phrase matches score ``weight * 0.85``,
    which lands on a .5 boundary often enough that using the built-in silently
    desynchronised the two engines -- a keyword weighted 10 scored 8 here and 9
    in the browser. Caught by the parity check against the live frontend.
    """
    return math.floor(value + 0.5)


@dataclass(slots=True)
class ScoreContribution:
    rule_id: str
    label: str
    points: int


@dataclass(slots=True)
class ScoreResult:
    score: int
    intent: Intent
    confidence: Confidence
    matched_keywords: list[str] = field(default_factory=list)
    contributions: list[ScoreContribution] = field(default_factory=list)
    risk_flags: list[RiskFlag] = field(default_factory=list)


# --- risk detection -------------------------------------------------------
# Patterns run against normalised text, where punctuation has become spaces --
# hence "don t" rather than "don't". The spam patterns run against raw lowercase
# because URLs lose their dots and slashes under normalisation.

_UNDERAGE = (
    re.compile(r"\b(i am|im|i m)\s+(1[0-7]|[0-9])\b"),
    re.compile(r"\bunder\s*18\b"),
    re.compile(r"\bunderage\b"),
    re.compile(r"\bminor\b"),
    re.compile(r"\b(13|14|15|16|17)\s*years?\b"),
)

_REAL_MONEY = (
    re.compile(r"\breal\s*money\b"),
    re.compile(r"\bcash\s*app\b"),
    re.compile(r"\bstake\s*real\b"),
    re.compile(r"\bdeposit\s*(money|cash|usd|usdt|btc|crypto)\b"),
    re.compile(r"\bwithdraw\s*(money|winnings|usd|usdt|btc|crypto)\b"),
    re.compile(r"\bgambling\s*site\b"),
    re.compile(r"\bodds?\s*for\s*real\b"),
)

_SPAM_NORMALISED = (
    re.compile(r"\bdm me\b"),
    re.compile(r"\bdm\s*for\s*link\b"),
    re.compile(r"\bcheck\s*my\s*profile\b"),
    re.compile(r"\bpromo\s*code\b"),
    re.compile(r"\bfollow\s*me\b"),
    re.compile(r"\breferral\s*link\b"),
)
_SPAM_RAW = (re.compile(r"discord\.gg/"), re.compile(r"t\.me/"))


def detect_risk_flags(message: str) -> list[RiskFlag]:
    """Content-derived risk flags. Negative-keyword risk is added by
    ``score_message`` because it depends on configuration."""
    m = normalise_text(message)
    raw = message.lower()
    flags: list[RiskFlag] = []
    if any(p.search(m) for p in _UNDERAGE):
        flags.append("underage")
    if any(p.search(m) for p in _REAL_MONEY):
        flags.append("real_money")
    if any(p.search(raw) for p in _SPAM_RAW) or any(p.search(m) for p in _SPAM_NORMALISED):
        flags.append("spam")
    return flags


# --- signal detection -----------------------------------------------------

_SIG_RECOMMENDATION = re.compile(
    r"\b(recommend|suggestion|any good|looking for|anyone know|whats a good)\b"
)
_SIG_NO_DEPOSIT = (
    re.compile(r"\bno\s*deposit\b"),
    re.compile(r"\bwithout\s*depositing\b"),
    re.compile(r"\bfree\s*no\s*deposit\b"),
    re.compile(r"\bdeposit\s*free\b"),
    # apostrophes become spaces under normalisation: "don't" -> "don t"
    re.compile(r"\bdon\s*t\s*(have|need)\s*to\s*deposit\b"),
    re.compile(r"\bdoesn\s*t\s*(have|need)\s*to\s*deposit\b"),
    re.compile(r"\bwithout\s*a\s*deposit\b"),
    re.compile(r"\bno\s*need\s*to\s*deposit\b"),
)
_SIG_FREE = re.compile(r"\bfree\s*to\s*play\b|\bfree\s*game\b|\bf2p\b|\bfree\b")
_SIG_GAME = re.compile(r"\bgame\b|\bapp\b|\bsite\b")
_SIG_SOCIAL = re.compile(r"\bsocial\b|\bfriends?\b|\bcommunity\b")
_SIG_PROMOTIONAL = re.compile(r"\bcheck\s*out\b|\bjoin\s*my\b|\bshill\b")
_SIG_OFF_TOPIC = re.compile(r"\bporn\b|\bgore\b|\bdrug\b")


@dataclass(frozen=True, slots=True)
class Signals:
    asks_recommendation: bool
    mentions_no_deposit: bool
    mentions_free: bool
    mentions_game: bool
    mentions_social: bool
    promotional: bool
    off_topic: bool


def detect_signals(message: str) -> Signals:
    m = normalise_text(message)
    return Signals(
        asks_recommendation=bool(_SIG_RECOMMENDATION.search(m)),
        mentions_no_deposit=any(p.search(m) for p in _SIG_NO_DEPOSIT),
        mentions_free=bool(_SIG_FREE.search(m)),
        mentions_game=bool(_SIG_GAME.search(m)),
        mentions_social=bool(_SIG_SOCIAL.search(m)),
        promotional=bool(_SIG_PROMOTIONAL.search(m)),
        off_topic=bool(_SIG_OFF_TOPIC.search(m)),
    )


def determine_confidence(
    contributions: list[ScoreContribution], risk_flags: list[RiskFlag]
) -> Confidence:
    """A hard risk flag is itself an unambiguous signal, so it reads as high
    confidence even though the conversation is unusable."""
    if risk_flags and "negative_keyword" not in risk_flags:
        return "high"
    total_abs = sum(abs(c.points) for c in contributions)
    if total_abs >= 30:
        return "high"
    if total_abs >= 12:
        return "medium"
    return "low"


def intent_from_score(score: int, thresholds, has_risk_flag: bool) -> Intent:
    """Thresholds are lower bounds. Any risk flag forces ``not_relevant``."""
    if has_risk_flag:
        return "not_relevant"
    if score >= thresholds.high:
        return "high"
    if score >= thresholds.medium:
        return "medium"
    if score >= thresholds.low:
        return "low"
    return "not_relevant"


def score_message(
    message: str,
    config: TuningConfig,
    country: str | None = None,
    posted_at: datetime | None = None,
) -> ScoreResult:
    """Pure function: same inputs always produce the same score."""
    normalised = normalise_text(message)
    tokens = tokenise(message)
    contributions: list[ScoreContribution] = []
    matched_keywords: list[str] = []

    risk_flags = detect_risk_flags(message)

    # Negative-keyword risk flag (config-dependent, so not in detect_risk_flags)
    for nk in config.negative_keywords:
        if match_keyword(tokens, normalised, nk.term, nk.match_type).hit:
            risk_flags.append("negative_keyword")
            break

    # Positive keywords
    for kw in config.keywords:
        result = match_keyword(tokens, normalised, kw.term, kw.match_type)
        if result.hit:
            contributions.append(
                ScoreContribution(
                    rule_id=kw.id,
                    label=f'"{kw.term}" ({kw.match_type})',
                    points=js_round(kw.weight * result.weight),
                )
            )
            matched_keywords.append(kw.term)

    # Negative keywords
    for nk in config.negative_keywords:
        result = match_keyword(tokens, normalised, nk.term, nk.match_type)
        if result.hit:
            contributions.append(
                ScoreContribution(
                    rule_id=nk.id,
                    label=f'Negative: "{nk.term}"',
                    points=js_round(nk.weight * result.weight),
                )
            )
            if nk.term not in matched_keywords:
                matched_keywords.append(nk.term)

    # Signal boosts
    signals = detect_signals(message)
    boosts = config.scoring.boosts
    for flag, rule_id, label, points in (
        (signals.asks_recommendation, "signal_asks_recommendation",
         "Asks for a recommendation", boosts.asks_recommendation),
        (signals.mentions_no_deposit, "signal_no_deposit",
         "Mentions no deposit", boosts.mentions_no_deposit),
        (signals.mentions_free, "signal_free",
         "Mentions free / free-to-play", boosts.mentions_free),
        (signals.mentions_game, "signal_game",
         "Mentions game / app / site", boosts.mentions_game),
        (signals.mentions_social, "signal_social",
         "Mentions social / community", boosts.mentions_social),
    ):
        if flag:
            contributions.append(ScoreContribution(rule_id=rule_id, label=label, points=points))

    # Country priority
    if country:
        rule = next((c for c in config.countries if c.code == country), None)
        if rule is not None and rule.priority == "high":
            contributions.append(
                ScoreContribution(
                    rule_id=f"country_{country}",
                    label=f"High-priority country ({country})",
                    points=boosts.high_priority_country,
                )
            )
        elif rule is not None and rule.priority == "low":
            contributions.append(
                ScoreContribution(
                    rule_id=f"country_{country}",
                    label=f"Low-priority country ({country})",
                    points=config.scoring.penalties.low_priority_country,
                )
            )

    # Freshness
    if posted_at is not None:
        if posted_at.tzinfo is None:
            posted_at = posted_at.replace(tzinfo=UTC)
        age_hours = (datetime.now(UTC) - posted_at).total_seconds() / 3600
        if age_hours < 24:
            contributions.append(
                ScoreContribution(
                    rule_id="recent_post",
                    label="Posted within 24h",
                    points=boosts.recent_post,
                )
            )

    # Penalties
    if signals.off_topic:
        contributions.append(
            ScoreContribution(
                rule_id="off_topic",
                label="Off-topic content",
                points=config.scoring.penalties.off_topic,
            )
        )
        risk_flags.append("off_topic")
    if signals.promotional:
        contributions.append(
            ScoreContribution(
                rule_id="promotional",
                label="Promotional bait",
                points=config.scoring.penalties.promotional,
            )
        )
        if "spam" not in risk_flags:
            risk_flags.append("spam")

    score = max(0, min(100, sum(c.points for c in contributions)))
    return ScoreResult(
        score=score,
        intent=intent_from_score(score, config.thresholds, bool(risk_flags)),
        confidence=determine_confidence(contributions, risk_flags),
        matched_keywords=matched_keywords,
        contributions=contributions,
        risk_flags=risk_flags,
    )
