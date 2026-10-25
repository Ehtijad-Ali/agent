"""Telegram user-account connector: public groups and channels by keyword.

A bot only sees groups it was added to. A regular Telegram account can search
public groups and channels and read their messages, the same way anyone can
in the Telegram app. This connector does exactly that, read-only:

  1. finds public groups/channels matching each search term,
  2. adds any chats listed by username on the Platforms page,
  3. reads their recent messages.

It never joins, posts, or messages anyone: an account that sends promotional
messages to strangers is what Telegram bans. Use a dedicated account (its own
phone number), not anyone's personal one.

Setup: create API credentials at https://my.telegram.org (API development
tools), then run ``scripts/telegram_login.py`` once to sign in and print the
session string for TELEGRAM_SESSION.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from app.integrations.base import (
    ConnectionStatus,
    ManualReplyOnly,
    NormalisedMessage,
    PlatformConnector,
)
from app.utils.hashing import pseudonymise

logger = logging.getLogger(__name__)

CHATS_PER_QUERY = 8
MAX_CHATS = 25
MESSAGES_PER_CHAT = 40
LOOKBACK_DAYS = 7


class TelegramAccountError(RuntimeError):
    pass


def _client(api_id: int, api_hash: str, session: str):
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    return TelegramClient(StringSession(session), api_id, api_hash)


class TelegramAccountConnector(PlatformConnector):
    platform = "telegram"
    label = "telegram (account)"

    def __init__(
        self,
        api_id: str | int,
        api_hash: str,
        session: str,
        pseudonym_salt: str,
        queries: list[str] | None = None,
        chats: list[str] | None = None,
    ) -> None:
        if not (api_id and api_hash and session):
            raise ValueError("TELEGRAM_API_ID, TELEGRAM_API_HASH and TELEGRAM_SESSION are required")
        self._api_id = int(api_id)
        self._api_hash = api_hash
        self._session = session
        self._salt = pseudonym_salt
        self.queries = [q for q in (queries or []) if q.strip()]
        self.chats = [c.strip().removeprefix("https://t.me/").removeprefix("@") for c in (chats or []) if c.strip()]

    async def health_check(self) -> ConnectionStatus:
        now = datetime.now(UTC)
        try:
            async with _client(self._api_id, self._api_hash, self._session) as client:
                if not await client.is_user_authorized():
                    raise TelegramAccountError("The session is not signed in. Run scripts/telegram_login.py again.")
                me = await client.get_me()
        except Exception as exc:  # noqa: BLE001 -- Telethon raises many types; report the reason
            return ConnectionStatus(platform="telegram", status="error", last_checked=now, error=str(exc)[:300])
        name = f"@{me.username}" if getattr(me, "username", None) else (me.first_name or "account")
        return ConnectionStatus(
            platform="telegram", status="connected", last_checked=now,
            detail=f"Signed in as {name}. Searching {len(self.queries)} term(s) and {len(self.chats)} listed chat(s).",
        )

    async def fetch_messages(self, limit: int = 100) -> list[NormalisedMessage]:
        from telethon import functions, utils
        from telethon.errors import FloodWaitError

        since = datetime.now(UTC) - timedelta(days=LOOKBACK_DAYS)
        out: list[NormalisedMessage] = []
        async with _client(self._api_id, self._api_hash, self._session) as client:
            if not await client.is_user_authorized():
                raise TelegramAccountError("The Telegram account session is not signed in.")

            entities: dict[int, Any] = {}
            for name in self.chats:
                try:
                    entity = await client.get_entity(name)
                    entities[utils.get_peer_id(entity)] = entity
                except Exception as exc:  # noqa: BLE001 -- a bad username must not stop the rest
                    logger.info("Telegram chat %s not found: %s", name, exc)
            for q in self.queries:
                if len(entities) >= MAX_CHATS:
                    break
                try:
                    found = await client(functions.contacts.SearchRequest(q=q, limit=CHATS_PER_QUERY))
                except FloodWaitError as exc:
                    logger.warning("Telegram asked to wait %ss; stopping search", exc.seconds)
                    break
                for chat in found.chats:
                    # Public only: a username means anyone can open it.
                    if getattr(chat, "username", None) and (
                        getattr(chat, "megagroup", False) or getattr(chat, "broadcast", False)
                    ):
                        entities.setdefault(utils.get_peer_id(chat), chat)

            for peer_id, entity in list(entities.items())[:MAX_CHATS]:
                try:
                    async for msg in client.iter_messages(entity, limit=MESSAGES_PER_CHAT):
                        if msg.date and msg.date < since:
                            break
                        normalised = self.normalise(msg, entity, peer_id)
                        if normalised:
                            out.append(normalised)
                except FloodWaitError as exc:
                    logger.warning("Telegram asked to wait %ss; stopping read", exc.seconds)
                    break
                except Exception as exc:  # noqa: BLE001 -- private history or kicked; skip chat
                    logger.info("Cannot read %s: %s", getattr(entity, "username", peer_id), exc)
        return out

    def normalise(self, msg: Any, entity: Any, peer_id: int) -> NormalisedMessage | None:
        text = getattr(msg, "message", None) or ""
        if not text.strip():
            return None
        username = getattr(entity, "username", None)
        author = getattr(msg, "sender_id", None) or f"chat{peer_id}"
        return NormalisedMessage(
            platform="telegram",
            # Same "{chat id}:{message id}" form as the bot connector, so a
            # message both can see is stored once.
            external_id=f"{peer_id}:{msg.id}",
            community=f"@{username}" if username else (getattr(entity, "title", None) or str(peer_id)),
            author_pseudonym=pseudonymise("telegram", str(author), self._salt),
            message=text.strip()[:4000],
            posted_at=msg.date if msg.date.tzinfo else msg.date.replace(tzinfo=UTC),
            country=None,
            language=None,
            source_url=f"https://t.me/{username}/{msg.id}" if username else None,
        )

    async def send_message(self, chat_id: str, text: str, reply_to: str | None = None) -> str:
        raise ManualReplyOnly(
            "This message was found by the Telegram account, which never posts. "
            "Reply in Telegram yourself, then click Mark posted."
        )
