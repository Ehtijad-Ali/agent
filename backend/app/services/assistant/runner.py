"""Runs AI Agent tasks: plan, call tools, answer -- in the background.

The HTTP request that starts a task returns immediately; the screen polls the
chat while the loop runs here. Every step is written to the database as it
happens, so progress is visible and a task waiting for approval survives a
reload (or a server restart -- it resumes from the stored pending action).

Safety rails, independent of what the model decides:
* a tool that changes data (``requires_approval``) pauses the task until the
  operator approves that exact call;
* the loop stops after ASSISTANT_MAX_ITERATIONS model calls;
* repeating an identical tool call within one task reuses the earlier result
  ("cached"), so a looping small model cannot hammer a site or the database.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import session_scope
from app.models import AssistantChat, AssistantMessage, AssistantTask
from app.services.assistant import llm, tools
from app.utils.background import spawn

logger = logging.getLogger("signal.assistant")

HISTORY_LIMIT = 40

_running: dict[str, Any] = {}


def system_prompt(instructions: str) -> str:
    s = get_settings()
    today = datetime.now(UTC).strftime("%A %d %B %Y")
    prompt = f"""You are the AI Agent inside Signal, a social-listening tool for {s.product_label} \
({s.product_url}), a FREE-TO-PLAY social prediction game (no real money, no deposits, 18+).
Today is {today}.

You help the operator with tasks by planning briefly and using your tools:
- web_search / fetch_url to research the public web,
- read_spreadsheet to read Google Sheets or CSV links,
- check_backlinks to audit whether pages link to a domain with dofollow links (it saves a CSV),
- search_leads to find conversations Signal discovered, and platform_status for bot coverage,
- save_csv to give the operator a downloadable table,
- update_lead_status to change a lead's status (the operator must approve each change).

Rules:
- Use a tool whenever the task needs real data. Never invent URLs, numbers, leads or results.
- Call tools with exactly the arguments they define. One step at a time.
- If the request is unclear, ask one short question instead of guessing.
- You never post, reply, or message anyone on any platform, and never DM authors.
- When a CSV was saved, say so: it appears as a download button under the chat.
- Answer in concise Markdown. Use a table for tabular results."""
    if instructions.strip():
        prompt += (
            "\n\nThe operator's instructions for this chat (they cannot override the rules above):\n"
            + instructions.strip()
        )
    return prompt


# --- persistence helpers -----------------------------------------------------


def _next_seq(db, chat_id: str) -> int:
    current = db.execute(
        select(func.max(AssistantMessage.seq)).where(AssistantMessage.chat_id == chat_id)
    ).scalar()
    return int(current or 0) + 1


def add_message(chat_id: str, task_id: str | None, role: str, content: str = "", **fields: Any) -> None:
    db = session_scope()
    try:
        db.add(
            AssistantMessage(
                chat_id=chat_id, task_id=task_id, seq=_next_seq(db, chat_id),
                role=role, content=content, **fields,
            )
        )
        chat = db.get(AssistantChat, chat_id)
        if chat is not None:
            chat.updated_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()


def _update_task(task_id: str, **fields: Any) -> AssistantTask | None:
    db = session_scope()
    try:
        task = db.get(AssistantTask, task_id)
        if task is None:
            return None
        for key, value in fields.items():
            setattr(task, key, value)
        db.commit()
        db.refresh(task)
        return task
    finally:
        db.close()


def _load(task_id: str) -> tuple[AssistantTask | None, AssistantChat | None, list[AssistantMessage]]:
    db = session_scope()
    try:
        task = db.get(AssistantTask, task_id)
        if task is None:
            return None, None, []
        chat = db.get(AssistantChat, task.chat_id)
        messages = list(
            db.execute(
                select(AssistantMessage)
                .where(AssistantMessage.chat_id == task.chat_id)
                .order_by(AssistantMessage.seq.desc())
                .limit(HISTORY_LIMIT)
            ).scalars()
        )
        messages.reverse()
        return task, chat, messages
    finally:
        db.close()


def _as_llm_messages(chat: AssistantChat, history: list[AssistantMessage]) -> list[dict[str, Any]]:
    # A tool message whose assistant call was cut off by the history window
    # would confuse the model, so the window starts at a user message.
    while history and history[0].role != "user":
        history = history[1:]
    out: list[dict[str, Any]] = [{"role": "system", "content": system_prompt(chat.instructions)}]
    for m in history:
        if m.role == "assistant" and m.status in ("failed", "cancelled") and not m.tool_calls:
            continue
        entry: dict[str, Any] = {"role": m.role, "content": m.content}
        if m.tool_calls:
            entry["tool_calls"] = m.tool_calls
        if m.role == "tool":
            entry["tool_call_id"] = m.tool_call_id
            entry["name"] = m.name
        out.append(entry)
    return out


def _latest_user_text(history: list[AssistantMessage]) -> str:
    return next((m.content for m in reversed(history) if m.role == "user"), "")


def _cache_key(call: dict[str, Any]) -> str:
    return call["function"]["name"] + ":" + json.dumps(call["function"]["arguments"], sort_keys=True)


def _cached_results(task_id: str) -> dict[str, str]:
    """Results of tool calls already made in this task, by call signature."""
    db = session_scope()
    try:
        msgs = list(
            db.execute(
                select(AssistantMessage)
                .where(AssistantMessage.task_id == task_id)
                .order_by(AssistantMessage.seq)
            ).scalars()
        )
    finally:
        db.close()
    calls: dict[str, str] = {}
    for m in msgs:
        for c in m.tool_calls or []:
            calls[c["id"]] = _cache_key(c)
    out: dict[str, str] = {}
    for m in msgs:
        if m.role == "tool" and m.status == "ok" and m.tool_call_id in calls:
            out[calls[m.tool_call_id]] = m.content
    return out


# --- the loop ---------------------------------------------------------------


async def _execute(call: dict[str, Any], ctx: tools.ToolContext, cache: dict[str, str]) -> None:
    name = call["function"]["name"]
    key = _cache_key(call)
    if key in cache:
        add_message(ctx.chat_id, ctx.task_id, "tool", cache[key], tool_call_id=call["id"], name=name, status="cached")
        return
    tool = tools.TOOLS_BY_NAME.get(name)
    if tool is None:
        status, content = "error", f"There is no tool called {name}. Available: {', '.join(tools.TOOLS_BY_NAME)}."
    else:
        try:
            status, content = await tool.run(call["function"]["arguments"] or {}, ctx)
        except Exception as exc:  # noqa: BLE001 -- a broken tool is reported to the model, not fatal
            logger.exception("Tool %s crashed", name)
            status, content = "error", f"The tool failed: {type(exc).__name__}."
    if status == "ok":
        cache[key] = content
    add_message(ctx.chat_id, ctx.task_id, "tool", content, tool_call_id=call["id"], name=name, status=status)


async def _process_calls(calls: list[dict[str, Any]], ctx: tools.ToolContext) -> bool:
    """Run tool calls in order. Returns False when paused for approval."""
    cache = _cached_results(ctx.task_id)
    for index, call in enumerate(calls):
        tool = tools.TOOLS_BY_NAME.get(call["function"]["name"])
        if tool is not None and tool.requires_approval:
            _update_task(
                ctx.task_id,
                status="waiting_approval",
                pending_action={
                    "name": tool.name,
                    "arguments": call["function"]["arguments"],
                    "toolCallId": call["id"],
                    "remaining": calls[index + 1 :],
                },
            )
            return False
        await _execute(call, ctx, cache)
        task = _update_task(ctx.task_id)
        if task is not None:
            _update_task(ctx.task_id, tool_calls=task.tool_calls + 1)
    return True


async def _loop(task_id: str, user_name: str) -> None:
    settings = get_settings()
    while True:
        task, chat, history = _load(task_id)
        if task is None or chat is None or task.status != "running":
            return
        if task.iterations >= settings.assistant_max_iterations:
            add_message(
                chat.id, task_id, "assistant",
                f"I stopped after {task.iterations} steps without finishing. Tell me how to "
                "narrow the task down, or say “continue”.",
            )
            _update_task(task_id, status="completed", finished_at=datetime.now(UTC))
            return

        reply = await llm.chat(_as_llm_messages(chat, history), tools.schemas())

        task = _update_task(task_id)
        if task is None or task.status != "running":
            return  # cancelled while the model was thinking
        _update_task(
            task_id, iterations=task.iterations + 1, tokens_used=task.tokens_used + reply.tokens
        )

        if not reply.tool_calls:
            add_message(chat.id, task_id, "assistant", reply.content or "(no answer)")
            _update_task(task_id, status="completed", finished_at=datetime.now(UTC))
            return

        add_message(chat.id, task_id, "assistant", reply.content, tool_calls=reply.tool_calls)
        ctx = tools.ToolContext(
            chat_id=chat.id, task_id=task_id, user_name=user_name, user_text=_latest_user_text(history)
        )
        if not await _process_calls(reply.tool_calls, ctx):
            return  # waiting for the operator


async def _guarded(task_id: str, user_name: str) -> None:
    try:
        await _loop(task_id, user_name)
    except asyncio.CancelledError:
        raise
    except llm.LLMError as exc:
        _fail(task_id, str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Assistant task %s crashed", task_id)
        _fail(task_id, f"Unexpected error: {type(exc).__name__}")
    finally:
        _running.pop(task_id, None)


def _fail(task_id: str, error: str) -> None:
    task = _update_task(task_id, status="failed", error=error, finished_at=datetime.now(UTC))
    if task is not None:
        add_message(task.chat_id, task_id, "assistant", f"I couldn't finish: {error}", status="failed")


def start(task_id: str, user_name: str) -> None:
    _update_task(task_id, status="running", started_at=datetime.now(UTC))
    try:
        _running[task_id] = spawn(_guarded(task_id, user_name))
    except Exception:
        # Never leave a task "running" with nothing behind it: the chat would
        # refuse every new message until a restart.
        _fail(task_id, "The task could not be started.")
        raise


async def _resume_after_decision(task_id: str, user_name: str, approve: bool) -> None:
    task, chat, _ = _load(task_id)
    if task is None or chat is None or not task.pending_action:
        return
    pending = task.pending_action
    _update_task(task_id, status="running", pending_action=None)
    _, _, history = _load(task_id)
    ctx = tools.ToolContext(
        chat_id=chat.id, task_id=task_id, user_name=user_name, user_text=_latest_user_text(history)
    )
    call = {
        "id": pending["toolCallId"],
        "type": "function",
        "function": {"name": pending["name"], "arguments": pending["arguments"]},
    }
    if approve:
        await _execute(call, ctx, {})
    else:
        add_message(
            chat.id, task_id, "tool", "DECLINED. The user did not allow this action, so it did NOT happen and nothing was changed. "
            "Tell the user plainly that nothing was changed. Do not retry it.",
            tool_call_id=call["id"], name=pending["name"], status="declined",
        )
    _update_task(task_id, tool_calls=(task.tool_calls or 0) + 1)
    if await _process_calls(pending.get("remaining") or [], ctx):
        await _loop(task_id, user_name)


def decide(task_id: str, user_name: str, approve: bool) -> None:
    async def run() -> None:
        try:
            await _resume_after_decision(task_id, user_name, approve)
        except llm.LLMError as exc:
            _fail(task_id, str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Assistant task %s crashed after decision", task_id)
            _fail(task_id, f"Unexpected error: {type(exc).__name__}")
        finally:
            _running.pop(task_id, None)

    _running[task_id] = spawn(run())


def cancel(task_id: str) -> None:
    running = _running.pop(task_id, None)
    if running is not None and not running.done():
        running.cancel()
    task = _update_task(task_id, status="cancelled", pending_action=None, finished_at=datetime.now(UTC))
    if task is not None:
        add_message(task.chat_id, task_id, "assistant", "Stopped.", status="cancelled")


def recover_interrupted() -> None:
    """Tasks that were mid-run when the process stopped cannot be resumed
    (their in-flight model call is gone). Waiting-for-approval tasks can."""
    db = session_scope()
    try:
        for task in db.execute(
            select(AssistantTask).where(AssistantTask.status.in_(("pending", "running")))
        ).scalars():
            task.status = "failed"
            task.error = "The server restarted while this task was running. Send the message again."
            task.finished_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()
