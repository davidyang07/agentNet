"""Inference capability and topology (PLAN 14.4 C.2, after [S2]: only
inference-capable agents propagate)."""

import networkx as nx

from app.benchmark.config import BenchmarkConfig
from app.engine.propagation import is_finished
from app.engine.propagation import step as propagation_step
from app.engine.state import AgentNode, SecurityState, WorldState
from app.engine.topology import build_world
from app.graph.builder import build_security_graph
from app.metrics.epidemic import r_effective
from app.scenarios.adaptive_attacker_scenario import step as adaptive_step
from app.schemas.experiment import ExperimentConfig

C, H = SecurityState.COMPROMISED, SecurityState.HEALTHY


def _capable(world: WorldState) -> set[str]:
    return {n for n, node in world.nodes.items() if node.inference_capable}


def _seed(world: WorldState) -> str:
    return next(n for n, node in world.nodes.items() if node.security_state == C)


def test_by_default_every_agent_is_capable_and_nothing_new_is_emitted():
    world, drafts = build_world(ExperimentConfig(seed=1, node_count=40))
    assert _capable(world) == set(world.nodes)
    assert all("inference_capable" not in d.metadata for d in drafts)


def test_the_fraction_sets_how_many_agents_are_capable_and_the_seed_always_is():
    for placement in ("random", "hubs", "periphery"):
        config = ExperimentConfig(
            seed=3, node_count=40, inference_fraction=0.25, inference_placement=placement
        )
        world, drafts = build_world(config)
        assert len(_capable(world)) == 10, placement
        assert _seed(world) in _capable(world), placement
        created = {d.agent_id: d.metadata["inference_capable"] for d in drafts if d.agent_id}
        assert {n for n, capable in created.items() if capable} == _capable(world)


def test_hub_and_periphery_placement_follow_degree():
    def degrees(world):
        return {n: len(node.neighbors) for n, node in world.nodes.items()}

    base = dict(seed=5, node_count=60, inference_fraction=0.2, initial_compromised="random_node")
    hubs, _ = build_world(ExperimentConfig(**base, inference_placement="hubs"))
    periphery, _ = build_world(ExperimentConfig(**base, inference_placement="periphery"))
    degree = degrees(hubs)
    others = lambda world: _capable(world) - {_seed(world)}  # noqa: E731
    lowest_capable_hub = min(degree[n] for n in others(hubs))
    highest_capable_peripheral = max(degree[n] for n in others(periphery))
    assert lowest_capable_hub >= max(degree[n] for n in set(degree) - _capable(hubs))
    assert highest_capable_peripheral <= min(degree[n] for n in set(degree) - _capable(periphery))


def test_random_placement_is_keyed_on_the_seed():
    config = dict(node_count=50, inference_fraction=0.3)
    first, _ = build_world(ExperimentConfig(seed=8, **config))
    again, _ = build_world(ExperimentConfig(seed=8, **config))
    other, _ = build_world(ExperimentConfig(seed=9, **config))
    assert _capable(first) == _capable(again)
    assert _capable(first) != _capable(other)


def test_with_no_capable_fraction_only_the_seed_and_real_agents_propagate():
    world, _ = build_world(
        ExperimentConfig(seed=2, node_count=40, inference_fraction=0.0, real_agent_count=3)
    )
    real = {n for n, node in world.nodes.items() if node.agent_kind == "real"}
    assert _capable(world) == real | {_seed(world)}


def _line(capable_b: bool) -> WorldState:
    """a (compromised, capable) - b (healthy) - c (healthy)."""
    nodes = {
        "a": AgentNode("a", "sw-a", C, ("b",), tick_compromised=0),
        "b": AgentNode("b", "sw-a", H, ("a", "c"), inference_capable=capable_b),
        "c": AgentNode("c", "sw-a", H, ("b",)),
    }
    return WorldState(tick=0, nodes=nodes, edges=(("a", "b"), ("b", "c")))


def test_a_dead_end_is_infected_but_never_attacks():
    config = ExperimentConfig(seed=1, node_count=25, p_same=1.0, p_cross=1.0)
    world = _line(capable_b=False)
    world, _ = propagation_step(world, config)
    assert world.nodes["b"].security_state == C  # still susceptible
    world, drafts = propagation_step(world, config)
    assert world.nodes["c"].security_state == H
    assert all(d.source_agent_id != "b" for d in drafts)
    # Nothing can spread any more, so the run is over.
    assert is_finished(world, config)


def test_a_capable_agent_keeps_spreading_and_the_run_going():
    config = ExperimentConfig(seed=1, node_count=25, p_same=1.0, p_cross=1.0)
    world, _ = propagation_step(_line(capable_b=True), config)
    assert not is_finished(world, config)
    world, _ = propagation_step(world, config)
    assert world.nodes["c"].security_state == C


def test_the_adaptive_attacker_never_attacks_from_a_dead_end():
    config = ExperimentConfig(
        seed=1, node_count=25, p_same=1.0, p_cross=1.0, active_scenarios=["adaptive_attacker"]
    )
    world = _line(capable_b=False)
    world.nodes["b"].security_state = C
    world.nodes["b"].tick_compromised = 0
    world.nodes["b"].compromised_by = "a"
    _, drafts = adaptive_step(WorldState(tick=1, nodes=world.nodes, edges=world.edges), config)
    assert all(d.source_agent_id != "b" for d in drafts)


def test_a_dead_end_does_not_censor_its_cohort():
    world = _line(capable_b=False)
    world.nodes["b"].security_state = C
    world.nodes["b"].tick_compromised = 1
    world.nodes["b"].compromised_by = "a"
    assert r_effective(world)[-1] == (1, 0.0, False)


def test_the_graph_view_marks_capability():
    config = ExperimentConfig(seed=4, node_count=30, inference_fraction=0.5)
    world, _ = build_world(config)
    graph = build_security_graph(world, config)
    marked = {n.id for n in graph.nodes if n.attrs.get("inference_capable")}
    assert marked == _capable(world)


def test_erdos_renyi_keeps_the_edge_count_and_the_default_stays_barabasi_albert():
    # 180 agents is the [S2] sweep's size (C.6), past the API's cap.
    for n, m in ((40, 2), (60, 3), (180, 3)):
        ba, _ = build_world(BenchmarkConfig(seed=7, node_count=n, edge_density=m))
        er, _ = build_world(
            BenchmarkConfig(seed=7, node_count=n, edge_density=m, topology="erdos_renyi")
        )
        assert len(ba.edges) == len(er.edges) == m * (n - m)
        assert set(ba.edges) != set(er.edges)

    default, _ = build_world(ExperimentConfig(seed=7, node_count=40))
    reference = nx.barabasi_albert_graph(40, 2, seed=7)
    assert len(default.edges) == reference.number_of_edges()


def test_erdos_renyi_is_keyed_on_the_seed():
    config = dict(node_count=50, topology="erdos_renyi")
    first, _ = build_world(ExperimentConfig(seed=1, **config))
    again, _ = build_world(ExperimentConfig(seed=1, **config))
    other, _ = build_world(ExperimentConfig(seed=2, **config))
    assert first.edges == again.edges
    assert first.edges != other.edges
