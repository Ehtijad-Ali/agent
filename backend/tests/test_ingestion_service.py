"""Ingestion tests. No network calls; the connector is faked.

The property that matters most here is idempotence. The poller re-reads the
same channel every cycle, so a second pass over identical messages must add
nothing -- otherwise the Inbox fills with duplicates of every lead.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.defaults import default_tuning
from app.db.session import Base
from app.integrations.base import NormalisedMessage
from app.models import Conversation
from app.services.ingestion_service import (
    UNKNOWN_COUNTRY,
    build_summary,
    initial_status,
    normalise_to_conversation,
    persist_messages,
)
from app.services.scoring_service import score_message


@pytest.fixture
def db():
    """An in-memory database per test, with the real schema."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()


@pytest.fixture
def config():
    return default_tuning()


def _message(**overrides) -> NormalisedMessage:
    base = {
        "platform": "discord",
        "external_id": "chan:1",
        "community": "Test#general",
        "author_pseudonym": "user_abcd",
        "message": "anyone know a free to play prediction game with no deposit?",
        "posted_at": datetime.now(UTC),
        "country": None,
        "language": None,
        "source_url": "https://discord.com/channels/1/2/3",
    }
    base.update(overrides)
    return NormalisedMessage(**base)


class TestNormalisation:
    def test_scores_and_drafts(self, config):
        row = normalise_to_conversation(_message(), config)
        assert row.score > 0
        assert row.matched_keywords
        assert row.status == "new"
        # A clean lead gets drafts; a human still has to approve one.
        assert len(row.reply_variants) == 3
        assert row.selected_variant == 0
        assert row.edited_reply is None

    def test_unknown_country_is_recorded_not_invented(self, config):
        row = normalise_to_conversation(_message(country=None), config)
        assert row.country == UNKNOWN_COUNTRY

    def test_unknown_country_earns_no_country_boost(self, config):
        """The country boost must not be awarded to a message with no country."""
        row = normalise_to_conversation(_message(country=None), config)
        labels = [c["label"] for c in row.contributions]
        assert not any("country" in label.lower() for label in labels)

    def test_known_country_is_preserved(self, config):
        row = normalise_to_conversation(_message(country="GB"), config)
        assert row.country == "GB"

    def test_history_starts_with_discovery(self, config):
        row = normalise_to_conversation(_message(), config)
        assert len(row.history) == 1
        assert row.history[0]["actor"] == "system"

    def test_language_is_detected_when_absent(self, config):
        row = normalise_to_conversation(_message(language=None), config)
        assert row.language


class TestRiskHandling:
    def test_flagged_message_is_blocked_with_no_draft(self, config):
        """Spec §15: a risky message must never arrive with a reply ready to send."""
        row = normalise_to_conversation(
            _message(message="im 15 and want to bet real money"), config
        )
        assert row.risk_flags
        assert row.status == "blocked"
        assert row.reply_variants == []

    def test_initial_status_is_never_approved(self, config):
        """Nothing is auto-approved, whatever it scores."""
        for message in (
            "anyone know a free to play prediction game with no deposit?",
            "hello",
            "im 15",
        ):
            result = score_message(message, config)
            assert initial_status(result) in {"new", "blocked"}


class TestSummary:
    def test_underage_summary_wins_over_keywords(self):
        summary = build_summary("free game", ["free game"], ["underage"])
        assert "under 18" in summary

    def test_no_match_summary(self):
        assert build_summary("hello", [], []) == (
            "No keywords matched, and the message is not asking for a recommendation."
        )

    def test_asking_and_no_deposit_are_both_reported(self):
        summary = build_summary(
            "anyone know a game with no deposit", ["anyone know a game"], []
        )
        assert "asking for a recommendation" in summary
        assert "no deposit" in summary


class TestPersistence:
    def test_inserts_new_messages(self, db, config):
        added = persist_messages(db, "discord", [_message()], config)
        assert added == 1
        assert db.execute(select(Conversation)).scalars().all()

    def test_second_pass_adds_nothing(self, db, config):
        """The poller re-reads the same channel; a duplicate must not appear."""
        messages = [_message()]
        assert persist_messages(db, "discord", messages, config) == 1
        assert persist_messages(db, "discord", messages, config) == 0
        assert len(db.execute(select(Conversation)).scalars().all()) == 1

    def test_duplicates_within_one_batch_collapse(self, db, config):
        added = persist_messages(
            db, "discord", [_message(), _message()], config
        )
        assert added == 1

    def test_same_external_id_on_another_platform_is_distinct(self, db, config):
        """external_id is only unique per platform, not globally."""
        persist_messages(db, "discord", [_message(external_id="shared")], config)
        persist_messages(
            db, "telegram", [_message(platform="telegram", external_id="shared")], config
        )
        assert len(db.execute(select(Conversation)).scalars().all()) == 2

    def test_empty_batch_is_a_noop(self, db, config):
        assert persist_messages(db, "discord", [], config) == 0

    def test_new_message_is_added_alongside_an_existing_one(self, db, config):
        persist_messages(db, "discord", [_message(external_id="chan:1")], config)
        added = persist_messages(db, "discord", [_message(external_id="chan:2")], config)
        assert added == 1
        assert len(db.execute(select(Conversation)).scalars().all()) == 2


class TestTimestamps:
    def test_posted_at_round_trips_as_utc(self, db, config):
        """SQLite drops tzinfo. Without UtcDateTime the browser would read every
        timestamp as local time and shift it by the viewer's offset."""
        posted = datetime.now(UTC) - timedelta(hours=3)
        persist_messages(db, "discord", [_message(posted_at=posted)], config)

        row = db.execute(select(Conversation)).scalars().one()
        assert row.posted_at.tzinfo is not None
        assert row.posted_at.utcoffset() == timedelta(0)
        assert abs((row.posted_at - posted).total_seconds()) < 1

    def test_naive_input_is_treated_as_utc(self, db, config):
        naive = datetime(2026, 9, 1, 12, 0, 0)
        persist_messages(db, "discord", [_message(posted_at=naive)], config)

        row = db.execute(select(Conversation)).scalars().one()
        assert row.posted_at.tzinfo is not None
        assert row.posted_at.hour == 12


class TestAgents:
    def _agent(self, db, **rules):
        from app.models import Agent

        agent = Agent(name="Test agent", agent_type="engagement", enabled=1,
                      rules={"platforms": ["discord", "telegram"], **rules})
        db.add(agent)
        db.commit()
        return agent

    def test_enabled_agent_picks_up_new_conversation(self, db, config):
        from app.services.ingestion_service import enabled_engagement_agents

        self._agent(db)
        counts: dict[str, int] = {}
        persist_messages(db, "discord", [_message()], config,
                         enabled_engagement_agents(db), counts)
        assert counts == {"Test agent": 1}
        row = db.execute(select(Conversation)).scalar_one()
        assert any(h["action"] == "picked up by agent" for h in row.history)

    def test_score_floor_excludes(self, db, config):
        from app.services.ingestion_service import enabled_engagement_agents

        self._agent(db, minScore=90)
        counts: dict[str, int] = {}
        persist_messages(db, "discord", [_message(message="hello everyone")], config,
                         enabled_engagement_agents(db), counts)
        assert counts == {"Test agent": 0}

    def test_disabled_agent_is_ignored(self, db):
        from app.services.ingestion_service import enabled_engagement_agents

        agent = self._agent(db)
        agent.enabled = 0
        db.commit()
        assert enabled_engagement_agents(db) == []


class TestScanSummary:
    def test_empty_telegram_poll_is_explained(self):
        from app.services.ingestion_service import scan_summary

        text = scan_summary(
            [{"platform": "telegram", "examined": 0, "discovered": 0, "error": None,
              "received": {"updates": 0, "textMessages": 0, "skippedNoText": 0,
                           "chats": [], "events": []}}],
            {},
        )
        assert "delivered nothing" in text
        assert "no engagement agent is enabled" in text
