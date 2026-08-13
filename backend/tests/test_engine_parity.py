"""Cross-engine parity: Python must score identically to the TypeScript engine.

``tests/fixtures/ts_engine_scores.json`` is real output captured from
``src/lib/scoring.ts`` running in the browser against the 60-message seed corpus
under DEFAULT_TUNING. It is a golden file, not something this suite generates.

Why this matters: spec §13 requires the frontend to render the exact score
explanation the backend produced, and §22 requires the Playground to use the
same engine as ingestion. If the two implementations drift, the Inspector shows
a breakdown that does not add up to the score next to it.

This already caught one real defect -- Python's ``round`` is banker's rounding,
so a partial phrase match worth ``10 * 0.85`` scored 8 in Python and 9 in JS.
See ``scoring_service.js_round``.

To regenerate after an intentional engine change, re-capture from the running
frontend; do not hand-edit the fixture.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from app.core.defaults import default_tuning
from app.services.scoring_service import score_message

FIXTURE = Path(__file__).parent / "fixtures" / "ts_engine_scores.json"


def _load():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _ids(rows):
    return [r["id"] for r in rows]


ROWS = _load()


@pytest.fixture(scope="module")
def config():
    return default_tuning()


def _score(row, config):
    posted = datetime.fromisoformat(row["postedAt"].replace("Z", "+00:00"))
    return score_message(row["message"], config, row["country"], posted)


def test_fixture_is_the_full_corpus():
    assert len(ROWS) == 60


@pytest.mark.parametrize("row", ROWS, ids=_ids(ROWS))
def test_score_matches(row, config):
    assert _score(row, config).score == row["score"], row["message"][:80]


@pytest.mark.parametrize("row", ROWS, ids=_ids(ROWS))
def test_matched_keywords_match(row, config):
    assert sorted(_score(row, config).matched_keywords) == sorted(row["matchedKeywords"])


@pytest.mark.parametrize("row", ROWS, ids=_ids(ROWS))
def test_intent_and_confidence_match(row, config):
    result = _score(row, config)
    assert result.intent == row["intent"]
    assert result.confidence == row["confidence"]


@pytest.mark.parametrize("row", ROWS, ids=_ids(ROWS))
def test_risk_flags_match(row, config):
    assert sorted(_score(row, config).risk_flags) == sorted(row["riskFlags"])


@pytest.mark.parametrize("row", ROWS, ids=_ids(ROWS))
def test_contributions_match_exactly(row, config):
    """Order, rule ids, labels and points all matter -- the frontend renders
    this list verbatim."""
    got = [(c.rule_id, c.label, c.points) for c in _score(row, config).contributions]
    expected = [(c["ruleId"], c["label"], c["points"]) for c in row["contributions"]]
    assert got == expected


def test_js_round_matches_math_round():
    """Regression guard for the banker's-rounding defect."""
    from app.services.scoring_service import js_round

    # Math.round in JS: 8.5 -> 9, -7.5 -> -7 (ties go toward +Infinity)
    assert js_round(8.5) == 9
    assert js_round(7.5) == 8
    assert js_round(-7.5) == -7
    assert js_round(2.4) == 2
    assert js_round(2.6) == 3
