"""Agent chat endpoints.

Every lookup is scoped to the signed-in user: a chat, task or file that
belongs to someone else is a 404, not a 403, so ids cannot be probed.

Sending a message returns at once with a task id; the agent runs in the
background and the client polls the chat for progress.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.auth import current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models import (
    ActivityEntry,
    AssistantChat,
    AssistantFile,
    AssistantMessage,
    AssistantTask,
    User,
)
from app.schemas.assistant import (
    ChatCreate,
    ChatDetail,
    ChatOut,
    ChatUpdate,
    DecisionCreate,
    FileOut,
    MessageCreate,
    MessageOut,
    TaskOut,
    ToolInfo,
)
from app.services import agent_engine, llm
from app.services.agent_tools import available_tools

router = APIRouter(prefix="/assistant", tags=["assistant"])
logger = logging.getLogger("signal.assistant")

ACTIVE = ("pending", "running", "waiting_approval")


def _chat_or_404(db: Session, chat_id: str, user: User) -> AssistantChat:
    chat = db.get(AssistantChat, chat_id)
    if chat is None or chat.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such chat.")
    return chat


def _task_or_404(db: Session, task_id: str, user: User) -> AssistantTask:
    task = db.get(AssistantTask, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such task.")
    return task


def _task_out(task: AssistantTask) -> TaskOut:
    out = TaskOut.model_validate(task)
    if task.pending_action:
        # The queue of later calls is internal; the operator decides on one.
        out.pending_action = {
            "name": task.pending_action["name"],
            "arguments": task.pending_action["arguments"],
        }
    return out


@router.get("/status")
def assistant_status() -> dict:
    return {
        "configured": llm.is_configured(),
        "provider": llm.provider(),
        "model": llm.agent_model_name(),
        "tools": [
            ToolInfo(
                name=t.name, description=t.description, requires_approval=t.requires_approval
            ).model_dump(by_alias=True)
            for t in available_tools()
        ],
    }


@router.get("/chats", response_model=list[ChatOut])
def list_chats(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[ChatOut]:
    rows = db.execute(
        select(AssistantChat)
        .where(AssistantChat.user_id == user.id)
        .order_by(AssistantChat.updated_at.desc())
        .limit(200)
    ).scalars().all()
    return [ChatOut.model_validate(r) for r in rows]


@router.post("/chats", response_model=ChatOut, status_code=status.HTTP_201_CREATED)
def create_chat(
    body: ChatCreate, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> ChatOut:
    chat = AssistantChat(
        user_id=user.id, title=body.title.strip() or "New chat", instructions=body.instructions
    )
    db.add(chat)
    db.commit()
    return ChatOut.model_validate(chat)


@router.get("/chats/{chat_id}", response_model=ChatDetail)
def get_chat(
    chat_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> ChatDetail:
    chat = _chat_or_404(db, chat_id, user)
    messages = db.execute(
        select(AssistantMessage)
        .where(AssistantMessage.chat_id == chat.id)
        .order_by(AssistantMessage.seq)
    ).scalars().all()
    tasks = db.execute(
        select(AssistantTask)
        .where(AssistantTask.chat_id == chat.id)
        .order_by(AssistantTask.created_at)
    ).scalars().all()
    files = db.execute(
        select(AssistantFile)
        .where(AssistantFile.chat_id == chat.id)
        .order_by(AssistantFile.created_at)
    ).scalars().all()
    return ChatDetail(
        chat=ChatOut.model_validate(chat),
        messages=[MessageOut.model_validate(m) for m in messages],
        tasks=[_task_out(t) for t in tasks],
        files=[FileOut.model_validate(f) for f in files],
        configured=llm.is_configured(),
    )


@router.patch("/chats/{chat_id}", response_model=ChatOut)
def update_chat(
    chat_id: str,
    body: ChatUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ChatOut:
    chat = _chat_or_404(db, chat_id, user)
    if body.title is not None:
        chat.title = body.title.strip() or chat.title
    if body.instructions is not None:
        chat.instructions = body.instructions
    db.commit()
    return ChatOut.model_validate(chat)


@router.delete("/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(
    chat_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> None:
    chat = _chat_or_404(db, chat_id, user)
    for task in db.execute(
        select(AssistantTask).where(AssistantTask.chat_id == chat.id, AssistantTask.status.in_(ACTIVE))
    ).scalars():
        agent_engine.cancel(db, task)
    agent_engine.delete_chats(db, [chat.id])


@router.post("/chats/{chat_id}/clear", status_code=status.HTTP_204_NO_CONTENT)
def clear_chat(
    chat_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> None:
    """Forget the conversation's history but keep the chat and instructions."""
    chat = _chat_or_404(db, chat_id, user)
    if db.execute(
        select(AssistantTask.id).where(AssistantTask.chat_id == chat.id, AssistantTask.status.in_(ACTIVE))
    ).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Stop the running task first.")
    db.query(AssistantMessage).filter(AssistantMessage.chat_id == chat.id).delete()
    db.commit()


@router.post(
    "/chats/{chat_id}/messages", response_model=TaskOut, status_code=status.HTTP_202_ACCEPTED
)
async def send_message(
    chat_id: str,
    body: MessageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TaskOut:
    chat = _chat_or_404(db, chat_id, user)
    if not llm.is_configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, llm.not_configured_reason())
    if db.execute(
        select(AssistantTask.id).where(AssistantTask.chat_id == chat.id, AssistantTask.status.in_(ACTIVE))
    ).first():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This chat already has a task in progress. Wait for it, or stop it first.",
        )
    limit = get_settings().agent_daily_tasks_per_user
    if agent_engine.tasks_today(db, user.id) >= limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Daily limit of {limit} agent tasks reached. Try again tomorrow.",
        )

    task = AssistantTask(chat_id=chat.id, user_id=user.id, status="pending")
    db.add(task)
    db.commit()
    agent_engine.add_message(db, chat.id, task.id, "user", content=body.content.strip())
    if chat.title == "New chat":
        chat.title = body.content.strip().splitlines()[0][:60] or "New chat"
        db.commit()
    agent_engine.start(task.id)
    return _task_out(task)


@router.post("/tasks/{task_id}/cancel", response_model=TaskOut)
def cancel_task(
    task_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> TaskOut:
    task = _task_or_404(db, task_id, user)
    if task.status not in ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, f"The task is already {task.status}.")
    agent_engine.cancel(db, task)
    db.refresh(task)
    return _task_out(task)


@router.post("/tasks/{task_id}/decision", response_model=TaskOut)
async def decide(
    task_id: str,
    body: DecisionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TaskOut:
    """Approve or decline the action the agent is waiting on."""
    task = _task_or_404(db, task_id, user)
    if task.status != "waiting_approval" or not task.pending_action:
        raise HTTPException(status.HTTP_409_CONFLICT, "This task is not waiting for approval.")
    pending = task.pending_action
    db.add(
        ActivityEntry(
            actor=(user.name or user.email)[:64],
            action="approved agent action" if body.approve else "declined agent action",
            item=pending["name"],
            after=str(pending["arguments"])[:500],
        )
    )
    task.status = "running"
    db.commit()
    agent_engine.start(task.id, decision=body.approve)
    return _task_out(task)


@router.get("/files/{file_id}")
def download_file(
    file_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> Response:
    record = db.get(AssistantFile, file_id)
    if record is None or record.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such file.")
    return Response(
        content=record.content,
        media_type=record.media_type,
        headers={"Content-Disposition": f'attachment; filename="{record.filename}"'},
    )
