"""The AI Agent: chats, their messages, the tasks that run them, and files.

A *task* is one run of the agent loop, started by one user message. It is
stored rather than held in memory so the screen can poll its progress, and so
a run that is waiting for the operator's approval survives a page reload.

Messages use the OpenAI/Ollama chat shape (role, content, tool_calls,
tool_call_id) so the history can be replayed to the model as-is.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.types import UtcDateTime

TASK_STATUSES: tuple[str, ...] = (
    "pending",
    "running",
    "waiting_approval",
    "completed",
    "failed",
    "cancelled",
)
ACTIVE_TASK_STATUSES = frozenset({"pending", "running", "waiting_approval"})


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class AssistantChat(Base):
    __tablename__ = "assistant_chats"
    __table_args__ = (Index("ix_assistant_chats_user", "user_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # Chats are private to the user who started them.
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="New chat")
    instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=_now, onupdate=_now
    )


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"
    __table_args__ = (Index("ix_assistant_messages_chat_seq", "chat_id", "seq"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    chat_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assistant_chats.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Tool name, on role="tool" messages.
    name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # ok | cached | error | declined on tool messages; failed | cancelled on a
    # closing assistant message.
    status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False, default=_now)


class AssistantTask(Base):
    __tablename__ = "assistant_tasks"
    __table_args__ = (Index("ix_assistant_tasks_chat", "chat_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    chat_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assistant_chats.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # {"name", "arguments", "toolCallId"} while status == waiting_approval.
    pending_action: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False, default=_now)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)


class AssistantFile(Base):
    """A CSV the agent produced for download."""

    __tablename__ = "assistant_files"
    __table_args__ = (Index("ix_assistant_files_chat", "chat_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    chat_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assistant_chats.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False, default=_now)
