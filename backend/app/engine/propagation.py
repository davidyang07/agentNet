from dataclasses import replace

from app.engine.rng import rng
from app.engine.state import SecurityState, WorldState
from app.schemas.events import EventDraft, EventType
from app.schemas.experiment import ExperimentConfig


def step(state: WorldState, config: ExperimentConfig) -> tuple[WorldState, list[EventDraft]]:
    """Advance exactly one tick. Pure, synchronous, total.

    Same (state, config) in -> same (state', drafts) out, always.
    """
    sources = sorted(
        node_id
        for node_id, node in state.nodes.items()
        if node.security_state == SecurityState.COMPROMISED
    )

    drafts: list[EventDraft] = []
    claims: dict[str, str] = {}

    for source in sources:
        source_type = state.nodes[source].software_type
        targets = sorted(
            t
            for t in state.nodes[source].neighbors
            if state.nodes[t].security_state == SecurityState.HEALTHY
        )
        for target in targets:
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
                if already_claimed:
                    metadata["already_compromised"] = True
                else:
                    claims[target] = source
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
        )

    new_state = WorldState(tick=state.tick + 1, nodes=new_nodes, edges=state.edges)
    return new_state, drafts


def is_finished(state: WorldState, config: ExperimentConfig) -> bool:
    """Run ends at max_ticks, or when no HEALTHY node borders a COMPROMISED one."""
    if state.tick >= config.max_ticks:
        return True
    for node in state.nodes.values():
        if node.security_state != SecurityState.COMPROMISED:
            continue
        for neighbor_id in node.neighbors:
            if state.nodes[neighbor_id].security_state == SecurityState.HEALTHY:
                return False
    return True
