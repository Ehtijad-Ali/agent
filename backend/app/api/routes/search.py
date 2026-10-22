"""General search across the platform (brief §8).

One query, every searchable record type, each capped so a broad term cannot
return thousands of rows. Results carry a ``kind`` and a ``url`` so the caller
can route a hit to the screen that owns it without knowing the shape of each
table.

Case-insensitive substring matching via ILIKE. Not full-text: Postgres and
SQLite disagree on how to do that, and the honest answer at this data volume is
that a LIKE scan is fast enough. When it stops being fast enough the fix is a
Postgres tsvector column, which is a change here only.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import ActivityEntry, Agent, AgentOutput, Conversation
from app.schemas.base import CamelModel

router = APIRouter(prefix="/search", tags=["search"])

Kind = Literal["conversation", "agent", "content", "activity"]


class SearchHit(CamelModel):
    kind: Kind
    id: str
    title: str
    subtitle: str = ""
    snippet: str = ""


class SearchResponse(CamelModel):
    query: str
    total: int
    hits: list[SearchHit]


@router.get("", response_model=SearchResponse)
def search(
    db: Session = Depends(get_db),
    q: str = Query(..., min_length=2, description="At least two characters"),
    limit_per_kind: int = Query(10, ge=1, le=50, alias="limitPerKind"),
) -> SearchResponse:
    like = f"%{q.strip()}%"
    hits: list[SearchHit] = []

    conversations = (
        db.execute(
            select(Conversation)
            .where(
                or_(
                    Conversation.message.ilike(like),
                    Conversation.community.ilike(like),
                    Conversation.author_pseudonym.ilike(like),
                    Conversation.summary.ilike(like),
                )
            )
            .order_by(Conversation.posted_at.desc())
            .limit(limit_per_kind)
        )
        .scalars()
        .all()
    )
    hits.extend(
        SearchHit(
            kind="conversation",
            id=row.id,
            title=row.message[:90],
            subtitle=f"{row.platform} · {row.community} · score {row.score}",
            snippet=row.summary[:140],
        )
        for row in conversations
    )

    agents = (
        db.execute(
            select(Agent)
            .where(or_(Agent.name.ilike(like), Agent.description.ilike(like)))
            .limit(limit_per_kind)
        )
        .scalars()
        .all()
    )
    hits.extend(
        SearchHit(
            kind="agent",
            id=row.id,
            title=row.name,
            subtitle=f"{row.agent_type} · {'enabled' if row.enabled else 'disabled'}",
            snippet=row.description[:140],
        )
        for row in agents
    )

    outputs = (
        db.execute(
            select(AgentOutput)
            .where(
                or_(
                    AgentOutput.title.ilike(like),
                    AgentOutput.body.ilike(like),
                    AgentOutput.city.ilike(like),
                )
            )
            .order_by(AgentOutput.created_at.desc())
            .limit(limit_per_kind)
        )
        .scalars()
        .all()
    )
    hits.extend(
        SearchHit(
            kind="content",
            id=row.id,
            title=row.title[:90],
            subtitle=f"{row.city}, {row.state} · {row.category} · {row.status}",
            snippet=row.body[:140],
        )
        for row in outputs
    )

    entries = (
        db.execute(
            select(ActivityEntry)
            .where(
                or_(
                    ActivityEntry.action.ilike(like),
                    ActivityEntry.item.ilike(like),
                    ActivityEntry.actor.ilike(like),
                )
            )
            .order_by(ActivityEntry.timestamp.desc())
            .limit(limit_per_kind)
        )
        .scalars()
        .all()
    )
    hits.extend(
        SearchHit(
            kind="activity",
            id=row.id,
            title=row.action,
            subtitle=f"{row.actor} · {row.timestamp.isoformat()}",
            snippet=row.item[:140],
        )
        for row in entries
    )

    return SearchResponse(query=q, total=len(hits), hits=hits)
