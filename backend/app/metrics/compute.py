"""Pure metric functions (docs/PLAN.md §6). Split into two families:

State/graph metrics need only the current WorldState + SecurityGraph --
computable on demand exactly like the analysis endpoints, no event log
required (compromise_fraction, blast_radius_fraction, retained_utility,
privileged_exposure, security_plane_integrity).

Event-log metrics (attack_success_rate, false_quarantine_rate) count
occurrences across a run's events and need the event sequence -- for a
live experiment that's `runner.bus.since(-1)` (bounded by EventBus.
RING_SIZE, the same bound every other live-runner consumer already lives
with); a persisted run's full log works identically once a history
equivalent is wired in (docs/PLAN.md §9, not yet built this session).

Detection/containment latency (docs/PLAN.md §6) need per-event tick
correlation beyond what this pass implements and are deliberately left out
-- see docs/PLAN.md §9 remaining work rather than approximating them.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.engine.state import SecurityState, WorldState
from app.graph.analysis import blast_radius
from app.graph.security_graph import SecurityGraph
from app.graph.types import NodeType
from app.schemas.events import Event


def compromise_fraction(state: WorldState) -> float:
    if not state.nodes:
        return 0.0
    compromised = sum(
        1 for node in state.nodes.values() if node.security_state == SecurityState.COMPROMISED
    )
    return compromised / len(state.nodes)


def retained_utility(state: WorldState) -> float:
    """Fraction of agents neither COMPROMISED nor QUARANTINED."""
    if not state.nodes:
        return 0.0
    unaffected = sum(
        1
        for node in state.nodes.values()
        if node.security_state not in (SecurityState.COMPROMISED, SecurityState.QUARANTINED)
    )
    return unaffected / len(state.nodes)


def blast_radius_fraction(graph: SecurityGraph) -> float:
    """Fraction of AGENT nodes reachable from a currently compromised agent
    -- restricted to agents (not tools/credentials/resources also in the
    reachable set) since this tracks the standard "how much of the
    population is at risk" reading; see privileged_exposure for the
    credential/resource-focused count over the same reachable set."""
    agent_ids = {n.id for n in graph.nodes_of_type(NodeType.AGENT)}
    if not agent_ids:
        return 0.0
    reachable = blast_radius(graph)
    return len(reachable & agent_ids) / len(agent_ids)


def privileged_exposure(graph: SecurityGraph) -> int:
    """Count of CREDENTIAL/RESOURCE nodes reachable from a currently
    compromised agent -- how much of the privileged surface a compromise
    has put at risk, not merely how many agents it touched."""
    reachable = blast_radius(graph)
    return sum(
        1
        for node in graph.nodes
        if node.id in reachable and node.node_type in (NodeType.CREDENTIAL, NodeType.RESOURCE)
    )


def security_plane_integrity(graph: SecurityGraph) -> float:
    """Fraction of SENTINEL/SECURITY_CONTROL nodes still HEALTHY. Always 1.0
    (or undefined, reported as 1.0) today since no scenario yet compromises
    these nodes (docs/PLAN.md §5 remaining work) -- a true reflection of
    current reality, not a placeholder."""
    plane_nodes = graph.nodes_of_type(NodeType.SENTINEL) + graph.nodes_of_type(
        NodeType.SECURITY_CONTROL
    )
    if not plane_nodes:
        return 1.0
    healthy = sum(1 for node in plane_nodes if node.security_state == SecurityState.HEALTHY)
    return healthy / len(plane_nodes)


def attack_success_rate(events: Sequence[Event]) -> float:
    succeeded = sum(1 for e in events if e.event_type.value == "COMPROMISE_SUCCEEDED")
    failed = sum(1 for e in events if e.event_type.value == "COMPROMISE_FAILED")
    total = succeeded + failed
    return (succeeded / total) if total else 0.0


def false_quarantine_rate(events: Sequence[Event]) -> float:
    quarantined = [e for e in events if e.event_type.value == "AGENT_QUARANTINED"]
    if not quarantined:
        return 0.0
    false_ones = sum(1 for e in quarantined if e.metadata.get("legitimate") is False)
    return false_ones / len(quarantined)
