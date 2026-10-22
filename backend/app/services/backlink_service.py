"""Backlink checking: does a page link to us, and is that link dofollow?

A link counts as *nofollow* when its ``rel`` carries nofollow, ugc or
sponsored -- all three tell search engines not to pass ranking credit. When a
page links to the domain more than once, one dofollow link is enough for the
page to count as dofollow.

Shared by the ``backlink_audit`` agent (a whole sheet, in the background) and
the AI Agent's ``check_backlinks`` tool (a handful of URLs, inline).
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

from sqlalchemy import delete, select

from app.db.session import session_scope
from app.models import ActivityEntry, Agent, BacklinkAudit, BacklinkCheck
from app.services import web_service
from app.services.web_service import FetchError
from app.utils.background import spawn

logger = logging.getLogger("signal.backlinks")

NOFOLLOW_RELS = {"nofollow", "ugc", "sponsored"}
CONCURRENCY = 6

# Audits running in this process, so a second "Run audit" is refused instead
# of racing the first over the same rows.
_running: dict = {}


@dataclass(slots=True)
class CheckResult:
    row: int
    page_url: str
    result: str
    rel: str = ""
    link_href: str = ""
    anchor_text: str = ""
    http_status: int | None = None
    detail: str = ""


def normalise_domain(domain: str) -> str:
    value = domain.strip().lower()
    if "://" in value:
        value = urlparse(value).hostname or value
    value = value.split("/")[0]
    return value.removeprefix("www.")


def _points_to(href: str, domain: str) -> bool:
    host = (urlparse(href).hostname or "").lower().removeprefix("www.")
    return bool(host) and (host == domain or host.endswith("." + domain))


def _looks_like_url(value: str) -> bool:
    value = value.strip()
    if not value or " " in value:
        return False
    if "://" not in value:
        value = "https://" + value
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and "." in (parsed.hostname or "")


async def check_page(row: int, page_url: str, domain: str) -> CheckResult:
    url = page_url.strip()
    if not _looks_like_url(url):
        return CheckResult(row, page_url, "error", detail="Not a URL.")
    if "://" not in url:
        url = "https://" + url

    try:
        page = await web_service.fetch(url)
    except FetchError as exc:
        return CheckResult(row, page_url, "error", detail=str(exc))

    if page.status >= 400:
        return CheckResult(
            row, page_url, "error", http_status=page.status,
            detail=f"The page returned HTTP {page.status}.",
        )

    content = web_service.parse_html(page.text, page.url)
    matches = [link for link in content.links if _points_to(link.href, domain)]
    if not matches:
        return CheckResult(
            row, page_url, "not_found", http_status=page.status,
            detail=f"No link to {domain} on the page.",
        )

    def is_follow(link: web_service.Link) -> bool:
        return not (set(link.rel.split()) & NOFOLLOW_RELS)

    best = next((link for link in matches if is_follow(link)), matches[0])
    result = "dofollow" if is_follow(best) else "nofollow"
    extra = f" ({len(matches)} links to {domain})" if len(matches) > 1 else ""
    detail = (
        f"Links to {domain} without nofollow{extra}."
        if result == "dofollow"
        else f"Link has rel=\"{best.rel}\"{extra}."
    )
    return CheckResult(
        row=row,
        page_url=page_url,
        result=result,
        rel=best.rel,
        link_href=best.href,
        anchor_text=best.text,
        http_status=page.status,
        detail=detail,
    )


async def check_many(
    rows: list[tuple[int, str]], domain: str, on_result=None
) -> list[CheckResult]:
    """Check (row, url) pairs with bounded concurrency, preserving order."""
    semaphore = asyncio.Semaphore(CONCURRENCY)
    domain = normalise_domain(domain)

    async def one(row: int, url: str) -> CheckResult:
        async with semaphore:
            try:
                result = await check_page(row, url, domain)
            except Exception as exc:  # noqa: BLE001 -- one bad page must not stop the rest
                logger.exception("Backlink check crashed for %s", url)
                result = CheckResult(row, url, "error", detail=f"Unexpected error: {type(exc).__name__}")
        if on_result is not None:
            on_result(result)
        return result

    return list(await asyncio.gather(*(one(r, u) for r, u in rows)))


async def urls_from_sheet(sheet_url: str, column: str = "A", limit: int = 10000) -> list[tuple[int, str]]:
    """(sheet row number, cell) for every row from the first URL down.

    A leading header row is skipped; blank rows after it are kept, so the
    results line up with the sheet when pasted back next to it.
    """
    table = await web_service.read_spreadsheet(sheet_url)
    index = web_service.column_index(column)
    cells = [(n + 1, (r[index] if index < len(r) else "").strip()) for n, r in enumerate(table)]

    first = next((i for i, (_, value) in enumerate(cells) if _looks_like_url(value)), None)
    if first is None:
        return []
    last = max(i for i, (_, value) in enumerate(cells) if _looks_like_url(value))
    return cells[first : last + 1][:limit]


def to_csv(results: list[CheckResult] | list[BacklinkCheck]) -> str:
    """Sheet order. "Result" is the second column, so the first two columns
    paste straight over A:B of the original sheet."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Page URL", "Result", "Rel", "Link", "Anchor text", "HTTP status", "Detail", "Row"])
    for r in results:
        writer.writerow(
            [r.page_url, r.result, r.rel, r.link_href, r.anchor_text, r.http_status or "", r.detail, r.row]
        )
    return out.getvalue()


# --- the agent's background audit -----------------------------------------


def is_running(agent_id: str) -> bool:
    task = _running.get(agent_id)
    return task is not None and not task.done()


def start_audit(agent: Agent) -> None:
    """Reset the agent's audit row and kick off the background run."""
    rules = agent.rules or {}
    db = session_scope()
    try:
        db.execute(delete(BacklinkCheck).where(BacklinkCheck.agent_id == agent.id))
        audit = db.get(BacklinkAudit, agent.id) or BacklinkAudit(agent_id=agent.id)
        audit.status = "running"
        audit.total = 0
        audit.done = 0
        audit.error = None
        audit.started_at = datetime.now(UTC)
        audit.finished_at = None
        db.add(audit)
        db.add(
            ActivityEntry(actor="you", action="started backlink audit", item=agent.name)
        )
        db.commit()
    finally:
        db.close()

    _running[agent.id] = spawn(
        _run(
            agent.id,
            agent.name,
            str(rules.get("sheetUrl", "")),
            str(rules.get("urlColumn", "A") or "A"),
            str(rules.get("targetDomain", "")),
            int(rules.get("maxUrls", 10000) or 10000),
        )
    )


async def _run(agent_id: str, name: str, sheet_url: str, column: str, domain: str, limit: int) -> None:
    def update(**fields) -> None:
        db = session_scope()
        try:
            audit = db.get(BacklinkAudit, agent_id)
            if audit is None:
                return
            for key, value in fields.items():
                setattr(audit, key, value)
            db.commit()
        finally:
            db.close()

    try:
        rows = await urls_from_sheet(sheet_url, column, limit)
        if not rows:
            update(
                status="failed",
                error=f"No URLs found in column {column.upper()} of the sheet.",
                finished_at=datetime.now(UTC),
            )
            return
        update(total=len(rows))

        buffer: list[CheckResult] = []
        done = 0

        def flush() -> None:
            nonlocal buffer
            if not buffer:
                return
            db = session_scope()
            try:
                for r in buffer:
                    db.add(
                        BacklinkCheck(
                            agent_id=agent_id, row=r.row, page_url=r.page_url, result=r.result,
                            rel=r.rel, link_href=r.link_href, anchor_text=r.anchor_text,
                            http_status=r.http_status, detail=r.detail,
                        )
                    )
                audit = db.get(BacklinkAudit, agent_id)
                if audit is not None:
                    audit.done = done
                db.commit()
            finally:
                db.close()
            buffer = []

        def on_result(result: CheckResult) -> None:
            nonlocal done
            done += 1
            buffer.append(result)
            if len(buffer) >= 10:
                flush()

        await check_many(rows, domain, on_result)
        flush()

        update(status="completed", done=done, finished_at=datetime.now(UTC))
        db = session_scope()
        try:
            db.add(
                ActivityEntry(
                    actor="system", action="finished backlink audit", item=name,
                    after=f"{done} page(s) checked",
                )
            )
            db.commit()
        finally:
            db.close()
    except FetchError as exc:
        update(status="failed", error=str(exc), finished_at=datetime.now(UTC))
    except asyncio.CancelledError:
        update(status="failed", error="The audit was interrupted.", finished_at=datetime.now(UTC))
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Backlink audit crashed")
        update(status="failed", error=f"Unexpected error: {type(exc).__name__}", finished_at=datetime.now(UTC))
    finally:
        _running.pop(agent_id, None)


def recover_interrupted() -> None:
    """A restart kills in-flight audits; mark them failed rather than leave
    them "running" forever with a spinner nobody can stop."""
    db = session_scope()
    try:
        for audit in db.execute(
            select(BacklinkAudit).where(BacklinkAudit.status == "running")
        ).scalars():
            audit.status = "failed"
            audit.error = "The server restarted during the audit. Run it again."
            audit.finished_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()
