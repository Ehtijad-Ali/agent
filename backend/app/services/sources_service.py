"""Discovery sources: what Reddit, YouTube and the Telegram account search.

Settings live in the ``platform_sources`` table and are edited from the
Platforms screen. Credentials do not: they stay in the environment, and this
module only ever reports *whether* they are set (spec §29).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.base import PlatformConnector
from app.integrations.discord import DiscordConnector, DiscordError
from app.integrations.reddit import RedditConnector
from app.integrations.telegram_account import (
    TelegramAccountConnector,
    session_path,
    telethon_available,
)
from app.integrations.youtube import YouTubeConnector
from app.models import PlatformSource

logger = logging.getLogger("signal.sources")

DISCOVERY_PLATFORMS: tuple[str, ...] = ("reddit", "youtube", "telegram_account")

# Which list fields each platform accepts, besides "queries".
EXTRA_FIELDS: dict[str, str] = {
    "reddit": "subreddits",
    "youtube": "channel_ids",
    "telegram_account": "chats",
}

DEFAULTS: dict[str, dict[str, list[str]]] = {
    "reddit": {
        "queries": [
            "free prediction game",
            "sports prediction app",
            "free sports predictions",
            "prediction league friends",
            "free fantasy football game",
        ],
        "subreddits": [],
    },
    "youtube": {
        "queries": ["free prediction game", "sports prediction app", "free sports predictions"],
        "channel_ids": [],
    },
    "telegram_account": {
        "queries": ["sports predictions", "football tips free"],
        "chats": [],
    },
}

# Discord permissions the invite asks for: View Channel (1024), Send Messages
# (2048) and Read Message History (65536). Nothing administrative.
DISCORD_INVITE_PERMISSIONS = 1024 + 2048 + 65536


def is_configured(platform: str) -> bool:
    s = get_settings()
    if platform == "reddit":
        return bool(s.reddit_client_id and s.reddit_client_secret)
    if platform == "youtube":
        return bool(s.youtube_api_key)
    if platform == "telegram_account":
        return bool(
            s.telegram_api_id
            and s.telegram_api_hash
            and telethon_available()
            and session_path(s.telegram_session).exists()
        )
    return False


def not_configured_detail(platform: str) -> str:
    if platform == "reddit":
        return "Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET on the server."
    if platform == "youtube":
        return "Set YOUTUBE_API_KEY on the server."
    return (
        "Set TELEGRAM_API_ID and TELEGRAM_API_HASH, install telethon, and sign "
        "the account in with scripts/telegram_login.py on the server."
    )


def get_settings_for(db: Session, platform: str) -> dict[str, list[str]]:
    row = db.get(PlatformSource, platform)
    base = {k: list(v) for k, v in DEFAULTS[platform].items()}
    if row is not None:
        for key in base:
            if isinstance(row.settings.get(key), list):
                base[key] = [str(v) for v in row.settings[key]]
    return base


def list_sources(db: Session) -> dict[str, dict[str, Any]]:
    return {
        p: {"configured": is_configured(p), "settings": get_settings_for(db, p)}
        for p in DISCOVERY_PLATFORMS
    }


def update_sources(db: Session, platform: str, values: dict[str, list[str] | None]) -> dict[str, Any]:
    current = get_settings_for(db, platform)
    allowed = {"queries", EXTRA_FIELDS[platform]}
    for key, items in values.items():
        if key not in allowed or items is None:
            continue
        cleaned: list[str] = []
        for item in items:
            value = " ".join(str(item).split())[:200]
            if value and value not in cleaned:
                cleaned.append(value)
        current[key] = cleaned
    row = db.get(PlatformSource, platform)
    if row is None:
        db.add(PlatformSource(platform=platform, settings=current))
    else:
        row.settings = current
    db.commit()
    return {"configured": is_configured(platform), "settings": current}


def build_connector(db: Session, platform: str) -> PlatformConnector | None:
    """A connector for a configured discovery platform, else None."""
    s = get_settings()
    if not is_configured(platform) or not s.pseudonym_salt:
        return None
    cfg = get_settings_for(db, platform)
    if platform == "reddit":
        return RedditConnector(
            s.reddit_client_id, s.reddit_client_secret, s.reddit_user_agent,
            s.pseudonym_salt, cfg["queries"], cfg["subreddits"],
        )
    if platform == "youtube":
        return YouTubeConnector(s.youtube_api_key, s.pseudonym_salt, cfg["queries"], cfg["channel_ids"])
    return TelegramAccountConnector(
        s.telegram_api_id, s.telegram_api_hash, s.telegram_session,
        s.pseudonym_salt, cfg["queries"], cfg["chats"],
    )


async def source_status(db: Session, platform: str) -> dict[str, Any]:
    connector = build_connector(db, platform)
    if connector is None:
        return {"status": "not_connected", "detail": None, "error": None}
    status = await connector.health_check()
    return {"status": status.status, "detail": status.detail, "error": status.error}


# --- Discord ---------------------------------------------------------------


def discord_invite_url() -> str | None:
    app_id = get_settings().discord_application_id
    if not app_id:
        return None
    return (
        f"https://discord.com/oauth2/authorize?client_id={app_id}"
        f"&scope=bot&permissions={DISCORD_INVITE_PERMISSIONS}"
    )


async def discord_overview() -> dict[str, Any]:
    """Invite link plus every server and text channel the bot can see.

    A channel is "readable" when fetching one message from it succeeds, which
    is exactly the permission pair ingestion needs.
    """
    s = get_settings()
    invite = discord_invite_url()
    if not s.discord_bot_token:
        return {
            "connected": False,
            "inviteUrl": invite,
            "servers": [],
            "error": "DISCORD_BOT_TOKEN is not set on the server.",
        }

    connector = DiscordConnector(s.discord_bot_token, s.pseudonym_salt or "-")
    try:
        if invite is None:
            # The application id equals the bot user's id; derive the invite
            # so the button works even when DISCORD_APPLICATION_ID is unset.
            me = await connector._get("/users/@me")  # noqa: SLF001
            invite = (
                f"https://discord.com/oauth2/authorize?client_id={me['id']}"
                f"&scope=bot&permissions={DISCORD_INVITE_PERMISSIONS}"
            )
        guilds = await connector._get("/users/@me/guilds")  # noqa: SLF001
    except DiscordError as exc:
        return {"connected": False, "inviteUrl": invite, "servers": [], "error": str(exc)}

    servers: list[dict[str, Any]] = []
    for guild in guilds:
        try:
            channels = await connector._get(f"/guilds/{guild['id']}/channels")  # noqa: SLF001
        except DiscordError as exc:
            servers.append({"id": guild["id"], "name": guild["name"], "channels": [], "error": str(exc)})
            continue
        listed: list[dict[str, Any]] = []
        for channel in sorted((c for c in channels if c.get("type") == 0), key=lambda c: c.get("position", 0)):
            try:
                await connector._get(f"/channels/{channel['id']}/messages", limit=1)  # noqa: SLF001
                readable = True
            except DiscordError:
                readable = False
            listed.append({"id": channel["id"], "name": channel["name"], "readable": readable})
        servers.append({"id": guild["id"], "name": guild["name"], "channels": listed, "error": None})

    return {"connected": True, "inviteUrl": invite, "servers": servers, "error": None}


async def telegram_bot_overview() -> dict[str, Any]:
    """Which Telegram groups the bot has seen recently (from getUpdates)."""
    s = get_settings()
    if not s.telegram_bot_token:
        return {"connected": False, "groups": [], "error": "TELEGRAM_BOT_TOKEN is not set."}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"https://api.telegram.org/bot{s.telegram_bot_token}/getUpdates",
                params={"limit": 100, "timeout": 0},
            )
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return {"connected": False, "groups": [], "error": type(exc).__name__}
    if not data.get("ok"):
        return {"connected": False, "groups": [], "error": data.get("description", "Telegram error")}
    groups: dict[int, str] = {}
    for update in data.get("result", []):
        message = update.get("message") or update.get("channel_post") or {}
        chat = message.get("chat") or {}
        if chat.get("type") in ("group", "supergroup", "channel"):
            groups[chat["id"]] = chat.get("title", str(chat["id"]))
    return {"connected": True, "groups": sorted(groups.values()), "error": None}


__all__ = [
    "DISCOVERY_PLATFORMS",
    "build_connector",
    "discord_overview",
    "is_configured",
    "list_sources",
    "not_configured_detail",
    "source_status",
    "telegram_bot_overview",
    "update_sources",
]
