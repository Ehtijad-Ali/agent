"""Authentication (spec §38).

These clear the suite-wide ``signed_in`` override so the real dependency runs:
everything here is about what happens when a request is NOT already trusted.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.auth import current_user
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.db.session import Base, get_db
from app.main import app
from app.models import User

PASSWORD = "a-real-enough-password"


@pytest.fixture
def client(signed_in):  # noqa: ARG001 - depends on it only to undo it
    """A client with NO session, talking to a fresh in-memory database."""
    app.dependency_overrides.pop(current_user, None)

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    db = Session()
    db.add(
        User(
            id="u-1",
            email="operator@example.com",
            name="Operator",
            password_hash=hash_password(PASSWORD),
            role="admin",
        )
    )
    db.commit()
    db.close()

    def override():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestPasswordHashing:
    def test_hash_is_not_the_password(self):
        h = hash_password(PASSWORD)
        assert PASSWORD not in h
        assert h.startswith("$argon2")

    def test_same_password_hashes_differently(self):
        """Argon2 salts every hash, so two users with the same password must
        not be detectable by comparing stored values."""
        assert hash_password(PASSWORD) != hash_password(PASSWORD)

    def test_verify_round_trips(self):
        assert verify_password(PASSWORD, hash_password(PASSWORD))

    @pytest.mark.parametrize("stored", ["", "not-a-hash", "$argon2id$broken"])
    def test_malformed_stored_hash_is_false_not_an_exception(self, stored):
        """A corrupt row must fail the login, not 500 the endpoint."""
        assert verify_password(PASSWORD, stored) is False


class TestTokens:
    def test_round_trips_subject_and_role(self):
        token, ttl = create_access_token("u-1", "admin")
        payload = decode_access_token(token)
        assert payload["sub"] == "u-1"
        assert payload["role"] == "admin"
        assert ttl > 0

    def test_tampering_is_rejected(self):
        token, _ = create_access_token("u-1", "admin")
        assert decode_access_token(token[:-4] + "AAAA") is None

    def test_garbage_is_rejected(self):
        assert decode_access_token("not.a.token") is None


class TestProtectedRoutes:
    @pytest.mark.parametrize(
        "path", ["/api/conversations", "/api/scans", "/api/activity", "/api/insights/overview"]
    )
    def test_require_a_session(self, client, path):
        assert client.get(path).status_code == 401

    def test_login_endpoint_is_open(self, client):
        """Signing in must not require being signed in."""
        assert client.post("/api/auth/login", json={}).status_code != 401


class TestLogin:
    def test_correct_credentials_sign_in(self, client):
        r = client.post(
            "/api/auth/login",
            json={"email": "operator@example.com", "password": PASSWORD},
        )
        assert r.status_code == 200
        assert r.json()["email"] == "operator@example.com"
        assert client.get("/api/conversations").status_code == 200

    def test_email_is_case_insensitive(self, client):
        r = client.post(
            "/api/auth/login",
            json={"email": "OPERATOR@Example.COM", "password": PASSWORD},
        )
        assert r.status_code == 200

    def test_wrong_password_is_refused(self, client):
        r = client.post(
            "/api/auth/login",
            json={"email": "operator@example.com", "password": "wrong"},
        )
        assert r.status_code == 401

    def test_unknown_email_gives_the_same_message(self, client):
        """Distinguishing the two tells an attacker which addresses exist."""
        unknown = client.post(
            "/api/auth/login", json={"email": "nobody@example.com", "password": "wrong"}
        )
        wrong = client.post(
            "/api/auth/login", json={"email": "operator@example.com", "password": "wrong"}
        )
        assert unknown.status_code == wrong.status_code == 401
        assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]

    def test_disabled_account_cannot_sign_in(self, client):
        client.post(
            "/api/auth/login",
            json={"email": "operator@example.com", "password": PASSWORD},
        )
        # Deactivate behind the session's back; the next request must fail.
        db = next(app.dependency_overrides[get_db]())
        db.query(User).filter(User.id == "u-1").update({"is_active": False})
        db.commit()
        assert client.get("/api/conversations").status_code == 401

    def test_session_cookie_is_httponly(self, client):
        """A token readable from JavaScript is one an XSS can steal."""
        r = client.post(
            "/api/auth/login",
            json={"email": "operator@example.com", "password": PASSWORD},
        )
        cookie = r.headers.get("set-cookie", "")
        assert "httponly" in cookie.lower()

    def test_logout_ends_the_session(self, client):
        client.post(
            "/api/auth/login",
            json={"email": "operator@example.com", "password": PASSWORD},
        )
        assert client.get("/api/conversations").status_code == 200
        client.post("/api/auth/logout")
        assert client.get("/api/conversations").status_code == 401

    def test_forged_cookie_is_rejected(self, client):
        client.cookies.set("signal_session", "forged.jwt.value")
        assert client.get("/api/conversations").status_code == 401
