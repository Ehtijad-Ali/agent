"""Scoring-engine endpoints: playground, tuning read, and live preview.

These are pure functions over the scoring engine and need no database, which is
why they are the first routes to come online. Conversation, auth and reply
endpoints arrive with Phase 2 and depend on Postgres.
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.defaults import NON_NEGOTIABLE_RULES, default_tuning
from app.db.session import get_db, get_sessionmaker
from app.models import ActivityEntry, ConfigurationVersion, TuningPreset
from app.schemas.base import CamelModel
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
logger = logging.getLogger("signal.engine")

# Until auth lands, config edits are attributed to the single local operator.
ACTOR = "you"

# The active config is cached in process and backed by the
# configuration_versions table, so every edit is versioned and auditable
# (spec §4). Ingestion reads it through get_active_config() rather than keeping
# its own copy, so scoring cannot drift from what Tuning shows.
_active_config: TuningConfig = default_tuning()


def get_active_config() -> TuningConfig:
    """The config both the API and ingestion score against."""
    return _active_config


def load_active_config() -> None:
    """Restore the highest-numbered saved version at startup.

    Without this a restart silently reverts scoring to defaults while the
    Tuning screen still shows the saved values on next save.
    """
    global _active_config
    factory = get_sessionmaker()
    if factory is None:
        return
    db = factory()
    try:
        row = db.execute(
            select(ConfigurationVersion).order_by(ConfigurationVersion.version.desc()).limit(1)
        ).scalar_one_or_none()
        if row is not None:
            _active_config = TuningConfig.model_validate(row.payload)
            logger.info("Loaded tuning config version %s", row.version)
    except Exception:  # noqa: BLE001 -- a corrupt row must not stop the app booting
        logger.exception("Could not load saved tuning config; using defaults")
    finally:
        db.close()


@router.get("/tuning", response_model=TuningConfig)
def get_tuning() -> TuningConfig:
    return _active_config


def _persist_config(db: Session, config: TuningConfig) -> None:
    """Write a new configuration_versions row plus its audit entry."""
    highest = db.execute(select(func.max(ConfigurationVersion.version))).scalar()
    version = (highest or 0) + 1
    db.add(
        ConfigurationVersion(
            version=version,
            payload=config.model_dump(mode="json", by_alias=True),
            actor=ACTOR,
        )
    )
    db.add(
        ActivityEntry(
            actor=ACTOR,
            action="saved tuning config",
            item=f"version {version}",
            after=f"{len(config.keywords)} keyword(s)",
        )
    )
    db.commit()


@router.put("/tuning", response_model=TuningConfig)
def put_tuning(
    config: TuningConfig, db: Session = Depends(get_db)
) -> TuningConfig:
    """Writes a new configuration_versions row rather than mutating one, so a
    scoring change is attributable and reversible (spec §4).

    Takes the session from the dependency rather than the global factory, so it
    runs in the request's transaction and can be tested against an injected
    database.
    """
    global _active_config
    _active_config = config
    _persist_config(db, config)
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


# --- presets (brief §5) ----------------------------------------------------


class PresetOut(CamelModel):
    id: str
    name: str
    created_at: datetime
    config: TuningConfig


class PresetCreate(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    # Omitted means "snapshot whatever is active right now", which is how an
    # operator actually uses this: tune until it feels right, then name it.
    config: TuningConfig | None = None


@router.get("/tuning/presets", response_model=list[PresetOut])
def list_presets(db: Session = Depends(get_db)) -> list[PresetOut]:
    rows = (
        db.execute(select(TuningPreset).order_by(TuningPreset.created_at.desc()))
        .scalars()
        .all()
    )
    return [
        PresetOut(
            id=r.id,
            name=r.name,
            created_at=r.created_at,
            config=TuningConfig.model_validate(r.config),
        )
        for r in rows
    ]


@router.post(
    "/tuning/presets", response_model=PresetOut, status_code=status.HTTP_201_CREATED
)
def create_preset(
    request: PresetCreate, db: Session = Depends(get_db)
) -> PresetOut:
    config = request.config or get_active_config()
    preset = TuningPreset(
        name=request.name.strip(),
        config=config.model_dump(mode="json", by_alias=True),
    )
    db.add(preset)
    db.add(
        ActivityEntry(actor=ACTOR, action="saved preset", item=preset.name)
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A preset named '{request.name}' already exists.",
        ) from exc

    db.refresh(preset)
    return PresetOut(
        id=preset.id,
        name=preset.name,
        created_at=preset.created_at,
        config=TuningConfig.model_validate(preset.config),
    )


@router.post("/tuning/presets/{preset_id}/apply", response_model=TuningConfig)
def apply_preset(preset_id: str, db: Session = Depends(get_db)) -> TuningConfig:
    """Make a preset the active config.

    Routed through put_tuning so applying a preset writes a
    configuration_versions row like any other change -- a preset must not be a
    way to alter scoring without an audit trail.
    """
    preset = db.get(TuningPreset, preset_id)
    if preset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No preset with id {preset_id}.",
        )
    return put_tuning(TuningConfig.model_validate(preset.config), db)


@router.delete("/tuning/presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_preset(preset_id: str, db: Session = Depends(get_db)) -> None:
    preset = db.get(TuningPreset, preset_id)
    if preset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No preset with id {preset_id}.",
        )
    db.delete(preset)
    db.add(ActivityEntry(actor=ACTOR, action="deleted preset", item=preset.name))
    db.commit()


def reset_active_config() -> None:
    """Restore the built-in defaults.

    The active config is process-global, so without this one test (or one
    operator session) mutating it leaks into everything after it.
    """
    global _active_config
    _active_config = default_tuning()
