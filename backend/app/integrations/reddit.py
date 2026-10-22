"""Reddit discovery connector (official OAuth API, read-only).

Unlike the Discord and Telegram bots, Reddit offers real keyword search across
public subreddits, so this *discovers* people rather than watching rooms it
was invited to. It uses an app-only "script" token: it can read public posts
and comments, and it has no user to post as -- replies happen on Reddit, by a
person, which is why the Inbox shows "Reply on Reddit" instead of Send.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.integrations.base import ConnectionStatus, NormalisedMessage, PlatformConnector
from app.utils.hashing import pseudonymise

logger = logging.getLogger(__name__)

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API_ROOT = "https://oauth.reddit.com"


class RedditError(RuntimeError):
    pass


class RedditConnector(PlatformConnector):
    platform = "reddit"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        user_agent: str,
        pseudonym_salt: str,
        queries: list[str] | None = None,
        subreddits: list[str] | None = None,
    ) -> None:
        self._id = client_id
        self._secret = client_secret
        self._agent = user_agent or "signal-discovery/0.1"
        self._salt = pseudonym_salt
        self.queries = queries or []
        self.subreddits = [s.strip().removeprefix("r/").removeprefix("/r/") for s in subreddits or [] if s.strip()]
        self._token: str | None = None

    async def _auth(self, client: httpx.AsyncClient) -> str:
        if self._token:
            return self._token
        response = await client.post(
            TOKEN_URL,
            auth=(self._id, self._secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": self._agent},
        )
        if response.status_code == 401:
            raise RedditError("Reddit rejected the app id or secret.")
        if response.status_code >= 400:
            raise RedditError(f"Reddit token request failed: HTTP {response.status_code}")
        token = response.json().get("access_token")
        if not token:
            raise RedditError("Reddit returned no access token.")
        self._token = token
        return token

    async def _get(self, client: httpx.AsyncClient, path: str, **params: Any) -> Any:
        token = await self._auth(client)
        response = await client.get(
            f"{API_ROOT}{path}",
            params={**params, "raw_json": 1},
            headers={"Authorization": f"Bearer {token}", "User-Agent": self._agent},
        )
        if response.status_code == 429:
            raise RedditError("Reddit rate limit reached; try the scan again later.")
        if response.status_code >= 400:
            raise RedditError(f"GET {path}: HTTP {response.status_code}")
        return response.json()

    async def health_check(self) -> ConnectionStatus:
        now = datetime.now(UTC)
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                await self._auth(client)
        except (RedditError, httpx.HTTPError) as exc:
            return ConnectionStatus("reddit", "error", now, error=str(exc))
        detail = f"Connected. Searching {len(self.queries)} term(s)"
        if self.subreddits:
            detail += f" and watching {len(self.subreddits)} subreddit(s)"
        return ConnectionStatus("reddit", "connected", now, detail=detail + ".")

    async def fetch_messages(self, limit: int = 100) -> list[NormalisedMessage]:
        out: dict[str, NormalisedMessage] = {}
        async with httpx.AsyncClient(timeout=30) as client:
            for query in self.queries:
                try:
                    data = await self._get(
                        client, "/search", q=query, sort="new", t="week", limit=25, type="link"
                    )
                except RedditError as exc:
                    logger.info("Reddit search %r failed: %s", query, exc)
                    continue
                for child in data.get("data", {}).get("children", []):
                    self._add(out, child)
            for sub in self.subreddits:
                for path in (f"/r/{sub}/new", f"/r/{sub}/comments"):
                    try:
                        data = await self._get(client, path, limit=25)
                    except RedditError as exc:
                        logger.info("Reddit %s failed: %s", path, exc)
                        continue
                    for child in data.get("data", {}).get("children", []):
                        self._add(out, child)
        return list(out.values())[:limit] if limit else list(out.values())

    def _add(self, out: dict[str, NormalisedMessage], child: dict) -> None:
        kind = child.get("kind")
        data = child.get("data") or {}
        name = data.get("name")
        author = data.get("author") or ""
        if not name or name in out or author in ("", "[deleted]", "AutoModerator"):
            return
        if kind == "t3":
            text = "\n".join(p for p in (data.get("title", ""), data.get("selftext", "")) if p).strip()
        elif kind == "t1":
            text = (data.get("body") or "").strip()
        else:
            return
        if not text:
            return
        permalink = data.get("permalink") or ""
        out[name] = NormalisedMessage(
            platform="reddit",
            external_id=name,
            community=f"r/{data.get('subreddit', '?')}",
            author_pseudonym=pseudonymise("reddit", author, self._salt),
            message=text[:4000],
            posted_at=datetime.fromtimestamp(float(data.get("created_utc", 0)) or datetime.now(UTC).timestamp(), UTC),
            source_url=f"https://www.reddit.com{permalink}" if permalink else None,
        )

    async def send_message(self, chat_id: str, text: str, reply_to: str | None = None) -> str:
        raise NotImplementedError("Reddit is read-only here: reply on Reddit, then mark it posted.")
