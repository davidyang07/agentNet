from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, JsonValue

from app.events.version import SCHEMA_VERSION


class EventType(StrEnum):
    EXPERIMENT_STARTED = "EXPERIMENT_STARTED"
    EXPERIMENT_STOPPED = "EXPERIMENT_STOPPED"
    AGENT_CREATED = "AGENT_CREATED"
    AGENT_STARTED = "AGENT_STARTED"
    AGENT_STOPPED = "AGENT_STOPPED"
    MESSAGE_SENT = "MESSAGE_SENT"
    MESSAGE_RECEIVED = "MESSAGE_RECEIVED"
    MODEL_REQUESTED = "MODEL_REQUESTED"
    MODEL_RESPONDED = "MODEL_RESPONDED"
    TOOL_REQUESTED = "TOOL_REQUESTED"
    TOOL_EXECUTED = "TOOL_EXECUTED"
    TOOL_DENIED = "TOOL_DENIED"
    MEMORY_READ = "MEMORY_READ"
    MEMORY_WRITE = "MEMORY_WRITE"
    CREDENTIAL_ACCESSED = "CREDENTIAL_ACCESSED"
    CREDENTIAL_REVOKED = "CREDENTIAL_REVOKED"
    COMPROMISE_ATTEMPTED = "COMPROMISE_ATTEMPTED"
    COMPROMISE_SUCCEEDED = "COMPROMISE_SUCCEEDED"
    COMPROMISE_FAILED = "COMPROMISE_FAILED"
    ANOMALY_DETECTED = "ANOMALY_DETECTED"
    AGENT_QUARANTINED = "AGENT_QUARANTINED"
    AGENT_RELEASED = "AGENT_RELEASED"
    PERMISSION_CHANGED = "PERMISSION_CHANGED"
    INFERENCE_DISABLED = "INFERENCE_DISABLED"
    THREAT_SIGNATURE_PUBLISHED = "THREAT_SIGNATURE_PUBLISHED"
    THREAT_SIGNATURE_RECEIVED = "THREAT_SIGNATURE_RECEIVED"
    AGENT_RECOVERED = "AGENT_RECOVERED"


# M0 emits only this subset (SPEC §3.5).
M0_EVENT_TYPES = frozenset(
    {
        EventType.EXPERIMENT_STARTED,
        EventType.EXPERIMENT_STOPPED,
        EventType.AGENT_CREATED,
        EventType.COMPROMISE_ATTEMPTED,
        EventType.COMPROMISE_SUCCEEDED,
        EventType.COMPROMISE_FAILED,
    }
)


class EventDraft(BaseModel):
    """Engine output: no identity, no clock. This is what keeps step() pure."""

    sim_tick: int
    event_type: EventType
    agent_id: str | None = None
    source_agent_id: str | None = None
    target_agent_id: str | None = None
    risk_score: float | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class Event(EventDraft):
    """Emitted, ordered, streamable."""

    event_id: UUID
    seq: int
    schema_version: int = SCHEMA_VERSION
    experiment_id: UUID
    wall_time: datetime
