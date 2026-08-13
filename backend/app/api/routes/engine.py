"""Scoring-engine endpoints: playground, tuning read, and live preview.

These are pure functions over the scoring engine and need no database, which is
why they are the first routes to come online. Conversation, auth and reply
endpoints arrive with Phase 2 and depend on Postgres.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.defaults import NON_NEGOTIABLE_RULES, default_tuning
from app.schemas.playground import (
    AnalyzeRequest,
    AnalyzeResponse,
    PreviewRequest,
    PreviewResponse,
    PreviewResult,
    ScoreContributionOut,
)
from app.schemas.tuning import TuningConfig
from app.services.reply_service import detect_language, draft_all_variants
from app.services.scoring_service import intent_from_score, score_message

router = APIRouter(tags=["engine"])

# Phase 1 holds the active config in memory. Phase 2 moves it to the
# configuration_versions table so edits are versioned and auditable (spec §4).
_active_config: TuningConfig = default_tuning()


@router.get("/tuning", response_model=TuningConfig)
def get_tuning() -> TuningConfig:
    return _active_config


@router.put("/tuning", response_model=TuningConfig)
def put_tuning(config: TuningConfig) -> TuningConfig:
    """Persisted in memory only until Phase 2. Writing a configuration_versions
    row and an activity entry happens there."""
    global _active_config
    _active_config = config
    return _active_config


@router.get("/tuning/non-negotiables")
def get_non_negotiables() -> dict[str, list[str]]:
    """Locked rules shown as disabled toggles in Tuning. Enforced server-side
    in the reply safety check; the API cannot switch them off (spec §15)."""
    return {"rules": list(NON_NEGOTIABLE_RULES)}


@router.post("/tuning/preview", response_model=PreviewResponse)
def preview(request: PreviewRequest) -> PreviewResponse:
    """Spec §21. Re-score samples against a candidate config without saving."""
    results: list[PreviewResult] = []
    for sample in request.samples:
        scored = score_message(sample.message, request.config, sample.country)
        results.append(
            PreviewResult(
                conversation_id=sample.conversation_id,
                old_score=sample.old_score,
                new_score=scored.score,
                delta=scored.score - sample.old_score,
                intent=scored.intent,
            )
        )
    return PreviewResponse(results=results)


@router.post("/playground/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """Spec §22. Uses exactly the same engine as ingestion -- there is no
    separate simplified playground path."""
    result = score_message(request.message, _active_config, request.country)

    community = request.community or "your community"
    variants = draft_all_variants(community, _active_config.voice)

    if result.matched_keywords:
        joined = ", ".join(result.matched_keywords)
        plural = "" if len(result.matched_keywords) == 1 else "s"
        summary = f"Matched {len(result.matched_keywords)} configured keyword{plural}: {joined}."
    else:
        summary = "No keywords matched, and the message is not asking for a recommendation."

    return AnalyzeResponse(
        score=result.score,
        intent=result.intent,
        confidence=result.confidence,
        matched_keywords=result.matched_keywords,
        contributions=[
            ScoreContributionOut(rule_id=c.rule_id, label=c.label, points=c.points)
            for c in result.contributions
        ],
        risk_flags=list(result.risk_flags),
        language=detect_language(request.message),
        summary=summary,
        reply=variants[0]["text"],
        reply_variants=variants,
    )


# Re-exported so Phase 2 services can read the same in-memory config.
def active_config() -> TuningConfig:
    return _active_config
