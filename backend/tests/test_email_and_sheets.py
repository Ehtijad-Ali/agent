"""Welcome emails and Google Sheets write-back. No network: SMTP and Google's
APIs are replaced, but the service-account JWT is really signed and checked."""

from __future__ import annotations

import asyncio
import json
from urllib.parse import parse_qs

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.session import Base, get_db
from app.main import app
from app.services import email_service, google_sheets


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


# --- welcome email -------------------------------------------------------------


class FakeSMTP:
    sent: list = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        self.tls = True

    def login(self, user, password):
        self.user = user

    def send_message(self, message):
        FakeSMTP.sent.append(message)


def test_new_user_gets_a_welcome_email_without_the_password(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(s, "smtp_from", "Signal <noreply@example.com>")
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.sent = []

    body = client.post(
        "/api/users",
        json={"email": "new@example.com", "name": "New", "password": "a-long-secret-1", "role": "operator"},
    ).json()

    assert body["welcomeEmail"] == "sent"
    assert len(FakeSMTP.sent) == 1
    message = FakeSMTP.sent[0]
    assert message["To"] == "new@example.com"
    text = message.get_content()
    assert "/login" in text and "Operator" in text
    assert "a-long-secret-1" not in text


def test_without_smtp_the_admin_is_told(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "smtp_host", "")
    body = client.post(
        "/api/users",
        json={"email": "other@example.com", "password": "a-long-secret-1", "role": "operator"},
    ).json()
    assert body["welcomeEmail"] == "not_configured"


# --- Google Sheets write-back ------------------------------------------------


@pytest.fixture
def service_account(tmp_path, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    path = tmp_path / "sa.json"
    path.write_text(json.dumps({
        "type": "service_account",
        "client_email": "signal@project.iam.gserviceaccount.com",
        "private_key": pem,
        "token_uri": "https://oauth2.googleapis.com/token",
    }))
    monkeypatch.setattr(get_settings(), "google_service_account_file", str(path))
    google_sheets._credentials.cache_clear()
    yield key.public_key()
    google_sheets._credentials.cache_clear()


def _fake_google(monkeypatch, public_key, edit_status=200):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "oauth2.googleapis.com":
            assertion = parse_qs(request.content.decode())["assertion"][0]
            claims = jwt.decode(
                assertion, public_key, algorithms=["RS256"], audience="https://oauth2.googleapis.com/token"
            )
            assert claims["scope"] == google_sheets.SCOPE
            return httpx.Response(200, json={"access_token": "tok"})
        if request.method == "GET":
            return httpx.Response(200, json={"sheets": [
                {"properties": {"sheetId": 0, "title": "First"}},
                {"properties": {"sheetId": 42, "title": "Link's list"}},
            ]})
        if edit_status != 200:
            return httpx.Response(edit_status, json={})
        body = json.loads(request.content)
        return httpx.Response(200, json={"totalUpdatedCells": len(body["data"])})

    real = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda *a, **k: real(transport=httpx.MockTransport(handler))
    )
    return calls


def test_results_are_written_next_to_their_urls(service_account, monkeypatch):
    calls = _fake_google(monkeypatch, service_account)
    written = asyncio.run(google_sheets.write_column(
        "https://docs.google.com/spreadsheets/d/SHEET123/edit#gid=42",
        "b",
        [(2, "Dofollow"), (3, "No link")],
    ))
    assert written == 2
    update = json.loads(calls[-1].content)
    assert update["valueInputOption"] == "RAW"
    assert [d["range"] for d in update["data"]] == ["'Link''s list'!B2", "'Link''s list'!B3"]
    assert calls[-1].headers["Authorization"] == "Bearer tok"


def test_read_only_sharing_says_which_account_to_share_with(service_account, monkeypatch):
    _fake_google(monkeypatch, service_account, edit_status=403)
    with pytest.raises(google_sheets.SheetsError, match="signal@project.iam.gserviceaccount.com"):
        asyncio.run(google_sheets.write_column(
            "https://docs.google.com/spreadsheets/d/SHEET123/edit", "B", [(2, "Dofollow")]
        ))


def test_integrations_report_status_only(client, service_account):
    body = client.get("/api/platforms/integrations").json()
    assert body["googleSheets"] == {
        "configured": True, "serviceAccountEmail": "signal@project.iam.gserviceaccount.com"
    }
    assert "private_key" not in json.dumps(body)


def test_sheet_write_refused_when_not_set_up(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "google_service_account_file", "")
    google_sheets._credentials.cache_clear()
    agent = client.post(
        "/api/agents",
        json={"name": "Audit", "agentType": "backlink_audit", "enabled": True,
              "rules": {"sheetUrl": "https://docs.google.com/spreadsheets/d/x/edit"}},
    ).json()
    assert client.post(f"/api/agents/{agent['id']}/audit/sheet").status_code == 503
