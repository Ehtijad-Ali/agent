"""Conversation endpoints (spec §5, §18).

Filtering, sorting and pagination happen in SQL, not in the client. The
aggregates the Inbox header and Insights need are served by /api/insights/*
instead of being recomputed from a page of rows -- see
docs/frontend-api-mapping.md finding (b).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import ActivityEntry, Conversation
from app.schemas.conversation import (
    ACTION_TO_STATUS,
    TERMINAL_STATUSES,
    BulkActionRequest,
    BulkActionResponse,
    BulkActionResult,
    ConversationOut,
    ConversationPage,
    EditReplyRequest,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])

# Until auth lands, every write is attributed to the single local operator.
# The JWT subject replaces this; it is never accepted from the client body.
ACTOR = "you"

SortField = Literal["postedAt", "score", "status"]


def _apply_filters(
    stmt: Select,
    *,
    status_filter: list[str] | None,
    platform: list[str] | None,
    country: list[str] | None,
    intent: list[str] | None,
    min_score: int | None,
    max_score: int | None,
    search: str | None,
    has_risk: bool | None,
    posted_after: datetime | None,
    posted_before: datetime | None,
) -> Select:
    if status_filter:
        stmt = stmt.where(Conversation.status.in_(status_filter))
    if platform:
        stmt = stmt.where(Conversation.platform.in_(platform))
    if country:
        stmt = stmt.where(Conversation.country.in_(country))
    if intent:
        stmt = stmt.where(Conversation.intent.in_(intent))
    if min_score is not None:
        stmt = stmt.where(Conversation.score >= min_score)
    if max_score is not None:
        stmt = stmt.where(Conversation.score <= max_score)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            or_(
                Conversation.message.ilike(like),
                Conversation.community.ilike(like),
                Conversation.author_pseudonym.ilike(like),
            )
        )
    if has_risk is not None:
        # risk_flags is a JSON array. json_array_length is available on both
        # SQLite and Postgres, so this needs no dialect branch. (JSON.as_string
        # is not an option -- it only works on an index expression.)
        flagged = func.json_array_length(Conversation.risk_flags) > 0
        stmt = stmt.where(flagged if has_risk else ~flagged)
    if posted_after is not None:
        stmt = stmt.where(Conversation.posted_at >= posted_after)
    if posted_before is not None:
        stmt = stmt.where(Conversation.posted_at <= posted_before)
    return stmt


@router.get("", response_model=ConversationPage)
def list_conversations(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200, alias="perPage"),
    sort: SortField = "postedAt",
    direction: Literal["asc", "desc"] = "desc",
    status_filter: list[str] | None = Query(None, alias="status"),
    platform: list[str] | None = Query(None),
    country: list[str] | None = Query(None),
    intent: list[str] | None = Query(None),
    min_score: int | None = Query(None, alias="minScore"),
    max_score: int | None = Query(None, alias="maxScore"),
    search: str | None = Query(None),
    has_risk: bool | None = Query(None, alias="hasRisk"),
    posted_after: datetime | None = Query(None, alias="postedAfter"),
    posted_before: datetime | None = Query(None, alias="postedBefore"),
) -> ConversationPage:
    filters = {
        "status_filter": status_filter,
        "platform": platform,
        "country": country,
        "intent": intent,
        "min_score": min_score,
        "max_score": max_score,
        "search": search,
        "has_risk": has_risk,
        "posted_after": posted_after,
        "posted_before": posted_before,
    }

    count_stmt = _apply_filters(select(func.count(Conversation.id)), **filters)
    total = db.execute(count_stmt).scalar_one()

    column = {
        "postedAt": Conversation.posted_at,
        "score": Conversation.score,
        "status": Conversation.status,
    }[sort]
    order = column.desc() if direction == "desc" else column.asc()

    stmt = _apply_filters(select(Conversation), **filters)
    stmt = stmt.order_by(order, Conversation.id).limit(per_page).offset((page - 1) * per_page)
    rows = db.execute(stmt).scalars().all()

    return ConversationPage(
        items=[ConversationOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


def _get_or_404(db: Session, conversation_id: str) -> Conversation:
    row = db.get(Conversation, conversation_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No conversation with id {conversation_id}.",
        )
    return row


@router.get("/{conversation_id}", response_model=ConversationOut)
def get_conversation(
    conversation_id: str, db: Session = Depends(get_db)
) -> ConversationOut:
    return ConversationOut.model_validate(_get_or_404(db, conversation_id))


def _terminal_refusal(row: Conversation) -> str | None:
    """Why this row cannot change status, or None if it can."""
    if row.status in TERMINAL_STATUSES:
        return (
            f"This conversation is '{row.status}' and cannot be changed. The "
            "reply has already been posted and cannot be unposted."
        )
    return None


def _emit_status(row: Conversation, before: str) -> None:
    if row.status != before:
        from app.services import events_service

        events_service.emit(
            "lead.status_changed",
            {**events_service.lead_payload(row), "before": before, "after": row.status},
        )


def _record(db: Session, row: Conversation, action: str, before: str, after: str) -> None:
    """Append to the conversation's own history and the global audit log.

    Both, deliberately: the Inspector shows per-conversation history, the
    Activity screen shows everything, and neither can be derived from the other.
    """
    entry = {"at": datetime.now(UTC).isoformat(), "actor": ACTOR, "action": action}
    # JSON columns need a new list object to be seen as dirty.
    row.history = [*(row.history or []), entry]
    db.add(
        ActivityEntry(
            actor=ACTOR,
            action=action,
            item=f"{row.community} / {row.author_pseudonym}",
            before=before,
            after=after,
        )
    )


@router.post("/{conversation_id}/edit", response_model=ConversationOut)
def edit_reply(
    conversation_id: str,
    request: EditReplyRequest,
    db: Session = Depends(get_db),
) -> ConversationOut:
    row = _get_or_404(db, conversation_id)

    # Editing the draft of a reply that is already public would be misleading:
    # the stored text would no longer be what was posted.
    refusal = _terminal_refusal(row)
    if refusal:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=refusal)

    if request.selected_variant is not None:
        variants = row.reply_variants or []
        if not 0 <= request.selected_variant < len(variants):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"selectedVariant {request.selected_variant} is out of range; "
                    f"this conversation has {len(variants)} variant(s)."
                ),
            )
        row.selected_variant = request.selected_variant

    if request.edited_reply is not None:
        row.edited_reply = request.edited_reply or None

    _record(db, row, "edited reply", "", "")
    db.commit()
    db.refresh(row)
    return ConversationOut.model_validate(row)


@router.post("/{conversation_id}/ai-draft", response_model=ConversationOut)
async def ai_redraft(
    conversation_id: str,
    db: Session = Depends(get_db),
) -> ConversationOut:
    """Rewrite the summary and reply drafts with the local AI model.

    Replaces the drafts and clears any manual edit, so it is refused once a
    reply has been sent, and for risk-flagged rows, which never get a draft.
    """
    from app.api.routes.engine import get_active_config
    from app.services import ai_service
    from app.services.reply_service import detect_language

    row = _get_or_404(db, conversation_id)
    refusal = _terminal_refusal(row)
    if refusal:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=refusal)
    if row.risk_flags:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This conversation carries risk flags, so no reply may be drafted.",
        )
    if not ai_service.enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI drafting is off: set OLLAMA_MODEL on the server.",
        )

    draft = await ai_service.draft(
        row.message, row.community, get_active_config().voice, detect_language(row.message)
    )
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI model did not answer. Check that Ollama is running, then try again.",
        )

    row.reply_variants = draft.variants
    row.selected_variant = 0
    row.edited_reply = None
    row.language = draft.language
    if draft.summary:
        row.summary = draft.summary
    _record(db, row, "AI redrafted replies", "", "")
    db.commit()
    db.refresh(row)
    return ConversationOut.model_validate(row)


@router.post("/bulk", response_model=BulkActionResponse)
def bulk_action(
    request: BulkActionRequest, db: Session = Depends(get_db)
) -> BulkActionResponse:
    """Per-id results so a partial failure is visible instead of swallowed."""
    new_status = ACTION_TO_STATUS.get(request.action)
    if new_status is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unknown action '{request.action}'. Valid actions: "
                f"{', '.join(sorted(ACTION_TO_STATUS))}."
            ),
        )

    results: list[BulkActionResult] = []
    changed: list[tuple[Conversation, str]] = []
    updated = 0
    for conversation_id in request.ids:
        row = db.get(Conversation, conversation_id)
        if row is None:
            results.append(
                BulkActionResult(id=conversation_id, ok=False, error="not found")
            )
            continue
        refusal = _terminal_refusal(row)
        if refusal:
            results.append(
                BulkActionResult(id=conversation_id, ok=False, error=refusal)
            )
            continue
        before = row.status
        row.status = new_status
        _record(db, row, request.action.replace("-", " "), before, new_status)
        results.append(BulkActionResult(id=conversation_id, ok=True))
        updated += 1
        changed.append((row, before))

    db.commit()
    for row, before in changed:
        _emit_status(row, before)
    return BulkActionResponse(results=results, updated=updated)


# Declared last on purpose. FastAPI resolves routes in declaration order, so a
# two-segment catch-all placed above /{id}/edit would swallow it and reject
# "edit" as an unknown action.
@router.post("/{conversation_id}/{action}", response_model=ConversationOut)
def act_on_conversation(
    conversation_id: str,
    action: str,
    db: Session = Depends(get_db),
) -> ConversationOut:
    """The five §18 verbs: approve, reject, snooze, mark-posted, block."""
    new_status = ACTION_TO_STATUS.get(action)
    if new_status is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unknown action '{action}'. Valid actions: "
                f"{', '.join(sorted(ACTION_TO_STATUS))}."
            ),
        )

    row = _get_or_404(db, conversation_id)

    refusal = _terminal_refusal(row)
    if refusal:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=refusal)

    before = row.status
    row.status = new_status
    _record(db, row, action.replace("-", " "), before, new_status)
    db.commit()
    db.refresh(row)
    _emit_status(row, before)
    return ConversationOut.model_validate(row)
