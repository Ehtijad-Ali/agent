"""Discovery connectors (Reddit, YouTube, Telegram account), the Ollama
adapter, AI drafts and the sources API. No network."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.session import Base, get_db
from app.integrations.reddit import RedditConnector
from app.integrations.telegram_account import TelegramAccountConnector
from app.integrations.youtube import YouTubeConnector
from app.main import app
from app.models import Conversation
from app.services import ai_drafts, llm
from app.services.reply_service import DISCLOSURE, FREE_TO_PLAY

SALT = "test-salt-not-a-real-one"


# --- Reddit -------------------------------------------------------------------


@pytest.fixture
def reddit():
    return RedditConnector("id", "secret", "ua", SALT, ["free prediction game"], ["r/soccer"])


class TestReddit:
    def test_post_is_title_plus_body(self, reddit):
        msg = reddit.normalise({"kind": "t3", "data": {
            "name": "t3_abc", "title": "Any free prediction game?", "selftext": "for the world cup",
            "author": "someone", "subreddit": "soccer", "created_utc": 1_700_000_000,
            "permalink": "/r/soccer/comments/abc/x/",
        }})
        assert msg.platform == "reddit"
        assert msg.external_id == "t3_abc"
        assert msg.community == "r/soccer"
        assert msg.message == "Any free prediction game?\n\nfor the world cup"
        assert msg.source_url == "https://www.reddit.com/r/soccer/comments/abc/x/"
        assert "someone" not in msg.author_pseudonym

    def test_comment(self, reddit):
        msg = reddit.normalise({"kind": "t1", "data": {
            "name": "t1_c1", "body": "I use a free picks app", "author": "u2",
            "subreddit": "nba", "created_utc": 1_700_000_000, "permalink": "/r/nba/c1",
        }})
        assert msg.external_id == "t1_c1" and msg.message == "I use a free picks app"

    @pytest.mark.parametrize("data", [
        {"name": "t1_x", "body": "[removed]", "author": "u"},
        {"name": "t1_x", "body": "hi", "author": "[deleted]"},
        {"name": "t1_x", "body": "rules", "author": "AutoModerator"},
    ])
    def test_skips_removed_deleted_and_bots(self, reddit, data):
        assert reddit.normalise({"kind": "t1", "data": {**data, "created_utc": 0}}) is None

    def test_subreddit_prefix_is_normalised(self, reddit):
        assert reddit.subreddits == ["soccer"]

    def test_replies_are_manual(self, reddit):
        from app.integrations.base import ManualReplyOnly

        with pytest.raises(ManualReplyOnly):
            asyncio.run(reddit.send_message("x", "y"))


# --- YouTube ------------------------------------------------------------------


class TestYouTube:
    def test_comment_thread(self):
        yt = YouTubeConnector("key", SALT, ["q"])
        msg = yt.normalise({"snippet": {"topLevelComment": {"id": "Ug1", "snippet": {
            "textOriginal": "Which app do you use for predictions?",
            "authorChannelId": {"value": "UCabc"},
            "publishedAt": "2026-10-20T10:00:00Z",
        }}}}, "vid1", "Premier League predictions week 9")
        assert msg.platform == "youtube"
        assert msg.external_id == "vid1:Ug1"
        assert msg.community == "YouTube: Premier League predictions week 9"
        assert msg.source_url == "https://www.youtube.com/watch?v=vid1&lc=Ug1"
        assert msg.posted_at.tzinfo is not None

    def test_empty_comment_skipped(self):
        yt = YouTubeConnector("key", SALT)
        assert yt.normalise({"snippet": {"topLevelComment": {"id": "x", "snippet": {}}}}, "v", "t") is None


# --- Telegram account -----------------------------------------------------------


class TestTelegramAccount:
    def test_same_id_scheme_as_the_bot(self):
        tg = TelegramAccountConnector(1, "hash", "session", SALT, chats=["https://t.me/somegroup", "@other"])
        assert tg.chats == ["somegroup", "other"]
        entity = SimpleNamespace(username="somegroup", title="Some Group")
        msg = SimpleNamespace(id=5, message="anyone know a free prediction game?", sender_id=99,
                              date=datetime(2026, 10, 20, tzinfo=UTC))
        out = tg.normalise(msg, entity, -1001234)
        assert out.external_id == "-1001234:5"
        assert out.community == "@somegroup"
        assert out.source_url == "https://t.me/somegroup/5"

    def test_requires_all_credentials(self):
        with pytest.raises(ValueError):
            TelegramAccountConnector(1, "hash", "", SALT)


# --- Ollama adapter -------------------------------------------------------------


class TestOllamaAdapter:
    def test_history_is_translated(self):
        out = llm._to_ollama([
            {"role": "system", "content": "s"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "c1", "function": {"name": "fetch_url", "arguments": '{"url": "https://a.b"}'}}]},
            {"role": "tool", "tool_call_id": "c1", "name": "fetch_url", "content": "{}"},
        ])
        assert out[1]["tool_calls"][0]["function"]["arguments"] == {"url": "https://a.b"}
        assert out[2] == {"role": "tool", "content": "{}", "tool_name": "fetch_url"}

    def test_response_is_normalised(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "ai_provider", "ollama")
        monkeypatch.setattr(get_settings(), "ollama_model", "qwen2.5:7b")

        class FakeResponse:
            status_code = 200

            def json(self):
                return {"message": {"content": "", "tool_calls": [
                    {"function": {"name": "search_leads", "arguments": {"query": "x"}}}]},
                    "prompt_eval_count": 100, "eval_count": 20}

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, json):
                assert json["options"]["num_ctx"] == get_settings().ollama_context
                return FakeResponse()

        monkeypatch.setattr(llm.httpx, "AsyncClient", FakeClient)
        result = asyncio.run(llm.chat([{"role": "user", "content": "hi"}], tools=[{}]))
        call = result["message"]["tool_calls"][0]
        assert call["function"]["name"] == "search_leads"
        assert json.loads(call["function"]["arguments"]) == {"query": "x"}
        assert result["usage"]["total_tokens"] == 120

    def test_provider_switch(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "ai_provider", "groq")
        monkeypatch.setattr(get_settings(), "groq_api_key", "")
        assert not llm.is_configured()
        assert "GROQ_API_KEY" in llm.not_configured_reason()


# --- AI drafts ------------------------------------------------------------------


@pytest.fixture
def factory(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(ai_drafts, "session_scope", make)
    return make


def _lead(make, score=80, status="new", flags=None):
    db = make()
    row = Conversation(platform="reddit", external_id=f"t3_{score}{status}", community="r/soccer",
                       author_pseudonym="u", message="any free prediction game for the world cup?",
                       posted_at=datetime.now(UTC), score=score, status=status,
                       risk_flags=flags or [], summary="template", reply_variants=[], history=[])
    db.add(row)
    db.commit()
    db.close()
    return row.id


class TestAiDrafts:
    def _fake(self, monkeypatch, content):
        monkeypatch.setattr(get_settings(), "ollama_model", "test")
        monkeypatch.setattr(get_settings(), "ai_provider", "ollama")

        async def fake_chat(messages, tools=None, max_tokens=2048, json_mode=False):
            assert json_mode
            return {"message": {"content": content}, "usage": {}}

        monkeypatch.setattr(llm, "chat", fake_chat)

    def test_drafts_keep_the_mandatory_wording(self, factory, monkeypatch):
        self._fake(monkeypatch, json.dumps({
            "summary": "Wants a free game to predict World Cup matches with friends.",
            "helpful": "It lets you predict every World Cup match and compete with friends in a private league.",
            "concise": "Free World Cup predictions with friends.",
            "conversational": "Sounds like exactly what we built for tournaments like this. https://evil.example",
        }))
        lead = _lead(factory)
        assert asyncio.run(ai_drafts.enrich([lead])) == 1
        row = factory().get(Conversation, lead)
        assert row.summary.startswith("Wants a free game")
        for variant in row.reply_variants:
            assert DISCLOSURE in variant["text"]
            assert FREE_TO_PLAY in variant["text"]
            assert "evil.example" not in variant["text"]
        assert "World Cup" in row.reply_variants[0]["text"]
        assert row.history[-1]["action"] == "wrote summary and reply drafts"

    def test_money_talk_is_discarded(self, factory, monkeypatch):
        self._fake(monkeypatch, json.dumps({
            "summary": "ok", "helpful": "Get a $10 deposit bonus code today!",
            "concise": "No real money anywhere.", "conversational": "Bet money on picks.",
        }))
        lead = _lead(factory)
        asyncio.run(ai_drafts.enrich([lead]))
        texts = " ".join(v["text"] for v in factory().get(Conversation, lead).reply_variants)
        assert "bonus code" not in texts and "Bet money" not in texts

    def test_low_score_and_flagged_leads_are_skipped(self, factory, monkeypatch):
        self._fake(monkeypatch, '{"summary": "x", "helpful": "y"}')
        ids = [_lead(factory, score=10), _lead(factory, flags=["real_money"], status="new")]
        assert asyncio.run(ai_drafts.enrich(ids)) == 0

    def test_bad_json_keeps_template(self, factory, monkeypatch):
        self._fake(monkeypatch, "not json at all")
        lead = _lead(factory)
        assert asyncio.run(ai_drafts.enrich([lead])) == 0
        assert factory().get(Conversation, lead).summary == "template"


# --- API ------------------------------------------------------------------------


@pytest.fixture
def client(factory):
    def override():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


class TestSourcesApi:
    def test_defaults_then_update(self, client):
        body = client.get("/api/platforms/sources").json()
        assert body["reddit"]["configured"] is False
        assert body["reddit"]["settings"]["queries"]
        r = client.put("/api/platforms/sources/reddit",
                       json={"queries": [" free  picks app ", "free picks app", ""], "subreddits": ["soccer"]})
        assert r.status_code == 200
        assert r.json()["settings"] == {"queries": ["free picks app"], "subreddits": ["soccer"]}

    def test_unknown_platform(self, client):
        assert client.put("/api/platforms/sources/myspace", json={"queries": []}).status_code == 404

    def test_status_when_not_configured(self, client):
        assert client.get("/api/platforms/status/youtube").json()["status"] == "not_connected"

    def test_reddit_reply_is_manual(self, client, factory):
        db = factory()
        row = Conversation(platform="reddit", external_id="t3_z", community="r/x", author_pseudonym="u",
                           message="m", posted_at=datetime.now(UTC), status="approved",
                           reply_variants=[{"tone": "helpful", "text": f"{DISCLOSURE} {FREE_TO_PLAY} x"}],
                           history=[])
        db.add(row)
        db.commit()
        db.close()
        r = client.post(f"/api/replies/{row.id}/send")
        assert r.status_code == 409
        assert "posted by hand" in r.json()["error"]["message"]


def test_refinement_counts_only_the_agents_own_leads(factory):
    from app.models import Agent
    from app.services.refinement_service import compute

    db = factory()
    agent = Agent(name="Watcher", agent_type="engagement", enabled=1, rules={})
    db.add(agent)
    for i, picked in enumerate([True, True, False]):
        history = [{"actor": "Watcher", "action": "picked up by agent"}] if picked else []
        db.add(Conversation(platform="discord", external_id=f"x:{i}", community="c", author_pseudonym="u",
                            message="m", posted_at=datetime.now(UTC), intent="high", status="new",
                            history=history))
    db.commit()
    assert compute(db)["sampleSize"] == 3
    assert compute(db, agent)["sampleSize"] == 2
