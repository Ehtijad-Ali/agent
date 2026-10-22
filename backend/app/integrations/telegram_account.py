"""Telegram *account* discovery (MTProto via Telethon), read-only.

The Bot API cannot search Telegram or read groups it was not added to. A
regular user account can search public groups and channels by keyword and
read their history without joining, which is what this does -- and nothing
more: it never joins, posts or messages anyone.

Telethon is an optional dependency (``pip install telethon``). The account is
signed in once on the server with ``scripts/telegram_login.py``, which leaves a
session file next to the backend; until then this reports "not set up".
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from app.integrations.base import ConnectionStatus, NormalisedMessage, PlatformConnector
from app.utils.hashing import pseudonymise

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def telethon_available() -> bool:
    try:
        import telethon  # noqa: F401
    except ImportError:
        return False
    return True


def session_path(name: str) -> Path:
    return BACKEND_ROOT / f"{name}.session"


class TelegramAccountConnector(PlatformConnector):
    platform = "telegram"

    def __init__(
        self,
        api_id: str,
        api_hash: str,
        session: str,
        pseudonym_salt: str,
        queries: list[str] | None = None,
        chats: list[str] | None = None,
    ) -> None:
        self._api_id = int(api_id)
        self._api_hash = api_hash
        self._session = str(BACKEND_ROOT / session)
        self._salt = pseudonym_salt
        self.queries = queries or []
        self.chats = [c.strip() for c in chats or [] if c.strip()]

    def _client(self):
        from telethon import TelegramClient

        return TelegramClient(self._session, self._api_id, self._api_hash)

    async def health_check(self) -> ConnectionStatus:
        now = datetime.now(UTC)
        try:
            client = self._client()
            await client.connect()
            try:
                if not await client.is_user_authorized():
                    return ConnectionStatus(
                        "telegram", "error", now,
                        error="The account is not signed in. Run scripts/telegram_login.py on the server.",
                    )
                me = await client.get_me()
            finally:
                await client.disconnect()
        except Exception as exc:  # noqa: BLE001 -- surface any Telethon failure as status
            return ConnectionStatus("telegram", "error", now, error=f"{type(exc).__name__}: {exc}"[:300])
        handle = f"@{me.username}" if getattr(me, "username", None) else "the account"
        return ConnectionStatus(
            "telegram", "connected", now,
            detail=f"Signed in as {handle}. Searching {len(self.queries)} term(s), watching {len(self.chats)} chat(s).",
        )

    async def fetch_messages(self, limit: int = 100) -> list[NormalisedMessage]:
        from telethon.tl.functions.contacts import SearchRequest

        out: list[NormalisedMessage] = []
        client = self._client()
        await client.connect()
        try:
            if not await client.is_user_authorized():
                raise RuntimeError("Telegram account is not signed in.")
            targets: dict[int, object] = {}
            for query in self.queries:
                try:
                    found = await client(SearchRequest(q=query, limit=10))
                except Exception as exc:  # noqa: BLE001
                    logger.info("Telegram search %r failed: %s", query, exc)
                    continue
                for chat in found.chats:
                    if getattr(chat, "username", None):  # public only
                        targets[chat.id] = chat
            for ref in self.chats:
                handle = ref.replace("https://t.me/", "").replace("http://t.me/", "")
                try:
                    entity = await client.get_entity(handle)
                    targets[entity.id] = entity
                except Exception as exc:  # noqa: BLE001
                    logger.info("Telegram chat %r unavailable: %s", ref, exc)

            for entity in targets.values():
                title = getattr(entity, "title", None) or getattr(entity, "username", "?")
                username = getattr(entity, "username", None)
                async for message in client.iter_messages(entity, limit=30):
                    text = (message.message or "").strip()
                    if not text:
                        continue
                    sender = message.sender_id or message.chat_id or 0
                    out.append(
                        NormalisedMessage(
                            platform="telegram",
                            external_id=f"acct:{entity.id}:{message.id}",
                            community=str(title)[:200],
                            author_pseudonym=pseudonymise("telegram", str(sender), self._salt),
                            message=text[:4000],
                            posted_at=message.date or datetime.now(UTC),
                            source_url=f"https://t.me/{username}/{message.id}" if username else None,
                        )
                    )
        finally:
            await client.disconnect()
        return out[:limit] if limit else out

    async def send_message(self, chat_id: str, text: str, reply_to: str | None = None) -> str:
        raise NotImplementedError("The Telegram account never posts.")
