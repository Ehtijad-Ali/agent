"""AI agents as first-class records (brief §3).

Until now the system had one hardcoded behaviour: poll every connected
platform, score with the single active config, draft with the single voice.
That is a bot, not a platform. The brief asks for "as many as I require,
operating under custom rules", which means an agent has to be a row the
operator creates, names, configures and switches off -- and that every action
taken can be attributed to.

``rules`` is JSON on purpose. Each agent *type* needs a different shape
(an engagement agent cares about platforms and score floors; a content agent
cares about cities and categories), and modelling every variant as columns
would mean a migration per agent type. The shape is validated by a Pydantic
model per type at the API boundary, so it is checked without being frozen into
the schema.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.types import UtcDateTime

# What an agent does. Kept deliberately small -- a type exists only when there
# is code that can execute it.
AGENT_TYPES: tuple[str, ...] = (
    # Monitors platforms, scores leads, drafts replies for human approval.
    "engagement",
    # Generates per-location classified-ad content for manual posting (§2).
    "content",
    # Checks the pages listed in a Google Sheet for a dofollow link to us.
    "backlink_audit",
)


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint("name", name="uq_agent_name"),
        Index("ix_agents_type", "agent_type"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    agent_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Off by default. An agent that starts running the moment it is created
    # would act before anyone had reviewed its rules.
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rules: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class AgentOutput(Base):
    """Something an agent produced (brief §2.9).

    For a content agent this is the generated ad plus, once a human has posted
    it, the live URL. ``published_url`` starts empty and is filled in by the
    operator -- the platform records what was generated and where it ended up,
    which is what the brief asks a Google Sheet to do.
    """

    __tablename__ = "agent_outputs"
    __table_args__ = (
        Index("ix_agent_outputs_agent", "agent_id"),
        Index("ix_agent_outputs_created", "created_at"),
        # One output per agent per location, which is what makes "a US city
        # different from any used before" enforceable rather than hopeful.
        UniqueConstraint("agent_id", "location_key", name="uq_agent_output_location"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # e.g. "US:TX:Austin" -- the uniqueness key for "not used before".
    location_key: Mapped[str] = mapped_column(String(120), nullable=False)

    city: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    state: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    zipcode: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    # Filled in by the human who posted it. Empty until then.
    published_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="generated")

    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    published_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
