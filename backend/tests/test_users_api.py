"""User administration (spec §38).

Two things are worth testing here beyond the happy path: that an operator
genuinely cannot manage users (otherwise the second role is decorative), and
that the screen cannot lock everyone out of it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.auth import current_user
from app.core.security import hash_password, verify_password
from app.db.session import Base, get_db
from app.main import app
from app.models import User

ADMIN_ID = "admin-1"
OPERATOR_ID = "operator-1"


@pytest.fixture
def env(signed_in):  # noqa: ARG001 - present only to override it
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    db = Session()
    db.add_all([
        User(id=ADMIN_ID, email="admin@example.com", name="Admin",
             password_hash=hash_password("admin-password"), role="admin"),
        User(id=OPERATOR_ID, email="op@example.com", name="Operator",
             password_hash=hash_password("operator-password"), role="operator"),
    ])
    db.commit()
    db.close()

    def override_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db

    def as_user(user_id: str):
        def _dep():
            s = Session()
            try:
                return s.get(User, user_id)
            finally:
                s.close()
        app.dependency_overrides[current_user] = _dep

    as_user(ADMIN_ID)
    with TestClient(app) as client:
        yield client, as_user, Session
    app.dependency_overrides.clear()


class TestRoleBoundary:
    def test_admin_can_list_users(self, env):
        client, _, _ = env
        r = client.get("/api/users")
        assert r.status_code == 200
        assert {u["email"] for u in r.json()} == {"admin@example.com", "op@example.com"}

    @pytest.mark.parametrize(
        "method,path,body",
        [
            ("get", "/api/users", None),
            ("post", "/api/users", {"email": "x@example.com", "password": "0123456789"}),
            ("patch", f"/api/users/{ADMIN_ID}", {"name": "Renamed"}),
        ],
    )
    def test_operator_is_refused(self, env, method, path, body):
        """The whole point of a second role: an operator cannot manage users."""
        client, as_user, _ = env
        as_user(OPERATOR_ID)
        r = getattr(client, method)(path, **({"json": body} if body else {}))
        assert r.status_code == 403

    def test_operator_can_still_read_roles(self, env):
        client, as_user, _ = env
        as_user(OPERATOR_ID)
        assert client.get("/api/users/roles").status_code == 200


class TestCreate:
    def test_creates_with_a_hashed_password(self, env):
        client, _, Session = env
        r = client.post("/api/users", json={
            "email": "New.Person@Example.com", "name": "New Person",
            "password": "a-long-enough-password", "role": "operator",
        })
        assert r.status_code == 201
        assert r.json()["email"] == "new.person@example.com", "email should be lowercased"

        db = Session()
        created = db.query(User).filter(User.email == "new.person@example.com").one()
        assert created.password_hash != "a-long-enough-password"
        assert verify_password("a-long-enough-password", created.password_hash)
        db.close()

    def test_duplicate_email_is_refused(self, env):
        client, _, _ = env
        r = client.post("/api/users", json={
            "email": "ADMIN@example.com", "password": "a-long-enough-password",
        })
        assert r.status_code == 409

    def test_short_password_is_refused(self, env):
        client, _, _ = env
        assert client.post("/api/users", json={
            "email": "x@example.com", "password": "short",
        }).status_code == 422

    def test_unknown_role_is_refused(self, env):
        client, _, _ = env
        assert client.post("/api/users", json={
            "email": "x@example.com", "password": "a-long-enough-password",
            "role": "superuser",
        }).status_code == 422


class TestLockoutGuards:
    def test_cannot_deactivate_yourself(self, env):
        client, _, _ = env
        r = client.patch(f"/api/users/{ADMIN_ID}", json={"isActive": False})
        assert r.status_code == 400
        assert "your own account" in r.json()["error"]["message"]

    def test_cannot_demote_yourself(self, env):
        client, _, _ = env
        r = client.patch(f"/api/users/{ADMIN_ID}", json={"role": "operator"})
        assert r.status_code == 400

    def test_cannot_remove_the_last_admin(self, env):
        """Even a second admin must not be able to strip the platform of all of them."""
        client, as_user, Session = env
        db = Session()
        db.add(User(id="admin-2", email="admin2@example.com", name="Admin Two",
                    password_hash=hash_password("another-password"), role="admin"))
        db.commit()
        db.close()

        # admin-2 demotes admin-1: allowed, two admins exist.
        as_user("admin-2")
        assert client.patch(f"/api/users/{ADMIN_ID}", json={"role": "operator"}).status_code == 200

        # admin-2 is now the only one left and cannot be demoted by anyone.
        as_user("admin-2")
        r = client.patch("/api/users/admin-2", json={"role": "operator"})
        assert r.status_code == 400

    def test_deactivating_an_operator_is_fine(self, env):
        client, _, _ = env
        r = client.patch(f"/api/users/{OPERATOR_ID}", json={"isActive": False})
        assert r.status_code == 200
        assert r.json()["isActive"] is False


class TestUpdate:
    def test_password_change_takes_effect(self, env):
        client, _, Session = env
        assert client.patch(
            f"/api/users/{OPERATOR_ID}", json={"password": "a-brand-new-password"}
        ).status_code == 200
        db = Session()
        u = db.get(User, OPERATOR_ID)
        assert verify_password("a-brand-new-password", u.password_hash)
        db.close()

    def test_unknown_user_is_404(self, env):
        client, _, _ = env
        assert client.patch("/api/users/nope", json={"name": "x"}).status_code == 404
