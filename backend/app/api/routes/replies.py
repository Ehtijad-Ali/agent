"""Outbound reply endpoints (spec §17, §18).

This is the only code path in the project that says something to a real person
on a real platform, so it is deliberately narrow:

  - it refuses anything the safety check objects to, as a 422 listing every
    reason, never a warning the caller can ignore;
  - it requires status ``approved``, which only a human action sets;
  - it records the send in the ledger *before* reporting success, so the
    one-reply-per-person rule cannot be lost to a crash after posting.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routes.engine import get_active_config
from app.db.session import get_db
from app.models import ActivityEntry, Conversation, ReplySend
from app.schemas.conversation import ConversationOut
from app.schemas.reply import ReplyPreview, SendResult, UsageOut
from app.services.ingestion_service import build_connectors
from app.services.safety_service import check_reply, outgoing_text, usage
from app.services.tracking_service import apply_tracking, ensure_link

router = APIRouter(prefix="/replies", tags=["replies"])
logger = logging.getLogger("signal.replies")

# Until auth lands, sends are attributed to the single local operator.
ACTOR = "you"


def _get_or_404(db: Session, conversation_id: str) -> Conversation:
    row = db.get(Conversation, conversation_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No conversation with id {conversation_id}.",
        )
    return row


@router.get("/usage", response_model=UsageOut)
def get_usage(db: Session = Depends(get_db)) -> UsageOut:
    """Cap consumption, counted from real sends (spec §30)."""
    return UsageOut.model_validate(usage(db, get_active_config()))


@router.get("/{conversation_id}/preview", response_model=ReplyPreview)
def preview(conversation_id: str, db: Session = Depends(get_db)) -> ReplyPreview:
    """What would be sent, and why it would be refused.

    Lets the UI disable the send control and show the reasons before anyone
    clicks, rather than only after a failed attempt.
    """
    conversation = _get_or_404(db, conversation_id)
    problems = check_reply(db, conversation, get_active_config())

    # Minting the link here means the preview shows the real short URL rather
    # than a placeholder the operator never sees. The row is committed because
    # the same link must be reused by the send that follows.
    link = ensure_link(db, conversation)
    db.commit()

    return ReplyPreview(
        text=apply_tracking(outgoing_text(conversation), link),
        can_send=not problems,
        problems=problems,
    )


@router.post("/{conversation_id}/send", response_model=SendResult)
async def send(conversation_id: str, db: Session = Depends(get_db)) -> SendResult:
    conversation = _get_or_404(db, conversation_id)
    config = get_active_config()

    problems = check_reply(db, conversation, config)
    if problems:
        # 422, not 400: the request is well formed, the reply is not permitted.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Reply refused by the safety check: " + " ".join(problems),
        )

    connector = dict(build_connectors()).get(conversation.platform)
    if connector is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"{conversation.platform} is not connected, so nothing can be "
                "sent. Check the bot token in backend/.env."
            ),
        )

    # Both connectors encode external_id as "{destination}:{message_id}", so the
    # reply goes to the channel it came from and quotes the original.
    destination, _, source_message_id = conversation.external_id.partition(":")

    # Swap in the tracking link, then store exactly what was posted. The
    # mandatory wording is unaffected -- the safety check does not depend on
    # the URL -- but the ledger must record the real text, not the draft.
    link = ensure_link(db, conversation)
    text = apply_tracking(outgoing_text(conversation), link)

    try:
        external_message_id = await connector.send_message(
            destination, text, reply_to=source_message_id or None
        )
    except Exception as exc:  # noqa: BLE001 -- surface the platform's own reason
        logger.exception("Send failed for %s", conversation_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{conversation.platform} rejected the reply: {exc}",
        ) from exc

    # Recorded immediately. The message is already public; losing the ledger row
    # would let the same person be replied to twice.
    db.add(
        ReplySend(
            conversation_id=conversation.id,
            platform=conversation.platform,
            author_pseudonym=conversation.author_pseudonym,
            external_message_id=external_message_id,
            text=text,
            actor=ACTOR,
        )
    )

    conversation.status = "sent"
    conversation.history = [
        *(conversation.history or []),
        {
            "at": datetime.now(UTC).isoformat(),
            "actor": ACTOR,
            "action": "sent reply",
        },
    ]
    db.add(
        ActivityEntry(
            actor=ACTOR,
            action="sent reply",
            item=f"{conversation.community} / {conversation.author_pseudonym}",
            before="approved",
            after="sent",
        )
    )

    try:
        db.commit()
    except IntegrityError as exc:
        # The unique constraint fired between the check and the commit. The
        # message went out, so say so rather than pretending it did not.
        db.rollback()
        logger.error("Ledger conflict after sending %s", conversation_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The reply was posted, but a concurrent send already recorded "
                "one for this author. No further replies will be allowed."
            ),
        ) from exc

    db.refresh(conversation)
    from app.services import events_service

    events_service.emit(
        "reply.sent",
        {**events_service.lead_payload(conversation), "text": text,
         "externalMessageId": external_message_id},
    )
    return SendResult(
        external_message_id=external_message_id,
        text=text,
        conversation=ConversationOut.model_validate(conversation),
    )
