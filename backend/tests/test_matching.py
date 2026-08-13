"""Matcher tests (spec §33).

These mirror the 49 TypeScript tests in src/lib/__tests__/scoring.test.ts. If a
case passes here and fails there (or vice versa) the two engines have drifted
and the frontend will render an explanation the backend did not produce.
"""

from __future__ import annotations

import pytest

from app.services.matching_service import (
    edit_distance,
    match_keyword,
    normalise_text,
    stem,
    tokenise,
)


class TestNormaliseText:
    def test_lowercases(self):
        assert normalise_text("ANYONE Know A Game") == "anyone know a game"

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("free game!!!", "free game"),
            ("no-deposit, please.", "no deposit please"),
            ("what's a good game?", "what s a good game"),
            ("free   game\n\tnow", "free game now"),
        ],
    )
    def test_strips_punctuation_and_collapses_whitespace(self, raw, expected):
        assert normalise_text(raw) == expected

    def test_keeps_unicode_letters(self):
        # Accented text must survive; the matcher supports non-English messages.
        assert normalise_text("prédiction gratuite!") == "prédiction gratuite"

    def test_nfkc_folds_fullwidth(self):
        assert normalise_text("ｆｒｅｅ ｇａｍｅ") == "free game"

    def test_empty(self):
        assert normalise_text("") == ""
        assert normalise_text("!!!") == ""


class TestStem:
    @pytest.mark.parametrize(
        "word,expected",
        [
            ("depositing", "deposit"),
            ("playing", "play"),
            ("played", "play"),
            ("games", "game"),
            ("friends", "friend"),
            ("countries", "country"),
            ("boxes", "box"),
        ],
    )
    def test_strips_suffixes(self, word, expected):
        assert stem(word) == expected

    @pytest.mark.parametrize("word", ["bus", "this", "loss", "app", "fun"])
    def test_leaves_short_and_ambiguous_words_alone(self, word):
        assert stem(word) == word


class TestTokenise:
    def test_removes_stopwords(self):
        tokens = tokenise("the quick brown fox jumps over the lazy dog")
        assert "the" not in tokens
        assert "over" not in tokens
        assert "quick" in tokens

    def test_stems_tokens(self):
        tokens = tokenise("playing games with depositing")
        assert "play" in tokens
        assert "game" in tokens
        assert "deposit" in tokens

    def test_no_deposit_reduces_to_deposit(self):
        # "no" is a stopword. This is the mechanism the §33 critical test relies
        # on -- if it changes, that test fails.
        assert tokenise("no deposit") == ["deposit"]

    def test_drops_single_characters(self):
        assert "a" not in tokenise("a free game")


class TestEditDistance:
    def test_identical(self):
        assert edit_distance("deposit", "deposit") == 0

    def test_single_edit(self):
        assert edit_distance("gamble", "gambl") == 1
        assert edit_distance("game", "gaem") == 2

    def test_short_circuits_beyond_max(self):
        assert edit_distance("a", "abcdefgh", 2) == 3


class TestPhraseMatching:
    def test_direct_substring(self):
        msg = "looking for a free game to play"
        assert match_keyword(tokenise(msg), normalise_text(msg), "free game", "phrase").hit

    def test_matches_across_inflection(self):
        msg = "play without depositing money"
        assert match_keyword(
            tokenise(msg), normalise_text(msg), "play without depositing", "phrase"
        ).hit

    def test_requires_all_tokens(self):
        # "real money" must NOT match a message that only says "money".
        msg = "i have no money for this"
        assert not match_keyword(
            tokenise(msg), normalise_text(msg), "real money", "phrase"
        ).hit

    def test_non_adjacent_scores_lower(self):
        adjacent = "i want a free game"
        scattered = "free stuff, and separately, a game"
        near = match_keyword(
            tokenise(scattered), normalise_text(scattered), "free game", "phrase"
        )
        exact = match_keyword(
            tokenise(adjacent), normalise_text(adjacent), "free game", "phrase"
        )
        assert near.hit and exact.hit
        assert near.weight < exact.weight

    def test_no_match(self):
        msg = "what time does the shop close"
        assert not match_keyword(
            tokenise(msg), normalise_text(msg), "prediction game", "phrase"
        ).hit


class TestBroadMatching:
    def test_matches_single_token(self):
        msg = "any betting recommendations"
        result = match_keyword(tokenise(msg), normalise_text(msg), "betting game", "broad")
        assert result.hit
        assert result.weight == pytest.approx(0.5)  # 1 of 2 tokens

    def test_no_tokens_match(self):
        msg = "how do i fix my router"
        assert not match_keyword(
            tokenise(msg), normalise_text(msg), "betting game", "broad"
        ).hit


class TestCriticalPhraseFamily:
    """Spec §33 CRITICAL TEST.

    A relevant message returning zero matched keywords is a failure.
    """

    MESSAGE = "Anyone know a game I can play with friends without depositing money?"

    def test_no_deposit_family_is_detected(self):
        tokens = tokenise(self.MESSAGE)
        normalised = normalise_text(self.MESSAGE)
        assert match_keyword(tokens, normalised, "no deposit", "phrase").hit, (
            "The configured phrase 'no deposit' must match "
            "'without depositing money'. Check STOP_WORDS still contains "
            "'no' and 'without', and that the stemmer maps depositing -> deposit."
        )

    def test_related_phrases_also_match(self):
        tokens = tokenise(self.MESSAGE)
        normalised = normalise_text(self.MESSAGE)
        assert match_keyword(tokens, normalised, "play without depositing", "phrase").hit
        assert match_keyword(tokens, normalised, "anyone know a game", "phrase").hit
