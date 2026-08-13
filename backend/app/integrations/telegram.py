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

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.integrations.base import ConnectionStatus, NormalisedMessage, PlatformConnector
from app.utils.hashing import pseudonymise

logger = logging.getLogger(__name__)

API_ROOT = "https://api.telegram.org"


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

    # -- internals ---------------------------------------------------------

    @property
    def _base(self) -> str:
        return f"{API_ROOT}/bot{self._token}"

    async def _call(self, method: str, **params: Any) -> Any:
        """One Bot API call. Never logs the token or the full URL."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                response = await client.post(f"{self._base}/{method}", json=params)
            except httpx.HTTPError as exc:
                raise TelegramError(f"{method}: transport error: {exc}") from exc

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
        if not can_read_all:
            detail += (
                " Privacy mode is ON, so this bot only receives messages that "
                "mention it. Disable it in BotFather: /setprivacy -> Disable, "
                "then remove and re-add the bot to each group."
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
            "allowed_updates": ["message", "channel_post"],
        }
        if self._offset is not None:
            params["offset"] = self._offset

        updates = await self._call("getUpdates", **params)

        messages: list[NormalisedMessage] = []
        for update in updates:
            self._offset = update["update_id"] + 1
            raw = update.get("message") or update.get("channel_post")
            if raw is None:
                continue
            normalised = self.normalise_message(raw)
            if normalised is not None:
                messages.append(normalised)
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

        community = (
            chat.get("username")
            and f"@{chat['username']}"
            or chat.get("title")
            or str(chat.get("id"))
        )

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
            allowed_updates=["message", "channel_post"],
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
