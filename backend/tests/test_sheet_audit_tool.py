"""The AI Agent hands whole-sheet backlink checks to the background audit
instead of running them inside the (slow, local) model loop."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import agents as agents_route
from app.db.session import Base
from app.models import Agent, BacklinkCheck
from app.services import agent_tools, backlink_service

SHEET = "https://docs.google.com/spreadsheets/d/1mTZe9_Zf6f5BMmtAsxElW80boI5/edit?usp=sharing"


@pytest.fixture
def ctx():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    yield agent_tools.ToolContext(db=db, user_id="u1", user_name="Sergio", chat_id="c1", task_id="t1")
    db.close()
    agents_route._audits.clear()


@pytest.fixture
def launched(monkeypatch):
    started: list[str] = []

    async def fake_run(agent_id: str) -> None:
        started.append(agent_id)

    async def fake_read(sheet_url: str, column: str = "A"):
        if "/spreadsheets/d/" not in sheet_url:
            raise backlink_service.BacklinkError("That is not a Google Sheets link.")
        return "A", [(1, "https://a.example/1"), (2, "https://a.example/2")]

    monkeypatch.setattr(agents_route, "_run_audit", fake_run)
    monkeypatch.setattr(backlink_service, "read_sheet_detecting", fake_read)
    return started


def _start(ctx, **args):
    async def go():
        result = await agent_tools.start_backlink_audit(
            ctx, agent_tools.StartAuditArgs(sheet_url=SHEET, **args)
        )
        await asyncio.sleep(0)  # let the scheduled background task run
        return result

    return asyncio.run(go())


def test_starting_an_audit_needs_approval():
    assert agent_tools.TOOLS["start_backlink_audit"].requires_approval is True
    assert agent_tools.TOOLS["backlink_audit_status"].requires_approval is False


def test_whole_sheet_goes_to_a_background_audit_agent(ctx, launched):
    result = _start(ctx)
    assert result["started"] is True
    agent = ctx.db.query(Agent).one()
    assert agent.agent_type == "backlink_audit" and agent.enabled
    assert agent.rules["sheetUrl"] == SHEET and agent.rules["targetDomain"] == "all-bettors.com"
    assert launched == [agent.id]
    assert agents_route.audit_running(agent.id)


def test_a_running_audit_is_not_started_twice(ctx, launched):
    _start(ctx)
    again = _start(ctx)
    assert again["started"] is False and again["status"] == "already running"
    assert ctx.db.query(Agent).count() == 1 and len(launched) == 1


def test_status_reports_progress_and_results(ctx, launched):
    _start(ctx)
    agent = ctx.db.query(Agent).one()
    agents_route._audits[agent.id].update(status="completed", done=2, total=2)
    for row, result in ((2, "dofollow"), (3, "nofollow")):
        ctx.db.add(BacklinkCheck(agent_id=agent.id, row=row, page_url=f"https://x/{row}", result=result))
    ctx.db.commit()

    status = asyncio.run(agent_tools.backlink_audit_status(
        ctx, agent_tools.AuditStatusArgs(sheet_url=SHEET)
    ))
    assert status["status"] == "completed"
    assert status["results"] == {"dofollow": 1, "nofollow": 1}


def test_not_a_sheet_link_is_refused(ctx, launched):
    with pytest.raises(agent_tools.ToolError):
        asyncio.run(agent_tools.start_backlink_audit(
            ctx, agent_tools.StartAuditArgs(sheet_url="https://example.com/list")
        ))
    assert launched == []


def test_inline_checks_are_capped_small():
    with pytest.raises(Exception):
        agent_tools.CheckBacklinksArgs(sheet_url=SHEET, limit=500)


def test_a_wrong_column_guess_still_finds_the_urls(ctx, launched):
    result = _start(ctx, column="B")  # the model guessed B; the URLs are in A
    assert result["column"] == "A" and result["urls"] == 2
    assert ctx.db.query(Agent).one().rules["urlColumn"] == "A"


def test_url_column_detection():
    text = "Page,Result\nhttps://x.example/1,\nhttps://x.example/2,dofollow\n"
    assert backlink_service.url_column(text) == "A"
    assert backlink_service.url_column("a,b,c\n,,https://x\n") == "C"
    assert backlink_service.url_column("no,urls\n") is None


def test_invented_links_are_removed_but_real_ones_kept(ctx):
    from app.models import AssistantChat, AssistantMessage
    from app.services.agent_engine import strip_unseen_links

    chat = AssistantChat(user_id="u1", title="t")
    ctx.db.add(chat)
    ctx.db.commit()
    ctx.db.add(AssistantMessage(chat_id=chat.id, seq=1, role="user", content=f"Check this sheet {SHEET}"))
    ctx.db.commit()

    reply = (
        "Started. Download: ![](https://all-bettors.com/agents/1mTZe9.csv) "
        "or [the CSV](https://all-bettors.com/agents/1mTZe9.csv). "
        f"Your sheet: [sheet]({SHEET}) and https://made.up/page"
    )
    cleaned = strip_unseen_links(ctx.db, chat.id, reply)
    assert "all-bettors.com/agents" not in cleaned and "made.up" not in cleaned
    assert "the CSV" in cleaned and SHEET in cleaned


def test_rate_limited_pages_are_retried(monkeypatch):
    calls: list[int] = []

    async def flaky(client, row, url, domain):
        calls.append(row)
        if len(calls) < 3:
            return backlink_service.CheckResult(row, url, "error", http_status=429, detail="HTTP 429")
        return backlink_service.CheckResult(row, url, "dofollow", http_status=200)

    async def no_wait(_seconds):
        return None

    monkeypatch.setattr(backlink_service, "check_page", flaky)
    monkeypatch.setattr(backlink_service.asyncio, "sleep", no_wait)
    [result] = asyncio.run(backlink_service.audit([(1, "https://a.blogzet.com/x")], "all-bettors.com"))
    assert result.result == "dofollow" and len(calls) == 3


def test_subdomains_share_one_site_limit():
    assert backlink_service._site("https://a.blogzet.com/x") == backlink_service._site("https://b.blogzet.com/y")
