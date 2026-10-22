"""YouTube comments discovery connector (YouTube Data API v3, API key only).

Finds recent videos matching the search terms (and the latest uploads of any
watched channels) and reads their top-level comments. An API key can read but
never post, so replies happen on YouTube, by a person.

Quota: search.list costs 100 units, commentThreads.list costs 1. The default
daily quota is 10,000 units, so each search term costs about 1% of a day.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.integrations.base import ConnectionStatus, NormalisedMessage, PlatformConnector
from app.utils.hashing import pseudonymise

logger = logging.getLogger(__name__)

API_ROOT = "https://www.googleapis.com/youtube/v3"


class YouTubeError(RuntimeError):
    pass


class YouTubeConnector(PlatformConnector):
    platform = "youtube"

    def __init__(
        self,
        api_key: str,
        pseudonym_salt: str,
        queries: list[str] | None = None,
        channel_ids: list[str] | None = None,
        videos_per_query: int = 5,
    ) -> None:
        self._key = api_key
        self._salt = pseudonym_salt
        self.queries = queries or []
        self.channel_ids = [c.strip() for c in channel_ids or [] if c.strip()]
        self._videos = videos_per_query

    async def _get(self, client: httpx.AsyncClient, path: str, **params: Any) -> Any:
        response = await client.get(f"{API_ROOT}{path}", params={**params, "key": self._key})
        if response.status_code >= 400:
            reason = ""
            try:
                errors = response.json().get("error", {}).get("errors", [])
                reason = errors[0].get("reason", "") if errors else ""
            except ValueError:
                pass
            if reason == "quotaExceeded":
                raise YouTubeError("YouTube daily quota is used up; it resets at midnight Pacific.")
            if reason == "commentsDisabled":
                raise YouTubeError("comments disabled")
            raise YouTubeError(f"GET {path}: HTTP {response.status_code} {reason}".strip())
        return response.json()

    async def health_check(self) -> ConnectionStatus:
        now = datetime.now(UTC)
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                # 1 quota unit: the cheapest call that proves the key works.
                await self._get(client, "/i18nRegions", part="snippet", hl="en")
        except (YouTubeError, httpx.HTTPError) as exc:
            return ConnectionStatus("youtube", "error", now, error=str(exc))
        detail = f"Connected. Searching {len(self.queries)} term(s)"
        if self.channel_ids:
            detail += f" and watching {len(self.channel_ids)} channel(s)"
        return ConnectionStatus("youtube", "connected", now, detail=detail + ".")

    async def fetch_messages(self, limit: int = 100) -> list[NormalisedMessage]:
        since = (datetime.now(UTC) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
        videos: dict[str, str] = {}
        async with httpx.AsyncClient(timeout=30) as client:
            searches = [{"q": q} for q in self.queries] + [{"channelId": c} for c in self.channel_ids]
            for params in searches:
                try:
                    data = await self._get(
                        client, "/search", part="snippet", type="video", order="date",
                        maxResults=self._videos, publishedAfter=since, **params,
                    )
                except YouTubeError as exc:
                    logger.info("YouTube search %s failed: %s", params, exc)
                    if "quota" in str(exc):
                        break
                    continue
                for item in data.get("items", []):
                    video_id = item.get("id", {}).get("videoId")
                    if video_id:
                        videos[video_id] = item.get("snippet", {}).get("title", "")

            out: list[NormalisedMessage] = []
            for video_id, title in videos.items():
                try:
                    data = await self._get(
                        client, "/commentThreads", part="snippet", videoId=video_id,
                        maxResults=50, order="time", textFormat="plainText",
                    )
                except YouTubeError as exc:
                    logger.info("YouTube comments for %s skipped: %s", video_id, exc)
                    continue
                for thread in data.get("items", []):
                    msg = self._normalise(thread, video_id, title)
                    if msg is not None:
                        out.append(msg)
        return out[:limit] if limit else out

    def _normalise(self, thread: dict, video_id: str, title: str) -> NormalisedMessage | None:
        top = (thread.get("snippet") or {}).get("topLevelComment") or {}
        snippet = top.get("snippet") or {}
        text = (snippet.get("textDisplay") or snippet.get("textOriginal") or "").strip()
        comment_id = top.get("id")
        if not text or not comment_id:
            return None
        author = (snippet.get("authorChannelId") or {}).get("value") or snippet.get("authorDisplayName", "")
        posted = snippet.get("publishedAt")
        try:
            posted_at = datetime.fromisoformat(posted.replace("Z", "+00:00")) if posted else datetime.now(UTC)
        except ValueError:
            posted_at = datetime.now(UTC)
        return NormalisedMessage(
            platform="youtube",
            external_id=comment_id,
            community=(title or video_id)[:200],
            author_pseudonym=pseudonymise("youtube", str(author), self._salt),
            message=text[:4000],
            posted_at=posted_at,
            source_url=f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}",
        )

    async def send_message(self, chat_id: str, text: str, reply_to: str | None = None) -> str:
        raise NotImplementedError("YouTube is read-only here: reply on YouTube, then mark it posted.")
