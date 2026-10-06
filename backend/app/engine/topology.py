from dataclasses import replace

import networkx as nx

from app.engine import strains
from app.engine.rng import rng
from app.engine.state import AgentNode, SecurityState, Signature, WorldState
from app.schemas.events import EventDraft, EventType
from app.schemas.experiment import ExperimentConfig
from app.security import immunity

_TYPE_LETTERS = "abcdefghijklmnopqrstuvwxyz"


def _software_types(sorted_ids: list[str], software_type_count: int) -> dict[str, str]:
    labels = [f"sw-{_TYPE_LETTERS[i]}" for i in range(software_type_count)]
    return {node_id: labels[i % software_type_count] for i, node_id in enumerate(sorted_ids)}


def _generate_confidential_token(seed: int, node_id: str) -> str:
    """Deterministic per-(seed, node_id) synthetic secret -- reproducible
    across replays of the same seed, never derived
    from anything real. Uses the same rng() keying discipline as every other
    engine draw site, drawing raw bytes rather than a float."""
    draw = rng(seed, 0, node_id, "confidential_token")
    return f"TOKEN-{draw.getrandbits(64):016x}"


def _select_real_agents(sorted_ids: list[str], degree: dict[str, int], count: int) -> set[str]:
    """The `count` highest-degree nodes become agent_kind="real" (ties broken
    by lowest id -- same convention build_world() already uses for
    initial_compromised="highest_degree"). Barabasi-Albert graphs are hub-
    heavy, so highest-degree selection maximizes the odds that at least one
    real-real edge exists for the LLM-mediated propagation path to exercise,
    rather than leaving that to chance."""
    if count <= 0:
        return set()
    ranked = sorted(sorted_ids, key=lambda n: (-degree[n], n))
    return set(ranked[:count])


def _place(
    ids: list[str], degree: dict[str, int], placement: str, config: ExperimentConfig, purpose: str
) -> list[str]:
    """`ids` in placement order: hubs (highest degree first) or periphery
    (lowest first), ties by lowest id; or a keyed shuffle for random."""
    if placement == "hubs":
        return sorted(ids, key=lambda n: (-degree[n], n))
    if placement == "periphery":
        return sorted(ids, key=lambda n: (degree[n], n))
    ranked = list(ids)
    rng(config.seed, 0, "topology", purpose).shuffle(ranked)
    return ranked


def _select_inference_capable(
    sorted_ids: list[str], degree: dict[str, int], config: ExperimentConfig, always: set[str]
) -> set[str]:
    """docs/PLAN.md §14.4 C.2, after [S2]: round(inference_fraction x agents)
    agents can run inference. The seed and real agents always can -- every
    run has a propagator, and a real agent is a model -- and count toward
    the total; the rest are placed at random, on the hubs, or on the
    periphery. At the default fraction every agent is capable and nothing is
    drawn."""
    if config.inference_fraction >= 1.0:
        return set(sorted_ids)
    count = round(config.inference_fraction * len(sorted_ids))
    others = [n for n in sorted_ids if n not in always]
    ranked = _place(others, degree, config.inference_placement, config, "inference_placement")
    return always | set(ranked[: max(0, count - len(always))])


def _select_immune_participants(
    sorted_ids: list[str], degree: dict[str, int], config: ExperimentConfig
) -> set[str]:
    """docs/PLAN.md §14.4 C.4: round(immunity_coverage x agents) agents take
    part in shared immune memory, placed like inference capability."""
    if not config.immunity_enabled:
        return set()
    count = round(config.immunity_coverage * len(sorted_ids))
    ranked = _place(sorted_ids, degree, config.immunity_placement, config, "immunity_placement")
    return set(ranked[:count])


def build_world_from_agents(
    agent_ids: list[str], edges: set[tuple[str, str]], config: ExperimentConfig
) -> tuple[WorldState, list[EventDraft]]:
    """Same assembly as build_world (software-type round-robin, seeded
    initial compromise, real-agent selection, confidential tokens) but over
    a caller-supplied topology instead of a barabasi_albert_graph draw --
    the entry point for importing an externally-authored multi-agent
    topology (app/importers/external_topology.py). Agent ids are
    caller-defined strings (not the "agent-NNN" convention build_world
    generates), sorted for every deterministic operation exactly like
    build_world sorts its generated ids.
    """
    sorted_ids = sorted(agent_ids)
    types = _software_types(sorted_ids, config.software_type_count)

    neighbors: dict[str, set[str]] = {n: set() for n in sorted_ids}
    edge_set: set[tuple[str, str]] = set()
    for u, v in edges:
        neighbors[u].add(v)
        neighbors[v].add(u)
        edge_set.add((u, v) if u < v else (v, u))

    degree = {n: len(neighbors[n]) for n in sorted_ids}

    if config.initial_compromised == "random_node":
        seed_node = rng(config.seed, 0, "topology", "initial_compromise").choice(sorted_ids)
    else:
        max_degree = max(degree.values())
        seed_node = sorted(n for n in sorted_ids if degree[n] == max_degree)[0]

    real_agent_ids = _select_real_agents(sorted_ids, degree, config.real_agent_count)
    capable = _select_inference_capable(
        sorted_ids, degree, config, always={seed_node} | real_agent_ids
    )
    patient_zero = strains.patient_zero_strain(config) if strains.tracked(config) else None
    participants = _select_immune_participants(sorted_ids, degree, config)

    nodes: dict[str, AgentNode] = {}
    for n in sorted_ids:
        state = SecurityState.COMPROMISED if n == seed_node else SecurityState.HEALTHY
        is_real = n in real_agent_ids
        nodes[n] = AgentNode(
            id=n,
            software_type=types[n],
            security_state=state,
            neighbors=tuple(sorted(neighbors[n])),
            compromised_by=None,
            tick_compromised=0 if n == seed_node else None,
            agent_kind="real" if is_real else "simulated",
            confidential_token=_generate_confidential_token(config.seed, n) if is_real else None,
            inference_capable=n in capable,
            strain=patient_zero if n == seed_node else None,
            immune_participant=n in participants,
        )

    world = WorldState(tick=0, nodes=nodes, edges=tuple(sorted(edge_set)))

    drafts: list[EventDraft] = []
    for n in sorted_ids:
        metadata: dict[str, object] = {"software_type": types[n]}
        if config.inference_fraction < 1.0:
            metadata["inference_capable"] = n in capable
        if config.immunity_enabled:
            metadata["immune_participant"] = n in participants
        drafts.append(
            EventDraft(
                sim_tick=0,
                event_type=EventType.AGENT_CREATED,
                agent_id=n,
                metadata=metadata,
            )
        )
    drafts.append(
        EventDraft(
            sim_tick=0,
            event_type=EventType.COMPROMISE_SUCCEEDED,
            target_agent_id=seed_node,
            metadata={"initial_compromise": True},
        )
    )

    if config.immunity_enabled and config.preseed_patient_zero_signature:
        # [S1]'s red-team pre-seeding: held from tick 0, before any attack.
        assert patient_zero is not None
        preseeded = Signature(vector=patient_zero, legitimate=True, adopt_tick=0, announced=True)
        drafts.append(immunity.published_draft(config, preseeded, None, 0, preseeded=True))
        drafts.append(immunity.received_draft(config, preseeded, len(participants), 0))
        world = replace(world, signatures=(preseeded,))

    return world, drafts


def build_world(config: ExperimentConfig) -> tuple[WorldState, list[EventDraft]]:
    """Build topology, assign software types, seed the initial compromise.

    Returns tick-0 state plus one AGENT_CREATED draft per node and one
    COMPROMISE_SUCCEEDED draft for the seeded node.
    """
    if config.topology == "erdos_renyi":
        # docs/PLAN.md §14.4 C.2: as many edges as barabasi_albert_graph makes
        # (edge_density x (node_count - edge_density)), placed uniformly.
        graph = nx.gnm_random_graph(
            n=config.node_count,
            m=config.edge_density * (config.node_count - config.edge_density),
            seed=config.seed,
        )
    else:
        graph = nx.barabasi_albert_graph(
            n=config.node_count, m=config.edge_density, seed=config.seed
        )

    def node_id(i: int) -> str:
        return f"agent-{i:03d}"

    sorted_ids = sorted(node_id(i) for i in graph.nodes)
    edge_set = {
        (node_id(u), node_id(v)) if node_id(u) < node_id(v) else (node_id(v), node_id(u))
        for u, v in graph.edges
    }
    return build_world_from_agents(sorted_ids, edge_set, config)
