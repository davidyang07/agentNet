from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


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
    # Phase 2: "real" nodes are LLM-backed via the
    # Model Gateway; "simulated" (the default) keeps the pre-Phase-2
    # probabilistic behavior byte-for-byte unchanged. confidential_token is
    # the synthetic secret a real agent must never leak (§6) -- engine-
    # internal only, never added to NodeView or any other outbound schema.
    agent_kind: Literal["simulated", "real"] = "simulated"
    confidential_token: str | None = None
    # docs/PLAN.md §14.4 C.2: an agent that can't run inference is a dead end
    # -- it can be compromised, but never attacks anyone.
    inference_capable: bool = True
    # docs/PLAN.md §14.4 C.3: the worm strain this agent carries, a
    # signature_bits-bit vector; None unless strains are tracked.
    strain: int | None = None
    # docs/PLAN.md §14.4 C.4: whether this agent takes part in shared
    # immune memory, holding every adopted signature.
    immune_participant: bool = False
    # docs/PLAN.md §14.4 C.5, graduated response: the tick a first detection
    # made this agent SUSPICIOUS; None otherwise.
    suspicious_since: int | None = None


def is_infected(node: AgentNode) -> bool:
    """COMPROMISED, or SUSPICIOUS while infected (graduated response, §14.4
    C.5): an advisory flag doesn't cure anything."""
    return node.security_state == SecurityState.COMPROMISED or (
        node.security_state == SecurityState.SUSPICIOUS and node.tick_compromised is not None
    )


def is_susceptible(node: AgentNode) -> bool:
    """HEALTHY, or SUSPICIOUS without an infection (a detector false
    positive, §14.4 C.5)."""
    return node.security_state == SecurityState.HEALTHY or (
        node.security_state == SecurityState.SUSPICIOUS and node.tick_compromised is None
    )


@dataclass(frozen=True)
class Signature:
    """One entry of shared immune memory (docs/PLAN.md §14.4 C.4): a strain
    vector, legitimate (published on a detection) or poisoned (published by
    a subverted sentinel). Participants hold it from adopt_tick on;
    `announced` records that its adoption event has been emitted."""

    vector: int
    legitimate: bool
    adopt_tick: int
    announced: bool = False


@dataclass
class WorldState:
    tick: int
    nodes: dict[str, AgentNode]
    edges: tuple[tuple[str, str], ...]
    # Byzantine/security-plane attacks (docs/PLAN.md §5): ids of non-agent
    # security-graph nodes (SENTINEL, SECURITY_CONTROL, CREDENTIAL, ...)
    # currently compromised. Agent compromise stays tracked on AgentNode
    # itself (unchanged); this set exists because those node kinds have no
    # WorldState-resident dataclass of their own -- app/graph/builder.py
    # reads it to set a GraphNode's security_state, exactly mirroring how it
    # already reads AgentNode.security_state for AGENT nodes. Defaults to
    # empty, so every existing WorldState() call site is unaffected.
    compromised_graph_nodes: frozenset[str] = frozenset()
    # Shared immune memory (docs/PLAN.md §14.4 C.4), and the benign probes
    # participants have screened against it so far (autoimmunity). Empty
    # and zero unless immunity is enabled.
    signatures: tuple[Signature, ...] = ()
    benign_probes: int = 0
    benign_blocked: int = 0
