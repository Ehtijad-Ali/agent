"""Backlink-audit agent tests.

The HTML classification and sheet parsing are pure and tested directly. The
API is exercised through TestClient with the network-touching run patched out.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import agents as agents_routes
from app.db.session import Base, get_db
from app.main import app
from app.models import BacklinkCheck
from app.services.backlink_service import (
    BacklinkError,
    classify,
    column_index,
    results_csv,
    sheet_csv_url,
    urls_from_csv,
)

DOMAIN = "all-bettors.com"
PAGE = "https://blog.example.com/post"
SHEET = "https://docs.google.com/spreadsheets/d/1mTZe9_Zf6f5BMmtAsxElW80boI5_EG85cAxo_0jjM4I/edit?usp=sharing"


class TestSheet:
    def test_export_url(self):
        assert sheet_csv_url(SHEET) == (
            "https://docs.google.com/spreadsheets/d/"
            "1mTZe9_Zf6f5BMmtAsxElW80boI5_EG85cAxo_0jjM4I/export?format=csv"
        )

    def test_export_url_keeps_tab(self):
        assert sheet_csv_url(SHEET + "#gid=42").endswith("&gid=42")

    def test_rejects_non_sheet_link(self):
        with pytest.raises(BacklinkError):
            sheet_csv_url("https://example.com/not-a-sheet")

    @pytest.mark.parametrize("letter,index", [("A", 0), ("b", 1), ("Z", 25), ("AA", 26)])
    def test_column_index(self, letter, index):
        assert column_index(letter) == index

    def test_urls_skip_headers_and_blanks_and_keep_row_numbers(self):
        text = "URL,Dofollow\nhttps://a.com/x,\n,\nnot a url,\nhttp://b.com/y,yes\n"
        assert urls_from_csv(text) == [(2, "https://a.com/x"), (5, "http://b.com/y")]

    def test_other_column(self):
        assert urls_from_csv("x,https://a.com\n", "B") == [(1, "https://a.com")]


class TestClassify:
    def test_plain_link_is_dofollow(self):
        html = '<p>See <a href="https://www.all-bettors.com/">All Bettors</a></p>'
        v = classify(html, PAGE, DOMAIN)
        assert v["result"] == "dofollow"
        assert v["anchor_text"] == "All Bettors"

    @pytest.mark.parametrize("rel", ["nofollow", "sponsored", "ugc", "noopener NoFollow"])
    def test_rel_values_that_block_value(self, rel):
        html = f'<a rel="{rel}" href="https://all-bettors.com">x</a>'
        assert classify(html, PAGE, DOMAIN)["result"] == "nofollow"

    def test_noopener_alone_is_still_dofollow(self):
        html = '<a rel="noopener noreferrer" href="https://all-bettors.com">x</a>'
        assert classify(html, PAGE, DOMAIN)["result"] == "dofollow"

    def test_meta_robots_nofollow_overrides(self):
        html = (
            '<meta name="robots" content="index, nofollow">'
            '<a href="https://all-bettors.com">x</a>'
        )
        assert classify(html, PAGE, DOMAIN)["result"] == "nofollow"

    def test_x_robots_tag_header(self):
        html = '<a href="https://all-bettors.com">x</a>'
        assert classify(html, PAGE, DOMAIN, "nofollow")["result"] == "nofollow"

    def test_one_dofollow_among_several_wins(self):
        html = (
            '<a rel="nofollow" href="https://all-bettors.com/a">a</a>'
            '<a href="https://all-bettors.com/b">b</a>'
        )
        assert classify(html, PAGE, DOMAIN)["result"] == "dofollow"

    def test_lookalike_domain_does_not_count(self):
        html = '<a href="https://all-bettors.com.evil.net">x</a><a href="https://notall-bettors.com">y</a>'
        assert classify(html, PAGE, DOMAIN)["result"] == "not_found"

    def test_relative_links_resolve_against_the_page(self):
        html = '<a href="/elsewhere">x</a>'
        assert classify(html, PAGE, DOMAIN)["result"] == "not_found"

    def test_no_link(self):
        assert classify("<p>nothing</p>", PAGE, DOMAIN)["result"] == "not_found"


def test_results_csv_is_in_sheet_order_with_result_in_column_b():
    rows = [
        BacklinkCheck(row=3, page_url="https://b", result="nofollow", rel="nofollow",
                      link_href="", anchor_text="", detail=""),
        BacklinkCheck(row=1, page_url="https://a", result="dofollow", rel="",
                      link_href="", anchor_text="", detail=""),
    ]
    lines = results_csv(rows).splitlines()
    assert lines[0].startswith("URL,Result")
    assert lines[1].startswith("https://a,dofollow")
    assert lines[2].startswith("https://b,nofollow")


# --- API ---------------------------------------------------------------------


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
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)
    agents_routes._audits.clear()


def _create(client, **body):
    payload = {"name": "Audit", "agentType": "backlink_audit", "enabled": True}
    payload.update(body)
    response = client.post("/api/agents", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


class TestAuditApi:
    def test_type_is_listed(self, client):
        types = [t["type"] for t in client.get("/api/agents/types").json()["types"]]
        assert "backlink_audit" in types

    def test_sheet_link_is_taken_from_the_description(self, client):
        agent = _create(client, description=f"1 - Look on the first URL cell in {SHEET} and check")
        assert agent["rules"]["sheetUrl"] == SHEET
        assert agent["rules"]["targetDomain"] == DOMAIN

    def test_audit_without_sheet_is_refused(self, client):
        agent = _create(client)
        assert client.post(f"/api/agents/{agent['id']}/audit").status_code == 422

    def test_disabled_agent_is_refused(self, client):
        agent = _create(client, enabled=False, rules={"sheetUrl": SHEET})
        assert client.post(f"/api/agents/{agent['id']}/audit").status_code == 409

    def test_wrong_agent_type_is_refused(self, client):
        agent = _create(client, agentType="engagement")
        assert client.get(f"/api/agents/{agent['id']}/audit").status_code == 409

    def test_start_reports_running(self, client, monkeypatch):
        async def no_run(agent_id):
            return None

        monkeypatch.setattr(agents_routes, "_run_audit", no_run)
        agent = _create(client, rules={"sheetUrl": SHEET})
        response = client.post(f"/api/agents/{agent['id']}/audit")
        assert response.status_code == 202
        assert response.json()["status"] == "running"
        # A second start while the first is running is refused.
        assert client.post(f"/api/agents/{agent['id']}/audit").status_code == 409

    def test_idle_before_first_run_and_csv_has_header(self, client):
        agent = _create(client, rules={"sheetUrl": SHEET})
        assert client.get(f"/api/agents/{agent['id']}/audit").json()["status"] == "idle"
        csv = client.get(f"/api/agents/{agent['id']}/audit.csv")
        assert csv.status_code == 200
        assert csv.text.startswith("URL,Result")
