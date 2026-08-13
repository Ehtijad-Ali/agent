"""Playground and preview wire schemas.

Response shapes mirror ``AnalyseResult`` in ``src/lib/mockApi.ts`` and the
preview contract in spec §21, so the existing screens bind without changes.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.tuning import CamelModel, TuningConfig

Intent = Literal["high", "medium", "low", "not_relevant"]
Confidence = Literal["low", "medium", "high"]


class ScoreContributionOut(CamelModel):
    """Rendered verbatim by the Inspector -- label format is contract."""

    rule_id: str
    label: str
    points: int


class ReplyVariantOut(CamelModel):
    tone: str
    text: str


class AnalyzeRequest(CamelModel):
    message: str = Field(min_length=1, max_length=10_000)
    platform: str | None = None
    country: str | None = None
    community: str | None = None
    url: str | None = None


class AnalyzeResponse(CamelModel):
    score: int
    intent: Intent
    confidence: Confidence
    matched_keywords: list[str]
    contributions: list[ScoreContributionOut]
    risk_flags: list[str]
    language: str
    summary: str
    reply: str
    reply_variants: list[ReplyVariantOut]


class PreviewSampleIn(CamelModel):
    """One sample to re-score. ``old_score`` comes from the caller so the
    response can report a delta without a database round trip."""

    conversation_id: str
    message: str
    country: str | None = None
    old_score: int = 0


class PreviewRequest(CamelModel):
    """Spec §21. The supplied config is used for scoring only and is never
    persisted -- saving happens through PUT /api/tuning."""

    config: TuningConfig
    samples: list[PreviewSampleIn] = Field(default_factory=list, max_length=200)


class PreviewResult(CamelModel):
    conversation_id: str
    old_score: int
    new_score: int
    delta: int
    intent: Intent


class PreviewResponse(CamelModel):
    results: list[PreviewResult]
