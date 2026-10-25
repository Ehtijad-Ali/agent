"""Discord connector tests. No network calls."""

from __future__ import annotations

import pytest

from app.integrations.discord import DiscordConnector
from app.utils.hashing import pseudonymise

SALT = "test-salt-not-a-real-one"


@pytest.fixture
def connector():
    return DiscordConnector(bot_token="fake.token", pseudonym_salt=SALT)


def _message(**overrides):
    base = {
        "id": "1111111111111111111",
        "channel_id": "2222222222222222222",
        "guild_id": "3333333333333333333",
        "timestamp": "2026-08-13T10:30:00.000000+00:00",
        "content": "anyone know a free prediction game with no deposit?",
        "author": {"id": "4444444444444444444", "username": "someone", "bot": False},
    }
    base.update(overrides)
    return base


class TestNormalisation:
    def test_maps_to_shared_shape(self, connector):
        msg = connector.normalise_message(_message(), "Free Games", "general")
        assert msg is not None
        assert msg.platform == "discord"
        assert msg.external_id == "2222222222222222222:1111111111111111111"
        assert msg.community == "Free Games#general"
        assert msg.message.startswith("anyone know a free prediction game")

    def test_builds_deep_link(self, connector):
        msg = connector.normalise_message(_message(), "Free Games", "general")
        assert msg.source_url == (
            "https://discord.com/channels/3333333333333333333"
            "/2222222222222222222/1111111111111111111"
        )

    def test_parses_timestamp_as_utc(self, connector):
        msg = connector.normalise_message(_message(), "G", "c")
        assert msg.posted_at.year == 2026
        assert msg.posted_at.tzinfo is not None

    def test_survives_a_bad_timestamp(self, connector):
        msg = connector.normalise_message(_message(timestamp="not-a-date"), "G", "c")
        assert msg is not None  # falls back to now rather than dropping the message

    def test_drops_bot_messages(self, connector):
        raw = _message(author={"id": "9", "username": "otherbot", "bot": True})
        assert connector.normalise_message(raw, "G", "c") is None

    @pytest.mark.parametrize("content", ["", "   ", None])
    def test_drops_empty_content(self, connector, content):
        """Empty content is what a missing MESSAGE CONTENT intent looks like.
        Queueing those would fill the inbox with zero-scoring conversations."""
        assert connector.normalise_message(_message(content=content), "G", "c") is None

    def test_country_is_not_guessed(self, connector):
        """Discord exposes no user location; inferring one from server region
        would be wrong more often than right."""
        msg = connector.normalise_message(_message(), "G", "c")
        assert msg.country is None


class TestPseudonymisation:
    def test_real_identity_never_survives(self, connector):
        raw = _message(author={"id": "4444444444444444444", "username": "realhandle", "bot": False})
        msg = connector.normalise_message(raw, "G", "c")
        serialised = repr(msg)
        assert "realhandle" not in serialised
        assert "4444444444444444444" not in msg.author_pseudonym

    def test_deterministic_and_namespaced(self):
        a = pseudonymise("discord", "123", SALT)
        assert a == pseudonymise("discord", "123", SALT)
        assert a != pseudonymise("telegram", "123", SALT)


class TestAuth:
    def test_requires_a_token(self):
        with pytest.raises(ValueError, match="DISCORD_BOT_TOKEN"):
            DiscordConnector(bot_token="", pseudonym_salt=SALT)

    def test_uses_the_bot_scheme(self, connector):
        """Discord rejects a bare token; it must be prefixed with 'Bot '."""
        assert connector._headers["Authorization"] == "Bot fake.token"

    def test_identifies_itself(self, connector):
        assert "SignalBot" in connector._headers["User-Agent"]


class TestErrorMapping:
    """Status codes must map to messages that name the actual fix."""

    @pytest.mark.parametrize(
        "status,expected",
        [
            (401, "unauthorised"),
            (403, "Read Message History"),
            (429, "rate limited"),
        ],
    )
    def test_messages_are_actionable(self, status, expected):
        import httpx

        from app.integrations.discord import DiscordError

        response = httpx.Response(status, headers={"Retry-After": "5"})
        with pytest.raises(DiscordError, match=expected):
            DiscordConnector._handle(response, "GET /test")


class TestInviteAndOverview:
    def test_invite_url_requests_only_read_and_send(self):
        from app.integrations.discord import DiscordConnector

        url = DiscordConnector.invite_url("123")
        assert url.startswith("https://discord.com/oauth2/authorize?client_id=123")
        assert "scope=bot" in url
        assert "permissions=68608" in url  # view + send + read history

    def test_overview_marks_blocked_channels(self, monkeypatch):
        import asyncio

        from app.integrations.discord import DiscordConnector, DiscordError

        connector = DiscordConnector("fake", "salt")

        async def fake_get(path, **params):
            if path == "/users/@me/guilds":
                return [{"id": "g1", "name": "Server"}]
            if path == "/guilds/g1/channels":
                return [
                    {"id": "c1", "name": "general", "type": 0},
                    {"id": "c2", "name": "staff", "type": 0},
                    {"id": "v1", "name": "voice", "type": 2},
                ]
            if path == "/channels/c2/messages":
                raise DiscordError("forbidden")
            return []

        monkeypatch.setattr(connector, "_get", fake_get)
        servers = asyncio.run(connector.server_overview())
        assert servers[0]["name"] == "Server"
        assert servers[0]["channels"] == [
            {"id": "c1", "name": "general", "readable": True},
            {"id": "c2", "name": "staff", "readable": False},
        ]


def test_platforms_route_without_token_says_so():
    from fastapi.testclient import TestClient

    from app.main import app

    body = TestClient(app).get("/api/platforms/discord").json()
    assert body["connected"] is False
    assert "DISCORD_BOT_TOKEN" in body["error"]
