"""Agent wire schemas (brief §2, §3)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.base import CamelModel

AgentType = Literal["engagement", "content", "backlink_audit"]
AdCategory = Literal["community", "events", "services"]


class EngagementRules(CamelModel):
    """Rules for an agent that monitors and drafts replies.

    ``min_score`` is the agent's own floor, applied on top of the global
    thresholds -- so one agent can chase only high-intent leads while another
    sweeps everything, without either changing the shared scoring config.
    """

    platforms: list[str] = Field(default_factory=lambda: ["discord", "telegram"])
    min_score: int = Field(default=0, ge=0, le=100)
    skip_risk_flagged: bool = True


class ContentRules(CamelModel):
    """Rules for an agent that generates per-city ad copy."""

    contact_email: str = ""
    categories: list[AdCategory] = Field(
        default_factory=lambda: ["community", "events", "services"]
    )


def _default_domain() -> str:
    from urllib.parse import urlparse

    from app.core.config import get_settings

    host = urlparse(get_settings().product_url).hostname or "all-bettors.com"
    return host.removeprefix("www.")


class BacklinkRules(CamelModel):
    """Rules for an agent that audits backlinks listed in a Google Sheet."""

    sheet_url: str = ""
    url_column: str = Field(default="A", min_length=1, max_length=3)
    target_domain: str = Field(default_factory=_default_domain)
    max_urls: int = Field(default=10000, ge=1, le=10000)


class AgentCreate(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    agent_type: AgentType
    description: str = ""
    enabled: bool = False
    rules: dict = Field(default_factory=dict)


class AgentUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    enabled: bool | None = None
    rules: dict | None = None


class AgentOut(CamelModel):
    id: str
    name: str
    agent_type: AgentType
    description: str
    enabled: bool
    rules: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class AgentOutputOut(CamelModel):
    id: str
    agent_id: str
    location_key: str
    city: str
    state: str
    zipcode: str
    category: str
    title: str
    body: str
    contact_email: str
    published_url: str | None = None
    status: str
    created_at: datetime
    published_at: datetime | None = None


class AgentOutputPage(CamelModel):
    items: list[AgentOutputOut] = Field(default_factory=list)
    total: int
    page: int
    per_page: int


class PublishRequest(CamelModel):
    """Where the operator actually posted the generated ad."""

    published_url: str = Field(min_length=1)


class RefinementIndex(CamelModel):
    """Agent Refinement Index (brief §8).

    A single 0-100 score per agent, plus the components it is built from, so it
    can be acted on rather than just looked at. Components are only included
    once there is enough data to mean anything -- an agent with two replies
    does not get a confident grade.
    """

    agent_id: str | None = None
    agent_name: str | None = None
    sample_size: int
    confident: bool
    score: float
    approval_rate: float
    click_through_rate: float
    precision: float
    notes: list[str] = Field(default_factory=list)


class BacklinkCheckOut(CamelModel):
    row: int
    page_url: str
    result: str
    rel: str
    link_href: str
    anchor_text: str
    http_status: int | None = None
    detail: str
    checked_at: datetime


class BacklinkAuditOut(CamelModel):
    """Where the last audit stands and what it found."""

    status: str
    total: int = 0
    done: int = 0
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    items: list[BacklinkCheckOut] = Field(default_factory=list)
