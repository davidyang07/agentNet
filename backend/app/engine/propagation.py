from dataclasses import replace

from app.engine import strains
from app.engine.rng import rng
from app.engine.state import AgentNode, SecurityState, WorldState
from app.schemas.events import EventDraft, EventType
from app.schemas.experiment import ExperimentConfig


def is_active_source(node: AgentNode, tick: int) -> bool:
    """SPEC §3.4 rule 7: a newly compromised agent attacks only from the next
    tick. The seeded compromise (no source) attacks from tick 0. Real-agent
    compromises are stamped with the post-increment tick, so without this
    they would attack in the same tick they were compromised. An agent that
    can't run inference never attacks (docs/PLAN.md §14.4 C.2)."""
    return (
        node.security_state == SecurityState.COMPROMISED
        and node.inference_capable
        and (
            node.compromised_by is None
            or node.tick_compromised is None
            or node.tick_compromised < tick
        )
    )


def can_still_infect(node: AgentNode, state: WorldState) -> bool:
    """Compromised, able to run inference, and bordering a healthy agent."""
    return (
        node.security_state == SecurityState.COMPROMISED
        and node.inference_capable
        and any(state.nodes[n].security_state == SecurityState.HEALTHY for n in node.neighbors)
    )


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
        source_type = source_node.software_type
        targets = sorted(
            t
            for t in source_node.neighbors
            if state.nodes[t].security_state == SecurityState.HEALTHY
        )
        for target in targets:
            # A real-real edge is owned exclusively by agents.runtime's
            # LLM-mediated attempt, not this probabilistic mechanism -- each
            # edge is attacked by exactly one path.
            # A no-op whenever no node is agent_kind="real" (real_agent_count
            # defaults to 0), which is what keeps this function's behavior
            # byte-for-byte unchanged for the synthetic baseline.
            if source_node.agent_kind == "real" and state.nodes[target].agent_kind == "real":
                continue
            same = state.nodes[target].software_type == source_type
            p = config.p_same if same else config.p_cross
            draw = rng(config.seed, state.tick, target, f"infect:{source}").random()

            drafts.append(
                EventDraft(
                    sim_tick=state.tick,
                    event_type=EventType.COMPROMISE_ATTEMPTED,
                    source_agent_id=source,
                    target_agent_id=target,
                    metadata={"probability": p},
                )
            )

            if draw < p:
                already_claimed = target in claims
                metadata: dict[str, object] = {"probability": p}
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
                        metadata={"probability": p},
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
        )

    new_state = WorldState(
        tick=state.tick + 1,
        nodes=new_nodes,
        edges=state.edges,
        compromised_graph_nodes=state.compromised_graph_nodes,
    )
    return new_state, drafts


def is_finished(state: WorldState, config: ExperimentConfig) -> bool:
    """Run ends at max_ticks, or when no agent can infect anyone any more: no
    HEALTHY node borders a COMPROMISED one that can run inference."""
    if state.tick >= config.max_ticks:
        return True
    return not any(can_still_infect(node, state) for node in state.nodes.values())
