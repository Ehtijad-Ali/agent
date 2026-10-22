"""Tuning configuration schemas.

Mirrors ``tuningConfigSchema`` in ``src/lib/types.ts``. Fields are snake_case in
Python and serialise to camelCase on the wire via ``alias_generator``, so the
existing frontend types need no changes (see docs/frontend-api-mapping.md §3).
"""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

MatchType = Literal["broad", "exact", "phrase"]
Priority = Literal["high", "medium", "low"]


class CamelModel(BaseModel):
    """Base: accepts either casing on input, always emits camelCase."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class KeywordRule(CamelModel):
    id: str
    term: str
    match_type: MatchType
    priority: int = Field(ge=1, le=5)
    weight: float
    # to_camel() emits "hits7D", but the contract in src/lib/types.ts says
    # "hits7d". Serialisation is pinned to the contract; validation accepts the
    # old spelling too, so configuration_versions rows written before this was
    # fixed still load instead of silently resetting to 0.
    hits7d: int = Field(
        default=0,
        validation_alias=AliasChoices("hits7d", "hits7D"),
        serialization_alias="hits7d",
    )


class NegativeKeywordRule(CamelModel):
    id: str
    term: str
    match_type: MatchType
    weight: float
    # to_camel() emits "hits7D", but the contract in src/lib/types.ts says
    # "hits7d". Serialisation is pinned to the contract; validation accepts the
    # old spelling too, so configuration_versions rows written before this was
    # fixed still load instead of silently resetting to 0.
    hits7d: int = Field(
        default=0,
        validation_alias=AliasChoices("hits7d", "hits7D"),
        serialization_alias="hits7d",
    )


class CountryRule(CamelModel):
    code: str = Field(min_length=2, max_length=2)
    name: str
    priority: Priority
    enabled: bool = True
    # Brief §5: "languages to use per country". Empty means fall back to
    # voice.reply_language, so existing configs keep working unchanged.
    language: str = ""


class Thresholds(CamelModel):
    """Lower bounds. ``score >= high`` means high intent."""

    not_relevant: int = Field(ge=0, le=100, default=0)
    low: int = Field(ge=0, le=100, default=40)
    medium: int = Field(ge=0, le=100, default=60)
    high: int = Field(ge=0, le=100, default=80)


class VoiceConfig(CamelModel):
    friendliness: int = Field(ge=0, le=100, default=70)
    helpfulness: int = Field(ge=0, le=100, default=80)
    formality: int = Field(ge=0, le=100, default=35)
    cta_strength: int = Field(ge=0, le=100, default=55)
    emoji: int = Field(ge=0, le=100, default=20)
    max_length: int = Field(ge=80, le=600, default=280)
    reply_language: str = "en"


class ScoringBoosts(CamelModel):
    asks_recommendation: int = 14
    mentions_no_deposit: int = 18
    mentions_free: int = 12
    mentions_game: int = 10
    mentions_social: int = 8
    high_priority_country: int = 6
    recent_post: int = 4


class ScoringPenalties(CamelModel):
    negative_keyword: int = -15
    off_topic: int = -20
    promotional: int = -25
    low_priority_country: int = -4


class ScoringConfig(CamelModel):
    boosts: ScoringBoosts = Field(default_factory=ScoringBoosts)
    penalties: ScoringPenalties = Field(default_factory=ScoringPenalties)


class RateCaps(CamelModel):
    """Enforced before any reply is sent (spec §30)."""

    per_platform_per_hour: int = 5
    daily_approved_ceiling: int = 30


class TuningConfig(CamelModel):
    keywords: list[KeywordRule] = Field(default_factory=list)
    negative_keywords: list[NegativeKeywordRule] = Field(default_factory=list)
    countries: list[CountryRule] = Field(default_factory=list)
    thresholds: Thresholds = Field(default_factory=Thresholds)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    rate_caps: RateCaps = Field(default_factory=RateCaps)
