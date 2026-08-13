"""Telegram connector tests.

Normalisation and pseudonymisation are pure, so they are tested directly. No
network calls are made.
"""

from __future__ import annotations

from datetime import UTC

import pytest

from app.integrations.telegram import TelegramConnector
from app.utils.hashing import content_hash, pseudonymise

SALT = "test-salt-not-a-real-one"


@pytest.fixture
def connector():
    return TelegramConnector(bot_token="123:fake", pseudonym_salt=SALT)


def _message(**overrides):
    base = {
        "message_id": 42,
        "date": 1_700_000_000,
        "text": "anyone know a free prediction game?",
        "chat": {"id": -100123, "title": "Free Games Chat", "username": "freegameschat"},
        "from": {"id": 987654, "language_code": "en"},
    }
    base.update(overrides)
    return base


class TestNormalisation:
    def test_maps_to_shared_shape(self, connector):
        msg = connector.normalise_message(_message())
        assert msg is not None
        assert msg.platform == "telegram"
        assert msg.external_id == "-100123:42"
        assert msg.community == "@freegameschat"
        assert msg.message == "anyone know a free prediction game?"
        assert msg.language == "en"
        assert msg.posted_at.tzinfo is UTC

    def test_builds_source_url_for_public_chats(self, connector):
        assert connector.normalise_message(_message()).source_url == (
            "https://t.me/freegameschat/42"
        )

    def test_no_source_url_for_private_groups(self, connector):
        msg = connector.normalise_message(
            _message(chat={"id": -100123, "title": "Private Group"})
        )
        assert msg.source_url is None
        assert msg.community == "Private Group"

    def test_uses_caption_when_text_absent(self, connector):
        raw = _message(text=None)
        raw["caption"] = "free game with no deposit?"
        assert connector.normalise_message(raw).message == "free game with no deposit?"

    @pytest.mark.parametrize("text", [None, "", "   "])
    def test_skips_messages_with_no_usable_text(self, connector, text):
        raw = _message(text=text)
        raw.pop("caption", None)
        assert connector.normalise_message(raw) is None

    def test_channel_post_without_author_is_attributed_to_the_chat(self, connector):
        raw = _message()
        raw.pop("from")
        msg = connector.normalise_message(raw)
        assert msg is not None
        assert msg.author_pseudonym.startswith("user_")

    def test_country_is_not_inferred_from_language(self, connector):
        """language_code is the author's app language, not a location."""
        msg = connector.normalise_message(_message(**{"from": {"id": 1, "language_code": "de"}}))
        assert msg.language == "de"
        assert msg.country is None


class TestPseudonymisation:
    def test_real_handle_never_survives(self, connector):
        raw = _message(**{"from": {"id": 987654, "username": "realhandle", "first_name": "Dave"}})
        msg = connector.normalise_message(raw)
        serialised = repr(msg)
        assert "realhandle" not in serialised
        assert "Dave" not in serialised
        assert "987654" not in msg.author_pseudonym

    def test_deterministic(self):
        first = pseudonymise("telegram", "987654", SALT)
        second = pseudonymise("telegram", "987654", SALT)
        assert first == second == pseudonymise("telegram", "987654", SALT)

    def test_namespaced_by_platform(self):
        assert pseudonymise("telegram", "1", SALT) != pseudonymise("discord", "1", SALT)

    def test_salt_changes_the_output(self):
        assert pseudonymise("telegram", "1", "a") != pseudonymise("telegram", "1", "b")

    def test_refuses_empty_salt(self):
        with pytest.raises(ValueError, match="PSEUDONYM_SALT"):
            pseudonymise("telegram", "1", "")

    def test_expected_format(self):
        value = pseudonymise("telegram", "987654", SALT)
        assert value.startswith("user_")
        assert len(value) == len("user_") + 4


class TestContentHash:
    def test_ignores_whitespace_and_case(self):
        assert content_hash("telegram", "Free  Game?") == content_hash("telegram", "free game?")

    def test_differs_across_platforms(self):
        assert content_hash("telegram", "hi") != content_hash("discord", "hi")


class TestWebhookSecret:
    def test_accepts_match(self):
        assert TelegramConnector.verify_webhook_secret("s3cret", "s3cret")

    @pytest.mark.parametrize("received,expected", [("wrong", "s3cret"), (None, "s3cret"), ("s3cret", "")])
    def test_rejects_everything_else(self, received, expected):
        assert not TelegramConnector.verify_webhook_secret(received, expected)


def test_requires_a_token():
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        TelegramConnector(bot_token="", pseudonym_salt=SALT)
