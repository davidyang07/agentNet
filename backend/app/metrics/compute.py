"""Pure metric functions (docs/PLAN.md §6). Split into two families:

State/graph metrics need only the current WorldState + SecurityGraph --
computable on demand exactly like the analysis endpoints, no event log
required (compromise_fraction, blast_radius_fraction, retained_utility,
privileged_exposure, security_plane_integrity).

Event-log metrics (attack_success_rate, false_quarantine_rate,
gateway_failure_count) count occurrences across a run's whole event log.
attack_success_rate is new compromises -- COMPROMISE_SUCCEEDED that won a
target, excluding the seeded compromise and a second same-tick success on an
already-won target -- per COMPROMISE_ATTEMPTED. A model-gateway failure emits
no COMPROMISE_ATTEMPTED (the attempt never reached the model), so it is
counted in gateway_failure_count rather than as a defended attack. Both families of event-log
metric are computed by folding events into an EventLogTally, whose memory is
O(agents) rather than O(events): a live runner folds each batch as it
publishes (ExperimentRunner.event_tally), so its metrics cover the whole run
-- not just the EventBus ring, which stops holding a long run's start --
while replay folds its full reconstructed log through the same arithmetic.

Detection/containment latency (docs/PLAN.md §6) are event-log metrics too:
the number of ticks between a node's tick_compromised and its first
ANOMALY_DETECTED (detection latency), and between that detection and the
node's first (legitimate) AGENT_QUARANTINED (containment latency). Both
return None rather than 0.0 when no node has completed the measured
transition -- unlike the fraction/rate metrics above, 0.0 would misreport
"instant" as "no data," and every caller already must handle an optional
value from an on-demand, possibly-empty event window.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace

from app.engine.state import SecurityState, WorldState
from app.graph.analysis import blast_radius
from app.graph.security_graph import SecurityGraph
from app.graph.types import NodeType
from app.metrics import epidemic
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


@dataclass
class EventLogTally:
    """Running fold of everything the event-log metrics read from a run's
    events. Feeding it a log in any batching gives the same result as
    feeding it the whole log at once."""

    attempted: int = 0
    new_compromises: int = 0
    gateway_failures: int = 0
    quarantined: int = 0
    false_quarantined: int = 0
    # First ANOMALY_DETECTED tick, and first legitimate AGENT_QUARANTINED
    # tick, per agent -- insertion order is first-occurrence order.
    first_detected: dict[str, int] = field(default_factory=dict)
    first_quarantined: dict[str, int] = field(default_factory=dict)
    # Prevalence (PLAN 14.4 C.1): the agents infectious and quarantined right
    # now, and one closed (tick, infectious, quarantined) row per earlier
    # tick -- O(agents + ticks), never O(events). Event ticks never decrease,
    # so a tick's row is final once an event from a later tick arrives.
    infectious_ids: set[str] = field(default_factory=set)
    quarantined_ids: set[str] = field(default_factory=set)
    prevalence_rows: list[tuple[int, int, int]] = field(default_factory=list)
    open_tick: int | None = None

    def snapshot(self) -> EventLogTally:
        """An independent copy, safe to read off the event loop while the
        live runner keeps folding new events into this one."""
        return replace(
            self,
            first_detected=dict(self.first_detected),
            first_quarantined=dict(self.first_quarantined),
            infectious_ids=set(self.infectious_ids),
            quarantined_ids=set(self.quarantined_ids),
            prevalence_rows=list(self.prevalence_rows),
        )

    @classmethod
    def of(cls, events: Iterable[Event]) -> EventLogTally:
        tally = cls()
        tally.add(events)
        return tally

    def add(self, events: Iterable[Event]) -> None:
        for e in events:
            self._advance_to(e.sim_tick)
            etype = e.event_type.value
            if etype == "COMPROMISE_ATTEMPTED":
                self.attempted += 1
            elif etype == "COMPROMISE_SUCCEEDED":
                if not e.metadata.get("already_compromised"):
                    if not e.metadata.get("initial_compromise"):
                        self.new_compromises += 1
                    if e.target_agent_id is not None:
                        self.infectious_ids.add(e.target_agent_id)
            elif etype == "COMPROMISE_FAILED":
                if e.metadata.get("gateway_error"):
                    self.gateway_failures += 1
            elif etype == "ANOMALY_DETECTED":
                if e.agent_id is not None:
                    self.first_detected.setdefault(e.agent_id, e.sim_tick)
            elif etype == "AGENT_QUARANTINED":
                self.quarantined += 1
                if e.metadata.get("legitimate") is False:
                    self.false_quarantined += 1
                elif e.agent_id is not None:
                    self.first_quarantined.setdefault(e.agent_id, e.sim_tick)
                if e.agent_id is not None:
                    self.infectious_ids.discard(e.agent_id)
                    self.quarantined_ids.add(e.agent_id)

    def _advance_to(self, tick: int) -> None:
        if self.open_tick is None:
            self.open_tick = tick
            return
        for closed in range(self.open_tick, tick):
            self.prevalence_rows.append(
                (closed, len(self.infectious_ids), len(self.quarantined_ids))
            )
        self.open_tick = max(self.open_tick, tick)

    def prevalence(self, final_tick: int) -> list[tuple[int, int, int]]:
        """(tick, infectious, quarantined) at the end of every tick through
        final_tick. A tick with no events repeats the one before it."""
        if self.open_tick is None:
            return []
        current = (len(self.infectious_ids), len(self.quarantined_ids))
        return self.prevalence_rows + [
            (tick, *current) for tick in range(self.open_tick, max(self.open_tick, final_tick) + 1)
        ]

    def attack_success_rate(self) -> float:
        return (self.new_compromises / self.attempted) if self.attempted else 0.0

    def false_quarantine_rate(self) -> float:
        if not self.quarantined:
            return 0.0
        return self.false_quarantined / self.quarantined

    def detection_latency(self, state: WorldState) -> float | None:
        """Mean ticks between a node's tick_compromised and its first
        ANOMALY_DETECTED. None when no currently-compromised-or-recovered
        node with a recorded tick_compromised has been detected yet."""
        latencies = [
            self.first_detected[node_id] - node.tick_compromised
            for node_id, node in state.nodes.items()
            if node.tick_compromised is not None and node_id in self.first_detected
        ]
        if not latencies:
            return None
        return sum(latencies) / len(latencies)

    def containment_latency(self) -> float | None:
        """Mean ticks between a node's first ANOMALY_DETECTED and its first
        legitimate AGENT_QUARANTINED (metadata.legitimate is not False --
        excludes the false-quarantine attack, which by definition has no
        preceding detection to measure a containment response against).
        None when no node has completed that transition yet."""
        latencies = [
            self.first_quarantined[node_id] - self.first_detected[node_id]
            for node_id in self.first_quarantined
            if node_id in self.first_detected
        ]
        if not latencies:
            return None
        return sum(latencies) / len(latencies)


def attack_success_rate(events: Sequence[Event]) -> float:
    return EventLogTally.of(events).attack_success_rate()


def false_quarantine_rate(events: Sequence[Event]) -> float:
    return EventLogTally.of(events).false_quarantine_rate()


def detection_latency(state: WorldState, events: Sequence[Event]) -> float | None:
    return EventLogTally.of(events).detection_latency(state)


def containment_latency(events: Sequence[Event]) -> float | None:
    return EventLogTally.of(events).containment_latency()


def all_metrics(
    state: WorldState, graph: SecurityGraph, tally: EventLogTally
) -> dict[str, float | int | None]:
    """Every metric MetricsResponse reports, computed one way for the live
    endpoint, replay and the benchmarks."""
    return {
        "compromise_fraction": compromise_fraction(state),
        "retained_utility": retained_utility(state),
        "blast_radius_fraction": blast_radius_fraction(graph),
        "privileged_exposure": privileged_exposure(graph),
        "security_plane_integrity": security_plane_integrity(graph),
        "attack_success_rate": tally.attack_success_rate(),
        "false_quarantine_rate": tally.false_quarantine_rate(),
        "detection_latency": tally.detection_latency(state),
        # Detection and quarantine happen in the same tick in quarantine mode,
        # the only response mode until graduated response (PLAN 14.4 C.5), so
        # this gap is always 0 and says nothing -- reported as None (D1).
        "containment_latency": None,
        "gateway_failure_count": tally.gateway_failures,
        **epidemic.epidemic_metrics(state, tally),
    }
