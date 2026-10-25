"""n8n automation endpoints, outgoing events, the scan lock and on-demand AI
redrafting. No network: events are captured before delivery and the model
call is replaced."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.session import Base, get_db
from app.main import app
from app.models import Conversation


@pytest.fixture
def factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def client(factory):
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


def _lead(factory, **overrides) -> Conversation:
    from datetime import UTC, datetime

    row = Conversation(
        platform="discord", external_id="c:1", community="Server#general",
        author_pseudonym="user_abcd", message="Any free prediction game? No deposit please.",
        posted_at=datetime.now(UTC), country="ZZ", language="en", score=82, intent="high",
        confidence="high", matched_keywords=["free prediction game"], contributions=[],
        risk_flags=[], summary="template summary", status="new",
        reply_variants=[{"tone": "helpful", "text": "template"}], selected_variant=0,
        edited_reply=None, history=[],
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    db = factory()
    db.add(row)
    db.commit()
    db.refresh(row)
    db.close()
    return row


# --- automation --------------------------------------------------------------


def test_automation_needs_the_shared_secret(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "n8n_webhook_secret", "s3cret")
    assert client.get("/api/automation/leads").status_code == 401
    assert client.get("/api/automation/leads", headers={"X-Signal-Secret": "nope"}).status_code == 401
    ok = client.get("/api/automation/leads", headers={"X-Signal-Secret": "s3cret"})
    assert ok.status_code == 200 and ok.json() == {"count": 0, "leads": []}


def test_automation_is_off_without_a_secret(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "n8n_webhook_secret", "")
    assert client.get("/api/automation/leads", headers={"X-Signal-Secret": ""}).status_code == 503


def test_automation_lists_recent_strong_leads(client, factory, monkeypatch):
    monkeypatch.setattr(get_settings(), "n8n_webhook_secret", "s3cret")
    _lead(factory)
    body = client.get(
        "/api/automation/leads?minScore=80", headers={"X-Signal-Secret": "s3cret"}
    ).json()
    assert body["count"] == 1 and body["leads"][0]["author"] == "user_abcd"


# --- events ------------------------------------------------------------------


def test_status_change_emits_an_event(client, factory, monkeypatch):
    from app.services import events_service

    captured: list[tuple[str, dict]] = []
    monkeypatch.setattr(events_service, "emit", lambda e, d: captured.append((e, d)))
    row = _lead(factory)
    assert client.post(f"/api/conversations/{row.id}/approve").status_code == 200
    assert captured and captured[0][0] == "lead.status_changed"
    assert captured[0][1]["before"] == "new" and captured[0][1]["after"] == "approved"


def test_events_only_go_out_when_configured(monkeypatch):
    from app.services import events_service

    sent: list = []
    monkeypatch.setattr(events_service, "spawn", lambda coro: (sent.append(coro), coro.close()))
    monkeypatch.setattr(get_settings(), "n8n_events_webhook_url", "")
    events_service.emit("scan.completed", {})
    assert sent == []
    monkeypatch.setattr(get_settings(), "n8n_events_webhook_url", "http://n8n.example/webhook/x")
    events_service.emit("scan.completed", {})
    assert len(sent) == 1


# --- scan lock -----------------------------------------------------------------


def test_scan_lock_is_exclusive_without_redis():
    from app.core.redis import scan_lock

    with scan_lock() as first:
        with scan_lock() as second:
            assert first is True and second is False
    with scan_lock() as again:
        assert again is True


# --- on-demand AI redraft ----------------------------------------------------


def test_redraft_rewrites_drafts_and_keeps_compliance(client, factory, monkeypatch):
    from app.services import ai_drafts, llm

    monkeypatch.setattr(llm, "is_configured", lambda: True)

    async def fake_draft(conv):
        return {
            "summary": "Wants a free game to play with friends.",
            "bodies": {t: "It is a free prediction game you can play with friends." for t in
                       ("helpful", "concise", "conversational")},
        }

    monkeypatch.setattr(ai_drafts, "draft_for", fake_draft)
    row = _lead(factory, edited_reply="my manual edit")
    body = client.post(f"/api/conversations/{row.id}/ai-draft").json()
    assert body["summary"] == "Wants a free game to play with friends."
    assert body.get("editedReply") in (None, "")
    for variant in body["replyVariants"]:
        assert "Full disclosure" in variant["text"] and "18+" in variant["text"]


def test_redraft_refused_for_risk_flagged_leads(client, factory, monkeypatch):
    from app.services import llm

    monkeypatch.setattr(llm, "is_configured", lambda: True)
    row = _lead(factory, risk_flags=["underage"], status="blocked")
    assert client.post(f"/api/conversations/{row.id}/ai-draft").status_code == 409
