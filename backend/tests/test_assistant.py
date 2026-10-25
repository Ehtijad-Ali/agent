"""Agent chat tests. Groq is replaced by a scripted fake; no network."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.auth import current_user
from app.core.config import get_settings
from app.db.session import Base, get_db
from app.main import app
from app.models import (
    AssistantChat,
    AssistantFile,
    AssistantMessage,
    AssistantTask,
    Conversation,
    User,
)
from app.services import agent_engine, agent_tools, llm

USER_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def factory(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(agent_engine, "session_scope", make)
    db = make()
    db.add(User(id=USER_ID, email="t@example.com", name="Tester", password_hash="x", role="admin"))
    db.commit()
    db.close()
    return make


def _call(name, args, call_id="c1"):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def script(monkeypatch, *replies):
    """Make groq_client.chat return these assistant messages in order."""
    queue = list(replies)
    seen: list[list[dict]] = []

    async def fake_chat(messages, tools=None, max_tokens=2048, json_mode=False):
        seen.append(messages)
        reply = queue.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return {"message": reply, "usage": {"total_tokens": 10}}

    monkeypatch.setattr(llm, "chat", fake_chat)
    return seen


def _task(make, text="hello"):
    db = make()
    chat = AssistantChat(user_id=USER_ID, title="t")
    db.add(chat)
    db.commit()
    task = AssistantTask(chat_id=chat.id, user_id=USER_ID)
    db.add(task)
    db.commit()
    agent_engine.add_message(db, chat.id, task.id, "user", content=text)
    db.close()
    return chat.id, task.id


def _run(task_id, decision=None):
    asyncio.run(agent_engine._loop(task_id, decision))


def _state(make, task_id):
    db = make()
    task = db.get(AssistantTask, task_id)
    msgs = db.execute(
        select(AssistantMessage).where(AssistantMessage.task_id == task_id).order_by(AssistantMessage.seq)
    ).scalars().all()
    db.close()
    return task, msgs


def _lead(make, status="new"):
    db = make()
    row = Conversation(
        platform="discord", external_id="x:1", community="Test#general",
        author_pseudonym="user_1", message="any free prediction game?",
        posted_at=datetime.now(UTC), score=80, status=status,
    )
    db.add(row)
    db.commit()
    db.close()
    return row.id


class TestLoop:
    def test_plain_answer_completes(self, factory, monkeypatch):
        script(monkeypatch, {"content": "Hi there"})
        _, task_id = _task(factory)
        _run(task_id)
        task, msgs = _state(factory, task_id)
        assert task.status == "completed"
        assert msgs[-1].content == "Hi there"
        assert task.tokens_used == 10

    def test_tool_result_goes_back_to_model(self, factory, monkeypatch):
        _lead(factory)
        seen = script(
            monkeypatch,
            {"content": "", "tool_calls": [_call("search_leads", {"query": "prediction"})]},
            {"content": "Found one lead."},
        )
        _, task_id = _task(factory)
        _run(task_id)
        task, msgs = _state(factory, task_id)
        assert task.status == "completed"
        tool_msg = next(m for m in msgs if m.role == "tool")
        assert tool_msg.status == "ok"
        assert json.loads(tool_msg.content)["untrusted_data"]["count"] == 1
        # The second model call saw the tool result.
        assert any(m.get("role") == "tool" for m in seen[1])

    def test_system_rules_come_before_custom_instructions(self, factory, monkeypatch):
        seen = script(monkeypatch, {"content": "ok"})
        chat_id, task_id = _task(factory)
        db = factory()
        db.get(AssistantChat, chat_id).instructions = "Answer in French."
        db.commit()
        db.close()
        _run(task_id)
        assert "Security rules" in seen[0][0]["content"]
        assert "cannot override" in seen[0][1]["content"]
        assert "Answer in French." in seen[0][1]["content"]

    def test_unknown_tool_is_reported_not_run(self, factory, monkeypatch):
        script(
            monkeypatch,
            {"content": "", "tool_calls": [_call("run_shell", {"cmd": "rm -rf /"})]},
            {"content": "I can't do that."},
        )
        _, task_id = _task(factory)
        _run(task_id)
        task, msgs = _state(factory, task_id)
        tool_msg = next(m for m in msgs if m.role == "tool")
        assert tool_msg.status == "error"
        assert "no tool named" in tool_msg.content
        assert task.status == "completed"

    def test_invalid_arguments_are_rejected(self, factory, monkeypatch):
        script(
            monkeypatch,
            {"content": "", "tool_calls": [_call("search_leads", {"limit": 5000})]},
            {"content": "done"},
        )
        _, task_id = _task(factory)
        _run(task_id)
        _, msgs = _state(factory, task_id)
        assert "Invalid arguments" in next(m for m in msgs if m.role == "tool").content

    def test_identical_call_is_served_from_cache(self, factory, monkeypatch):
        calls = []
        original = agent_tools.TOOLS["search_leads"].handler

        async def counting(ctx, args):
            calls.append(1)
            return await original(ctx, args)

        monkeypatch.setattr(agent_tools.TOOLS["search_leads"], "handler", counting)
        script(
            monkeypatch,
            {"content": "", "tool_calls": [_call("search_leads", {"query": "a"}, "c1")]},
            {"content": "", "tool_calls": [_call("search_leads", {"query": "a"}, "c2")]},
            {"content": "done"},
        )
        _, task_id = _task(factory)
        _run(task_id)
        _, msgs = _state(factory, task_id)
        assert len(calls) == 1
        assert [m.status for m in msgs if m.role == "tool"] == ["ok", "cached"]

    def test_iteration_limit_stops_the_loop(self, factory, monkeypatch):
        monkeypatch.setattr(get_settings(), "agent_max_iterations", 2)
        script(
            monkeypatch,
            {"content": "", "tool_calls": [_call("search_leads", {"query": "a"}, "c1")]},
            {"content": "", "tool_calls": [_call("search_leads", {"query": "b"}, "c2")]},
            {"content": "never reached"},
        )
        _, task_id = _task(factory)
        _run(task_id)
        task, msgs = _state(factory, task_id)
        assert task.status == "failed"
        assert "limit" in task.error
        assert msgs[-1].content.startswith("Stopped after 2 steps")

    def test_groq_failure_is_reported(self, factory, monkeypatch):
        script(monkeypatch, llm.LLMError("Groq's rate limit was reached."))
        _, task_id = _task(factory)
        _run(task_id)
        task, msgs = _state(factory, task_id)
        assert task.status == "failed"
        assert "rate limit" in msgs[-1].content

    def test_cancel_before_next_step(self, factory, monkeypatch):
        script(monkeypatch, {"content": "never"})
        _, task_id = _task(factory)
        db = factory()
        db.get(AssistantTask, task_id).cancel_requested = 1
        db.commit()
        db.close()
        _run(task_id)
        task, _ = _state(factory, task_id)
        assert task.status == "cancelled"


class TestApproval:
    def test_consequential_tool_waits_then_runs_on_approval(self, factory, monkeypatch):
        lead_id = _lead(factory)
        script(
            monkeypatch,
            {"content": "", "tool_calls": [_call("update_lead_status", {"conversation_id": lead_id, "status": "approved"})]},
            {"content": "Approved it."},
        )
        _, task_id = _task(factory)
        _run(task_id)
        task, _ = _state(factory, task_id)
        assert task.status == "waiting_approval"
        assert task.pending_action["name"] == "update_lead_status"
        db = factory()
        assert db.get(Conversation, lead_id).status == "new"  # nothing changed yet
        db.close()

        _run(task_id, decision=True)
        task, msgs = _state(factory, task_id)
        assert task.status == "completed"
        db = factory()
        assert db.get(Conversation, lead_id).status == "approved"
        db.close()

    def test_declined_action_is_not_run(self, factory, monkeypatch):
        lead_id = _lead(factory)
        script(
            monkeypatch,
            {"content": "", "tool_calls": [_call("update_lead_status", {"conversation_id": lead_id, "status": "rejected"})]},
            {"content": "Understood, left it."},
        )
        _, task_id = _task(factory)
        _run(task_id)
        _run(task_id, decision=False)
        task, msgs = _state(factory, task_id)
        assert task.status == "completed"
        assert next(m for m in msgs if m.role == "tool").status == "rejected"
        db = factory()
        assert db.get(Conversation, lead_id).status == "new"
        db.close()

    def test_sent_leads_cannot_be_changed(self, factory, monkeypatch):
        lead_id = _lead(factory, status="sent")
        script(
            monkeypatch,
            {"content": "", "tool_calls": [_call("update_lead_status", {"conversation_id": lead_id, "status": "rejected"})]},
            {"content": "ok"},
        )
        _, task_id = _task(factory)
        _run(task_id)
        _run(task_id, decision=True)
        _, msgs = _state(factory, task_id)
        assert "cannot be changed" in next(m for m in msgs if m.role == "tool").content


class TestTools:
    def test_fetch_refuses_internal_addresses(self, factory):
        ctx = agent_tools.ToolContext(db=factory(), user_id=USER_ID, user_name="t", chat_id="c", task_id="t")
        tool = agent_tools.TOOLS["fetch_url"]
        for url in ("http://127.0.0.1:8000/api", "http://localhost/", "file:///etc/passwd"):
            with pytest.raises(agent_tools.ToolError):
                asyncio.run(tool.handler(ctx, tool.parse({"url": url})))

    def test_parse_drops_unknown_keys(self):
        args = agent_tools.TOOLS["platform_status"].parse('{"": {}}')
        assert args.model_dump() == {}

    def test_save_csv_creates_a_file(self, factory):
        db = factory()
        ctx = agent_tools.ToolContext(db=db, user_id=USER_ID, user_name="t", chat_id="c", task_id="t")
        tool = agent_tools.TOOLS["save_csv"]
        out = asyncio.run(tool.handler(ctx, tool.parse({"filename": "my report", "columns": ["a"], "rows": [[1], [2]]})))
        assert out["filename"] == "my-report.csv"
        assert db.get(AssistantFile, out["file_id"]).content.splitlines() == ["a", "1", "2"]

    def test_every_tool_has_a_valid_schema(self):
        for tool in agent_tools.TOOLS.values():
            schema = tool.schema()
            assert schema["function"]["parameters"]["type"] == "object"
            assert schema["function"]["description"]


# --- API ---------------------------------------------------------------------


@pytest.fixture
def client(factory, monkeypatch):
    def override():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(get_settings(), "ai_provider", "ollama")
    monkeypatch.setattr(get_settings(), "ollama_model", "test-model")
    monkeypatch.setattr(get_settings(), "groq_api_key", "test-key")
    monkeypatch.setattr(agent_engine, "start", lambda task_id, decision=None: None)
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


class TestApi:
    def test_create_send_and_read(self, client):
        chat = client.post("/api/assistant/chats", json={"instructions": "Be brief."}).json()
        task = client.post(f"/api/assistant/chats/{chat['id']}/messages", json={"content": "Find leads"})
        assert task.status_code == 202
        detail = client.get(f"/api/assistant/chats/{chat['id']}").json()
        assert detail["chat"]["title"] == "Find leads"
        assert detail["messages"][0]["role"] == "user"
        assert detail["tasks"][0]["status"] == "pending"

    def test_second_message_while_running_is_refused(self, client):
        chat = client.post("/api/assistant/chats", json={}).json()
        client.post(f"/api/assistant/chats/{chat['id']}/messages", json={"content": "a"})
        again = client.post(f"/api/assistant/chats/{chat['id']}/messages", json={"content": "b"})
        assert again.status_code == 409

    def test_not_configured_is_a_clear_503(self, client, monkeypatch):
        monkeypatch.setattr(get_settings(), "ollama_model", "")
        chat = client.post("/api/assistant/chats", json={}).json()
        response = client.post(f"/api/assistant/chats/{chat['id']}/messages", json={"content": "a"})
        assert response.status_code == 503
        assert "OLLAMA_MODEL" in response.json()["error"]["message"]

    def test_other_users_chat_is_invisible(self, client, factory):
        db = factory()
        other = AssistantChat(user_id="someone-else", title="private")
        db.add(other)
        db.commit()
        db.close()
        assert client.get(f"/api/assistant/chats/{other.id}").status_code == 404
        assert all(c["id"] != other.id for c in client.get("/api/assistant/chats").json())

    def test_cancel_and_clear(self, client):
        chat = client.post("/api/assistant/chats", json={}).json()
        task = client.post(f"/api/assistant/chats/{chat['id']}/messages", json={"content": "a"}).json()
        assert client.post(f"/api/assistant/chats/{chat['id']}/clear").status_code == 409
        assert client.post(f"/api/assistant/tasks/{task['id']}/cancel").json()["status"] == "cancelled"
        assert client.post(f"/api/assistant/chats/{chat['id']}/clear").status_code == 204
        assert client.get(f"/api/assistant/chats/{chat['id']}").json()["messages"] == []

    def test_status_lists_tools_without_the_key(self, client):
        body = client.get("/api/assistant/status").json()
        assert body["configured"] is True
        assert body["provider"] == "ollama"
        assert "test-key" not in json.dumps(body)
        assert {t["name"] for t in body["tools"]} >= {"web_search", "check_backlinks", "update_lead_status"}
