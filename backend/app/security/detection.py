from dataclasses import replace

from app.engine.rng import rng
from app.engine.state import SecurityState, WorldState
from app.schemas.events import EventDraft, EventType
from app.schemas.experiment import ExperimentConfig


def step(state: WorldState, config: ExperimentConfig) -> tuple[WorldState, list[EventDraft]]:
    """Advance detection/quarantine for one tick. Pure, synchronous, total.

    Same (state, config) in -> same (state', drafts) out, always.
    """
    if not config.defense_enabled:
        return state, []

    compromised = sorted(
        node_id
        for node_id, node in state.nodes.items()
        if node.security_state == SecurityState.COMPROMISED
    )

    drafts: list[EventDraft] = []
    quarantined: set[str] = set()

    for node_id in compromised:
        draw = rng(config.seed, state.tick, node_id, "detect").random()
        if draw < config.detector_sensitivity:
            quarantined.add(node_id)
            drafts.append(
                EventDraft(
                    sim_tick=state.tick,
                    event_type=EventType.ANOMALY_DETECTED,
                    agent_id=node_id,
                    metadata={"sensitivity": config.detector_sensitivity},
                )
            )
            drafts.append(
                EventDraft(
                    sim_tick=state.tick,
                    event_type=EventType.AGENT_QUARANTINED,
                    agent_id=node_id,
                )
            )

    if not quarantined:
        return state, drafts

    new_nodes = dict(state.nodes)
    for node_id in quarantined:
        new_nodes[node_id] = replace(
            new_nodes[node_id], security_state=SecurityState.QUARANTINED
        )

    new_state = WorldState(tick=state.tick, nodes=new_nodes, edges=state.edges)
    return new_state, drafts
