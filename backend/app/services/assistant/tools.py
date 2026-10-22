"""The AI Agent's tools.

Each tool returns ``(status, content)``: status is "ok" or "error", content is
the text the model reads next (JSON where structure helps). Results are
trimmed, because a small local model with an 8k context cannot read a whole web
page and still remember the task.

Only ``update_lead_status`` changes anything, and it never runs without the
operator approving that specific call (``requires_approval``).
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Awaitable, Callable

from sqlalchemy import or_, select

from app.db.session import session_scope
from app.models import ActivityEntry, AssistantFile, Conversation
from app.schemas.conversation import ACTION_TO_STATUS, TERMINAL_STATUSES
from app.services import backlink_service, sources_service, web_service
from app.services.web_service import FetchError

MAX_RESULT_CHARS = 6000


@dataclass(slots=True)
class ToolContext:
    chat_id: str
    task_id: str
    user_name: str
    # The user's latest message. Small models sometimes invent links; tools
    # that take URLs check them against what the user actually wrote.
    user_text: str = ""


@dataclass(slots=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    run: Callable[[dict[str, Any], ToolContext], Awaitable[tuple[str, str]]]
    requires_approval: bool = False

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


def _json(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + "… (truncated)"
    return text


def _int(value: Any, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(int(value), high))
    except (TypeError, ValueError):
        return default


def _save_file(ctx: ToolContext, filename: str, header: list[str], rows: list[list[Any]]) -> AssistantFile:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename.strip() or "results").strip("._") or "results"
    if not name.lower().endswith(".csv"):
        name += ".csv"
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    if header:
        writer.writerow(header)
    writer.writerows(rows)
    db = session_scope()
    try:
        record = AssistantFile(
            chat_id=ctx.chat_id, task_id=ctx.task_id, filename=name[:200],
            rows=len(rows), content=buffer.getvalue(),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record
    finally:
        db.close()


# --- tools -------------------------------------------------------------------


async def _web_search(args: dict, ctx: ToolContext) -> tuple[str, str]:
    query = str(args.get("query", "")).strip()
    if not query:
        return "error", "Give a search query."
    try:
        findings = await web_service.web_search(query, _int(args.get("limit"), 8, 1, 10))
    except FetchError as exc:
        return "error", str(exc)
    if not findings:
        return "ok", "No results."
    return "ok", _json({"query": query, "results": findings})


async def _fetch_url(args: dict, ctx: ToolContext) -> tuple[str, str]:
    url = str(args.get("url", "")).strip()
    if not url:
        return "error", "Give a URL."
    if "://" not in url:
        url = "https://" + url
    try:
        page = await web_service.fetch(url)
    except FetchError as exc:
        return "error", str(exc)
    content = web_service.parse_html(page.text, page.url)
    result: dict[str, Any] = {
        "url": page.url,
        "status": page.status,
        "title": content.title,
        "text": content.text[:4000],
    }
    if args.get("include_links"):
        result["links"] = [
            {"href": link.href, "text": link.text, "rel": link.rel} for link in content.links[:60]
        ]
    return "ok", _json(result)


async def _read_spreadsheet(args: dict, ctx: ToolContext) -> tuple[str, str]:
    url = str(args.get("url", "")).strip()
    if not url:
        return "error", "Give the sheet or CSV link."
    try:
        table = await web_service.read_spreadsheet(url)
    except FetchError as exc:
        return "error", str(exc)
    start = _int(args.get("start_row"), 1, 1, 1_000_000)
    limit = _int(args.get("limit"), 50, 1, 200)
    rows = table[start - 1 : start - 1 + limit]
    return "ok", _json(
        {"totalRows": len(table), "startRow": start,
         "rows": [{"row": start + i, "cells": r} for i, r in enumerate(rows)]}
    )


async def _check_backlinks(args: dict, ctx: ToolContext) -> tuple[str, str]:
    domain = backlink_service.normalise_domain(
        str(args.get("domain") or "") or _default_domain()
    )
    limit = _int(args.get("limit"), 100, 1, 500)
    pairs: list[tuple[int, str]] = []
    typed = re.findall(r"https?://[^\s,<>\"']+", ctx.user_text)
    sheet = str(args.get("sheet_url") or "").strip()
    if sheet and ctx.user_text and not any(_same_sheet(sheet, t) for t in typed):
        sheet = ""  # not a link the user gave: ignore rather than fetch a made-up URL
    if not sheet:
        sheet = next((t for t in typed if "/spreadsheets/d/" in t), "")
    args = {**args, "sheet_url": sheet}
    if args.get("sheet_url"):
        try:
            pairs = await backlink_service.urls_from_sheet(
                str(args["sheet_url"]), str(args.get("column") or "A"), limit
            )
        except (FetchError, ValueError) as exc:
            return "error", str(exc)
    urls = args.get("urls") or []
    if isinstance(urls, str):
        urls = [u for u in re.split(r"[\s,]+", urls) if u]
    if not urls and not pairs:
        urls = [t for t in typed if "/spreadsheets/d/" not in t]
    if not pairs:
        pairs = [(i + 1, str(u)) for i, u in enumerate(urls[:limit])]
    if not pairs:
        return "error", "Give a sheet_url or a list of urls to check."

    results = await backlink_service.check_many(pairs, domain)
    record = _save_file(
        ctx,
        f"backlinks_{domain}",
        ["Page URL", "Result", "Rel", "Link", "Anchor text", "HTTP status", "Detail", "Row"],
        [[r.page_url, r.result, r.rel, r.link_href, r.anchor_text, r.http_status or "", r.detail, r.row]
         for r in results],
    )
    counts: dict[str, int] = {}
    for r in results:
        counts[r.result] = counts.get(r.result, 0) + 1
    return "ok", _json(
        {
            "domain": domain,
            "checked": len(results),
            "counts": counts,
            "file": f"{record.filename} ({record.rows} rows) is ready to download below the chat.",
            "sample": [
                {"row": r.row, "url": r.page_url, "result": r.result, "detail": r.detail}
                for r in results[:25]
            ],
        }
    )


async def _search_leads(args: dict, ctx: ToolContext) -> tuple[str, str]:
    db = session_scope()
    try:
        stmt = select(Conversation)
        words = [w for w in str(args.get("query") or "").split() if w]
        if words:
            stmt = stmt.where(or_(*[Conversation.message.ilike(f"%{w}%") for w in words]))
        if args.get("status"):
            stmt = stmt.where(Conversation.status == str(args["status"]))
        if args.get("platform"):
            stmt = stmt.where(Conversation.platform == str(args["platform"]).lower())
        if args.get("min_score") is not None:
            stmt = stmt.where(Conversation.score >= _int(args.get("min_score"), 0, 0, 100))
        if args.get("days"):
            since = datetime.now(UTC) - timedelta(days=_int(args.get("days"), 7, 1, 365))
            stmt = stmt.where(Conversation.posted_at >= since)
        limit = _int(args.get("limit"), 20, 1, 50)
        rows = db.execute(stmt.order_by(Conversation.posted_at.desc()).limit(limit)).scalars().all()
        leads = [
            {
                "id": r.id, "platform": r.platform, "community": r.community,
                "score": r.score, "intent": r.intent, "status": r.status,
                "postedAt": r.posted_at.isoformat() if r.posted_at else None,
                "message": r.message[:300], "sourceUrl": r.source_url,
            }
            for r in rows
        ]
    finally:
        db.close()
    return "ok", _json({"count": len(leads), "leads": leads})


async def _platform_status(args: dict, ctx: ToolContext) -> tuple[str, str]:
    discord = await sources_service.discord_overview()
    telegram = await sources_service.telegram_bot_overview()
    db = session_scope()
    try:
        discovery = sources_service.list_sources(db)
    finally:
        db.close()
    return "ok", _json(
        {
            "discord": {
                "connected": discord["connected"],
                "error": discord["error"],
                "servers": [
                    {"name": s["name"],
                     "readableChannels": [c["name"] for c in s["channels"] if c["readable"]],
                     "blockedChannels": [c["name"] for c in s["channels"] if not c["readable"]]}
                    for s in discord["servers"]
                ],
            },
            "telegram": telegram,
            "discovery": {k: {"configured": v["configured"], "queries": v["settings"]["queries"]}
                          for k, v in discovery.items()},
        }
    )


async def _save_csv(args: dict, ctx: ToolContext) -> tuple[str, str]:
    rows = args.get("rows") or []
    columns = [str(c) for c in args.get("columns") or []]
    if isinstance(rows, str):
        try:
            rows = json.loads(rows)
        except ValueError:
            return "error", "rows must be a list of rows."
    table: list[list[Any]] = []
    for row in rows[:10000]:
        if isinstance(row, dict):
            if not columns:
                columns = [str(k) for k in row]
            table.append([row.get(c, "") for c in columns])
        elif isinstance(row, list):
            table.append(row)
        else:
            table.append([row])
    if not table:
        return "error", "There are no rows to save."
    record = _save_file(ctx, str(args.get("filename") or "results"), columns, table)
    return "ok", f"Saved {record.filename} with {record.rows} rows. It is ready to download below the chat."


_LEAD_ACTIONS = {"approve": "approve", "reject": "reject", "snooze": "snooze", "awaiting": "mark-awaiting"}


async def _update_lead_status(args: dict, ctx: ToolContext) -> tuple[str, str]:
    lead_id = str(args.get("lead_id") or "").strip()
    action = _LEAD_ACTIONS.get(str(args.get("action") or "").strip().lower())
    if not lead_id or action is None:
        return "error", "Give lead_id and an action: approve, reject, snooze or awaiting."
    db = session_scope()
    try:
        row = db.get(Conversation, lead_id)
        if row is None:
            return "error", f"No lead with id {lead_id}."
        if row.status in TERMINAL_STATUSES:
            return "error", f"The lead is '{row.status}' and cannot be changed."
        before, after = row.status, ACTION_TO_STATUS[action]
        row.status = after
        row.history = [
            *(row.history or []),
            {"at": datetime.now(UTC).isoformat(), "actor": "AI agent", "action": action.replace("-", " ")},
        ]
        db.add(
            ActivityEntry(
                actor="AI agent", action=f"{action.replace('-', ' ')} (approved by {ctx.user_name})",
                item=f"{row.community} / {row.author_pseudonym}", before=before, after=after,
            )
        )
        db.commit()
    finally:
        db.close()
    return "ok", f"Lead {lead_id} changed from {before} to {after}."


def _same_sheet(a: str, b: str) -> bool:
    ida = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", a)
    idb = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", b)
    if ida and idb:
        return ida.group(1) == idb.group(1)
    return a.rstrip("/") == b.rstrip("/")


def _default_domain() -> str:
    from app.schemas.agent import _default_domain as domain

    return domain()


TOOLS: list[Tool] = [
    Tool(
        "web_search",
        "Search the public web for current information. Returns findings with source URLs.",
        {"type": "object", "properties": {
            "query": {"type": "string", "description": "What to search for."},
            "limit": {"type": "integer", "description": "Max results, 1-10."}},
         "required": ["query"]},
        _web_search,
    ),
    Tool(
        "fetch_url",
        "Read a public web page: its title and visible text, optionally its links.",
        {"type": "object", "properties": {
            "url": {"type": "string"},
            "include_links": {"type": "boolean", "description": "Also list the links on the page."}},
         "required": ["url"]},
        _fetch_url,
    ),
    Tool(
        "read_spreadsheet",
        "Read rows from a Google Sheet shared by link, or from a CSV URL.",
        {"type": "object", "properties": {
            "url": {"type": "string", "description": "Google Sheets link or CSV URL."},
            "start_row": {"type": "integer", "description": "First row to return, 1-based."},
            "limit": {"type": "integer", "description": "How many rows, up to 200."}},
         "required": ["url"]},
        _read_spreadsheet,
    ),
    Tool(
        "check_backlinks",
        "Check pages for a link to a domain and whether it is dofollow or nofollow. Reads URLs "
        "from a Google Sheet column or a list, and saves a downloadable CSV of the results.",
        {"type": "object", "properties": {
            "domain": {"type": "string", "description": "Domain the links should point to, e.g. all-bettors.com."},
            "sheet_url": {"type": "string", "description": "Google Sheet with page URLs. Only a link the user gave."},
            "column": {"type": "string", "description": "Column letter holding the URLs. Default A."},
            "urls": {"type": "array", "items": {"type": "string"}, "description": "Page URLs the user listed, instead of a sheet."},
            "limit": {"type": "integer", "description": "Max pages to check, up to 500."}}},
        _check_backlinks,
    ),
    Tool(
        "search_leads",
        "Search the leads (conversations) found on Discord and Telegram, by words, status, "
        "platform and minimum score.",
        {"type": "object", "properties": {
            "query": {"type": "string", "description": "Words to look for in the message."},
            "status": {"type": "string", "enum": ["new", "awaiting", "approved", "rejected", "snoozed",
                                                  "manually_posted", "blocked", "sent"]},
            "platform": {"type": "string", "enum": ["discord", "telegram", "reddit", "youtube"]},
            "min_score": {"type": "integer"},
            "days": {"type": "integer", "description": "Only leads posted in the last N days. Leave out unless the user names a time window."},
            "limit": {"type": "integer", "description": "Max leads, up to 50."}}},
        _search_leads,
    ),
    Tool(
        "platform_status",
        "Which Discord servers/channels and Telegram groups the bots can read.",
        {"type": "object", "properties": {}},
        _platform_status,
    ),
    Tool(
        "save_csv",
        "Save a table as a CSV file the user can download.",
        {"type": "object", "properties": {
            "filename": {"type": "string"},
            "columns": {"type": "array", "items": {"type": "string"}},
            "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}},
                     "description": "Each row is a list of cell values in column order."}},
         "required": ["rows"]},
        _save_csv,
    ),
    Tool(
        "update_lead_status",
        "Change a lead's status (approve, reject, snooze, or back to awaiting). The user must "
        "approve each change before it happens.",
        {"type": "object", "properties": {
            "lead_id": {"type": "string", "description": "The lead id from search_leads."},
            "action": {"type": "string", "enum": ["approve", "reject", "snooze", "awaiting"]}},
         "required": ["lead_id", "action"]},
        _update_lead_status,
        requires_approval=True,
    ),
]

TOOLS_BY_NAME: dict[str, Tool] = {t.name: t for t in TOOLS}


def schemas() -> list[dict[str, Any]]:
    return [t.schema() for t in TOOLS]


def describe() -> list[dict[str, Any]]:
    return [
        {"name": t.name, "description": t.description, "requiresApproval": t.requires_approval}
        for t in TOOLS
    ]
