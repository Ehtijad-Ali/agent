"""Agent chat: conversations, their messages, the tasks that run them, and
files those tasks produce.

Messages are stored in the chat-completions shape (role, content, tool_calls,
tool_call_id, name) so a conversation can be replayed to the model exactly as
it happened, tool calls included. Every row carries the owning user, and every
route filters on it: one operator never sees another's conversations.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.types import UtcDateTime

TASK_STATES: tuple[str, ...] = (
    "pending",
    "running",
    "waiting_approval",
    "completed",
    "failed",
    "cancelled",
)


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class AssistantChat(Base):
    __tablename__ = "assistant_chats"
    __table_args__ = (Index("ix_assistant_chats_user", "user_id", "updated_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="New chat")
    # The operator's standing instructions for this conversation. Sent to the
    # model as user-level guidance, below the platform's own rules.
    instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=_now, onupdate=_now
    )


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"
    __table_args__ = (Index("ix_assistant_messages_chat", "chat_id", "seq"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    chat_id: Mapped[str] = mapped_column(String(36), nullable=False)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Monotonic order within a chat; timestamps can tie within one loop step.
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # "ok", "error", "rejected" or "cached" for tool results; shown in the UI.
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False, default=_now)


class AssistantTask(Base):
    """One run of the agent loop, started by one user message."""

    __tablename__ = "assistant_tasks"
    __table_args__ = (
        Index("ix_assistant_tasks_chat", "chat_id"),
        Index("ix_assistant_tasks_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    chat_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The tool call awaiting the operator's decision, while waiting_approval.
    pending_action: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Results of tool calls already made in this task, keyed by name+args, so
    # a repeated identical call is answered from here instead of re-run.
    call_cache: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    cancel_requested: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False, default=_now)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)


class AssistantFile(Base):
    """A file a task produced, e.g. a CSV report, for the owner to download."""

    __tablename__ = "assistant_files"
    __table_args__ = (Index("ix_assistant_files_chat", "chat_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    chat_id: Mapped[str] = mapped_column(String(36), nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    media_type: Mapped[str] = mapped_column(String(80), nullable=False, default="text/csv")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False, default=_now)
