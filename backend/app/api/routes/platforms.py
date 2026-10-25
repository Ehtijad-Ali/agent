"""Platform connection endpoints (spec §29).

What the dashboard needs to connect a platform without opening a developer
portal: the Discord invite link, and where the bot can actually read. Like the
health routes, nothing here exposes a token.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.integrations.discord import DiscordConnector, DiscordError
from app.models import ActivityEntry, PlatformSettings
from app.services.ingestion_service import build_connectors, source_settings

router = APIRouter(prefix="/platforms", tags=["platforms"])


@router.get("/discord")
async def discord_overview() -> dict:
    """Invite link plus every server and channel the bot can see."""
    settings = get_settings()
    if not settings.discord_bot_token or not settings.pseudonym_salt:
        return {
            "connected": False,
            "inviteUrl": None,
            "servers": [],
            "error": "DISCORD_BOT_TOKEN is not set on the server.",
        }

    connector = DiscordConnector(settings.discord_bot_token, settings.pseudonym_salt)
    try:
        app_id = settings.discord_application_id or await connector.application_id()
        servers = await connector.server_overview()
    except DiscordError as exc:
        return {"connected": False, "inviteUrl": None, "servers": [], "error": str(exc)}

    return {
        "connected": True,
        "inviteUrl": DiscordConnector.invite_url(app_id),
        "servers": servers,
        "error": None,
    }


# --- discovery sources (Reddit, YouTube, Telegram account) -------------------

SOURCE_KEYS = {
    "reddit": ("queries", "subreddits"),
    "youtube": ("queries", "channel_ids"),
    "telegram_account": ("queries", "chats"),
}


def _configured(platform: str) -> bool:
    s = get_settings()
    return {
        "reddit": bool(s.reddit_client_id and s.reddit_client_secret),
        "youtube": bool(s.youtube_api_key),
        "telegram_account": bool(s.telegram_api_id and s.telegram_api_hash and s.telegram_session),
    }[platform]


class SourcesUpdate(BaseModel):
    queries: list[str] = Field(default_factory=list, max_length=30)
    subreddits: list[str] | None = Field(default=None, max_length=50)
    channel_ids: list[str] | None = Field(default=None, max_length=50)
    chats: list[str] | None = Field(default=None, max_length=50)

    @field_validator("queries", "subreddits", "channel_ids", "chats")
    @classmethod
    def _clean(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        out = []
        for item in v:
            item = " ".join(str(item).split())
            if len(item) > 100:
                raise ValueError("each entry must be 100 characters or fewer")
            if item and item not in out:
                out.append(item)
        return out


@router.get("/sources")
def list_sources(db: Session = Depends(get_db)) -> dict:
    """What each discovery platform searches, and whether it is set up."""
    settings = source_settings(db)
    return {
        name: {"configured": _configured(name), "settings": settings.get(name, {})}
        for name in SOURCE_KEYS
    }


@router.put("/sources/{platform}")
def update_sources(platform: str, body: SourcesUpdate, db: Session = Depends(get_db)) -> dict:
    if platform not in SOURCE_KEYS:
        raise HTTPException(404, f"Unknown platform {platform}.")
    data = body.model_dump()
    config = {k: data[k] for k in SOURCE_KEYS[platform] if data.get(k) is not None}
    row = db.get(PlatformSettings, platform)
    if row is None:
        row = PlatformSettings(platform=platform, config=config)
        db.add(row)
    else:
        row.config = {**(row.config or {}), **config}
    db.add(ActivityEntry(actor="you", action="updated sources", item=platform,
                         after=", ".join(config.get("queries", []))[:500]))
    db.commit()
    return {"configured": _configured(platform), "settings": source_settings(db)[platform]}


@router.get("/status/{platform}")
async def source_status(platform: str, db: Session = Depends(get_db)) -> dict:
    """Live check of one discovery connector."""
    if platform not in SOURCE_KEYS:
        raise HTTPException(404, f"Unknown platform {platform}.")
    if not _configured(platform):
        return {"status": "not_connected", "detail": None, "error": None}
    labels = {"reddit": "reddit", "youtube": "youtube", "telegram_account": "telegram (account)"}
    for _, connector in build_connectors(db):
        if getattr(connector, "label", None) == labels[platform]:
            st = await connector.health_check()
            return {"status": st.status, "detail": st.detail, "error": st.error}
    return {"status": "not_connected", "detail": None, "error": None}
