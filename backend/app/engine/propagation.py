from dataclasses import replace

from app.engine import strains
from app.engine.rng import rng
from app.engine.state import AgentNode, SecurityState, WorldState, is_infected, is_susceptible
from app.schemas.events import EventDraft, EventType
from app.schemas.experiment import ExperimentConfig
from app.security import immunity


def is_active_source(node: AgentNode, tick: int) -> bool:
    """SPEC §3.4 rule 7: a newly compromised agent attacks only from the next
    tick. The seeded compromise (no source) attacks from tick 0. Real-agent
    compromises are stamped with the post-increment tick, so without this
    they would attack in the same tick they were compromised. An agent that
    can't run inference never attacks (docs/PLAN.md §14.4 C.2)."""
    return (
        is_infected(node)
        and node.inference_capable
        and (
            node.compromised_by is None
            or node.tick_compromised is None
            or node.tick_compromised < tick
        )
    )


def can_still_infect(node: AgentNode, state: WorldState) -> bool:
    """Infected, able to run inference, and bordering a susceptible agent."""
    return (
        is_infected(node)
        and node.inference_capable
        and any(is_susceptible(state.nodes[n]) for n in node.neighbors)
    )


def transmission_probability(
    source: AgentNode, target: AgentNode, config: ExperimentConfig
) -> tuple[float, dict[str, object]]:
    """SPEC §3.4 rule 3, scaled for a SUSPICIOUS source under graduated
    response (docs/PLAN.md §14.4 C.5); the metadata to emit with it."""
    p = config.p_same if target.software_type == source.software_type else config.p_cross
    if source.security_state == SecurityState.SUSPICIOUS:
        return p * config.suspicious_transmission_factor, {
            "probability": p * config.suspicious_transmission_factor,
            "suspicious_source": True,
        }
    return p, {"probability": p}


def step(state: WorldState, config: ExperimentConfig) -> tuple[WorldState, list[EventDraft]]:
    """Advance exactly one tick. Pure, synchronous, total.

    Same (state, config) in -> same (state', drafts) out, always.
    """
    sources = sorted(
        node_id for node_id, node in state.nodes.items() if is_active_source(node, state.tick)
    )

    drafts: list[EventDraft] = []
    claims: dict[str, str] = {}
    claimed_strains: dict[str, int] = {}
    track_strains = strains.tracked(config)

    for source in sources:
        source_node = state.nodes[source]
        targets = sorted(t for t in source_node.neighbors if is_susceptible(state.nodes[t]))
        for target in targets:
            # A real-real edge is owned exclusively by agents.runtime's
            # LLM-mediated attempt, not this probabilistic mechanism -- each
            # edge is attacked by exactly one path.
            # A no-op whenever no node is agent_kind="real" (real_agent_count
            # defaults to 0), which is what keeps this function's behavior
            # byte-for-byte unchanged for the synthetic baseline.
            if source_node.agent_kind == "real" and state.nodes[target].agent_kind == "real":
                continue
            p, base_metadata = transmission_probability(source_node, state.nodes[target], config)

            drafts.append(
                EventDraft(
                    sim_tick=state.tick,
                    event_type=EventType.COMPROMISE_ATTEMPTED,
                    source_agent_id=source,
                    target_agent_id=target,
                    metadata=dict(base_metadata),
                )
            )

            # docs/PLAN.md §14.4 C.4: immune memory stops the attack before
            # any draw.
            if immunity.blocks(state, config, target, source_node.strain, state.tick):
                drafts.append(immunity.blocked_draft(state.tick, source, target, base_metadata))
                continue

            draw = rng(config.seed, state.tick, target, f"infect:{source}").random()
            if draw < p:
                already_claimed = target in claims
                metadata: dict[str, object] = dict(base_metadata)
                if track_strains:
                    strain, mutated = strains.transmit(config, state.tick, source_node, target)
                    metadata.update(strains.success_metadata(config, strain, mutated))
                if already_claimed:
                    metadata["already_compromised"] = True
                else:
                    claims[target] = source
                    if track_strains:
                        claimed_strains[target] = strain
                drafts.append(
                    EventDraft(
                        sim_tick=state.tick,
                        event_type=EventType.COMPROMISE_SUCCEEDED,
                        source_agent_id=source,
                        target_agent_id=target,
                        metadata=metadata,
                    )
                )
            else:
                drafts.append(
                    EventDraft(
                        sim_tick=state.tick,
                        event_type=EventType.COMPROMISE_FAILED,
                        source_agent_id=source,
                        target_agent_id=target,
                        metadata=dict(base_metadata),
                    )
                )

    new_nodes = dict(state.nodes)
    for target, source in claims.items():
        new_nodes[target] = replace(
            new_nodes[target],
            security_state=SecurityState.COMPROMISED,
            compromised_by=source,
            tick_compromised=state.tick,
            strain=claimed_strains.get(target),
            suspicious_since=None,
        )

    new_state = replace(state, tick=state.tick + 1, nodes=new_nodes)
    return new_state, drafts


def is_finished(state: WorldState, config: ExperimentConfig) -> bool:
    """Run ends at max_ticks, or when no agent can infect anyone any more: no
    HEALTHY node borders a COMPROMISED one that can run inference."""
    if state.tick >= config.max_ticks:
        return True
    return not any(can_still_infect(node, state) for node in state.nodes.values())
