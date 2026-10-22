"""SQLAlchemy models. Imported for its side effect of registering mappers."""

from app.models.activity import NO_ITEM, ActivityEntry
from app.models.agent import AGENT_TYPES, Agent, AgentOutput
from app.models.assistant import (
    ACTIVE_TASK_STATUSES,
    AssistantChat,
    AssistantFile,
    AssistantMessage,
    AssistantTask,
)
from app.models.backlink import BACKLINK_RESULTS, BacklinkAudit, BacklinkCheck
from app.models.config_version import ConfigurationVersion
from app.models.conversation import Conversation
from app.models.reply import ReplySend
from app.models.preset import TuningPreset
from app.models.scan import ScanRun
from app.models.source import PlatformSource
from app.models.tracking import LinkClick, TrackingLink
from app.models.user import ROLES, User

__all__ = [
    "NO_ITEM",
    "AGENT_TYPES",
    "ACTIVE_TASK_STATUSES",
    "BACKLINK_RESULTS",
    "ActivityEntry",
    "Agent",
    "AgentOutput",
    "AssistantChat",
    "AssistantFile",
    "AssistantMessage",
    "AssistantTask",
    "BacklinkAudit",
    "BacklinkCheck",
    "PlatformSource",
    "ConfigurationVersion",
    "Conversation",
    "ReplySend",
    "LinkClick",
    "ScanRun",
    "TrackingLink",
    "TuningPreset",
    "ROLES",
    "User",
]
