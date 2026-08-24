from dataclasses import dataclass
from enum import StrEnum


class SecurityState(StrEnum):
    HEALTHY = "healthy"
    SUSPICIOUS = "suspicious"
    COMPROMISED = "compromised"
    QUARANTINED = "quarantined"
    RECOVERED = "recovered"


@dataclass
class AgentNode:
    id: str
    software_type: str
    security_state: SecurityState
    neighbors: tuple[str, ...]
    compromised_by: str | None = None
    tick_compromised: int | None = None


@dataclass
class WorldState:
    tick: int
    nodes: dict[str, AgentNode]
    edges: tuple[tuple[str, str], ...]
