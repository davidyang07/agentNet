"""Epidemic metrics (docs/PLAN.md §14.4 C.1, after [S1] and [S2] in §14.8).

Every infected agent records its one source -- `compromised_by`, the first
winner (SPEC §3.4 rule 6) -- and `tick_compromised`. Together they form an
infection tree, and everything here except prevalence is read from that tree
in the state, so the live endpoint and replay agree by construction.
Prevalence needs history, so EventLogTally folds it from the event log.

An infected agent with no recorded source (the seeded compromise) is a root,
generation 0. Offspring counts are right-censored while an agent can still
infect someone: a cohort is flagged `censored` if any member is still
compromised, can run inference, and borders a healthy agent.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from app.engine.propagation import can_still_infect
from app.engine.state import AgentNode, WorldState

if TYPE_CHECKING:  # compute.all_metrics imports this module
    from app.metrics.compute import EventLogTally


def _infected(state: WorldState) -> dict[str, AgentNode]:
    return {
        node_id: node
        for node_id, node in state.nodes.items()
        if node.tick_compromised is not None
    }


def _source(node: AgentNode, infected: dict[str, AgentNode]) -> str | None:
    """The agent that infected `node`, or None for a root."""
    return node.compromised_by if node.compromised_by in infected else None


def generations(state: WorldState) -> dict[str, int]:
    """Walks each agent's source chain up to a root. Not by tick order: the
    seed infects from tick 0, so it can share a tick with its offspring."""
    infected = _infected(state)
    generation: dict[str, int] = {}
    for node_id in sorted(infected):
        chain: list[str] = []
        current = node_id
        while current not in generation:
            source = _source(infected[current], infected)
            if source is None or source == current or source in chain:
                generation[current] = 0  # a root (or a malformed cycle)
                break
            chain.append(current)
            current = source
        for member in reversed(chain):
            generation[member] = generation[infected[member].compromised_by] + 1
    return generation


def offspring(state: WorldState) -> dict[str, int]:
    """How many agents each infected agent infected (0 for a dead end)."""
    infected = _infected(state)
    counts = dict.fromkeys(infected, 0)
    for node in infected.values():
        source = _source(node, infected)
        if source is not None:
            counts[source] += 1
    return counts


def r_effective(state: WorldState) -> list[tuple[int, float, bool]]:
    """(tick, mean offspring of the agents infected that tick, censored)."""
    infected = _infected(state)
    counts = offspring(state)
    cohorts: dict[int, list[str]] = defaultdict(list)
    for node_id, node in infected.items():
        cohorts[node.tick_compromised].append(node_id)
    return [
        (
            tick,
            sum(counts[n] for n in members) / len(members),
            any(can_still_infect(infected[n], state) for n in members),
        )
        for tick, members in sorted(cohorts.items())
    ]


def r0_estimate(state: WorldState) -> float | None:
    """Mean offspring of generations 0 and 1; None with no infection."""
    counts = offspring(state)
    early = [counts[n] for n, g in generations(state).items() if g <= 1]
    return sum(early) / len(early) if early else None


def serial_interval(state: WorldState) -> float | None:
    """Mean ticks from a source's infection to its target's; None with no
    transmission."""
    infected = _infected(state)
    gaps = [
        node.tick_compromised - infected[source].tick_compromised
        for node in infected.values()
        if (source := _source(node, infected)) is not None
    ]
    return sum(gaps) / len(gaps) if gaps else None


def final_size(state: WorldState) -> float:
    """Fraction of agents ever infected."""
    if not state.nodes:
        return 0.0
    return len(_infected(state)) / len(state.nodes)


def generation_stats(state: WorldState) -> list[tuple[int, int, float]]:
    """(generation, agents in it, their mean offspring)."""
    counts = offspring(state)
    by_generation: dict[int, list[int]] = defaultdict(list)
    for node_id, generation in generations(state).items():
        by_generation[generation].append(counts[node_id])
    return [
        (generation, len(members), sum(members) / len(members))
        for generation, members in sorted(by_generation.items())
    ]


def peak_prevalence(state: WorldState, tally: EventLogTally) -> tuple[float | None, int | None]:
    """The largest fraction of agents infectious at once, and the first tick
    it was reached; (None, None) before any event."""
    rows = tally.prevalence(state.tick)
    if not rows or not state.nodes:
        return None, None
    tick, infectious, _ = max(rows, key=lambda row: (row[1], -row[0]))
    return infectious / len(state.nodes), tick


def epidemic_metrics(state: WorldState, tally: EventLogTally) -> dict[str, float | int | None]:
    """The epidemic fields of MetricsResponse."""
    peak, peak_tick = peak_prevalence(state, tally)
    return {
        "r0_estimate": r0_estimate(state),
        "serial_interval": serial_interval(state),
        "final_size": final_size(state),
        "peak_prevalence": peak,
        "peak_tick": peak_tick,
    }


def epidemic_report(state: WorldState, tally: EventLogTally) -> dict[str, list[dict]]:
    """Everything EpidemicResponse reports, one way for live and replay."""
    return {
        "prevalence": [
            {"tick": tick, "infectious": infectious, "quarantined": quarantined}
            for tick, infectious, quarantined in tally.prevalence(state.tick)
        ],
        "r_effective": [
            {"tick": tick, "value": value, "censored": censored}
            for tick, value, censored in r_effective(state)
        ],
        "generations": [
            {"generation": generation, "nodes": nodes, "mean_offspring": mean}
            for generation, nodes, mean in generation_stats(state)
        ],
    }
