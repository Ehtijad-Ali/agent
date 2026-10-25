"""Reddit connector: public posts and comments, by keyword and by subreddit.

Unlike Discord and Telegram bots, Reddit offers real search across public
content, so this is discovery rather than presence: it finds people talking
about prediction games anywhere on Reddit, not only where a bot was invited.

Uses the official API with an app-only OAuth token (client credentials), which
reads public content without a Reddit user login. Create the app at
https://www.reddit.com/prefs/apps (type "script"). Reddit's terms require a
data agreement for commercial use at scale; low-volume monitoring sits within
the free tier's 100 requests per minute.

Read-only. Replies are posted by a person on Reddit itself: an automated
promotional reply would break most subreddits' self-promotion rules.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from app.integrations.base import (
    ConnectionStatus,
    ManualReplyOnly,
    NormalisedMessage,
    PlatformConnector,
)
from app.utils.hashing import pseudonymise

logger = logging.getLogger(__name__)

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API_ROOT = "https://oauth.reddit.com"


class RedditError(RuntimeError):
    pass


class RedditConnector(PlatformConnector):
    platform = "reddit"
    label = "reddit"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        user_agent: str,
        pseudonym_salt: str,
        queries: list[str] | None = None,
        subreddits: list[str] | None = None,
        timeout: float = 20.0,
    ) -> None:
        if not client_id or not client_secret:
            raise ValueError("REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET are required")
        self._id = client_id
        self._secret = client_secret
        self._ua = user_agent or "signal-monitor/1.0"
        self._salt = pseudonym_salt
        self.queries = [q for q in (queries or []) if q.strip()]
        self.subreddits = [s.strip().removeprefix("r/") for s in (subreddits or []) if s.strip()]
        self._timeout = timeout
        self._token: str | None = None
        self._token_expires = 0.0

    async def _auth(self, client: httpx.AsyncClient) -> str:
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        response = await client.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(self._id, self._secret),
            headers={"User-Agent": self._ua},
        )
        if response.status_code == 401:
            raise RedditError("Reddit rejected the app credentials (client id/secret).")
        if response.status_code != 200:
            raise RedditError(f"Reddit token request failed ({response.status_code}).")
        body = response.json()
        if "access_token" not in body:
            raise RedditError(f"Reddit returned no token: {body.get('error', 'unknown')}")
        self._token = body["access_token"]
        self._token_expires = time.time() + float(body.get("expires_in", 3600))
        return self._token

    async def _get(self, client: httpx.AsyncClient, path: str, **params: Any) -> Any:
        params.setdefault("raw_json", 1)
        for attempt in range(3):
            token = await self._auth(client)
            response = await client.get(
                f"{API_ROOT}{path}",
                params=params,
                headers={"Authorization": f"Bearer {token}", "User-Agent": self._ua},
            )
            if response.status_code == 429 and attempt < 2:
                wait = float(response.headers.get("x-ratelimit-reset", "2") or 2)
                await asyncio.sleep(min(wait, 30.0))
                continue
            if response.status_code == 401 and attempt < 2:
                self._token = None
                continue
            if response.status_code != 200:
                raise RedditError(f"GET {path} failed ({response.status_code}).")
            return response.json()
        raise RedditError(f"GET {path}: still rate limited.")

    async def health_check(self) -> ConnectionStatus:
        now = datetime.now(UTC)
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                await self._get(client, "/search", q="prediction", limit=1)
        except (RedditError, httpx.HTTPError) as exc:
            return ConnectionStatus(platform="reddit", status="error", last_checked=now, error=str(exc))
        detail = (
            f"Connected. Searching {len(self.queries)} term(s)"
            + (f" and watching {len(self.subreddits)} subreddit(s)." if self.subreddits else ".")
        )
        return ConnectionStatus(platform="reddit", status="connected", last_checked=now, detail=detail)

    async def fetch_messages(self, limit: int = 100) -> list[NormalisedMessage]:
        seen: set[str] = set()
        out: list[NormalisedMessage] = []
        per_call = max(5, min(25, limit))
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            listings: list[Any] = []
            for q in self.queries:
                listings.append(await self._get(client, "/search", q=q, sort="new", t="week", limit=per_call, type="link"))
            for sub in self.subreddits:
                listings.append(await self._get(client, f"/r/{sub}/new", limit=per_call))
                listings.append(await self._get(client, f"/r/{sub}/comments", limit=per_call * 2))
        for listing in listings:
            for child in (listing or {}).get("data", {}).get("children", []):
                msg = self.normalise(child)
                if msg and msg.external_id not in seen:
                    seen.add(msg.external_id)
                    out.append(msg)
        return out

    def normalise(self, child: dict[str, Any]) -> NormalisedMessage | None:
        kind = child.get("kind")
        d = child.get("data") or {}
        if kind == "t3":
            text = "\n\n".join(p for p in (d.get("title"), d.get("selftext")) if p)
        elif kind == "t1":
            text = d.get("body") or ""
        else:
            return None
        author = d.get("author") or ""
        if not text.strip() or author in ("", "[deleted]", "AutoModerator") or text.strip() in ("[removed]", "[deleted]"):
            return None
        return NormalisedMessage(
            platform="reddit",
            external_id=d.get("name") or f"{kind}_{d.get('id')}",
            community=f"r/{d.get('subreddit', 'unknown')}",
            author_pseudonym=pseudonymise("reddit", author, self._salt),
            message=text.strip()[:4000],
            posted_at=datetime.fromtimestamp(float(d.get("created_utc", 0)), tz=UTC),
            country=None,
            language=None,
            source_url=f"https://www.reddit.com{d['permalink']}" if d.get("permalink") else None,
        )

    async def send_message(self, chat_id: str, text: str, reply_to: str | None = None) -> str:
        raise ManualReplyOnly(
            "Replies on Reddit are posted by hand: open the post, reply there, "
            "then click Mark posted."
        )
