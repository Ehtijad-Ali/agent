"""Backlink audit agents: is each page's link to us dofollow?

The job, as the operator described it: take the URLs in column A of a Google
Sheet, open each page, find the link to the target domain, and record whether
it is dofollow. That is deterministic -- an HTML attribute check -- so it is
done with a parser, not a language model. A model would be slower, cost money
per page and occasionally be wrong about something a parser cannot get wrong.

Results are stored per agent and offered as a CSV whose second column lines up
with the sheet, so it can be pasted straight into column B. Writing to the
sheet directly needs Google credentials with edit access, which the platform
does not hold.

Every URL here comes from a user-supplied sheet and is fetched by the server,
so each one is checked before the request is made: http(s) only, and never an
address on the server's own network (spec §41).
"""

from __future__ import annotations

import asyncio
import csv
import io
import ipaddress
import logging
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger("signal.backlinks")

# Pages fetched at once. Enough to finish a few hundred rows in a minute or
# two without looking like an attack on any one host.
CONCURRENCY = 8
FETCH_TIMEOUT = 20.0
# Larger pages are cut off here; a link in the first 3 MB is found, and a
# runaway response cannot exhaust memory.
MAX_BYTES = 3_000_000
USER_AGENT = (
    "Mozilla/5.0 (compatible; SignalBacklinkAudit/1.0; "
    "+https://signal.joinallbettors.com)"
)

_SHEET_ID = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]+)")
_GID = re.compile(r"[#&?]gid=(\d+)")
_NOFOLLOW_RELS = {"nofollow", "sponsored", "ugc"}


class BacklinkError(RuntimeError):
    """The audit cannot start, and why -- shown to the operator verbatim."""


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


# -- the sheet ---------------------------------------------------------------


def sheet_csv_url(sheet_url: str) -> str:
    """Turn a Google Sheets link into its CSV export URL.

    Works for any sheet shared as "anyone with the link can view". The tab is
    taken from gid= in the link, so pasting a link to the right tab is enough.
    """
    match = _SHEET_ID.search(sheet_url or "")
    if not match:
        raise BacklinkError(
            "That is not a Google Sheets link. Paste the link from the browser "
            "address bar, e.g. https://docs.google.com/spreadsheets/d/…/edit"
        )
    url = f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=csv"
    gid = _GID.search(sheet_url)
    if gid:
        url += f"&gid={gid.group(1)}"
    return url


def column_index(letter: str) -> int:
    """'A' -> 0, 'B' -> 1, 'AA' -> 26."""
    letter = (letter or "A").strip().upper()
    if not letter.isalpha():
        raise BacklinkError(f"Column must be a letter such as A, not {letter!r}.")
    index = 0
    for ch in letter:
        index = index * 26 + (ord(ch) - ord("A") + 1)
    return index - 1


def urls_from_csv(text: str, column: str = "A") -> list[tuple[int, str]]:
    """(sheet row, url) for every cell in the column that looks like a URL.

    Header rows and blank cells are skipped by the same test: a cell that does
    not start with http is not a page to check.
    """
    col = column_index(column)
    out: list[tuple[int, str]] = []
    for row_number, row in enumerate(csv.reader(io.StringIO(text)), start=1):
        if col < len(row):
            cell = row[col].strip()
            if cell.lower().startswith(("http://", "https://")):
                out.append((row_number, cell))
    return out


async def read_sheet(sheet_url: str, column: str = "A") -> list[tuple[int, str]]:
    export = sheet_csv_url(sheet_url)
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
        try:
            response = await client.get(export)
        except httpx.HTTPError as exc:
            raise BacklinkError(f"Could not reach Google Sheets: {exc}") from exc

    content_type = response.headers.get("content-type", "")
    # A private sheet answers with a sign-in page (HTML), not an error code.
    if response.status_code != 200 or "text/csv" not in content_type:
        raise BacklinkError(
            "The sheet could not be read. In Google Sheets click Share -> "
            "General access -> 'Anyone with the link' (Viewer), then try again."
        )
    urls = urls_from_csv(response.text, column)
    if not urls:
        raise BacklinkError(f"No URLs found in column {column.upper()} of the sheet.")
    return urls


# -- one page ----------------------------------------------------------------


def _host_matches(host: str, domain: str) -> bool:
    host = (host or "").lower().rstrip(".")
    domain = domain.lower().strip().removeprefix("www.")
    return host == domain or host.endswith("." + domain)


class _LinkFinder(HTMLParser):
    """Collects <a> tags pointing at the target domain, plus meta robots."""

    def __init__(self, base_url: str, domain: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.domain = domain
        self.links: list[dict[str, str]] = []
        self.meta_nofollow = False
        self._open: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta" and a.get("name", "").lower() in ("robots", "googlebot"):
            if "nofollow" in a.get("content", "").lower():
                self.meta_nofollow = True
        elif tag == "base" and a.get("href"):
            self.base_url = urljoin(self.base_url, a["href"])
        elif tag == "a" and a.get("href"):
            href = urljoin(self.base_url, a["href"].strip())
            if _host_matches(urlparse(href).hostname or "", self.domain):
                self._open = {"href": href, "rel": a.get("rel", "").strip(), "text": ""}
                self.links.append(self._open)

    def handle_data(self, data: str) -> None:
        if self._open is not None:
            self._open["text"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._open = None


def classify(html: str, page_url: str, domain: str, robots_header: str = "") -> dict:
    """Decide dofollow / nofollow / not_found for one page's HTML.

    If the page links to us more than once, one dofollow link is enough for
    the page to count as dofollow -- that link passes value whatever the
    others say.
    """
    finder = _LinkFinder(page_url, domain)
    try:
        finder.feed(html)
        finder.close()
    except Exception:  # noqa: BLE001 -- malformed HTML still yields what was parsed
        pass

    if not finder.links:
        return {"result": "not_found", "detail": f"No link to {domain} on the page."}

    page_nofollow = finder.meta_nofollow or "nofollow" in robots_header.lower()
    for link in finder.links:
        rels = set(link["rel"].lower().split())
        if not (rels & _NOFOLLOW_RELS) and not page_nofollow:
            return {
                "result": "dofollow",
                "rel": link["rel"],
                "link_href": link["href"],
                "anchor_text": " ".join(link["text"].split())[:300],
                "detail": f"{len(finder.links)} link(s) to {domain} found.",
            }

    link = finder.links[0]
    reason = (
        "page-level robots nofollow"
        if page_nofollow
        else f'rel="{link["rel"]}"'
    )
    return {
        "result": "nofollow",
        "rel": link["rel"],
        "link_href": link["href"],
        "anchor_text": " ".join(link["text"].split())[:300],
        "detail": f"Nofollow: {reason}.",
    }


def _is_public_host(host: str) -> bool:
    """False for anything that resolves to a private, loopback or reserved
    address -- the server must not be steered into probing its own network."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            return False
    return True


async def check_page(
    client: httpx.AsyncClient, row: int, url: str, domain: str
) -> CheckResult:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return CheckResult(row, url, "error", detail="Not an http(s) URL.")
    if not await asyncio.to_thread(_is_public_host, parsed.hostname):
        return CheckResult(row, url, "error", detail="Host does not resolve to a public address.")

    try:
        async with client.stream("GET", url) as response:
            # Redirects are followed by the client; re-check where we landed.
            final_host = response.url.host
            if final_host != parsed.hostname and not await asyncio.to_thread(
                _is_public_host, final_host
            ):
                return CheckResult(row, url, "error", detail="Redirected to a non-public address.")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) >= MAX_BYTES:
                    break
            status = response.status_code
            robots = response.headers.get("x-robots-tag", "")
            encoding = response.encoding or "utf-8"
    except httpx.HTTPError as exc:
        return CheckResult(row, url, "error", detail=f"Could not load the page: {exc!s}"[:300])

    if status >= 400:
        return CheckResult(row, url, "error", http_status=status, detail=f"Page returned HTTP {status}.")

    html = bytes(body).decode(encoding, errors="replace")
    verdict = classify(html, str(response.url), domain, robots)
    return CheckResult(row=row, page_url=url, http_status=status, **verdict)


async def audit(urls: list[tuple[int, str]], domain: str) -> list[CheckResult]:
    semaphore = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(
        timeout=FETCH_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:

        async def one(row: int, url: str) -> CheckResult:
            async with semaphore:
                return await check_page(client, row, url, domain)

        return await asyncio.gather(*(one(r, u) for r, u in urls))


def results_csv(rows: list) -> str:
    """CSV in sheet order. Column B matches the operator's sheet layout, so the
    Result column can be pasted straight into it."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["URL", "Result", "Rel", "Link found", "Anchor text", "Detail"])
    for r in sorted(rows, key=lambda r: r.row):
        writer.writerow([r.page_url, r.result, r.rel, r.link_href, r.anchor_text, r.detail])
    return out.getvalue()
