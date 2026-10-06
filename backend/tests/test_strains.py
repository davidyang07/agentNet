"""Worm strains and mutation (PLAN 14.4 C.3, after [S1]: worms are
inherently polymorphic). A strain is a k-bit vector; Hamming distance stands
for semantic distance."""

import asyncio

import pytest
from pydantic import ValidationError

from app.agents.runtime import real_agent_step
from app.engine import strains
from app.engine.propagation import step as propagation_step
from app.engine.simulate import simulate
from app.engine.state import AgentNode, SecurityState, WorldState
from app.engine.topology import build_world
from app.gateway.gateway import ModelGateway
from app.gateway.mock_provider import MockProvider
from app.metrics.epidemic import strains_observed
from app.scenarios.adaptive_attacker_scenario import step as adaptive_step
from app.schemas.experiment import ExperimentConfig

C, H = SecurityState.COMPROMISED, SecurityState.HEALTHY


def _seed_node(world: WorldState) -> AgentNode:
    return next(n for n in world.nodes.values() if n.security_state == C)


def test_strains_are_off_by_default_and_nothing_is_emitted():
    final, drafts = simulate(ExperimentConfig(seed=1, node_count=40, p_same=0.5))
    assert all(node.strain is None for node in final.nodes.values())
    assert all("strain" not in d.metadata for d in drafts)
    assert strains_observed(final) is None


def test_patient_zero_sits_the_configured_distance_from_the_benign_centroid():
    for distance in (0, 5, 32):
        config = ExperimentConfig(
            seed=4, node_count=30, mutation_rate=0.1, strain_benign_distance=distance
        )
        world, _ = build_world(config)
        seed = _seed_node(world)
        assert strains.distance(seed.strain, strains.benign_centroid(config)) == distance
        assert all(n.strain is None for n in world.nodes.values() if n is not seed)


def test_strains_are_keyed_on_the_seed():
    def patient_zero(seed):
        return _seed_node(build_world(ExperimentConfig(seed=seed, mutation_rate=0.1))[0]).strain

    assert patient_zero(3) == patient_zero(3)
    assert patient_zero(3) != patient_zero(4)


def test_every_mutation_flips_exactly_mutation_bits():
    config = ExperimentConfig(
        seed=2, node_count=60, p_same=0.6, p_cross=0.3, mutation_rate=1.0, mutation_bits=3,
        defense_enabled=False, max_ticks=20,
    )
    final, drafts = simulate(config)
    infected = [n for n in final.nodes.values() if n.compromised_by is not None]
    assert infected
    for node in infected:
        source = final.nodes[node.compromised_by]
        assert strains.distance(node.strain, source.strain) == 3
    wins = [
        d for d in drafts
        if d.event_type.value == "COMPROMISE_SUCCEEDED" and "probability" in d.metadata
    ]
    assert wins and all(d.metadata["mutated"] is True for d in wins)
    assert all(d.metadata["strain"] == strains.encode(
        final.nodes[d.target_agent_id].strain, 64
    ) for d in wins if "already_compromised" not in d.metadata)


def test_without_a_mutation_a_target_inherits_its_sources_strain():
    config = ExperimentConfig(
        seed=5, node_count=60, p_same=0.6, p_cross=0.3, mutation_rate=0.3,
        defense_enabled=False, max_ticks=20,
    )
    final, drafts = simulate(config)
    mutated = {
        d.target_agent_id: d.metadata["mutated"]
        for d in drafts
        if d.event_type.value == "COMPROMISE_SUCCEEDED"
        and "probability" in d.metadata
        and "already_compromised" not in d.metadata
    }
    assert set(mutated.values()) == {True, False}
    for target, was_mutated in mutated.items():
        node = final.nodes[target]
        same = node.strain == final.nodes[node.compromised_by].strain
        assert same is not was_mutated
    assert strains_observed(final) == len(
        {n.strain for n in final.nodes.values() if n.strain is not None}
    )
    assert strains_observed(final) > 1


def _pair(first_kind="simulated") -> WorldState:
    """Two compromised sources both able to hit t."""
    config = ExperimentConfig(seed=1, mutation_rate=1.0)
    zero = strains.patient_zero_strain(config)
    nodes = {
        "s1": AgentNode("s1", "sw-a", C, ("t",), tick_compromised=0, strain=zero,
                        agent_kind=first_kind),
        "s2": AgentNode("s2", "sw-a", C, ("t",), tick_compromised=0, strain=zero ^ 0b1111),
        "t": AgentNode("t", "sw-a", H, ("s1", "s2")),
    }
    return WorldState(tick=1, nodes=nodes, edges=(("s1", "t"), ("s2", "t")))


def test_the_first_winner_sets_the_targets_strain():
    config = ExperimentConfig(seed=1, p_same=1.0, p_cross=1.0, mutation_rate=1.0)
    world, drafts = propagation_step(_pair(), config)
    wins = [d for d in drafts if d.event_type.value == "COMPROMISE_SUCCEEDED"]
    assert [d.source_agent_id for d in wins] == ["s1", "s2"]
    assert world.nodes["t"].compromised_by == "s1"
    assert strains.encode(world.nodes["t"].strain, 64) == wins[0].metadata["strain"]
    assert wins[1].metadata["strain"] != wins[0].metadata["strain"]


def test_the_adaptive_attacker_transmits_strains():
    config = ExperimentConfig(
        seed=1, p_same=1.0, p_cross=1.0, mutation_rate=1.0, active_scenarios=["adaptive_attacker"]
    )
    world, drafts = adaptive_step(_pair(), config)
    win = next(d for d in drafts if d.event_type.value == "COMPROMISE_SUCCEEDED")
    assert win.metadata["mutated"] is True
    target = world.nodes["t"]
    assert strains.encode(target.strain, 64) == win.metadata["strain"]
    assert strains.distance(target.strain, world.nodes[target.compromised_by].strain) == 1


def test_real_agents_transmit_strains():
    config = ExperimentConfig(seed=1, p_same=1.0, p_cross=1.0, mutation_rate=1.0)
    world = _pair(first_kind="real")
    world.nodes["t"].agent_kind = "real"
    world.nodes["t"].confidential_token = "TOKEN-0123"
    gateway = ModelGateway(
        MockProvider(), timeout_s=5.0, max_retries=0, max_concurrency=4,
        max_requests_per_experiment=10,
    )
    world, drafts = asyncio.run(real_agent_step(world, config, gateway, tick=1))
    win = next(d for d in drafts if d.event_type.value == "COMPROMISE_SUCCEEDED")
    assert win.source_agent_id == "s1"
    assert strains.encode(world.nodes["t"].strain, 64) == win.metadata["strain"]
    assert strains.distance(world.nodes["t"].strain, world.nodes["s1"].strain) == 1


@pytest.mark.parametrize(
    "fields",
    [
        {"signature_bits": 16, "strain_benign_distance": 17},
        {"signature_bits": 16, "strain_benign_distance": 8, "mutation_bits": 17},
    ],
)
def test_distances_cannot_exceed_the_strain_length(fields):
    with pytest.raises(ValidationError):
        ExperimentConfig(seed=1, **fields)
