"""Reply safety and send-path tests.

Nothing here touches a network. The connector is replaced with a fake, so a
regression cannot post to a real server while the suite runs.

These tests are the enforcement of the five non-negotiable rules in
core/defaults.py, which until Phase 2 were strings nothing checked.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.defaults import default_tuning
from app.db.session import Base, get_db
from app.main import app
from app.models import Conversation, ReplySend
from app.services.reply_service import draft_all_variants
from app.services.safety_service import check_reply, outgoing_text

COMPLIANT = (
    "Hey there. Full disclosure, I work on Join All Bettors. It's a free "
    "prediction game, which sounds like what you're after. Free to play, no "
    "deposits, 18+. https://joinallbettors.example"
)


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def db(session_factory):
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def config():
    return default_tuning()


def _conversation(**overrides) -> Conversation:
    base = {
        "platform": "discord",
        "external_id": "555:666",
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
        "contributions": [],
        "risk_flags": [],
        "summary": "",
        "status": "approved",
        "reply_variants": [{"tone": "concise", "text": COMPLIANT}],
        "selected_variant": 0,
        "history": [],
    }
    base.update(overrides)
    return Conversation(**base)


class TestOutgoingText:
    def test_prefers_the_edit(self):
        row = _conversation(edited_reply="my own words")
        assert outgoing_text(row) == "my own words"

    def test_falls_back_to_the_selected_variant(self):
        row = _conversation(
            reply_variants=[{"tone": "a", "text": "first"}, {"tone": "b", "text": "second"}],
            selected_variant=1,
        )
        assert outgoing_text(row) == "second"

    def test_out_of_range_index_yields_nothing_rather_than_crashing(self):
        row = _conversation(selected_variant=9)
        assert outgoing_text(row) == ""


class TestApprovalGate:
    def test_approved_compliant_reply_passes(self, db, config):
        assert check_reply(db, _conversation(), config) == []

    @pytest.mark.parametrize(
        "status", ["new", "awaiting", "rejected", "snoozed", "blocked", "manually_posted"]
    )
    def test_unapproved_status_is_refused(self, db, config, status):
        """"Never post autonomously": only a human-set 'approved' may send."""
        problems = check_reply(db, _conversation(status=status), config)
        assert any("approved" in p for p in problems)

    def test_already_sent_is_refused(self, db, config):
        problems = check_reply(db, _conversation(status="sent"), config)
        assert any("already been replied to" in p for p in problems)


class TestRiskFlags:
    def test_risk_flagged_conversation_cannot_be_replied_to(self, db, config):
        problems = check_reply(
            db, _conversation(risk_flags=["underage"]), config
        )
        assert any("risk flags" in p for p in problems)

    def test_risk_flag_refusal_survives_an_approved_status(self, db, config):
        """Approving a flagged row must not unlock sending."""
        problems = check_reply(
            db, _conversation(status="approved", risk_flags=["real_money"]), config
        )
        assert problems


class TestMandatoryWording:
    def test_missing_disclosure_is_refused(self, db, config):
        row = _conversation(
            edited_reply="Try this free to play game, no deposits, 18+."
        )
        problems = check_reply(db, row, config)
        assert any("disclosure" in p for p in problems)

    def test_missing_free_to_play_is_refused(self, db, config):
        row = _conversation(
            edited_reply="Full disclosure, I work on Join All Bettors. No deposits, 18+."
        )
        problems = check_reply(db, row, config)
        assert any("free-to-play" in p for p in problems)

    def test_missing_age_notice_is_refused(self, db, config):
        row = _conversation(
            edited_reply=(
                "Full disclosure, I work on Join All Bettors. Free to play, no deposits."
            )
        )
        problems = check_reply(db, row, config)
        assert any("18+" in p for p in problems)

    def test_empty_reply_is_refused(self, db, config):
        row = _conversation(reply_variants=[], edited_reply=None)
        problems = check_reply(db, row, config)
        assert any("no reply text" in p for p in problems)

    def test_rewording_is_allowed_while_the_substance_remains(self, db, config):
        """An operator may re-punctuate; they may not drop the requirements."""
        row = _conversation(
            edited_reply=(
                "full disclosure - i work on join all bettors! it is "
                "free-to-play, no deposit needed, 18 + only."
            )
        )
        assert check_reply(db, row, config) == []

    def test_line_breaks_do_not_defeat_the_check(self, db, config):
        row = _conversation(
            edited_reply=(
                "Full disclosure,\nI work on Join All Bettors.\nFree to play,\n"
                "no deposits,\n18+."
            )
        )
        assert check_reply(db, row, config) == []

    def test_over_length_reply_is_refused(self, db, config):
        row = _conversation(edited_reply=COMPLIANT + " x" * 400)
        problems = check_reply(db, row, config)
        assert any("over the" in p for p in problems)

    def test_every_drafted_variant_passes_its_own_check(self, db, config):
        """The drafter must not produce something the safety check rejects."""
        for variant in draft_all_variants("Test#general", config.voice):
            row = _conversation(edited_reply=variant["text"])
            assert check_reply(db, row, config) == [], variant["tone"]


class TestOneReplyPerPerson:
    def test_second_reply_to_the_same_author_is_refused(self, db, config):
        db.add(
            ReplySend(
                conversation_id="whatever",
                platform="discord",
                author_pseudonym="user_abcd",
                external_message_id="1",
                text=COMPLIANT,
            )
        )
        db.commit()

        problems = check_reply(db, _conversation(), config)
        assert any("one per person, ever" in p for p in problems)

    def test_the_same_pseudonym_on_another_platform_is_allowed(self, db, config):
        db.add(
            ReplySend(
                conversation_id="whatever",
                platform="telegram",
                author_pseudonym="user_abcd",
                external_message_id="1",
                text=COMPLIANT,
            )
        )
        db.commit()
        assert check_reply(db, _conversation(platform="discord"), config) == []

    def test_the_database_refuses_a_duplicate_outright(self, db):
        """The constraint is the rule, not just the check in front of it."""
        from sqlalchemy.exc import IntegrityError

        for _ in range(2):
            db.add(
                ReplySend(
                    conversation_id="c",
                    platform="discord",
                    author_pseudonym="user_same",
                    external_message_id="1",
                    text="x",
                )
            )
        with pytest.raises(IntegrityError):
            db.commit()


class TestRateCaps:
    def _fill(self, db, count: int, *, platform="discord", age=timedelta(minutes=5)):
        for i in range(count):
            db.add(
                ReplySend(
                    conversation_id=f"c{i}",
                    platform=platform,
                    author_pseudonym=f"other_{platform}_{i}",
                    external_message_id=str(i),
                    text="x",
                    sent_at=datetime.now(UTC) - age,
                )
            )
        db.commit()

    def test_hourly_cap_blocks_further_sends(self, db, config):
        self._fill(db, config.rate_caps.per_platform_per_hour)
        problems = check_reply(db, _conversation(), config)
        assert any("Hourly cap" in p for p in problems)

    def test_sends_outside_the_hour_do_not_count(self, db, config):
        self._fill(
            db, config.rate_caps.per_platform_per_hour, age=timedelta(hours=2)
        )
        problems = check_reply(db, _conversation(), config)
        assert not any("Hourly cap" in p for p in problems)

    def test_another_platform_has_its_own_hourly_budget(self, db, config):
        self._fill(db, config.rate_caps.per_platform_per_hour, platform="telegram")
        problems = check_reply(db, _conversation(platform="discord"), config)
        assert not any("Hourly cap" in p for p in problems)

    def test_daily_ceiling_blocks_further_sends(self, db, config):
        config.rate_caps.per_platform_per_hour = 1000
        self._fill(
            db, config.rate_caps.daily_approved_ceiling, age=timedelta(hours=5)
        )
        problems = check_reply(db, _conversation(), config)
        assert any("Daily cap" in p for p in problems)


class FakeConnector:
    """Stands in for a real platform. Records instead of posting."""

    def __init__(self, *, fail: bool = False):
        self.sent: list[tuple[str, str, str | None]] = []
        self.fail = fail

    async def send_message(self, chat_id, text, reply_to=None):
        if self.fail:
            raise RuntimeError("platform said no")
        self.sent.append((chat_id, text, reply_to))
        return "9999"


@pytest.fixture
def client(session_factory, monkeypatch):
    fake = FakeConnector()

    def override():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(
        "app.api.routes.replies.build_connectors", lambda: [("discord", fake)]
    )
    app.dependency_overrides[get_db] = override
    with TestClient(app) as test_client:
        test_client.fake = fake  # type: ignore[attr-defined]
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def approved(session_factory):
    session = session_factory()
    row = _conversation()
    session.add(row)
    session.commit()
    row_id = row.id
    session.close()
    return row_id


class TestSendEndpoint:
    def test_preview_reports_sendable(self, client, approved):
        body = client.get(f"/api/replies/{approved}/preview").json()
        assert body["canSend"] is True
        assert body["problems"] == []
        assert "Join All Bettors" in body["text"]

    def test_send_posts_and_records(self, client, approved, session_factory):
        response = client.post(f"/api/replies/{approved}/send")
        assert response.status_code == 200
        body = response.json()

        assert body["externalMessageId"] == "9999"
        assert body["conversation"]["status"] == "sent"

        # It replied in-thread to the original message, in the source channel.
        assert client.fake.sent == [("555", body["text"], "666")]

        session = session_factory()
        assert len(session.execute(select(ReplySend)).scalars().all()) == 1
        session.close()

    def test_send_is_audited(self, client, approved):
        client.post(f"/api/replies/{approved}/send")
        log = client.get("/api/activity").json()
        assert log["items"][0]["action"] == "sent reply"
        assert log["items"][0]["after"] == "sent"

    def test_sending_twice_is_refused(self, client, approved):
        assert client.post(f"/api/replies/{approved}/send").status_code == 200
        second = client.post(f"/api/replies/{approved}/send")
        assert second.status_code == 422
        # One message out, not two.
        assert len(client.fake.sent) == 1

    def test_unapproved_conversation_is_refused_without_posting(
        self, client, session_factory
    ):
        session = session_factory()
        row = _conversation(status="new", external_id="1:2", author_pseudonym="user_new")
        session.add(row)
        session.commit()
        row_id = row.id
        session.close()

        response = client.post(f"/api/replies/{row_id}/send")
        assert response.status_code == 422
        assert "approved" in response.json()["error"]["message"]
        assert client.fake.sent == []

    def test_stripped_disclosure_is_refused_without_posting(
        self, client, session_factory
    ):
        session = session_factory()
        row = _conversation(
            edited_reply="just check out this game",
            external_id="1:3",
            author_pseudonym="user_edit",
        )
        session.add(row)
        session.commit()
        row_id = row.id
        session.close()

        response = client.post(f"/api/replies/{row_id}/send")
        assert response.status_code == 422
        assert client.fake.sent == []

    def test_unknown_conversation_is_404(self, client):
        assert client.post("/api/replies/nope/send").status_code == 404

    def test_usage_reflects_a_send(self, client, approved):
        client.post(f"/api/replies/{approved}/send")
        usage = client.get("/api/replies/usage").json()
        assert usage["sentToday"] == 1
        assert usage["sentLastHour"]["discord"] == 1
