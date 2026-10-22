"""Fetching public web pages safely, and reading what is on them.

Used by the backlink audit and the AI Agent's web tools. Both fetch URLs that
came from outside -- a shared spreadsheet, or a chat message -- so every fetch
is treated as untrusted:

* only http(s), only public addresses. A URL that resolves to loopback, a
  private range, link-local (cloud metadata lives at 169.254.169.254) or any
  other non-global address is refused, and redirects are followed by hand so
  each hop is re-checked rather than trusting the first one;
* bodies are capped, so a multi-gigabyte "page" cannot exhaust memory.
"""

from __future__ import annotations

import asyncio
import base64
import csv
import io
import ipaddress
import re
import socket
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import httpx

MAX_BYTES = 3_000_000
MAX_REDIRECTS = 5
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 SignalBot/0.1"
)


class FetchError(RuntimeError):
    """The page could not be fetched; the message is safe to show."""


@dataclass(slots=True)
class FetchResult:
    url: str
    status: int
    content_type: str
    text: str


async def _assert_public(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchError("Only http and https URLs can be opened.")
    host = parsed.hostname
    if not host:
        raise FetchError("The URL has no host.")
    try:
        infos = await asyncio.to_thread(
            socket.getaddrinfo, host, parsed.port or (443 if parsed.scheme == "https" else 80)
        )
    except socket.gaierror as exc:
        raise FetchError(f"Could not resolve {host}.") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise FetchError(f"{host} is not a public address, so it will not be opened.")


async def fetch(url: str, timeout: float = 20.0) -> FetchResult:
    """GET a public URL, following redirects one checked hop at a time."""
    current = url.strip()
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"},
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            await _assert_public(current)
            try:
                async with client.stream("GET", current) as response:
                    if response.is_redirect and response.headers.get("location"):
                        current = urljoin(current, response.headers["location"])
                        continue
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_BYTES:
                            break
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    encoding = response.encoding or "utf-8"
                    try:
                        text = body.decode(encoding, errors="replace")
                    except LookupError:
                        text = body.decode("utf-8", errors="replace")
                    return FetchResult(
                        url=str(response.url),
                        status=response.status_code,
                        content_type=response.headers.get("content-type", ""),
                        text=text,
                    )
            except httpx.TimeoutException as exc:
                raise FetchError("The page took too long to respond.") from exc
            except httpx.HTTPError as exc:
                raise FetchError(f"Could not open the page: {type(exc).__name__}.") from exc
    raise FetchError("Too many redirects.")


# --- HTML ------------------------------------------------------------------


@dataclass(slots=True)
class Link:
    href: str
    rel: str
    text: str


@dataclass
class PageContent:
    title: str = ""
    text: str = ""
    links: list[Link] = field(default_factory=list)


class _PageParser(HTMLParser):
    _SKIP = {"script", "style", "noscript", "svg", "template", "head"}
    _BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article"}

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.page = PageContent()
        self._skip_depth = 0
        self._in_title = False
        self._text: list[str] = []
        self._link: dict | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        if tag in self._SKIP and tag != "head":
            self._skip_depth += 1
        if tag in self._BLOCK:
            self._text.append("\n")
        if tag == "a":
            values = {k.lower(): (v or "") for k, v in attrs}
            if values.get("href"):
                self._link = {
                    "href": urljoin(self.base_url, values["href"].strip()),
                    "rel": values.get("rel", "").lower(),
                    "text": [],
                }

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in self._SKIP and tag != "head" and self._skip_depth:
            self._skip_depth -= 1
        if tag == "a" and self._link is not None:
            self.page.links.append(
                Link(
                    href=self._link["href"],
                    rel=self._link["rel"],
                    text=" ".join("".join(self._link["text"]).split())[:200],
                )
            )
            self._link = None

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.page.title += data
            return
        if self._skip_depth:
            return
        self._text.append(data)
        if self._link is not None:
            self._link["text"].append(data)

    def result(self) -> PageContent:
        raw = "".join(self._text)
        lines = [" ".join(line.split()) for line in raw.splitlines()]
        self.page.text = "\n".join(line for line in lines if line)
        self.page.title = " ".join(self.page.title.split())
        return self.page


def parse_html(html: str, base_url: str) -> PageContent:
    parser = _PageParser(base_url)
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # noqa: BLE001 -- malformed HTML still yields what was parsed
        pass
    return parser.result()


# --- spreadsheets ----------------------------------------------------------

_SHEET_ID = re.compile(r"/spreadsheets/d/([A-Za-z0-9_-]+)")
_GID = re.compile(r"[#&?]gid=(\d+)")


def spreadsheet_csv_url(url: str) -> str:
    """Turn a Google Sheets link into its CSV export URL; pass others through."""
    match = _SHEET_ID.search(url)
    if not match:
        return url
    gid = _GID.search(url)
    export = f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=csv"
    if gid:
        export += f"&gid={gid.group(1)}"
    return export


async def read_spreadsheet(url: str) -> list[list[str]]:
    """Every row of a link-shared Google Sheet, or of a CSV URL."""
    result = await fetch(spreadsheet_csv_url(url), timeout=30)
    if result.status in (401, 403) or "accounts.google.com" in result.url:
        raise FetchError(
            "The sheet is not public. Share it as “Anyone with the link can view”."
        )
    if result.status >= 400:
        raise FetchError(f"The sheet returned HTTP {result.status}.")
    if "text/html" in result.content_type and "<html" in result.text[:500].lower():
        raise FetchError(
            "That link returned a web page, not a spreadsheet. Share the sheet as "
            "“Anyone with the link can view”, or give a CSV link."
        )
    return list(csv.reader(io.StringIO(result.text)))


def column_index(letter: str) -> int:
    """'A' -> 0, 'B' -> 1, 'AA' -> 26."""
    index = 0
    for char in letter.strip().upper():
        if not "A" <= char <= "Z":
            raise ValueError(f"'{letter}' is not a column letter.")
        index = index * 26 + (ord(char) - 64)
    return max(index - 1, 0)


# --- web search ------------------------------------------------------------


async def web_search(query: str, limit: int = 8) -> list[dict[str, str]]:
    """Keyless web search: Bing's results page, DuckDuckGo as a fallback.

    DuckDuckGo answers most server traffic with a bot check (HTTP 202), so it
    is only tried when Bing returns nothing.
    """
    errors: list[str] = []
    for engine in (_bing, _duckduckgo):
        try:
            findings = await engine(query, limit)
        except FetchError as exc:
            errors.append(str(exc))
            continue
        if findings:
            return findings
    if errors and len(errors) == 2:
        raise FetchError("Web search is unreachable right now: " + errors[0])
    return []


def _bing_target(href: str) -> str:
    """Bing wraps results as /ck/a?...&u=a1<base64url>; unwrap to the real URL."""
    if "bing.com/ck/" not in href:
        return href
    encoded = parse_qs(urlparse(href.replace("&amp;", "&")).query).get("u", [""])[0]
    if encoded.startswith("a1"):
        try:
            raw = encoded[2:]
            return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8", "replace")
        except (ValueError, UnicodeDecodeError):
            return href
    return href


async def _bing(query: str, limit: int) -> list[dict[str, str]]:
    result = await fetch(
        f"https://www.bing.com/search?q={quote_plus(query)}&setlang=en&count={max(limit, 10)}", timeout=40
    )
    if result.status >= 400:
        return []
    findings: list[dict[str, str]] = []
    for block in re.split(r'<li class="b_algo', result.text)[1:]:
        link = re.search(r"<h2[^>]*>\s*<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", block, re.S)
        if not link:
            continue
        snippet = re.search(r"<p[^>]*>(.*?)</p>", block, re.S)
        findings.append(
            {
                "title": _strip_tags(link.group(2)),
                "url": _bing_target(link.group(1)),
                "snippet": _strip_tags(snippet.group(1)) if snippet else "",
            }
        )
        if len(findings) >= limit:
            break
    return findings


async def _duckduckgo(query: str, limit: int) -> list[dict[str, str]]:
    result = await fetch(f"https://html.duckduckgo.com/html/?q={quote_plus(query)}", timeout=20)
    if result.status != 200:
        return []
    findings: list[dict[str, str]] = []
    for block in re.split(r'<div class="result[ "]', result.text)[1:]:
        link = re.search(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not link:
            continue
        href = link.group(1)
        if "uddg=" in href:
            href = unquote(parse_qs(urlparse(href).query).get("uddg", [href])[0])
        if href.startswith("//"):
            href = "https:" + href
        snippet = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, re.S)
        findings.append(
            {
                "title": _strip_tags(link.group(2)),
                "url": href,
                "snippet": _strip_tags(snippet.group(1)) if snippet else "",
            }
        )
        if len(findings) >= limit:
            break
    return findings


def _strip_tags(fragment: str) -> str:
    return " ".join(parse_html(fragment, "https://example.invalid").text.split())
