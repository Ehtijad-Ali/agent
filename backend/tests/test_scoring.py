"""Scoring engine tests (spec §33).

Covers determinism, score boundaries, risk detection, and the blocking rules
that the Safety engine depends on.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.defaults import default_tuning
from app.services.scoring_service import (
    detect_risk_flags,
    detect_signals,
    intent_from_score,
    score_message,
)


@pytest.fixture
def config():
    return default_tuning()


class TestDeterminism:
    def test_same_input_same_output(self, config):
        msg = "anyone know a free prediction game with no deposit?"
        first = score_message(msg, config, "US")
        second = score_message(msg, config, "US")
        assert first.score == second.score
        assert [c.rule_id for c in first.contributions] == [
            c.rule_id for c in second.contributions
        ]

    def test_score_is_clamped(self, config):
        # Stack every positive signal; must not exceed 100.
        msg = (
            "anyone know a good free game? free to play prediction game, "
            "no deposit, play without depositing, social prediction with friends"
        )
        result = score_message(msg, config, "US", datetime.now(UTC))
        assert 0 <= result.score <= 100

    def test_floor_at_zero(self, config):
        msg = "i want a real money gambling site with crypto withdrawal, under 18"
        assert score_message(msg, config, "NG").score >= 0


class TestContributions:
    def test_breakdown_is_returned_and_sums_to_score(self, config):
        msg = "anyone know a free prediction game? no deposit, playing with friends"
        result = score_message(msg, config)
        assert result.contributions
        raw = sum(c.points for c in result.contributions)
        assert result.score == max(0, min(100, raw))

    def test_labels_match_frontend_format(self, config):
        # The Inspector renders these verbatim -- format is contract.
        result = score_message("looking for a free game", config)
        labels = [c.label for c in result.contributions]
        assert '"free game" (phrase)' in labels
        assert "Asks for a recommendation" in labels

    def test_negative_keyword_label_prefix(self, config):
        result = score_message("i want real money betting", config)
        assert any(c.label.startswith('Negative: "') for c in result.contributions)


class TestIntentBands:
    @pytest.mark.parametrize(
        "score,expected",
        [(100, "high"), (80, "high"), (79, "medium"), (60, "medium"),
         (59, "low"), (40, "low"), (39, "not_relevant"), (0, "not_relevant")],
    )
    def test_boundaries(self, config, score, expected):
        assert intent_from_score(score, config.thresholds, False) == expected

    def test_risk_flag_forces_not_relevant(self, config):
        assert intent_from_score(100, config.thresholds, True) == "not_relevant"


class TestRiskDetection:
    @pytest.mark.parametrize(
        "msg",
        ["im 15 and looking for a game", "i am 16 years old", "under 18 here",
         "im underage", "17 years old"],
    )
    def test_underage(self, msg):
        assert "underage" in detect_risk_flags(msg)

    @pytest.mark.parametrize(
        "msg",
        ["looking for real money betting", "want to deposit crypto",
         "withdraw winnings fast", "any good gambling site?"],
    )
    def test_real_money(self, msg):
        assert "real_money" in detect_risk_flags(msg)

    @pytest.mark.parametrize(
        "msg",
        ["join my discord discord.gg/abc", "check out t.me/mylink",
         "DM me for link", "promo code in my profile", "referral link below"],
    )
    def test_spam(self, msg):
        assert "spam" in detect_risk_flags(msg)

    def test_clean_message_has_no_flags(self):
        assert detect_risk_flags("anyone know a fun free game to play?") == []

    def test_adult_age_is_not_underage(self):
        assert "underage" not in detect_risk_flags("im 25 and looking for a game")


class TestBlockingRules:
    """Spec §15: these two must never reach reply generation."""

    def test_underage_is_not_relevant_regardless_of_score(self, config):
        msg = "im 15, anyone know a free prediction game? no deposit, with friends"
        result = score_message(msg, config, "US")
        assert "underage" in result.risk_flags
        assert result.intent == "not_relevant"

    def test_real_money_request_is_flagged(self, config):
        msg = "anyone know a real money gambling site? want to deposit cash"
        result = score_message(msg, config, "US")
        assert "real_money" in result.risk_flags
        assert result.intent == "not_relevant"


class TestSignals:
    def test_no_deposit_variants(self):
        for msg in [
            "no deposit please",
            "play without depositing",
            "i don't have to deposit right?",
            "without a deposit",
        ]:
            assert detect_signals(msg).mentions_no_deposit, msg

    def test_country_priority_applies(self, config):
        msg = "anyone know a free prediction game?"
        high = score_message(msg, config, "US")
        low = score_message(msg, config, "IN")
        assert high.score > low.score

    def test_freshness_boost(self, config):
        msg = "anyone know a free prediction game?"
        fresh = score_message(msg, config, "US", datetime.now(UTC) - timedelta(hours=1))
        stale = score_message(msg, config, "US", datetime.now(UTC) - timedelta(days=10))
        assert fresh.score > stale.score


class TestNegativeKeywords:
    def test_penalty_is_applied(self, config):
        clean = score_message("anyone know a free prediction game?", config)
        dirty = score_message(
            "anyone know a free prediction game? real money only", config
        )
        assert dirty.score < clean.score
        assert "negative_keyword" in dirty.risk_flags


class TestCriticalEndToEnd:
    """Spec §33: a relevant message must never return zero matched keywords."""

    def test_relevant_message_matches_keywords(self, config):
        msg = "Anyone know a game I can play with friends without depositing money?"
        result = score_message(msg, config, "US")
        assert result.matched_keywords, (
            "Relevant message produced zero matched keywords -- spec §33 failure"
        )
        assert "no deposit" in result.matched_keywords
        assert result.score > 0
