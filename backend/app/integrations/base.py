"""Platform connector interface (spec §7).

Every platform produces the same NormalisedMessage, so the scoring, safety and
reply pipeline never knows which platform a message came from. Adding Reddit
later means implementing this class, not touching the core.

Deliberately absent: anything that reads private groups, harvests credentials,
or posts without human approval. ``send_message`` exists but is only ever
reached after a human approves and the reply safety check passes (spec §17-18).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Platform = Literal["discord", "telegram", "facebook", "reddit"]
ConnectionState = Literal["connected", "not_connected", "error", "not_implemented"]


@dataclass(slots=True)
class NormalisedMessage:
    """The one shape every platform converges on (spec §10).

    ``author_pseudonym`` is already hashed by the connector -- the real handle
    must not survive past this boundary.
    """

    platform: Platform
    external_id: str
    community: str
    author_pseudonym: str
    message: str
    posted_at: datetime
    country: str | None = None
    language: str | None = None
    source_url: str | None = None


@dataclass(slots=True)
class ConnectionStatus:
    """What the frontend is allowed to see about a platform (spec §29).

    Note there is no token field, and there must never be one.
    """

    platform: Platform
    status: ConnectionState
    last_checked: datetime | None = None
    error: str | None = None
    detail: str | None = None


class PlatformConnector(abc.ABC):
    """Base for every platform integration."""

    platform: Platform

    @abc.abstractmethod
    async def health_check(self) -> ConnectionStatus:
        """Verify credentials without sending anything."""

    @abc.abstractmethod
    async def fetch_messages(self, limit: int = 100) -> list[NormalisedMessage]:
        """Pull recent messages from the sources this connector can see.

        Implementations must return only public content the bot is authorised
        to read, and must not attempt to widen that access.
        """

    @abc.abstractmethod
    async def send_message(self, chat_id: str, text: str, reply_to: str | None = None) -> str:
        """Post an already-approved reply. Returns the platform message id.

        Callers are responsible for having run the §17 safety check first;
        connectors do not post autonomously and are never called from the
        ingestion path.
        """


class NotImplementedConnector(PlatformConnector):
    """Placeholder for platforms with no viable official access path.

    Spec §46 forbids claiming a platform is production-connected when it is
    not, so these report their real state instead of silently returning
    nothing and looking healthy.
    """

    def __init__(self, platform: Platform, reason: str) -> None:
        self.platform = platform
        self._reason = reason

    async def health_check(self) -> ConnectionStatus:
        return ConnectionStatus(
            platform=self.platform, status="not_implemented", detail=self._reason
        )

    async def fetch_messages(self, limit: int = 100) -> list[NormalisedMessage]:
        return []

    async def send_message(self, chat_id: str, text: str, reply_to: str | None = None) -> str:
        raise NotImplementedError(f"{self.platform}: {self._reason}")


# Why the two unbuilt platforms are unbuilt, surfaced through /api/health/platforms
# rather than left as a silent gap.
FACEBOOK_REASON = (
    "No official commercial access to public group content. The Groups API was "
    "restricted in 2020 and CrowdTangle shut down in August 2024; its replacement, "
    "the Meta Content Library, is limited to academic and non-profit applicants "
    "and explicitly excludes for-profit organisations. Pages you own can be posted "
    "to, but discovery is not available."
)
REDDIT_REASON = (
    "Not built yet. Unlike Discord and Telegram, Reddit does offer real keyword "
    "search across public subreddits, so it is the best discovery fit. Requires a "
    "commercial data agreement and compliance with subreddit self-promotion rules."
)
