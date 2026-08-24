import networkx as nx

from app.engine.rng import rng
from app.engine.state import AgentNode, SecurityState, WorldState
from app.schemas.events import EventDraft, EventType
from app.schemas.experiment import ExperimentConfig

_TYPE_LETTERS = "abcdefghijklmnopqrstuvwxyz"


def _software_types(sorted_ids: list[str], software_type_count: int) -> dict[str, str]:
    labels = [f"sw-{_TYPE_LETTERS[i]}" for i in range(software_type_count)]
    return {node_id: labels[i % software_type_count] for i, node_id in enumerate(sorted_ids)}


def build_world(config: ExperimentConfig) -> tuple[WorldState, list[EventDraft]]:
    """Build topology, assign software types, seed the initial compromise.

    Returns tick-0 state plus one AGENT_CREATED draft per node and one
    COMPROMISE_SUCCEEDED draft for the seeded node.
    """
    graph = nx.barabasi_albert_graph(
        n=config.node_count, m=config.edge_density, seed=config.seed
    )

    def node_id(i: int) -> str:
        return f"agent-{i:03d}"

    sorted_ids = sorted(node_id(i) for i in graph.nodes)
    types = _software_types(sorted_ids, config.software_type_count)

    neighbors: dict[str, set[str]] = {n: set() for n in sorted_ids}
    edge_set: set[tuple[str, str]] = set()
    for u, v in graph.edges:
        a, b = node_id(u), node_id(v)
        neighbors[a].add(b)
        neighbors[b].add(a)
        edge_set.add((a, b) if a < b else (b, a))

    if config.initial_compromised == "random_node":
        seed_node = rng(config.seed, 0, "topology", "initial_compromise").choice(sorted_ids)
    else:
        degree = {n: len(neighbors[n]) for n in sorted_ids}
        max_degree = max(degree.values())
        seed_node = sorted(n for n in sorted_ids if degree[n] == max_degree)[0]

    nodes: dict[str, AgentNode] = {}
    for n in sorted_ids:
        state = SecurityState.COMPROMISED if n == seed_node else SecurityState.HEALTHY
        nodes[n] = AgentNode(
            id=n,
            software_type=types[n],
            security_state=state,
            neighbors=tuple(sorted(neighbors[n])),
            compromised_by=None,
            tick_compromised=0 if n == seed_node else None,
        )

    world = WorldState(tick=0, nodes=nodes, edges=tuple(sorted(edge_set)))

    drafts: list[EventDraft] = []
    for n in sorted_ids:
        drafts.append(
            EventDraft(
                sim_tick=0,
                event_type=EventType.AGENT_CREATED,
                agent_id=n,
                metadata={"software_type": types[n]},
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

    return world, drafts
