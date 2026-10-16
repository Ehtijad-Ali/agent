"""Telegram connector tests.

Normalisation and pseudonymisation are pure, so they are tested directly. No
network calls are made.
"""

from __future__ import annotations

import asyncio
from datetime import UTC

import httpx
import pytest

from app.integrations import telegram as telegram_module
from app.integrations.telegram import (
    MAX_ATTEMPTS,
    TelegramConnector,
    TelegramError,
    _retry_after,
)
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


class TestErrorMapping:
    """Status codes must map to messages that name the actual fix."""

    @pytest.mark.parametrize(
        "status,expected",
        [
            (401, "unauthorised"),
            (429, "rate limited"),
        ],
    )
    def test_messages_are_actionable(self, status, expected):
        response = httpx.Response(status, headers={"Retry-After": "5"})
        with pytest.raises(TelegramError, match=expected):
            TelegramConnector._handle(response, "getMe")

    def test_ok_false_surfaces_the_description(self):
        response = httpx.Response(
            200, json={"ok": False, "description": "chat not found", "error_code": 400}
        )
        with pytest.raises(TelegramError, match="chat not found"):
            TelegramConnector._handle(response, "sendMessage")


class TestRetryAfter:
    """Telegram reports the flood-wait delay in two different places."""

    def test_reads_the_header(self):
        assert _retry_after(httpx.Response(429, headers={"Retry-After": "7"})) == 7.0

    def test_falls_back_to_the_json_body(self):
        """Unlike Discord, Telegram often sends the delay only in the body."""
        response = httpx.Response(429, json={"ok": False, "parameters": {"retry_after": 12}})
        assert _retry_after(response) == 12.0

    def test_caps_absurd_values(self):
        # A bad header must not park ingestion for an hour.
        assert _retry_after(httpx.Response(429, headers={"Retry-After": "3600"})) == 30.0

    def test_defaults_when_unparseable(self):
        assert _retry_after(httpx.Response(429, headers={"Retry-After": "soon"})) == 1.0

    def test_defaults_on_an_empty_body(self):
        assert _retry_after(httpx.Response(429)) == 1.0


class TestRateLimitRetry:
    """A 429 is waited out and retried rather than raised on first sight.

    Without this the connector fell over on its own second request: Telegram's
    per-chat flood limits trip routinely when a scan walks several chats in a
    row, and one 429 abandoned the remainder of the cycle.
    """

    @staticmethod
    def _patch(monkeypatch, responses):
        calls: list[str] = []
        slept: list[float] = []

        class _FakeClient:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def post(self, url, json=None):
                calls.append(url)
                return responses[min(len(calls) - 1, len(responses) - 1)]

        async def _fake_sleep(seconds):
            slept.append(seconds)

        monkeypatch.setattr(telegram_module.httpx, "AsyncClient", _FakeClient)
        monkeypatch.setattr(telegram_module.asyncio, "sleep", _fake_sleep)
        return calls, slept

    def test_retries_then_succeeds(self, connector, monkeypatch):
        calls, slept = self._patch(
            monkeypatch,
            [
                httpx.Response(429, headers={"Retry-After": "2"}),
                httpx.Response(200, json={"ok": True, "result": {"username": "bot"}}),
            ],
        )
        assert asyncio.run(connector._call("getMe")) == {"username": "bot"}
        assert len(calls) == 2, "the 429 should have been retried"
        assert slept == [2.0], "it should wait exactly as long as Telegram asked"

    def test_gives_up_after_max_attempts(self, connector, monkeypatch):
        calls, slept = self._patch(
            monkeypatch, [httpx.Response(429, headers={"Retry-After": "1"})]
        )
        # Specifically the exhaustion message, not the per-call "retry after Ns"
        # one -- after three refusals the caller needs to know it gave up.
        with pytest.raises(TelegramError, match="still rate limited after 3 attempts"):
            asyncio.run(connector._call("getMe"))
        assert len(calls) == MAX_ATTEMPTS
        assert len(slept) == MAX_ATTEMPTS - 1, "no sleep after the final attempt"

    def test_does_not_retry_other_errors(self, connector, monkeypatch):
        """Only 429 is transient. A 401 must fail immediately."""
        calls, slept = self._patch(monkeypatch, [httpx.Response(401)])
        with pytest.raises(TelegramError, match="unauthorised"):
            asyncio.run(connector._call("getMe"))
        assert len(calls) == 1
        assert slept == []


class TestHealthCheck:
    def _run(self, connector, monkeypatch, me):
        async def fake_call(method, **params):
            return me

        monkeypatch.setattr(connector, "_call", fake_call)
        return asyncio.run(connector.health_check())

    def test_flags_group_joining_disabled(self, connector, monkeypatch):
        status = self._run(
            connector,
            monkeypatch,
            {"username": "bot", "can_join_groups": False, "can_read_all_group_messages": True},
        )
        assert status.status == "connected"
        assert "/setjoingroups" in status.detail

    def test_clean_when_fully_configured(self, connector, monkeypatch):
        status = self._run(
            connector,
            monkeypatch,
            {"username": "bot", "can_join_groups": True, "can_read_all_group_messages": True},
        )
        assert status.status == "connected"
        assert status.detail.startswith("Connected as @bot.")
        assert "/setjoingroups" not in status.detail
        assert "re-added" in status.detail

    def test_webhook_blocks_polling(self, connector, monkeypatch):
        async def fake_call(method, **params):
            if method == "getWebhookInfo":
                return {"url": "https://example.com/hook"}
            return {"username": "bot", "can_join_groups": True,
                    "can_read_all_group_messages": True}

        monkeypatch.setattr(connector, "_call", fake_call)
        status = asyncio.run(connector.health_check())
        assert status.status == "error"
        assert "webhook" in status.error


class TestPollReport:
    def _poll(self, connector, monkeypatch, updates):
        seen = {}

        async def fake_call(method, **params):
            seen.update(params)
            return updates

        monkeypatch.setattr(connector, "_call", fake_call)
        msgs = asyncio.run(connector.fetch_messages())
        return msgs, seen

    def test_requests_membership_updates(self, connector, monkeypatch):
        _, params = self._poll(connector, monkeypatch, [])
        assert "my_chat_member" in params["allowed_updates"]
        assert connector.last_poll["updates"] == 0

    def test_records_bot_added_and_skipped_messages(self, connector, monkeypatch):
        sticker = _message(text=None)
        updates = [
            {"update_id": 1, "my_chat_member": {
                "chat": {"id": -1, "title": "Test Group"},
                "old_chat_member": {"status": "left"},
                "new_chat_member": {"status": "member"}}},
            {"update_id": 2, "message": _message()},
            {"update_id": 3, "message": sticker},
        ]
        msgs, _ = self._poll(connector, monkeypatch, updates)
        assert len(msgs) == 1
        poll = connector.last_poll
        assert poll["updates"] == 3
        assert poll["textMessages"] == 1
        assert poll["skippedNoText"] == 1
        assert poll["chats"] == ["@freegameschat"]
        assert poll["events"] == [{"action": "bot added to group", "chat": "Test Group"}]
