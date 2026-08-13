"""Discord connector (spec §9), built on the official Bot API (REST v10).

Three constraints decide what this can and cannot do:

1. There is no Discord-wide search. A bot only sees guilds it has been invited
   to by an admin, and within those, only channels its role can view. This is
   presence-based monitoring, not discovery.
2. MESSAGE CONTENT is a privileged intent. Without it enabled in the developer
   portal, Discord returns messages with ``content`` as an empty string -- the
   request succeeds, so a misconfigured bot looks perfectly healthy while
   scoring nothing. ``health_check`` tests for this specifically.
3. Reading history needs both View Channel and Read Message History on the
   bot's role. Missing either yields 403 per channel, not a global failure.

Uses REST polling rather than the gateway websocket: it is sufficient for
ingestion on a schedule, and avoids holding a persistent connection.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.integrations.base import ConnectionStatus, NormalisedMessage, PlatformConnector
from app.utils.hashing import pseudonymise

logger = logging.getLogger(__name__)

API_ROOT = "https://discord.com/api/v10"



def _retry_after(response: httpx.Response) -> float:
    """Seconds to wait from a 429. Discord sends Retry-After (and a JSON
    retry_after); default to a short pause and cap it so a bad header cannot
    stall ingestion for minutes."""
    raw = response.headers.get("Retry-After")
    if raw is None:
        try:
            raw = response.json().get("retry_after")
        except ValueError:
            raw = None
    try:
        return max(0.0, min(float(raw), 10.0))
    except (TypeError, ValueError):
        return 1.0


class DiscordError(RuntimeError):
    """Discord returned an error, or the transport failed."""


class DiscordConnector(PlatformConnector):
    platform = "discord"

    def __init__(self, bot_token: str, pseudonym_salt: str, timeout: float = 20.0) -> None:
        if not bot_token:
            raise ValueError("DISCORD_BOT_TOKEN is not set")
        self._token = bot_token
        self._salt = pseudonym_salt
        self._timeout = timeout
        # Per-channel high-water mark, so each poll only asks for what is new.
        self._last_seen: dict[str, str] = {}

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bot {self._token}",
            # Discord asks bots to identify themselves; unlabelled traffic is
            # more likely to be rate limited.
            "User-Agent": "SignalBot (https://joinallbettors.example, 0.1)",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        attempts: int = 3,
    ) -> Any:
        """One API call, honouring Discord's per-route rate limits.

        Discord's buckets are narrow and short: two calls to the same route in
        quick succession routinely return 429 with Retry-After under a second.
        Treating that as a hard failure made the connector fall over on its own
        second request, so a 429 is waited out and retried rather than raised.
        """
        label = f"{method} {path}"
        for attempt in range(attempts):
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                try:
                    response = await client.request(
                        method,
                        f"{API_ROOT}{path}",
                        headers=self._headers,
                        params=params or None,
                        json=payload,
                    )
                except httpx.HTTPError as exc:
                    raise DiscordError(f"{label}: transport error: {exc}") from exc

            if response.status_code == 429 and attempt < attempts - 1:
                delay = _retry_after(response)
                logger.info("%s rate limited, waiting %.2fs", label, delay)
                await asyncio.sleep(delay)
                continue
            return self._handle(response, label)

        raise DiscordError(f"{label}: still rate limited after {attempts} attempts")

    async def _get(self, path: str, **params: Any) -> Any:
        return await self._request("GET", path, params=params)

    async def _post(self, path: str, payload: dict[str, Any]) -> Any:
        return await self._request("POST", path, payload=payload)

    @staticmethod
    def _handle(response: httpx.Response, label: str) -> Any:
        if response.status_code == 401:
            raise DiscordError(f"{label}: unauthorised. The bot token is wrong or was reset.")
        if response.status_code == 403:
            raise DiscordError(
                f"{label}: forbidden. The bot's role lacks View Channel or "
                "Read Message History here."
            )
        if response.status_code == 429:
            retry = response.headers.get("Retry-After", "?")
            raise DiscordError(f"{label}: rate limited, retry after {retry}s")
        if response.status_code >= 400:
            raise DiscordError(f"{label}: HTTP {response.status_code}")
        if response.status_code == 204:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise DiscordError(f"{label}: non-JSON response") from exc

    # -- interface ---------------------------------------------------------

    async def health_check(self) -> ConnectionStatus:
        now = datetime.now(UTC)
        try:
            me = await self._get("/users/@me")
            guilds = await self._get("/users/@me/guilds")
        except DiscordError as exc:
            return ConnectionStatus(
                platform="discord", status="error", last_checked=now, error=str(exc)
            )

        username = me.get("username")
        detail = f"Connected as {username}. In {len(guilds)} server(s)."

        if not guilds:
            detail += (
                " The bot is not in any server, so it can see nothing. A server"
                " admin must invite it via the OAuth2 URL."
            )
            return ConnectionStatus(
                platform="discord", status="connected", last_checked=now, detail=detail
            )

        readable, blocked, content_visible = await self._probe_first_guild(guilds[0]["id"])
        detail += f" {readable} readable channel(s)"
        if blocked:
            detail += f", {blocked} blocked by permissions"
        detail += "."

        if content_visible is False:
            detail += (
                " Message content is EMPTY: the MESSAGE CONTENT privileged"
                " intent is not enabled. Turn it on in the Discord developer"
                " portal under Bot -> Privileged Gateway Intents, or every"
                " message will score zero."
            )
        return ConnectionStatus(
            platform="discord", status="connected", last_checked=now, detail=detail
        )

    async def _probe_first_guild(self, guild_id: str) -> tuple[int, int, bool | None]:
        """Count readable channels and check whether content actually arrives.

        Returns (readable, blocked, content_visible). ``content_visible`` is
        None when no message was found to judge by.
        """
        try:
            channels = await self._get(f"/guilds/{guild_id}/channels")
        except DiscordError:
            return 0, 0, None

        text_channels = [c for c in channels if c.get("type") == 0]
        readable = blocked = 0
        content_visible: bool | None = None

        for channel in text_channels[:5]:  # a sample is enough to diagnose
            try:
                messages = await self._get(f"/channels/{channel['id']}/messages", limit=5)
                readable += 1
            except DiscordError:
                blocked += 1
                continue
            # Content is blank for every message when the intent is missing,
            # except messages that mention the bot or that it sent itself.
            for msg in messages:
                if msg.get("author", {}).get("bot"):
                    continue
                if msg.get("content"):
                    content_visible = True
                    break
                content_visible = False
        return readable, blocked, content_visible

    async def list_sources(self) -> list[dict[str, Any]]:
        """Guilds and the text channels the bot can actually read."""
        guilds = await self._get("/users/@me/guilds")
        sources: list[dict[str, Any]] = []
        for guild in guilds:
            try:
                channels = await self._get(f"/guilds/{guild['id']}/channels")
            except DiscordError as exc:
                sources.append({"guild": guild["name"], "error": str(exc), "channels": []})
                continue
            sources.append(
                {
                    "guild": guild["name"],
                    "guildId": guild["id"],
                    "channels": [
                        {"id": c["id"], "name": c["name"]}
                        for c in channels
                        if c.get("type") == 0
                    ],
                }
            )
        return sources

    async def fetch_messages(self, limit: int = 100) -> list[NormalisedMessage]:
        """Poll every readable text channel in every guild the bot is in.

        A channel that 403s is skipped rather than failing the whole run: one
        locked channel should not stop ingestion everywhere else.
        """
        collected: list[NormalisedMessage] = []
        for source in await self.list_sources():
            for channel in source.get("channels", []):
                try:
                    collected.extend(
                        await self.fetch_channel(
                            channel["id"], source["guild"], channel["name"], limit
                        )
                    )
                except DiscordError as exc:
                    logger.info("Skipping #%s: %s", channel["name"], exc)
        return collected

    async def fetch_channel(
        self, channel_id: str, guild_name: str, channel_name: str, limit: int = 50
    ) -> list[NormalisedMessage]:
        params: dict[str, Any] = {"limit": min(limit, 100)}
        after = self._last_seen.get(channel_id)
        if after:
            params["after"] = after

        raw_messages = await self._get(f"/channels/{channel_id}/messages", **params)
        if raw_messages:
            # Discord returns newest first; the highest id is the new mark.
            self._last_seen[channel_id] = max(m["id"] for m in raw_messages)

        out: list[NormalisedMessage] = []
        for raw in raw_messages:
            normalised = self.normalise_message(raw, guild_name, channel_name)
            if normalised is not None:
                out.append(normalised)
        return out

    async def send_message(self, chat_id: str, text: str, reply_to: str | None = None) -> str:
        """Post an approved reply. Never called from the ingestion path."""
        payload: dict[str, Any] = {"content": text}
        if reply_to:
            payload["message_reference"] = {"message_id": reply_to}
        result = await self._post(f"/channels/{chat_id}/messages", payload)
        return str(result["id"])

    # -- normalisation (spec §10) -----------------------------------------

    def normalise_message(
        self, raw: dict[str, Any], guild_name: str, channel_name: str
    ) -> NormalisedMessage | None:
        """Convert a Discord message into the shared shape.

        Drops bot messages and anything with no text, so empty content caused
        by a missing intent never enters the queue as a zero-scoring
        conversation.
        """
        author = raw.get("author") or {}
        if author.get("bot"):
            return None

        content = (raw.get("content") or "").strip()
        if not content:
            return None

        message_id = raw.get("id")
        channel_id = raw.get("channel_id")
        guild_id = raw.get("guild_id")

        source_url = None
        if guild_id and channel_id and message_id:
            source_url = f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"

        posted_at = datetime.now(UTC)
        if raw.get("timestamp"):
            try:
                posted_at = datetime.fromisoformat(raw["timestamp"].replace("Z", "+00:00"))
            except ValueError:
                pass

        return NormalisedMessage(
            platform="discord",
            external_id=f"{channel_id}:{message_id}",
            community=f"{guild_name}#{channel_name}",
            author_pseudonym=pseudonymise("discord", str(author.get("id", "")), self._salt),
            message=content,
            posted_at=posted_at,
            # Discord exposes no location for users, and guessing one from a
            # server's region would be wrong more often than right.
            country=None,
            language=None,
            source_url=source_url,
        )
