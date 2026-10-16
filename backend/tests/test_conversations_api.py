"""Conversation, activity and insights endpoint tests.

Runs against a real in-memory database through TestClient, with the session
dependency overridden. No network, no Discord.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.main import app
from app.models import Conversation


@pytest.fixture
def session_factory():
    # StaticPool keeps every session on one connection. Without it each
    # connection gets its own empty in-memory database, and TestClient -- which
    # runs the app on another thread -- would see no tables at all.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def client(session_factory):
    def override():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _row(**overrides) -> Conversation:
    base = {
        "platform": "discord",
        "external_id": "chan:1",
        "community": "Test#general",
        "author_pseudonym": "user_abcd",
        "message": "anyone know a free to play prediction game?",
        "posted_at": datetime.now(UTC),
        "country": "GB",
        "language": "en",
        "score": 72,
        "intent": "high",
        "confidence": "high",
        "matched_keywords": ["free to play"],
        "contributions": [{"ruleId": "kw5", "label": '"free to play" (phrase)', "points": 12}],
        "risk_flags": [],
        "summary": "Author is asking for a recommendation.",
        "status": "new",
        "reply_variants": [
            {"tone": "helpful", "text": "a"},
            {"tone": "concise", "text": "b"},
        ],
        "selected_variant": 0,
        "history": [],
    }
    base.update(overrides)
    return Conversation(**base)


@pytest.fixture
def seeded(session_factory):
    db = session_factory()
    rows = [
        _row(external_id="chan:1", score=72, intent="high", status="new"),
        _row(external_id="chan:2", score=30, intent="low", status="approved", country="US"),
        _row(
            external_id="chan:3",
            score=0,
            intent="not_relevant",
            status="blocked",
            platform="telegram",
            posted_at=datetime.now(UTC) - timedelta(days=20),
        ),
    ]
    db.add_all(rows)
    db.commit()
    ids = [r.id for r in rows]
    db.close()
    return ids


class TestList:
    def test_returns_camel_case_wire_shape(self, client, seeded):
        body = client.get("/api/conversations").json()
        assert body["perPage"] == 50
        item = body["items"][0]
        # The frontend's Zod schema expects exactly these keys.
        for key in (
            "authorPseudonym",
            "matchedKeywords",
            "riskFlags",
            "replyVariants",
            "selectedVariant",
            "postedAt",
            "sourceUrl",
        ):
            assert key in item

    def test_posted_at_carries_a_timezone(self, client, seeded):
        """A naive timestamp would be read as local time by new Date()."""
        posted = client.get("/api/conversations").json()["items"][0]["postedAt"]
        assert posted.endswith("Z") or "+" in posted[10:]

    def test_total_counts_all_rows_not_just_the_page(self, client, seeded):
        body = client.get("/api/conversations?perPage=1").json()
        assert len(body["items"]) == 1
        assert body["total"] == 3

    def test_filters_by_status(self, client, seeded):
        body = client.get("/api/conversations?status=approved").json()
        assert body["total"] == 1
        assert body["items"][0]["status"] == "approved"

    def test_filters_by_platform(self, client, seeded):
        body = client.get("/api/conversations?platform=telegram").json()
        assert body["total"] == 1

    def test_filters_by_score_range(self, client, seeded):
        body = client.get("/api/conversations?minScore=50").json()
        assert body["total"] == 1
        assert body["items"][0]["score"] == 72

    def test_search_matches_message_text(self, client, seeded):
        assert client.get("/api/conversations?search=prediction").json()["total"] == 3
        assert client.get("/api/conversations?search=zzzznope").json()["total"] == 0

    def test_sorts_by_score(self, client, seeded):
        items = client.get("/api/conversations?sort=score&direction=desc").json()["items"]
        scores = [i["score"] for i in items]
        assert scores == sorted(scores, reverse=True)


class TestDetail:
    def test_returns_one(self, client, seeded):
        body = client.get(f"/api/conversations/{seeded[0]}").json()
        assert body["id"] == seeded[0]

    def test_unknown_id_is_404_with_the_error_envelope(self, client, seeded):
        response = client.get("/api/conversations/nope")
        assert response.status_code == 404
        assert response.json()["success"] is False
        assert response.json()["error"]["code"] == "HTTP_404"


class TestActions:
    @pytest.mark.parametrize(
        ("action", "expected"),
        [
            ("approve", "approved"),
            ("reject", "rejected"),
            ("snooze", "snoozed"),
            ("mark-posted", "manually_posted"),
            ("block", "blocked"),
            ("reset", "new"),
            ("mark-awaiting", "awaiting"),
        ],
    )
    def test_each_verb_sets_its_status(self, client, seeded, action, expected):
        body = client.post(f"/api/conversations/{seeded[0]}/{action}").json()
        assert body["status"] == expected

    def test_action_appends_history(self, client, seeded):
        body = client.post(f"/api/conversations/{seeded[0]}/approve").json()
        assert body["history"][-1]["action"] == "approve"
        assert body["history"][-1]["actor"] == "you"

    def test_action_writes_an_audit_row(self, client, seeded):
        client.post(f"/api/conversations/{seeded[0]}/approve")
        log = client.get("/api/activity").json()
        assert log["total"] == 1
        assert log["items"][0]["before"] == "new"
        assert log["items"][0]["after"] == "approved"

    def test_unknown_action_is_rejected(self, client, seeded):
        response = client.post(f"/api/conversations/{seeded[0]}/frobnicate")
        assert response.status_code == 400
        assert "Unknown action" in response.json()["error"]["message"]

    def test_edit_is_not_swallowed_by_the_action_route(self, client, seeded):
        """Route order matters: /{id}/edit must not resolve as action="edit"."""
        response = client.post(
            f"/api/conversations/{seeded[0]}/edit", json={"editedReply": "mine"}
        )
        assert response.status_code == 200
        assert response.json()["editedReply"] == "mine"


class TestEdit:
    def test_selects_a_variant(self, client, seeded):
        body = client.post(
            f"/api/conversations/{seeded[0]}/edit", json={"selectedVariant": 1}
        ).json()
        assert body["selectedVariant"] == 1

    def test_out_of_range_variant_is_rejected(self, client, seeded):
        response = client.post(
            f"/api/conversations/{seeded[0]}/edit", json={"selectedVariant": 99}
        )
        assert response.status_code == 400
        assert "out of range" in response.json()["error"]["message"]

    def test_blank_reply_clears_the_override(self, client, seeded):
        client.post(f"/api/conversations/{seeded[0]}/edit", json={"editedReply": "mine"})
        body = client.post(
            f"/api/conversations/{seeded[0]}/edit", json={"editedReply": ""}
        ).json()
        assert body["editedReply"] is None


class TestBulk:
    def test_partial_failure_is_visible(self, client, seeded):
        body = client.post(
            "/api/conversations/bulk",
            json={"ids": [seeded[0], "missing"], "action": "snooze"},
        ).json()
        assert body["updated"] == 1
        assert [r["ok"] for r in body["results"]] == [True, False]
        assert body["results"][1]["error"] == "not found"

    def test_unknown_action_is_rejected(self, client, seeded):
        response = client.post(
            "/api/conversations/bulk", json={"ids": seeded, "action": "nope"}
        )
        assert response.status_code == 400


class TestInsights:
    def test_overview_counts_only_the_window(self, client, seeded):
        """The 20-day-old row must be outside a 7d window."""
        body = client.get("/api/insights/overview?range=7d").json()
        assert body["discovered"] == 2
        assert body["highIntent"] == 1
        assert len(body["discoveredSeries"]) == 7

    def test_overview_window_widens(self, client, seeded):
        assert client.get("/api/insights/overview?range=30d").json()["discovered"] == 3

    def test_delta_does_not_divide_by_zero(self, client, seeded):
        body = client.get("/api/insights/overview?range=24h").json()
        assert isinstance(body["deltaDiscovered"], (int, float))

    def test_relevant_excludes_not_relevant(self, client, seeded):
        body = client.get("/api/insights/overview?range=30d").json()
        assert body["relevant"] == 2

    def test_platform_breakdown(self, client, seeded):
        rows = client.get("/api/insights/platforms?range=30d").json()["rows"]
        assert {r["label"]: r["count"] for r in rows} == {"discord": 2, "telegram": 1}

    def test_keyword_breakdown_counts_json_array_entries(self, client, seeded):
        rows = client.get("/api/insights/keywords?range=30d").json()["rows"]
        assert rows[0]["label"] == "free to play"
        assert rows[0]["count"] == 3

    def test_funnel(self, client, seeded):
        body = client.get("/api/insights/funnel?range=30d").json()
        assert body["discovered"] == 3
        assert body["approved"] == 1


class TestActivityExport:
    def test_csv_has_a_header_and_a_row(self, client, seeded):
        client.post(f"/api/conversations/{seeded[0]}/approve")
        response = client.get("/api/activity/export")
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        lines = response.text.strip().splitlines()
        assert lines[0] == "timestamp,actor,action,item,before,after"
        assert len(lines) == 2


class TestSentIsTerminal:
    """A posted reply cannot be unposted, so the row must not move again.

    Regression: the send succeeded, then an approve moved the row back to
    'approved', which put a live Send button on an already-replied conversation.
    """

    @pytest.fixture
    def sent_row(self, session_factory):
        db = session_factory()
        row = _row(external_id="chan:sent", status="sent")
        db.add(row)
        db.commit()
        row_id = row.id
        db.close()
        return row_id

    @pytest.mark.parametrize(
        "action", ["approve", "reject", "snooze", "mark-posted", "block", "reset"]
    )
    def test_no_action_can_move_a_sent_row(self, client, sent_row, action):
        response = client.post(f"/api/conversations/{sent_row}/{action}")
        assert response.status_code == 409
        assert "cannot be unposted" in response.json()["error"]["message"]

    def test_status_is_unchanged_after_a_refused_action(self, client, sent_row):
        client.post(f"/api/conversations/{sent_row}/approve")
        assert client.get(f"/api/conversations/{sent_row}").json()["status"] == "sent"

    def test_edit_is_refused(self, client, sent_row):
        response = client.post(
            f"/api/conversations/{sent_row}/edit", json={"editedReply": "changed"}
        )
        assert response.status_code == 409

    def test_bulk_reports_the_refusal_per_id(self, client, sent_row, seeded):
        body = client.post(
            "/api/conversations/bulk",
            json={"ids": [sent_row, seeded[0]], "action": "snooze"},
        ).json()
        assert body["updated"] == 1
        assert body["results"][0]["ok"] is False
        assert "cannot be unposted" in body["results"][0]["error"]
        assert body["results"][1]["ok"] is True
