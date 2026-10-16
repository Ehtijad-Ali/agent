"""Agent, content-generation, tracking, search and scheduling tests.

No network. The tracking redirect is exercised through TestClient, so no real
browser or Discord call is involved.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.engine import reset_active_config
from app.db.session import Base, get_db
from app.main import app
from app.models import Agent, AgentOutput, Conversation, LinkClick, TrackingLink
from app.services.content_service import ContentError, build_ad, generate_output
from app.services.locations import US_CITIES
from app.services.reply_service import DISCLOSURE, PRODUCT_URL
from app.services.tracking_service import apply_tracking, looks_like_bot
from app.workers.poller import next_due, parse_times


@pytest.fixture(autouse=True)
def _reset_active_config():
    """The active tuning config lives in module state, so a test that edits it
    would otherwise leak into every test after it."""
    reset_active_config()
    yield
    reset_active_config()


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
def client(session_factory):
    def override():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# --- scheduling (brief §1: twice a day) ------------------------------------


class TestSchedule:
    def test_parses_times(self):
        assert parse_times(["09:00", "21:00"]) == [
            time(9, 0, tzinfo=UTC),
            time(21, 0, tzinfo=UTC),
        ]

    def test_malformed_times_are_dropped_not_fatal(self):
        """A typo must not stop ingestion entirely."""
        assert parse_times(["09:00", "banana", "25:99"]) == [time(9, 0, tzinfo=UTC)]

    def test_picks_the_next_slot_today(self):
        now = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)
        due = next_due(now, parse_times(["09:00", "21:00"]))
        assert due == datetime(2026, 10, 1, 21, 0, tzinfo=UTC)

    def test_rolls_over_to_tomorrow_after_the_last_slot(self):
        now = datetime(2026, 10, 1, 22, 0, tzinfo=UTC)
        due = next_due(now, parse_times(["09:00", "21:00"]))
        assert due == datetime(2026, 10, 2, 9, 0, tzinfo=UTC)

    def test_exactly_on_a_slot_waits_for_the_next_one(self):
        """Strictly-after, or finishing at 09:00 would immediately re-run."""
        now = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
        due = next_due(now, parse_times(["09:00", "21:00"]))
        assert due == datetime(2026, 10, 1, 21, 0, tzinfo=UTC)

    def test_twice_daily_slots_are_24h_apart(self):
        times = parse_times(["09:00", "21:00"])
        first = next_due(datetime(2026, 10, 1, 0, 0, tzinfo=UTC), times)
        second = next_due(first, times)
        third = next_due(second, times)
        assert third - first == timedelta(days=1)


# --- tracking links (brief §1 analytics) -----------------------------------


def _conversation(**overrides) -> Conversation:
    base = {
        "platform": "discord",
        "external_id": "555:666",
        "community": "Test#general",
        "author_pseudonym": "user_abcd",
        "message": "any free prediction game?",
        "posted_at": datetime.now(UTC),
        "country": "US",
        "language": "en",
        "score": 70,
        "intent": "high",
        "confidence": "high",
        "matched_keywords": [],
        "contributions": [],
        "risk_flags": [],
        "summary": "",
        "status": "approved",
        "reply_variants": [{"tone": "concise", "text": f"hi {PRODUCT_URL}"}],
        "selected_variant": 0,
        "history": [],
    }
    base.update(overrides)
    return Conversation(**base)


class TestTracking:
    def test_bot_user_agents_are_recognised(self):
        assert looks_like_bot("Discordbot/2.0")
        assert looks_like_bot("TelegramBot (like TwitterBot)")
        assert looks_like_bot(None)
        assert not looks_like_bot(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit/605.1.15"
        )

    def test_apply_tracking_swaps_the_product_url(self, db):
        link = TrackingLink(
            slug="abc123", conversation_id="c", platform="discord", target_url=PRODUCT_URL
        )
        text = apply_tracking(f"come see {PRODUCT_URL} ok", link)
        assert PRODUCT_URL not in text
        assert "/r/abc123" in text

    def test_apply_tracking_leaves_text_without_the_url_alone(self, db):
        """Appending a link to an edited message would be worse than losing
        the attribution."""
        link = TrackingLink(
            slug="abc123", conversation_id="c", platform="discord", target_url=PRODUCT_URL
        )
        assert apply_tracking("no link here", link) == "no link here"

    def test_preview_shows_the_tracking_link(self, client, session_factory):
        session = session_factory()
        row = _conversation()
        session.add(row)
        session.commit()
        row_id = row.id
        session.close()

        body = client.get(f"/api/replies/{row_id}/preview").json()
        assert "/r/" in body["text"]
        assert PRODUCT_URL not in body["text"]

    def test_preview_reuses_the_same_link(self, client, session_factory):
        """One link per conversation, so a click maps to exactly one reply."""
        session = session_factory()
        row = _conversation()
        session.add(row)
        session.commit()
        row_id = row.id
        session.close()

        first = client.get(f"/api/replies/{row_id}/preview").json()["text"]
        second = client.get(f"/api/replies/{row_id}/preview").json()["text"]
        assert first == second

        session = session_factory()
        assert len(session.execute(select(TrackingLink)).scalars().all()) == 1
        session.close()

    def test_redirect_records_a_human_click(self, client, session_factory):
        session = session_factory()
        row = _conversation()
        session.add(row)
        session.commit()
        row_id = row.id
        session.close()
        client.get(f"/api/replies/{row_id}/preview")

        session = session_factory()
        slug = session.execute(select(TrackingLink.slug)).scalar_one()
        session.close()

        response = client.get(
            f"/r/{slug}",
            headers={"user-agent": "Mozilla/5.0 (Macintosh) AppleWebKit/605.1.15"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == PRODUCT_URL

        session = session_factory()
        clicks = session.execute(select(LinkClick)).scalars().all()
        assert len(clicks) == 1
        assert clicks[0].is_bot == 0
        session.close()

    def test_link_preview_fetch_is_recorded_but_flagged(self, client, session_factory):
        """Discord unfurls every link we post; counting it would fake a 100%
        click-through rate."""
        session = session_factory()
        row = _conversation()
        session.add(row)
        session.commit()
        row_id = row.id
        session.close()
        client.get(f"/api/replies/{row_id}/preview")

        session = session_factory()
        slug = session.execute(select(TrackingLink.slug)).scalar_one()
        session.close()

        client.get(f"/r/{slug}", headers={"user-agent": "Discordbot/2.0"}, follow_redirects=False)

        engagement = client.get("/api/insights/engagement?range=7d").json()
        assert engagement["clicks"] == 0
        assert engagement["botHits"] == 1

    def test_unknown_slug_still_lands_on_the_product(self, client):
        response = client.get("/r/nosuchslug", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == PRODUCT_URL

    def test_no_ip_is_stored(self, client, session_factory):
        session = session_factory()
        row = _conversation()
        session.add(row)
        session.commit()
        row_id = row.id
        session.close()
        client.get(f"/api/replies/{row_id}/preview")

        session = session_factory()
        slug = session.execute(select(TrackingLink.slug)).scalar_one()
        session.close()
        client.get(f"/r/{slug}", headers={"user-agent": "Mozilla/5.0"}, follow_redirects=False)

        session = session_factory()
        click = session.execute(select(LinkClick)).scalars().one()
        # The visitor hash must never be the address itself.
        assert "127.0.0.1" not in (click.visitor_hash or "")
        assert "testclient" not in (click.visitor_hash or "")
        session.close()


# --- agents (brief §3) -----------------------------------------------------


class TestAgents:
    def test_lists_types_with_rule_schemas(self, client):
        body = client.get("/api/agents/types").json()
        assert {t["type"] for t in body["types"]} == {"engagement", "content"}
        assert "properties" in body["types"][0]["ruleSchema"]

    def test_creates_disabled_by_default(self, client):
        body = client.post(
            "/api/agents",
            json={"name": "Discord watcher", "agentType": "engagement"},
        ).json()
        # An agent that ran the moment it was created would act before anyone
        # had reviewed its rules.
        assert body["enabled"] is False

    def test_rules_are_defaulted_and_validated(self, client):
        body = client.post(
            "/api/agents", json={"name": "A", "agentType": "engagement"}
        ).json()
        assert body["rules"]["platforms"] == ["discord", "telegram"]

    def test_invalid_rules_are_rejected(self, client):
        response = client.post(
            "/api/agents",
            json={
                "name": "B",
                "agentType": "engagement",
                "rules": {"minScore": 5000},
            },
        )
        assert response.status_code == 400

    def test_unknown_type_is_rejected(self, client):
        """422 from request validation: AgentType is a Literal."""
        response = client.post(
            "/api/agents", json={"name": "C", "agentType": "telepathy"}
        )
        assert response.status_code == 422

    def test_duplicate_name_is_refused(self, client):
        client.post("/api/agents", json={"name": "Dup", "agentType": "content"})
        second = client.post("/api/agents", json={"name": "Dup", "agentType": "content"})
        assert second.status_code == 409

    def test_many_agents_can_coexist(self, client):
        for i in range(5):
            assert (
                client.post(
                    "/api/agents",
                    json={"name": f"Agent {i}", "agentType": "engagement"},
                ).status_code
                == 201
            )
        assert len(client.get("/api/agents").json()) == 5

    def test_filters_by_type_and_enabled(self, client):
        client.post("/api/agents", json={"name": "E", "agentType": "engagement"})
        created = client.post(
            "/api/agents",
            json={
                "name": "C1",
                "agentType": "content",
                "enabled": True,
                "rules": {"contactEmail": "x@example.com"},
            },
        ).json()
        assert len(client.get("/api/agents?type=content").json()) == 1
        enabled = client.get("/api/agents?enabled=true").json()
        assert [a["id"] for a in enabled] == [created["id"]]

    def test_enable_and_delete(self, client):
        created = client.post(
            "/api/agents", json={"name": "Toggle", "agentType": "engagement"}
        ).json()
        patched = client.patch(
            f"/api/agents/{created['id']}", json={"enabled": True}
        ).json()
        assert patched["enabled"] is True
        assert client.delete(f"/api/agents/{created['id']}").status_code == 204
        assert client.get(f"/api/agents/{created['id']}").status_code == 404

    def test_creation_is_audited(self, client):
        client.post("/api/agents", json={"name": "Audited", "agentType": "content"})
        log = client.get("/api/activity").json()
        assert log["items"][0]["action"] == "created agent"


# --- content agents (brief §2) ---------------------------------------------


class TestContentGeneration:
    @pytest.fixture
    def content_agent(self, client):
        return client.post(
            "/api/agents",
            json={
                "name": "Ad writer",
                "agentType": "content",
                "enabled": True,
                "rules": {
                    "contactEmail": "ads@example.com",
                    "categories": ["community", "events"],
                },
            },
        ).json()

    def test_ad_carries_the_mandatory_wording(self):
        ad = build_ad(US_CITIES[0], "community", "x@example.com")
        assert DISCLOSURE in ad["body"]
        assert "free to play" in ad["body"].lower()
        assert "18+" in ad["body"]

    def test_ad_is_personalised_to_the_city(self):
        ad = build_ad(US_CITIES[0], "community", "x@example.com")
        assert US_CITIES[0].name in ad["title"]
        assert US_CITIES[0].name in ad["body"]
        assert ad["zipcode"] == US_CITIES[0].zipcode

    def test_different_cities_read_differently(self):
        """Not one template with the name swapped."""
        bodies = {
            build_ad(city, "community", "x@example.com")["body"]
            for city in US_CITIES[:12]
        }
        assert len(bodies) == 12

    def test_same_city_is_stable(self):
        first = build_ad(US_CITIES[3], "events", "x@example.com")
        second = build_ad(US_CITIES[3], "events", "x@example.com")
        assert first == second

    def test_generate_records_an_output(self, client, content_agent):
        body = client.post(f"/api/agents/{content_agent['id']}/generate").json()
        assert body["city"]
        assert body["status"] == "generated"
        assert body["publishedUrl"] is None
        assert body["category"] in ("community", "events")

    def test_never_repeats_a_city(self, client, content_agent):
        """Brief §2.2: a US city different from any used before."""
        seen = set()
        for _ in range(12):
            body = client.post(f"/api/agents/{content_agent['id']}/generate").json()
            assert body["locationKey"] not in seen
            seen.add(body["locationKey"])

    def test_remaining_cities_shrinks(self, client, content_agent):
        before = client.get(f"/api/agents/{content_agent['id']}/cities").json()["remaining"]
        client.post(f"/api/agents/{content_agent['id']}/generate")
        after = client.get(f"/api/agents/{content_agent['id']}/cities").json()["remaining"]
        assert after == before - 1

    def test_exhaustion_is_an_explicit_error(self, db):
        """Rather than silently repeating a city."""
        agent = Agent(
            name="Exhausted",
            agent_type="content",
            enabled=1,
            rules={"contactEmail": "x@example.com", "categories": ["community"]},
        )
        db.add(agent)
        db.commit()
        for city in US_CITIES:
            db.add(AgentOutput(agent_id=agent.id, location_key=city.key, city=city.name))
        db.commit()

        with pytest.raises(ContentError, match="already been used"):
            generate_output(db, agent)

    def test_disabled_agent_cannot_generate(self, client):
        agent = client.post(
            "/api/agents",
            json={
                "name": "Off",
                "agentType": "content",
                "rules": {"contactEmail": "x@example.com"},
            },
        ).json()
        response = client.post(f"/api/agents/{agent['id']}/generate")
        assert response.status_code == 409

    def test_missing_contact_email_is_refused(self, client):
        agent = client.post(
            "/api/agents",
            json={"name": "NoEmail", "agentType": "content", "enabled": True},
        ).json()
        response = client.post(f"/api/agents/{agent['id']}/generate")
        assert response.status_code == 422
        assert "contactEmail" in response.json()["error"]["message"]

    def test_engagement_agent_cannot_generate_ads(self, client):
        agent = client.post(
            "/api/agents",
            json={"name": "Wrong type", "agentType": "engagement", "enabled": True},
        ).json()
        assert client.post(f"/api/agents/{agent['id']}/generate").status_code == 422

    def test_publish_records_the_live_url(self, client, content_agent):
        """Brief §2.9: generated content plus published URL."""
        output = client.post(f"/api/agents/{content_agent['id']}/generate").json()
        body = client.post(
            f"/api/agents/outputs/{output['id']}/publish",
            json={"publishedUrl": "https://example.craigslist.org/abc/123.html"},
        ).json()
        assert body["status"] == "published"
        assert body["publishedUrl"].endswith("123.html")
        assert body["publishedAt"] is not None

    def test_outputs_are_listed_and_filterable(self, client, content_agent):
        first = client.post(f"/api/agents/{content_agent['id']}/generate").json()
        client.post(f"/api/agents/{content_agent['id']}/generate")
        client.post(
            f"/api/agents/outputs/{first['id']}/publish",
            json={"publishedUrl": "https://example.org/x"},
        )

        assert client.get(f"/api/agents/{content_agent['id']}/outputs").json()["total"] == 2
        published = client.get(
            f"/api/agents/{content_agent['id']}/outputs?status=published"
        ).json()
        assert published["total"] == 1


# --- refinement index (brief §8) -------------------------------------------


class TestRefinementIndex:
    def test_refuses_to_be_confident_on_thin_data(self, client):
        body = client.get("/api/insights/refinement").json()
        assert body["confident"] is False
        assert body["sampleSize"] == 0
        assert any("needed before this score" in n for n in body["notes"])

    def test_explains_low_precision(self, client, session_factory):
        session = session_factory()
        for i in range(25):
            session.add(
                _conversation(external_id=f"c:{i}", intent="not_relevant", status="new")
            )
        session.commit()
        session.close()

        body = client.get("/api/insights/refinement").json()
        assert body["precision"] == 0.0
        assert any("matching too broadly" in n for n in body["notes"])

    def test_score_is_bounded(self, client, session_factory):
        session = session_factory()
        for i in range(25):
            session.add(_conversation(external_id=f"d:{i}"))
        session.commit()
        session.close()
        body = client.get("/api/insights/refinement").json()
        assert 0 <= body["score"] <= 100


# --- filters and search ----------------------------------------------------


class TestFiltersAndSearch:
    @pytest.fixture
    def seeded(self, session_factory):
        session = session_factory()
        session.add(_conversation(external_id="r:1", risk_flags=["underage"]))
        session.add(_conversation(external_id="r:2", risk_flags=[]))
        session.add(
            _conversation(
                external_id="r:3",
                risk_flags=[],
                posted_at=datetime.now(UTC) - timedelta(days=10),
            )
        )
        session.commit()
        session.close()

    def test_filters_by_risk(self, client, seeded):
        assert client.get("/api/conversations?hasRisk=true").json()["total"] == 1
        assert client.get("/api/conversations?hasRisk=false").json()["total"] == 2

    def test_filters_by_custom_date_range(self, client, seeded):
        cutoff = quote((datetime.now(UTC) - timedelta(days=2)).isoformat())
        assert client.get(f"/api/conversations?postedAfter={cutoff}").json()["total"] == 2
        assert client.get(f"/api/conversations?postedBefore={cutoff}").json()["total"] == 1

    def test_global_search_spans_record_types(self, client, seeded):
        client.post(
            "/api/agents",
            json={"name": "prediction hunter", "agentType": "engagement"},
        )
        body = client.get("/api/search?q=prediction").json()
        kinds = {hit["kind"] for hit in body["hits"]}
        assert "conversation" in kinds
        assert "agent" in kinds

    def test_search_requires_two_characters(self, client):
        assert client.get("/api/search?q=a").status_code == 422

    def test_activity_filters_by_date(self, client):
        client.post("/api/agents", json={"name": "Logged", "agentType": "content"})
        future = quote((datetime.now(UTC) + timedelta(days=1)).isoformat())
        assert client.get(f"/api/activity?after={future}").json()["total"] == 0
        past = quote((datetime.now(UTC) - timedelta(days=1)).isoformat())
        assert client.get(f"/api/activity?after={past}").json()["total"] >= 1

    def test_activity_filters_by_agent_name(self, client):
        client.post("/api/agents", json={"name": "Alpha", "agentType": "content"})
        client.post("/api/agents", json={"name": "Beta", "agentType": "content"})
        assert client.get("/api/activity?agent=Alpha").json()["total"] == 1


# --- presets (brief §5) ----------------------------------------------------


class TestPresets:
    def test_snapshots_the_active_config(self, client):
        body = client.post("/api/tuning/presets", json={"name": "Baseline"}).json()
        assert body["name"] == "Baseline"
        assert len(body["config"]["keywords"]) > 0

    def test_duplicate_name_is_refused(self, client):
        client.post("/api/tuning/presets", json={"name": "Same"})
        assert client.post("/api/tuning/presets", json={"name": "Same"}).status_code == 409

    def test_applying_a_preset_writes_a_config_version(self, client):
        preset = client.post("/api/tuning/presets", json={"name": "Applied"}).json()
        assert client.post(f"/api/tuning/presets/{preset['id']}/apply").status_code == 200
        log = client.get("/api/activity?action=saved+tuning+config").json()
        assert log["total"] >= 1

    def test_presets_survive_as_rows(self, client):
        client.post("/api/tuning/presets", json={"name": "Persisted"})
        assert [p["name"] for p in client.get("/api/tuning/presets").json()] == [
            "Persisted"
        ]

    def test_delete(self, client):
        preset = client.post("/api/tuning/presets", json={"name": "Gone"}).json()
        assert client.delete(f"/api/tuning/presets/{preset['id']}").status_code == 204
        assert client.get("/api/tuning/presets").json() == []


class TestPerCountryLanguage:
    def test_country_rule_accepts_a_language(self, client):
        config = client.get("/api/tuning").json()
        config["countries"][0]["language"] = "es"
        saved = client.put("/api/tuning", json=config).json()
        assert saved["countries"][0]["language"] == "es"

    def test_language_defaults_to_empty_for_fallback(self, client):
        config = client.get("/api/tuning").json()
        assert config["countries"][0]["language"] == ""
