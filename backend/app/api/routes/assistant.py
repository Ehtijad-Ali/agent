"""AI Agent endpoints (the "AI Agent" screen).

Chats belong to the user who created them; every lookup is scoped to the
signed-in user, so one operator cannot read or drive another's chats by id.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.routes.auth import current_user
from app.db.session import get_db
from app.models import (
    ACTIVE_TASK_STATUSES,
    AssistantChat,
    AssistantFile,
    AssistantMessage,
    AssistantTask,
    User,
)
from app.schemas.base import CamelModel
from app.services.assistant import llm, runner, tools

router = APIRouter(prefix="/assistant", tags=["assistant"])


class ChatCreate(CamelModel):
    title: str = Field(default="New chat", max_length=200)
    instructions: str = Field(default="", max_length=8000)


class ChatUpdate(CamelModel):
    title: str | None = Field(default=None, max_length=200)
    instructions: str | None = Field(default=None, max_length=8000)


class MessageCreate(CamelModel):
    content: str = Field(min_length=1, max_length=20000)


class DecisionCreate(CamelModel):
    approve: bool


class ChatOut(CamelModel):
    id: str
    title: str
    instructions: str
    created_at: datetime
    updated_at: datetime


class MessageOut(CamelModel):
    id: str
    seq: int
    role: str
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None
    status: str | None = None
    task_id: str | None = None
    created_at: datetime


class TaskOut(CamelModel):
    id: str
    status: str
    iterations: int
    tool_calls: int
    tokens_used: int
    error: str | None = None
    pending_action: dict[str, Any] | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class FileOut(CamelModel):
    id: str
    task_id: str
    filename: str
    rows: int
    created_at: datetime


class ChatDetail(CamelModel):
    chat: ChatOut
    messages: list[MessageOut]
    tasks: list[TaskOut]
    files: list[FileOut]
    configured: bool


def _task_out(task: AssistantTask) -> TaskOut:
    out = TaskOut.model_validate(task)
    if out.pending_action:
        # "remaining" is the runner's bookkeeping, not something to show.
        out.pending_action = {k: v for k, v in out.pending_action.items() if k != "remaining"}
    return out


def _chat_or_404(db: Session, chat_id: str, user: User) -> AssistantChat:
    chat = db.get(AssistantChat, chat_id)
    if chat is None or chat.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No chat with id {chat_id}.")
    return chat


def _task_or_404(db: Session, task_id: str, user: User) -> AssistantTask:
    task = db.get(AssistantTask, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No task with id {task_id}.")
    _chat_or_404(db, task.chat_id, user)
    return task


def _active_task(db: Session, chat_id: str) -> AssistantTask | None:
    return db.execute(
        select(AssistantTask)
        .where(AssistantTask.chat_id == chat_id, AssistantTask.status.in_(ACTIVE_TASK_STATUSES))
        .limit(1)
    ).scalar_one_or_none()


@router.get("/status")
def assistant_status() -> dict:
    configured, provider, model = llm.provider()
    return {"configured": configured, "provider": provider, "model": model, "tools": tools.describe()}


@router.get("/chats", response_model=list[ChatOut])
def list_chats(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[ChatOut]:
    rows = db.execute(
        select(AssistantChat)
        .where(AssistantChat.user_id == user.id)
        .order_by(AssistantChat.updated_at.desc())
    ).scalars()
    return [ChatOut.model_validate(c) for c in rows]


@router.post("/chats", response_model=ChatOut)
def create_chat(
    request: ChatCreate, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> ChatOut:
    chat = AssistantChat(
        user_id=user.id, title=request.title.strip() or "New chat", instructions=request.instructions
    )
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return ChatOut.model_validate(chat)


@router.get("/chats/{chat_id}", response_model=ChatDetail)
def get_chat(chat_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> ChatDetail:
    chat = _chat_or_404(db, chat_id, user)
    messages = db.execute(
        select(AssistantMessage).where(AssistantMessage.chat_id == chat_id).order_by(AssistantMessage.seq)
    ).scalars()
    tasks = db.execute(
        select(AssistantTask).where(AssistantTask.chat_id == chat_id).order_by(AssistantTask.created_at)
    ).scalars()
    files = db.execute(
        select(AssistantFile).where(AssistantFile.chat_id == chat_id).order_by(AssistantFile.created_at)
    ).scalars()
    return ChatDetail(
        chat=ChatOut.model_validate(chat),
        messages=[MessageOut.model_validate(m) for m in messages],
        tasks=[_task_out(t) for t in tasks],
        files=[FileOut.model_validate(f) for f in files],
        configured=llm.provider()[0],
    )


@router.patch("/chats/{chat_id}", response_model=ChatOut)
def update_chat(
    chat_id: str, request: ChatUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> ChatOut:
    chat = _chat_or_404(db, chat_id, user)
    if request.title is not None:
        chat.title = request.title.strip() or chat.title
    if request.instructions is not None:
        chat.instructions = request.instructions
    db.commit()
    db.refresh(chat)
    return ChatOut.model_validate(chat)


@router.delete("/chats/{chat_id}")
def delete_chat(chat_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    chat = _chat_or_404(db, chat_id, user)
    active = _active_task(db, chat_id)
    if active is not None:
        runner.cancel(active.id)
    for model in (AssistantMessage, AssistantTask, AssistantFile):
        db.execute(delete(model).where(model.chat_id == chat_id))
    db.delete(chat)
    db.commit()
    return {"ok": True}


@router.post("/chats/{chat_id}/clear")
def clear_chat(chat_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """Forget the conversation's history but keep the chat and instructions."""
    _chat_or_404(db, chat_id, user)
    if _active_task(db, chat_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Stop the running task before clearing the chat.")
    db.execute(delete(AssistantMessage).where(AssistantMessage.chat_id == chat_id))
    db.commit()
    return {"ok": True}


@router.post("/chats/{chat_id}/messages")
def send_message(
    chat_id: str, request: MessageCreate, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> TaskOut:
    chat = _chat_or_404(db, chat_id, user)
    if not llm.provider()[0]:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "The agent is not configured: set OLLAMA_MODEL on the server."
        )
    if _active_task(db, chat_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "The agent is still working on the last message.")

    content = request.content.strip()
    task = AssistantTask(chat_id=chat_id, status="pending")
    db.add(task)
    db.flush()
    if chat.title == "New chat":
        chat.title = (content.splitlines()[0][:60]).strip() or "New chat"
    db.commit()
    db.refresh(task)

    runner.add_message(chat_id, task.id, "user", content)
    runner.start(task.id, user.name or user.email)
    db.refresh(task)
    return _task_out(task)


@router.post("/tasks/{task_id}/cancel", response_model=TaskOut)
def cancel_task(task_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> TaskOut:
    task = _task_or_404(db, task_id, user)
    if task.status in ACTIVE_TASK_STATUSES:
        runner.cancel(task.id)
    db.refresh(task)
    return _task_out(task)


@router.post("/tasks/{task_id}/decision", response_model=TaskOut)
def decide(
    task_id: str, request: DecisionCreate, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> TaskOut:
    """Approve or decline the action the agent is waiting on."""
    task = _task_or_404(db, task_id, user)
    if task.status != "waiting_approval" or not task.pending_action:
        raise HTTPException(status.HTTP_409_CONFLICT, "This task is not waiting for a decision.")
    runner.decide(task.id, user.name or user.email, request.approve)
    db.refresh(task)
    return _task_out(task)


@router.get("/files/{file_id}")
def download_file(file_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> Response:
    record = db.get(AssistantFile, file_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No file with id {file_id}.")
    _chat_or_404(db, record.chat_id, user)
    return Response(
        content=record.content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{record.filename}"'},
    )
