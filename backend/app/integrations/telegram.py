"""Telegram connector (spec §8), built on the official Bot API.

Two things about Telegram bots decide what this can and cannot do:

1. There is no global search. A bot only ever sees chats it has been added to,
   so "discovery" here means "the groups you were invited to", not "Telegram".
2. Privacy mode is ON by default, and while it is on the bot only receives
   messages that mention it or start with a command. It must be turned off via
   BotFather (/setprivacy -> Disable) or almost nothing arrives. ``health_check``
   reports this explicitly because a silent empty queue looks identical to a
   broken integration.
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

API_ROOT = "https://api.telegram.org"

# How many times a 429 is waited out before giving up.
MAX_ATTEMPTS = 3

# my_chat_member is the bot's own membership changing -- added to a group,
# removed, promoted to admin. Without it the platform has no record that the
# bot ever joined a group, so "the bot is in the group but nothing arrives"
# cannot be told apart from "the bot was never added".
ALLOWED_UPDATES = ["message", "channel_post", "my_chat_member"]


def _retry_after(response: httpx.Response) -> float:
    """Seconds to wait from a 429.

    Telegram reports the delay in ``parameters.retry_after`` in the JSON body,
    and usually -- but not always -- in a Retry-After header, so both are
    consulted. Its flood waits run longer than Discord's sub-second bucket
    limits, hence the 30s ceiling rather than 10; it is still capped, because a
    malformed value must not park ingestion indefinitely.
    """
    raw: Any = response.headers.get("Retry-After")
    if raw is None:
        try:
            raw = (response.json().get("parameters") or {}).get("retry_after")
        except ValueError:
            raw = None
    try:
        return max(0.0, min(float(raw), 30.0))
    except (TypeError, ValueError):
        return 1.0


def _empty_poll() -> dict[str, Any]:
    return {"updates": 0, "textMessages": 0, "skippedNoText": 0, "chats": [], "events": []}


def _chat_label(chat: dict[str, Any]) -> str:
    return (
        chat.get("username") and f"@{chat['username']}"
        or chat.get("title")
        or str(chat.get("id"))
    )


def membership_event(update: dict[str, Any]) -> dict[str, str] | None:
    """Describe a my_chat_member update in operator terms, or None."""
    change = update.get("my_chat_member")
    if not change:
        return None
    chat = change.get("chat") or {}
    old = (change.get("old_chat_member") or {}).get("status", "")
    new = (change.get("new_chat_member") or {}).get("status", "")
    if new in ("member", "administrator") and old in ("left", "kicked", ""):
        action = "bot added to group"
    elif new in ("left", "kicked"):
        action = "bot removed from group"
    elif new == "administrator":
        action = "bot promoted to admin"
    else:
        action = f"bot membership changed ({old} -> {new})"
    return {"action": action, "chat": _chat_label(chat)}


class TelegramError(RuntimeError):
    """Telegram returned ok:false, or the transport failed."""


class TelegramConnector(PlatformConnector):
    platform = "telegram"

    def __init__(self, bot_token: str, pseudonym_salt: str, timeout: float = 20.0) -> None:
        if not bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is not set")
        self._token = bot_token
        self._salt = pseudonym_salt
        self._timeout = timeout
        # getUpdates is a cursor: acknowledging offset N drops everything below
        # it server-side, which is what stops the same message being reprocessed.
        self._offset: int | None = None
        # What the last poll actually saw, including what it dropped. The scan
        # records this so an empty Inbox can be explained from the platform
        # itself rather than guessed at.
        self.last_poll: dict[str, Any] = _empty_poll()

    # -- internals ---------------------------------------------------------

    @property
    def _base(self) -> str:
        return f"{API_ROOT}/bot{self._token}"

    async def _call(self, method: str, **params: Any) -> Any:
        """One Bot API call. Never logs the token or the full URL.

        A 429 is waited out and retried rather than raised. Telegram enforces
        per-chat and per-second flood limits, so a scan that touches several
        chats in succession hits them routinely; failing on the first one would
        abandon the rest of the cycle.
        """
        for attempt in range(MAX_ATTEMPTS):
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                try:
                    response = await client.post(f"{self._base}/{method}", json=params)
                except httpx.HTTPError as exc:
                    raise TelegramError(f"{method}: transport error: {exc}") from exc

            if response.status_code == 429 and attempt < MAX_ATTEMPTS - 1:
                delay = _retry_after(response)
                logger.info("%s rate limited, waiting %.2fs", method, delay)
                await asyncio.sleep(delay)
                continue
            if response.status_code == 429:
                # Out of attempts: say so, rather than repeating the per-call
                # "retry after Ns" message as if this were the first refusal.
                raise TelegramError(
                    f"{method}: still rate limited after {MAX_ATTEMPTS} attempts"
                )
            return self._handle(response, method)

        raise TelegramError(f"{method}: retry loop exited without a response")

    @staticmethod
    def _handle(response: httpx.Response, method: str) -> Any:
        """Turn one response into a result or a TelegramError."""
        if response.status_code == 401:
            raise TelegramError(
                f"{method}: unauthorised. The bot token is wrong or was revoked."
            )
        if response.status_code == 429:
            retry = response.headers.get("Retry-After", "?")
            raise TelegramError(f"{method}: rate limited, retry after {retry}s")

        try:
            payload = response.json()
        except ValueError as exc:
            raise TelegramError(f"{method}: non-JSON response ({response.status_code})") from exc

        if not payload.get("ok"):
            raise TelegramError(
                f"{method}: {payload.get('description', 'unknown error')} "
                f"(code {payload.get('error_code')})"
            )
        return payload["result"]

    # -- interface ---------------------------------------------------------

    async def health_check(self) -> ConnectionStatus:
        now = datetime.now(UTC)
        try:
            me = await self._call("getMe")
        except TelegramError as exc:
            return ConnectionStatus(
                platform="telegram", status="error", last_checked=now, error=str(exc)
            )

        username = me.get("username")
        # can_read_all_group_messages is the API's name for privacy mode being
        # off. False here is the single most common reason a correctly
        # configured bot still sees nothing.
        can_read_all = me.get("can_read_all_group_messages", False)
        detail = f"Connected as @{username}."
        # can_join_groups is BotFather's "Allow Groups?" setting. When it is
        # off, Telegram hides the bot from the add-member picker entirely, so
        # it can be found by search but never added to a group.
        if not me.get("can_join_groups", True):
            detail += (
                " Group joining is OFF, so this bot cannot be added to any "
                "group. Enable it in BotFather: /setjoingroups -> select the "
                "bot -> Enable."
            )
        if not can_read_all:
            detail += (
                " Privacy mode is ON, so this bot only receives messages that "
                "mention it. Disable it in BotFather: /setprivacy -> Disable, "
                "then remove and re-add the bot to each group."
            )
        else:
            # The API reports the current setting, but Telegram applies it
            # per group at the moment the bot joins. A bot added before privacy
            # was disabled keeps the old behaviour in that group.
            detail += (
                " Privacy mode is off. Groups the bot joined before it was "
                "turned off still need the bot removed and re-added."
            )
        # A webhook and getUpdates are mutually exclusive: while one is set,
        # every poll fails with 409 Conflict and nothing is ingested.
        try:
            hook = await self._call("getWebhookInfo")
        except TelegramError:
            hook = {}
        if hook.get("url"):
            return ConnectionStatus(
                platform="telegram",
                status="error",
                last_checked=now,
                detail=detail,
                error=(
                    "A webhook is set on this bot, which blocks polling. "
                    "Remove it (deleteWebhook) or nothing will be received."
                ),
            )
        return ConnectionStatus(
            platform="telegram",
            status="connected",
            last_checked=now,
            detail=detail,
        )

    async def fetch_messages(self, limit: int = 100) -> list[NormalisedMessage]:
        """Long-poll getUpdates. Suits local testing, where Telegram cannot
        reach a webhook on localhost."""
        params: dict[str, Any] = {
            "limit": min(limit, 100),
            "timeout": 0,
            "allowed_updates": ALLOWED_UPDATES,
        }
        if self._offset is not None:
            params["offset"] = self._offset

        self.last_poll = _empty_poll()
        updates = await self._call("getUpdates", **params)

        poll = self.last_poll
        chats: set[str] = set()
        messages: list[NormalisedMessage] = []
        for update in updates:
            self._offset = update["update_id"] + 1
            poll["updates"] += 1

            event = membership_event(update)
            if event is not None:
                poll["events"].append(event)
                continue

            raw = update.get("message") or update.get("channel_post")
            if raw is None:
                continue
            chats.add(_chat_label(raw.get("chat") or {}))
            normalised = self.normalise_message(raw)
            if normalised is None:
                poll["skippedNoText"] += 1
                continue
            poll["textMessages"] += 1
            messages.append(normalised)
        poll["chats"] = sorted(chats)
        return messages

    async def send_message(self, chat_id: str, text: str, reply_to: str | None = None) -> str:
        """Post an approved reply. Not reachable from the ingestion path."""
        params: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": False,
        }
        if reply_to:
            params["reply_to_message_id"] = int(reply_to)
        result = await self._call("sendMessage", **params)
        return str(result["message_id"])

    # -- normalisation (spec §10) -----------------------------------------

    def normalise_message(self, raw: dict[str, Any]) -> NormalisedMessage | None:
        """Convert a Bot API message into the shared shape.

        Returns None for anything with no usable text (stickers, joins, photos
        without captions) rather than queueing an empty conversation.
        """
        text = raw.get("text") or raw.get("caption")
        if not text or not text.strip():
            return None

        chat = raw.get("chat") or {}
        author = raw.get("from") or {}

        # Channel posts have no "from"; attribute them to the channel itself so
        # pseudonymisation still has a stable subject.
        author_id = str(author.get("id") or f"chat{chat.get('id')}")

        community = _chat_label(chat)

        source_url = None
        if chat.get("username") and raw.get("message_id"):
            source_url = f"https://t.me/{chat['username']}/{raw['message_id']}"

        return NormalisedMessage(
            platform="telegram",
            external_id=f"{chat.get('id')}:{raw.get('message_id')}",
            community=str(community),
            author_pseudonym=pseudonymise("telegram", author_id, self._salt),
            message=text.strip(),
            posted_at=datetime.fromtimestamp(raw.get("date", 0), tz=UTC),
            # Telegram exposes no reliable country. language_code is the
            # author's app language, which is a hint, not a location.
            country=None,
            language=author.get("language_code"),
            source_url=source_url,
        )

    # -- webhook mode ------------------------------------------------------

    async def set_webhook(self, url: str, secret_token: str) -> bool:
        """Production alternative to polling. Requires a public HTTPS URL, so
        it cannot be used against localhost."""
        await self._call(
            "setWebhook",
            url=url,
            secret_token=secret_token,
            allowed_updates=ALLOWED_UPDATES,
        )
        return True

    async def delete_webhook(self) -> bool:
        await self._call("deleteWebhook")
        return True

    @staticmethod
    def verify_webhook_secret(received: str | None, expected: str) -> bool:
        """Telegram echoes the secret in X-Telegram-Bot-Api-Secret-Token.

        Without this check anyone who learns the webhook URL can inject
        messages straight into the scoring pipeline (spec §41: treat all
        external input as untrusted).
        """
        import hmac

        if not expected or not received:
            return False
        return hmac.compare_digest(received, expected)
