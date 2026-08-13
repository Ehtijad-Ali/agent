"""Reply drafting tests.

The load-bearing rule: a draft must never lose the brand disclosure, the
free-to-play note, or the link, whatever the configured length cap. Spec §17
rejects a reply missing the first two, so a drafter that truncates them
produces replies that cannot be sent.
"""

from __future__ import annotations

import pytest

from app.schemas.tuning import VoiceConfig
from app.services.reply_service import (
    DISCLOSURE,
    FREE_TO_PLAY,
    PRODUCT_URL,
    TONES,
    detect_language,
    draft_all_variants,
    draft_reply,
)

COMMUNITY = "r/socialprediction"


@pytest.mark.parametrize("tone", TONES)
@pytest.mark.parametrize("max_length", [280, 320, 400, 600])
def test_mandatory_parts_always_survive(tone, max_length):
    text = draft_reply(COMMUNITY, tone, VoiceConfig(max_length=max_length))
    assert DISCLOSURE in text, f"{tone}@{max_length} lost the disclosure"
    assert FREE_TO_PLAY in text, f"{tone}@{max_length} lost the free-to-play note"
    assert PRODUCT_URL in text, f"{tone}@{max_length} lost the link"


@pytest.mark.parametrize("tone", TONES)
def test_respects_length_cap_at_default(tone):
    voice = VoiceConfig(max_length=280)
    assert len(draft_reply(COMMUNITY, tone, voice)) <= 280


def test_regression_url_was_being_truncated_away():
    """At the default 280 the helpful variant used to end 'Link if it's
    useful:…' with the URL cut off entirely."""
    text = draft_reply(COMMUNITY, "helpful", VoiceConfig(max_length=280))
    assert not text.rstrip().endswith(":…")
    assert text.endswith(PRODUCT_URL)


def test_body_is_what_gets_sacrificed():
    roomy = draft_reply(COMMUNITY, "helpful", VoiceConfig(max_length=600))
    tight = draft_reply(COMMUNITY, "helpful", VoiceConfig(max_length=280))
    assert len(tight) < len(roomy)
    for part in (DISCLOSURE, FREE_TO_PLAY, PRODUCT_URL):
        assert part in tight and part in roomy


def test_three_distinct_variants():
    """Spec §16: genuinely different, not repeated boilerplate."""
    variants = draft_all_variants(COMMUNITY, VoiceConfig())
    assert [v["tone"] for v in variants] == list(TONES)
    texts = [v["text"] for v in variants]
    assert len(set(texts)) == 3


def test_voice_controls_change_the_output():
    formal = draft_reply(COMMUNITY, "helpful", VoiceConfig(formality=80))
    friendly = draft_reply(COMMUNITY, "helpful", VoiceConfig(formality=10, friendliness=90))
    assert formal.startswith("Hello")
    assert friendly.startswith("Hey there")

    no_emoji = draft_reply(COMMUNITY, "helpful", VoiceConfig(emoji=0))
    with_emoji = draft_reply(COMMUNITY, "helpful", VoiceConfig(emoji=80, max_length=600))
    assert "🎯" not in no_emoji
    assert "🎯" in with_emoji


def test_community_is_referenced():
    """Spec §16: variants must reference the actual conversation."""
    text = draft_reply("r/freegames", "helpful", VoiceConfig(max_length=600))
    assert "r/freegames" in text


class TestLanguageDetection:
    @pytest.mark.parametrize(
        "message,expected",
        [
            ("anyone know a free prediction game?", "en"),
            ("alguem conhece um jogo de previsao gratuito?", "pt"),
            ("Cherche un jeu de pronostics gratuit", "fr"),
            ("Kennt jemand ein kostenloses Vorhersagespiel?", "de"),
            ("alguien sabe de un juego de prediccion gratis?", "es"),
        ],
    )
    def test_detects(self, message, expected):
        assert detect_language(message) == expected
