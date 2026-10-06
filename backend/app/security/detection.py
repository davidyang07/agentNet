from dataclasses import replace

from app.engine.rng import rng
from app.engine.state import AgentNode, SecurityState, WorldState, is_infected, is_susceptible
from app.graph.builder import build_security_graph
from app.graph.types import EdgeType, NodeType
from app.schemas.events import EventDraft, EventType
from app.schemas.experiment import ExperimentConfig
from app.security import immunity


def _suppressed_by_compromised_sentinels(state: WorldState, config: ExperimentConfig) -> set[str]:
    """Sentinel compromise (docs/PLAN.md §5): a subverted sentinel's
    ANOMALY_DETECTED emissions become unreliable for the agents it monitors.
    Cheap and pure (like every other on-demand graph build in this codebase)
    -- only builds the graph when sentinels exist at all, so the zero-sentinel
    default path never pays for it."""
    if config.sentinel_count <= 0 or not state.compromised_graph_nodes:
        return set()
    graph = build_security_graph(state, config)
    compromised_sentinels = {
        n.id
        for n in graph.nodes_of_type(NodeType.SENTINEL)
        if n.id in state.compromised_graph_nodes
    }
    if not compromised_sentinels:
        return set()
    return {
        edge.target
        for edge in graph.edges(frozenset({EdgeType.MONITORS}))
        if edge.source in compromised_sentinels
    }


def detection_probability(node: AgentNode, config: ExperimentConfig, tick: int) -> float:
    """detector_sensitivity, ramped up linearly over detector_ramp_ticks after
    compromise (docs/PLAN.md §14.4 C.5): change-point detection needs
    evidence to accumulate. Without a ramp, today's flat sensitivity."""
    if config.detector_ramp_ticks <= 0 or node.tick_compromised is None:
        return config.detector_sensitivity
    age = max(0, tick - node.tick_compromised)
    return config.detector_sensitivity * min(1.0, age / config.detector_ramp_ticks)


def step(state: WorldState, config: ExperimentConfig) -> tuple[WorldState, list[EventDraft]]:
    """Advance detection/quarantine for one tick. Pure, synchronous, total.

    Same (state, config) in -> same (state', drafts) out, always.

    docs/PLAN.md §14.4 C.5 adds, all opt-in: a detection ramp; the
    detector's own false positives on uninfected agents (distinct from the
    false-quarantine attack below); and graduated response, where a first
    detection makes an agent SUSPICIOUS, a second quarantines it, and an
    agent not detected again within review_ticks is released.
    """
    if not config.defense_enabled:
        return state, []

    tick = state.tick
    graduated = config.response_mode == "graduated"
    suppressed = _suppressed_by_compromised_sentinels(state, config)

    # (agent, false positive, probability): true detections first, then the
    # detector's false positives, each in sorted id order.
    detections: list[tuple[str, bool, float]] = []
    for node_id in sorted(
        n for n, node in state.nodes.items() if is_infected(node) and n not in suppressed
    ):
        probability = detection_probability(state.nodes[node_id], config, tick)
        if rng(config.seed, tick, node_id, "detect").random() < probability:
            detections.append((node_id, False, probability))
    if config.detector_false_positive_rate > 0.0:
        for node_id in sorted(n for n, node in state.nodes.items() if is_susceptible(node)):
            draw = rng(config.seed, tick, node_id, "false_positive").random()
            if draw < config.detector_false_positive_rate:
                detections.append((node_id, True, config.detector_false_positive_rate))

    drafts: list[EventDraft] = []
    new_states: dict[str, SecurityState] = {}
    suspicious_since: dict[str, int | None] = {}
    signatures = list(state.signatures)

    for node_id, false_positive, probability in detections:
        node = state.nodes[node_id]
        quarantine = not graduated or node.security_state == SecurityState.SUSPICIOUS
        metadata: dict[str, object] = {"sensitivity": config.detector_sensitivity}
        if config.detector_ramp_ticks > 0 and not false_positive:
            metadata["detection_probability"] = probability
        if false_positive:
            metadata["false_positive"] = True
        if graduated:
            metadata["response"] = "quarantine" if quarantine else "suspicious"
        drafts.append(
            EventDraft(
                sim_tick=tick,
                event_type=EventType.ANOMALY_DETECTED,
                agent_id=node_id,
                metadata=metadata,
            )
        )
        # Shared immune memory (docs/PLAN.md §14.4 C.4): a detection
        # publishes the detected strain -- or, for a false positive, the
        # agent's benign behaviour, which is how autoimmunity emerges (C.5).
        if config.immunity_enabled:
            vector = (
                immunity.benign_vector(config, tick, node_id, "false_positive_signature")
                if false_positive
                else node.strain
            )
            if vector is not None:
                published = immunity.publish(
                    signatures, config, tick, vector, legitimate=True, agent_id=node_id
                )
                if published is not None:
                    drafts.append(published)
        if quarantine:
            drafts.append(
                EventDraft(
                    sim_tick=tick,
                    event_type=EventType.AGENT_QUARANTINED,
                    agent_id=node_id,
                    metadata={"false_positive": True} if false_positive else {},
                )
            )
            new_states[node_id] = SecurityState.QUARANTINED
        else:
            new_states[node_id] = SecurityState.SUSPICIOUS
            suspicious_since[node_id] = tick

    # Graduated response: an agent not detected again within review_ticks
    # goes back to what it was -- still COMPROMISED if it is infected.
    if graduated:
        for node_id in sorted(
            n
            for n, node in state.nodes.items()
            if node.security_state == SecurityState.SUSPICIOUS and n not in new_states
        ):
            node = state.nodes[node_id]
            if node.suspicious_since is None or tick - node.suspicious_since < config.review_ticks:
                continue
            restored = (
                SecurityState.COMPROMISED
                if node.tick_compromised is not None
                else SecurityState.HEALTHY
            )
            drafts.append(
                EventDraft(
                    sim_tick=tick,
                    event_type=EventType.AGENT_RELEASED,
                    agent_id=node_id,
                    metadata={"from": SecurityState.SUSPICIOUS.value, "to": restored.value},
                )
            )
            new_states[node_id] = restored
            suspicious_since[node_id] = None

    # Byzantine/security-plane attack (docs/PLAN.md §5): a subverted
    # quarantine authority falsely reporting a HEALTHY node. Defaults to 0.0,
    # a strict no-op that leaves this function's output byte-for-byte
    # unchanged for every existing caller/test. The observable violation is
    # mechanical, not an LLM judge: AGENT_QUARANTINED with
    # metadata.legitimate=false and no preceding ANOMALY_DETECTED on that
    # target -- exactly what distinguishes it from the legitimate path above.
    if config.false_quarantine_rate > 0.0:
        healthy = sorted(node_id for node_id, node in state.nodes.items() if is_susceptible(node))
        for node_id in healthy:
            draw = rng(config.seed, tick, node_id, "false_quarantine").random()
            if draw < config.false_quarantine_rate:
                new_states[node_id] = SecurityState.QUARANTINED
                drafts.append(
                    EventDraft(
                        sim_tick=tick,
                        event_type=EventType.AGENT_QUARANTINED,
                        agent_id=node_id,
                        metadata={"legitimate": False},
                    )
                )

    if not new_states:
        return state, drafts

    new_nodes = dict(state.nodes)
    for node_id, security_state in new_states.items():
        new_nodes[node_id] = replace(
            new_nodes[node_id],
            security_state=security_state,
            suspicious_since=suspicious_since.get(node_id, new_nodes[node_id].suspicious_since),
        )

    new_state = replace(state, nodes=new_nodes, signatures=tuple(signatures))
    return new_state, drafts
