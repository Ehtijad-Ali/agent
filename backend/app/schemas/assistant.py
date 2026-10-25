"""Agent chat wire schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.base import CamelModel


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


class ToolInfo(CamelModel):
    name: str
    description: str
    requires_approval: bool
