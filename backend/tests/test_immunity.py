"""Shared immune memory (PLAN 14.4 C.4, after [S1]'s signature database and
[S2]'s crowd defense): publication, adoption, protection, autoimmunity, and
poisoning, on hand-built worlds and simulated runs."""

import asyncio
from statistics import mean
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agents.runtime import real_agent_step
from app.engine import strains
from app.engine.propagation import step as propagation_step
from app.engine.simulate import simulate
from app.engine.state import AgentNode, SecurityState, Signature, WorldState
from app.engine.topology import build_world
from app.events.emitter import EventEmitter
from app.gateway.gateway import ModelGateway
from app.gateway.mock_provider import MockProvider
from app.graph.builder import build_security_graph
from app.metrics.compute import EventLogTally, all_metrics
from app.metrics.epidemic import final_size
from app.scenarios.adaptive_attacker_scenario import step as adaptive_step
from app.schemas.experiment import ExperimentConfig
from app.security import immunity

C, H, Q = SecurityState.COMPROMISED, SecurityState.HEALTHY, SecurityState.QUARANTINED


def _types(drafts, event_type):
    return [d for d in drafts if d.event_type.value == event_type]


def _metrics(config):
    final, drafts = simulate(config)
    tally = EventLogTally.of(EventEmitter(uuid4()).emit(drafts))
    return final, drafts, all_metrics(final, build_security_graph(final, config), tally), tally


def test_immune_memory_is_off_by_default():
    final, drafts, metrics, _ = _metrics(ExperimentConfig(seed=1, node_count=40, p_same=0.4))
    assert not any(n.immune_participant for n in final.nodes.values())
    assert final.signatures == () and final.benign_probes == 0
    assert not _types(drafts, "THREAT_SIGNATURE_RECEIVED")
    assert all("immune_participant" not in d.metadata for d in drafts)
    assert metrics["immunity_coverage"] is None
    assert metrics["signature_block_rate"] is None
    assert metrics["benign_block_rate"] is None


def test_coverage_and_placement_choose_the_participants():
    def participants(**fields):
        world, _ = build_world(ExperimentConfig(seed=6, node_count=40, immunity_enabled=True,
                                                **fields))
        degree = {n: len(node.neighbors) for n, node in world.nodes.items()}
        return {n for n, node in world.nodes.items() if node.immune_participant}, degree

    chosen, _ = participants(immunity_coverage=0.25)
    assert len(chosen) == 10
    hubs, degree = participants(immunity_coverage=0.25, immunity_placement="hubs")
    assert min(degree[n] for n in hubs) >= max(degree[n] for n in set(degree) - hubs)
    periphery, _ = participants(immunity_coverage=0.25, immunity_placement="periphery")
    assert max(degree[n] for n in periphery) <= min(degree[n] for n in set(degree) - periphery)
    assert participants(immunity_coverage=0.0)[0] == set()


def _attack(*, participant=True, signatures=(), tick=1, strain=0b1010, radius=0):
    """s (compromised, carrying `strain`) attacks t; certain to succeed
    unless immune memory blocks it."""
    config = ExperimentConfig(
        seed=1, p_same=1.0, p_cross=1.0, immunity_enabled=True, signature_radius=radius,
        signature_bits=8, strain_benign_distance=4,
    )
    nodes = {
        "s": AgentNode("s", "sw-a", C, ("t",), tick_compromised=0, strain=strain),
        "t": AgentNode("t", "sw-a", H, ("s",), immune_participant=participant),
    }
    world = WorldState(tick=tick, nodes=nodes, edges=(("s", "t"),), signatures=tuple(signatures))
    return world, config


def test_a_held_signature_blocks_the_attack_before_any_draw():
    world, config = _attack(signatures=[Signature(0b1010, True, adopt_tick=0)])
    after, drafts = propagation_step(world, config)
    assert after.nodes["t"].security_state == H
    assert [d.event_type.value for d in drafts] == ["COMPROMISE_ATTEMPTED", "COMPROMISE_FAILED"]
    assert drafts[1].metadata == {"probability": 1.0, "blocked_by_signature": True}


@pytest.mark.parametrize(
    "case",
    [
        dict(participant=False, signatures=[Signature(0b1010, True, adopt_tick=0)]),
        dict(signatures=[Signature(0b1010, True, adopt_tick=2)]),  # not adopted yet
        dict(signatures=[Signature(0b1011, True, adopt_tick=0)]),  # 1 bit away, radius 0
    ],
)
def test_no_protection_without_participation_adoption_or_a_close_enough_signature(case):
    world, config = _attack(**case)
    after, _ = propagation_step(world, config)
    assert after.nodes["t"].security_state == C


def test_the_radius_sets_how_far_a_variant_can_drift_and_still_be_caught():
    world, config = _attack(signatures=[Signature(0b1011, True, adopt_tick=0)], radius=1)
    after, _ = propagation_step(world, config)
    assert after.nodes["t"].security_state == H


def test_the_adaptive_attacker_is_blocked_too():
    world, config = _attack(signatures=[Signature(0b1010, True, adopt_tick=0)])
    config = config.model_copy(update={"active_scenarios": ["adaptive_attacker"]})
    after, drafts = adaptive_step(world, config)
    assert after.nodes["t"].security_state == H
    assert drafts[-1].metadata["blocked_by_signature"] is True


def test_a_blocked_real_agent_attack_never_reaches_the_model():
    world, config = _attack(signatures=[Signature(0b1010, True, adopt_tick=0)])
    for node in world.nodes.values():
        node.agent_kind = "real"
    world.nodes["t"].confidential_token = "TOKEN-0123"
    gateway = ModelGateway(
        MockProvider(), timeout_s=5.0, max_retries=0, max_concurrency=4,
        max_requests_per_experiment=10,
    )
    after, drafts = asyncio.run(real_agent_step(world, config, gateway, tick=1))
    assert after.nodes["t"].security_state == H
    assert gateway.requests_used == 0
    assert not _types(drafts, "MODEL_REQUESTED")
    assert drafts[-1].metadata == {
        "probability": 1.0, "real_agent": True, "blocked_by_signature": True,
    }


def _immune_run(**fields):
    base = dict(
        seed=3, node_count=60, p_same=0.5, p_cross=0.2, immunity_enabled=True,
        detector_sensitivity=0.5, max_ticks=40,
    )
    return _metrics(ExperimentConfig(**(base | fields)))


def test_a_detection_publishes_the_strain_and_participants_adopt_it_after_the_delay():
    final, drafts, metrics, _ = _immune_run(signature_delay_ticks=2)
    published = _types(drafts, "THREAT_SIGNATURE_PUBLISHED")
    received = _types(drafts, "THREAT_SIGNATURE_RECEIVED")
    assert published and len(received) == len(published)
    participants = sum(n.immune_participant for n in final.nodes.values())
    for pub, rec in zip(published, received, strict=True):
        assert pub.metadata["legitimate"] is True
        assert rec.metadata["signature"] == pub.metadata["signature"]
        assert rec.sim_tick == pub.sim_tick + 2
        assert rec.metadata["adopters"] == participants
    # One signature per distinct strain: without mutation, every detection
    # finds patient zero's.
    assert len(published) == 1
    assert metrics["immunity_coverage"] == participants / len(final.nodes)


def test_preseeding_holds_patient_zeros_strain_before_any_attack():
    final, drafts, metrics, _ = _immune_run(preseed_patient_zero_signature=True)
    assert final_size(final) == 1 / len(final.nodes)  # nobody else is ever infected
    assert metrics["signature_block_rate"] == 1.0
    first = _types(drafts, "THREAT_SIGNATURE_PUBLISHED")[0]
    assert first.sim_tick == 0 and first.metadata["preseeded"] is True


def test_higher_coverage_means_smaller_outbreaks():
    def mean_final_size(coverage):
        return mean(
            final_size(
                _immune_run(seed=seed, immunity_coverage=coverage, signature_delay_ticks=0)[0]
            )
            for seed in range(8)
        )

    sizes = [mean_final_size(c) for c in (0.0, 0.5, 1.0)]
    assert sizes[0] > sizes[1] > sizes[2]


def test_a_wider_radius_blocks_more_variants_and_more_benign_traffic():
    """[S1]'s trade-off. Every transmission mutates one bit, so an exact match
    (radius 0) almost never catches the next variant; radius 6 catches them,
    and also reaches benign traffic, which sits within 6 bits of the
    centroid. Averaged over seeds."""

    def rates(radius):
        runs = [
            _immune_run(
                seed=seed, p_same=0.6, p_cross=0.3, detector_sensitivity=0.3,
                mutation_rate=1.0, mutation_bits=1, signature_radius=radius,
                strain_benign_distance=6, benign_probes_per_tick=4, signature_delay_ticks=0,
            )[2]
            for seed in range(8)
        ]
        return (
            mean(m["signature_block_rate"] for m in runs),
            mean(m["benign_block_rate"] for m in runs),
            mean(m["final_size"] for m in runs),
        )

    narrow, wide = rates(0), rates(6)
    assert wide[0] > narrow[0] + 0.5  # variants caught
    assert wide[1] > narrow[1]  # benign traffic blocked
    assert wide[2] < narrow[2]  # smaller outbreaks


def test_prevalence_counts_healthy_participants_as_immune_once_a_signature_is_held():
    final, drafts, _, tally = _immune_run(preseed_patient_zero_signature=True)
    rows = tally.prevalence(final.tick)
    healthy_participants = sum(
        n.immune_participant and n.security_state == H for n in final.nodes.values()
    )
    assert rows[-1][3] == healthy_participants > 0


def test_poisoned_signatures_cost_benign_traffic_and_stop_no_worm():
    common = dict(
        seed=4, node_count=50, p_same=0.5, p_cross=0.2, sentinel_count=2,
        sentinel_compromise_rate=1.0, active_scenarios=["propagation", "sentinel_compromise"],
        immunity_enabled=True, signature_radius=6, strain_benign_distance=24,
        detector_sensitivity=0.0, max_ticks=30,
    )
    final, drafts, metrics, _ = _metrics(ExperimentConfig(**common))
    poisoned = [
        d for d in _types(drafts, "THREAT_SIGNATURE_PUBLISHED")
        if d.metadata["legitimate"] is False
    ]
    assert poisoned and all("signature" in d.metadata for d in poisoned)
    assert metrics["benign_block_rate"] > 0
    assert metrics["signature_block_rate"] == 0.0  # a benign-looking signature stops no worm
    assert metrics["immunity_coverage"] == 0.0  # nothing legitimate is held


def test_the_radius_cannot_exceed_the_strain_length():
    with pytest.raises(ValidationError):
        ExperimentConfig(seed=1, signature_bits=16, strain_benign_distance=8, signature_radius=17)


def test_benign_vectors_stay_within_the_worm_distance_of_the_centroid():
    config = ExperimentConfig(seed=2, strain_benign_distance=10)
    centroid = strains.benign_centroid(config)
    distances = {
        strains.distance(immunity.benign_vector(config, t, "a", "benign_probe:0"), centroid)
        for t in range(200)
    }
    assert max(distances) <= 10 and len(distances) > 5
