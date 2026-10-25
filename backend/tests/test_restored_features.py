"""AI Agent, backlink audit and Platforms tests.

No network and no model: HTML parsing and link classification run on fixed
strings, the SSRF guard is checked against addresses that never leave the
machine, and the agent routes are exercised without starting a task.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.main import app
from app.services import backlink_service, web_service
from app.services.assistant import llm, tools
from app.services.web_service import FetchError


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


# --- web fetching -----------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/api",
        "http://localhost/",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.5/",
        "file:///etc/passwd",
        "ftp://example.com/",
    ],
)
def test_fetch_refuses_non_public_targets(url):
    with pytest.raises(FetchError):
        asyncio.run(web_service.fetch(url))


def test_parse_html_extracts_title_text_and_links():
    page = web_service.parse_html(
        """<html><head><title> Hello </title><script>var x=1</script></head>
        <body><p>Visible text</p><a href="/about" rel="nofollow ugc">About us</a></body></html>""",
        "https://site.example/",
    )
    assert page.title == "Hello"
    assert "Visible text" in page.text and "var x" not in page.text
    assert page.links[0].href == "https://site.example/about"
    assert page.links[0].rel == "nofollow ugc"
    assert page.links[0].text == "About us"


def test_spreadsheet_link_becomes_csv_export():
    url = "https://docs.google.com/spreadsheets/d/AbC_123-x/edit#gid=42"
    assert web_service.spreadsheet_csv_url(url) == (
        "https://docs.google.com/spreadsheets/d/AbC_123-x/export?format=csv&gid=42"
    )
    assert web_service.column_index("A") == 0
    assert web_service.column_index("AA") == 26


# --- backlink classification -------------------------------------------------


def _check(html: str, domain: str = "all-bettors.com"):
    async def fake_fetch(url, timeout=20.0):
        return web_service.FetchResult(url=url, status=200, content_type="text/html", text=html)

    original = web_service.fetch
    web_service.fetch = fake_fetch
    try:
        return asyncio.run(backlink_service.check_page(1, "https://blog.example/post", domain))
    finally:
        web_service.fetch = original


def test_plain_link_is_dofollow():
    assert _check('<a href="https://www.all-bettors.com/join">x</a>').result == "dofollow"


@pytest.mark.parametrize("rel", ["nofollow", "ugc", "sponsored", "noopener nofollow"])
def test_rel_values_make_it_nofollow(rel):
    assert _check(f'<a rel="{rel}" href="https://all-bettors.com/">x</a>').result == "nofollow"


def test_one_dofollow_among_several_wins():
    html = (
        '<a rel="nofollow" href="https://all-bettors.com/a">a</a>'
        '<a href="https://sub.all-bettors.com/b">b</a>'
    )
    assert _check(html).result == "dofollow"


def test_lookalike_domains_do_not_count():
    html = '<a href="https://all-bettors.com.evil.example/">x</a><a href="https://notall-bettors.com/">y</a>'
    assert _check(html).result == "not_found"


def test_non_url_cells_are_errors():
    result = asyncio.run(backlink_service.check_page(3, "Page URL", "all-bettors.com"))
    assert result.result == "error"


# --- agents: backlink type -------------------------------------------------


def test_backlink_agent_round_trip(client):
    created = client.post(
        "/api/agents",
        json={"name": "Audit", "agentType": "backlink_audit", "enabled": True,
              "rules": {"sheetUrl": "https://docs.google.com/spreadsheets/d/x/edit"}},
    )
    assert created.status_code == 201
    agent = created.json()
    assert agent["rules"]["targetDomain"] == "all-bettors.com"
    assert agent["rules"]["urlColumn"] == "A"

    audit = client.get(f"/api/agents/{agent['id']}/audit").json()
    assert audit["status"] == "idle" and audit["items"] == []
    assert client.get(f"/api/agents/{agent['id']}/audit.csv").text.startswith("Page URL,Result")


def test_audit_refused_for_other_agent_types(client):
    agent = client.post("/api/agents", json={"name": "Watcher", "agentType": "engagement"}).json()
    response = client.get(f"/api/agents/{agent['id']}/audit")
    assert response.status_code == 409
    assert "not a backlink-audit agent" in response.json()["error"]["message"]


# --- platforms ----------------------------------------------------------------


def test_sources_have_defaults_and_save(client):
    sources = client.get("/api/platforms/sources").json()
    assert set(sources) == {"reddit", "youtube", "telegram_account"}
    assert "free prediction game" in sources["reddit"]["settings"]["queries"]

    saved = client.put(
        "/api/platforms/sources/reddit",
        json={"queries": [" free picks ", "free picks", ""], "subreddits": ["soccer"]},
    ).json()
    assert saved["settings"] == {"queries": ["free picks"], "subreddits": ["soccer"]}
    assert client.get("/api/platforms/sources").json()["reddit"]["settings"]["subreddits"] == ["soccer"]


def test_unknown_source_platform_is_404(client):
    assert client.put("/api/platforms/sources/myspace", json={"queries": []}).status_code == 404


def test_unconfigured_source_reports_not_connected(client, monkeypatch):
    monkeypatch.setattr("app.services.sources_service.is_configured", lambda platform: False)
    assert client.get("/api/platforms/status/youtube").json()["status"] == "not_connected"


# --- AI Agent -------------------------------------------------------------------


def test_status_lists_tools_and_flags_approval(client):
    body = client.get("/api/assistant/status").json()
    names = {t["name"] for t in body["tools"]}
    assert names == {
        "web_search", "fetch_url", "read_spreadsheet", "check_backlinks",
        "search_leads", "platform_status", "save_csv", "update_lead_status",
    }
    approval = {t["name"] for t in body["tools"] if t["requiresApproval"]}
    assert approval == {"update_lead_status"}


def test_chat_crud(client):
    chat = client.post("/api/assistant/chats", json={}).json()
    assert chat["title"] == "New chat"
    client.patch(f"/api/assistant/chats/{chat['id']}", json={"instructions": "Use tables."})
    detail = client.get(f"/api/assistant/chats/{chat['id']}").json()
    assert detail["chat"]["instructions"] == "Use tables."
    assert detail["messages"] == [] and detail["tasks"] == [] and detail["files"] == []
    assert client.post(f"/api/assistant/chats/{chat['id']}/clear").status_code == 200
    assert client.delete(f"/api/assistant/chats/{chat['id']}").status_code == 200
    assert client.get(f"/api/assistant/chats/{chat['id']}").status_code == 404


def test_send_without_model_is_503(client, monkeypatch):
    monkeypatch.setattr(llm, "provider", lambda: (False, "ollama", ""))
    chat = client.post("/api/assistant/chats", json={}).json()
    response = client.post(f"/api/assistant/chats/{chat['id']}/messages", json={"content": "hi"})
    assert response.status_code == 503


def test_tool_calls_written_as_text_are_recovered():
    calls = llm._tool_calls_from_text(
        '```json\n{"name": "search_leads", "arguments": {"limit": 3}}\n```', {"search_leads"}
    )
    assert calls[0]["function"] == {"name": "search_leads", "arguments": {"limit": 3}}
    assert llm._tool_calls_from_text('{"name": "rm_rf", "arguments": {}}', {"search_leads"}) == []


def test_invented_sheet_links_are_ignored(monkeypatch):
    seen: list[str] = []

    async def fake_from_sheet(url, column="A", limit=100):
        seen.append(url)
        return []

    async def fake_check_many(pairs, domain, on_result=None):
        return [backlink_service.CheckResult(r, u, "not_found") for r, u in pairs]

    monkeypatch.setattr(backlink_service, "urls_from_sheet", fake_from_sheet)
    monkeypatch.setattr(backlink_service, "check_many", fake_check_many)
    monkeypatch.setattr(tools, "_save_file", lambda *a: type("F", (), {"filename": "x.csv", "rows": 1})())

    ctx = tools.ToolContext("c", "t", "u", user_text="check https://blog.example/post please")
    status, _ = asyncio.run(
        tools._check_backlinks({"sheet_url": "https://docs.google.com/spreadsheets/d/MADEUP/edit"}, ctx)
    )
    assert status == "ok"
    assert seen == []  # the made-up sheet was never fetched


# --- automation (n8n) ----------------------------------------------------------


def test_automation_needs_the_shared_secret(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "n8n_webhook_secret", "s3cret")
    assert client.get("/api/automation/leads").status_code == 401
    assert client.get("/api/automation/leads", headers={"X-Signal-Secret": "wrong"}).status_code == 401
    ok = client.get("/api/automation/leads", headers={"X-Signal-Secret": "s3cret"})
    assert ok.status_code == 200 and ok.json() == {"count": 0, "leads": []}


def test_automation_disabled_without_secret(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "n8n_webhook_secret", "")
    assert client.get("/api/automation/leads", headers={"X-Signal-Secret": ""}).status_code == 503


def test_events_are_sent_only_when_configured(monkeypatch):
    from app.core.config import get_settings
    from app.services import events_service

    sent: list = []
    monkeypatch.setattr(events_service, "spawn", lambda coro: (sent.append(coro), coro.close()))
    monkeypatch.setattr(get_settings(), "n8n_webhook_url", "")
    events_service.emit("scan.completed", {})
    assert sent == []
    monkeypatch.setattr(get_settings(), "n8n_webhook_url", "https://n8n.example/webhook/x")
    events_service.emit("scan.completed", {})
    assert len(sent) == 1


# --- scan lock -------------------------------------------------------------------


def test_scan_lock_is_exclusive_without_redis():
    from app.core.redis import scan_lock

    with scan_lock() as first:
        with scan_lock() as second:
            assert first is True and second is False
    with scan_lock() as again:
        assert again is True


# --- AI summaries and replies ----------------------------------------------------


def _fake_ollama(monkeypatch, response_json: dict):
    import json as _json

    import httpx

    from app.core.config import get_settings
    from app.services import ai_service

    monkeypatch.setattr(get_settings(), "ollama_model", "test-model")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": _json.dumps(response_json)}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    return ai_service


def test_ai_drafts_always_carry_the_compliance_text(monkeypatch):
    import re

    from app.schemas.tuning import VoiceConfig

    ai_service = _fake_ollama(
        monkeypatch,
        {
            "language": "es",
            "summary": "The person wants a free prediction game to play with friends.",
            "replies": {
                t: {"opening": "¡Hola 😀", "body": "Es perfecto para ti, visita https://evil.example ahora."}
                for t in ("helpful", "concise", "conversational")
            },
        },
    )
    draft = asyncio.run(ai_service.draft("¿Alguien conoce un juego?", "futbol", VoiceConfig(), "es"))
    assert draft is not None and draft.language == "es"
    for variant in draft.variants:
        text = variant["text"]
        assert re.search(r"full disclosure.*i work on join all bettors", text, re.I)
        assert "Free to play, no deposits, 18+." in text
        assert "evil.example" not in text  # the model may not add its own links
        assert "😀" not in text  # emoji removed at the default emoji setting
        assert len(text) <= VoiceConfig().max_length


def test_incomplete_ai_answer_falls_back_to_templates(monkeypatch):
    from app.schemas.tuning import VoiceConfig

    ai_service = _fake_ollama(monkeypatch, {"language": "en", "summary": "x", "replies": {}})
    assert asyncio.run(ai_service.draft("hi", "c", VoiceConfig())) is None


def test_non_english_summary_is_dropped(monkeypatch):
    from app.schemas.tuning import VoiceConfig

    replies = {t: {"opening": "Hola", "body": "Es un juego gratis."} for t in ("helpful", "concise", "conversational")}
    ai_service = _fake_ollama(
        monkeypatch, {"language": "es", "summary": "Una persona busca un juego gratuito.", "replies": replies}
    )
    draft = asyncio.run(ai_service.draft("¿Alguien?", "c", VoiceConfig(), "es"))
    assert draft is not None and draft.summary is None
