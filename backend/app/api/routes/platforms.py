"""Platform setup: which communities the bots can see, and what discovery
connectors search for (the Platforms screen)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import ActivityEntry
from app.services import sources_service

router = APIRouter(prefix="/platforms", tags=["platforms"])


class SourcesUpdate(BaseModel):
    queries: list[str] = Field(default_factory=list, max_length=30)
    subreddits: list[str] | None = Field(default=None, max_length=50)
    channel_ids: list[str] | None = Field(default=None, max_length=50)
    chats: list[str] | None = Field(default=None, max_length=50)


def _known(platform: str) -> str:
    if platform not in sources_service.DISCOVERY_PLATFORMS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Unknown discovery platform '{platform}'. Expected one of: "
                f"{', '.join(sources_service.DISCOVERY_PLATFORMS)}."
            ),
        )
    return platform


@router.get("/discord")
async def discord_overview() -> dict:
    """Invite link plus every server and channel the bot can see."""
    return await sources_service.discord_overview()


@router.get("/sources")
def list_sources(db: Session = Depends(get_db)) -> dict:
    """What each discovery platform searches, and whether it is set up."""
    return sources_service.list_sources(db)


@router.put("/sources/{platform}")
def update_sources(platform: str, request: SourcesUpdate, db: Session = Depends(get_db)) -> dict:
    _known(platform)
    result = sources_service.update_sources(db, platform, request.model_dump())
    db.add(
        ActivityEntry(
            actor="you",
            action="updated discovery sources",
            item=platform,
            after=", ".join(result["settings"].get("queries", []))[:250],
        )
    )
    db.commit()
    return result


@router.get("/status/{platform}")
async def source_status(platform: str, db: Session = Depends(get_db)) -> dict:
    """Live check of one discovery connector."""
    return await sources_service.source_status(db, _known(platform))
