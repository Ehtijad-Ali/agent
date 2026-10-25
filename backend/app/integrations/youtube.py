"""YouTube connector: comments on recent videos about sports predictions.

YouTube comments are one of the largest public conversations about sports
picks and prediction apps, and the official Data API (v3) exposes them with a
plain API key: create one at https://console.cloud.google.com (enable
"YouTube Data API v3").

Quota is the constraint: 10,000 units a day by default. A search costs 100
units, a page of comments 1. With the default settings (3 search terms x 5
videos, twice a day) a day costs about 650 units.

Read-only. Posting comments needs a signed-in channel and would be
self-promotion under YouTube's spam policy, so replies are posted by hand.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
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

API_ROOT = "https://www.googleapis.com/youtube/v3"
VIDEOS_PER_SEARCH = 5
COMMENTS_PER_VIDEO = 50


class YouTubeError(RuntimeError):
    pass


class YouTubeConnector(PlatformConnector):
    platform = "youtube"
    label = "youtube"

    def __init__(
        self,
        api_key: str,
        pseudonym_salt: str,
        queries: list[str] | None = None,
        channel_ids: list[str] | None = None,
        timeout: float = 20.0,
    ) -> None:
        if not api_key:
            raise ValueError("YOUTUBE_API_KEY is required")
        self._key = api_key
        self._salt = pseudonym_salt
        self.queries = [q for q in (queries or []) if q.strip()]
        self.channel_ids = [c.strip() for c in (channel_ids or []) if c.strip()]
        self._timeout = timeout

    async def _get(self, client: httpx.AsyncClient, path: str, **params: Any) -> Any:
        params["key"] = self._key
        response = await client.get(f"{API_ROOT}/{path}", params=params)
        if response.status_code == 200:
            return response.json()
        try:
            reason = response.json()["error"]["errors"][0]["reason"]
        except (ValueError, KeyError, IndexError):
            reason = str(response.status_code)
        raise YouTubeError(reason)

    async def health_check(self) -> ConnectionStatus:
        now = datetime.now(UTC)
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                await self._get(client, "i18nRegions", part="snippet", hl="en")
        except (YouTubeError, httpx.HTTPError) as exc:
            msg = str(exc)
            if msg in ("keyInvalid", "400"):
                msg = "The YouTube API key is invalid."
            elif msg == "accessNotConfigured":
                msg = "Enable 'YouTube Data API v3' for this key in Google Cloud."
            return ConnectionStatus(platform="youtube", status="error", last_checked=now, error=msg)
        return ConnectionStatus(
            platform="youtube", status="connected", last_checked=now,
            detail=f"Connected. Searching {len(self.queries)} term(s) for recent videos and reading their comments.",
        )

    async def fetch_messages(self, limit: int = 100) -> list[NormalisedMessage]:
        since = (datetime.now(UTC) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
        videos: dict[str, str] = {}
        out: list[NormalisedMessage] = []
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            searches = [{"q": q} for q in self.queries] + [{"channelId": c} for c in self.channel_ids]
            for search in searches:
                try:
                    found = await self._get(
                        client, "search", part="snippet", type="video", order="date",
                        publishedAfter=since, maxResults=VIDEOS_PER_SEARCH, **search,
                    )
                except YouTubeError as exc:
                    if str(exc) == "quotaExceeded":
                        logger.warning("YouTube quota exhausted; stopping this scan")
                        break
                    raise
                for item in found.get("items", []):
                    vid = (item.get("id") or {}).get("videoId")
                    if vid:
                        videos[vid] = (item.get("snippet") or {}).get("title", "")

            for vid, title in videos.items():
                try:
                    threads = await self._get(
                        client, "commentThreads", part="snippet", videoId=vid,
                        maxResults=COMMENTS_PER_VIDEO, order="time", textFormat="plainText",
                    )
                except YouTubeError as exc:
                    # Comments disabled on this video, or quota gone.
                    if str(exc) == "quotaExceeded":
                        break
                    continue
                for thread in threads.get("items", []):
                    msg = self.normalise(thread, vid, title)
                    if msg:
                        out.append(msg)
        return out

    def normalise(self, thread: dict[str, Any], video_id: str, title: str) -> NormalisedMessage | None:
        top = ((thread.get("snippet") or {}).get("topLevelComment") or {})
        s = top.get("snippet") or {}
        text = s.get("textOriginal") or s.get("textDisplay") or ""
        author = ((s.get("authorChannelId") or {}).get("value")) or s.get("authorDisplayName") or ""
        if not text.strip() or not author or not top.get("id"):
            return None
        try:
            posted = datetime.fromisoformat(s.get("publishedAt", "").replace("Z", "+00:00"))
        except ValueError:
            posted = datetime.now(UTC)
        short_title = (title[:80] + "…") if len(title) > 80 else title
        return NormalisedMessage(
            platform="youtube",
            external_id=f"{video_id}:{top['id']}",
            community=f"YouTube: {short_title or video_id}",
            author_pseudonym=pseudonymise("youtube", author, self._salt),
            message=text.strip()[:4000],
            posted_at=posted,
            country=None,
            language=None,
            source_url=f"https://www.youtube.com/watch?v={video_id}&lc={top['id']}",
        )

    async def send_message(self, chat_id: str, text: str, reply_to: str | None = None) -> str:
        raise ManualReplyOnly(
            "Replies on YouTube are posted by hand: open the comment, reply there, "
            "then click Mark posted."
        )
