"""Default tuning configuration.

Ported from ``DEFAULT_TUNING`` in ``src/lib/constants.ts``. Used to seed a fresh
database and as the target of "Reset to defaults". Keeping the values identical
to the frontend's means a freshly seeded backend scores the sample corpus the
same way the current client-only build does.
"""

from __future__ import annotations

from app.schemas.tuning import (
    CountryRule,
    KeywordRule,
    NegativeKeywordRule,
    RateCaps,
    ScoringBoosts,
    ScoringConfig,
    ScoringPenalties,
    Thresholds,
    TuningConfig,
    VoiceConfig,
)

_KEYWORDS = [
    ("kw1", "free game", "phrase", 5, 14, 142),
    ("kw2", "prediction game", "phrase", 5, 16, 98),
    ("kw3", "no deposit", "phrase", 5, 18, 76),
    ("kw4", "play without depositing", "phrase", 4, 15, 41),
    ("kw5", "free to play", "phrase", 4, 12, 88),
    ("kw6", "social prediction", "phrase", 4, 14, 35),
    ("kw7", "recommend a game", "phrase", 3, 12, 52),
    ("kw8", "anyone know a game", "phrase", 3, 10, 47),
    ("kw9", "betting game", "broad", 3, 8, 64),
    ("kw10", "prediction", "broad", 2, 5, 231),
    ("kw11", "fun game", "phrase", 2, 6, 119),
    ("kw12", "free betting", "phrase", 3, 10, 33),
]

_NEGATIVE_KEYWORDS = [
    ("nk1", "real money", "phrase", -25, 28),
    ("nk2", "deposit required", "phrase", -20, 14),
    ("nk3", "crypto", "broad", -15, 22),
    ("nk4", "withdrawal", "broad", -18, 19),
    ("nk5", "under 18", "phrase", -100, 3),
    ("nk6", "gambling site", "phrase", -22, 12),
]

_COUNTRIES = [
    ("US", "United States", "high", True),
    ("GB", "United Kingdom", "high", True),
    ("CA", "Canada", "high", True),
    ("AU", "Australia", "medium", True),
    ("DE", "Germany", "medium", True),
    ("FR", "France", "medium", True),
    ("BR", "Brazil", "low", True),
    ("IN", "India", "low", True),
    ("PH", "Philippines", "low", True),
    ("NG", "Nigeria", "low", False),
    ("ZA", "South Africa", "low", False),
    ("MX", "Mexico", "low", True),
]


def default_tuning() -> TuningConfig:
    """A fresh copy every call -- callers mutate this for preview scoring."""
    return TuningConfig(
        keywords=[
            KeywordRule(
                id=i, term=t, match_type=m, priority=p, weight=w, hits7d=h
            )
            for i, t, m, p, w, h in _KEYWORDS
        ],
        negative_keywords=[
            NegativeKeywordRule(id=i, term=t, match_type=m, weight=w, hits7d=h)
            for i, t, m, w, h in _NEGATIVE_KEYWORDS
        ],
        countries=[
            CountryRule(code=c, name=n, priority=p, enabled=e)
            for c, n, p, e in _COUNTRIES
        ],
        thresholds=Thresholds(not_relevant=0, low=40, medium=60, high=80),
        voice=VoiceConfig(),
        scoring=ScoringConfig(boosts=ScoringBoosts(), penalties=ScoringPenalties()),
        rate_caps=RateCaps(),
    )


# Non-negotiable reply rules, surfaced as locked toggles in Tuning (spec §15/§17).
# These are enforced server-side in the reply safety check and cannot be
# disabled through the API.
NON_NEGOTIABLE_RULES: tuple[str, ...] = (
    "Always disclose brand connection",
    "Always include 'free-to-play, not real money'",
    "Never post autonomously",
    "Never DM authors",
    "One reply per person, ever",
)
