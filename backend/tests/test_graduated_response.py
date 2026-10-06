"""Realistic detection and graduated response (PLAN 14.4 C.5, after [S1]:
change-point detection needs evidence, and false positives are
"autoimmune")."""

import asyncio
from statistics import mean
from uuid import uuid4

from app.agents.runtime import real_agent_step
from app.engine.propagation import step as propagation_step
from app.engine.simulate import simulate
from app.engine.state import AgentNode, SecurityState, WorldState
from app.events.emitter import EventEmitter
from app.gateway.gateway import ModelGateway
from app.gateway.mock_provider import MockProvider
from app.graph.builder import build_security_graph
from app.metrics.compute import (
    EventLogTally,
    all_metrics,
    blast_radius_fraction,
    compromise_fraction,
    retained_utility,
)
from app.schemas.experiment import ExperimentConfig
from app.security.detection import detection_probability
from app.security.detection import step as detection_step

C, H, Q, S = (
    SecurityState.COMPROMISED,
    SecurityState.HEALTHY,
    SecurityState.QUARANTINED,
    SecurityState.SUSPICIOUS,
)


def _run(**fields):
    base = dict(seed=3, node_count=60, p_same=0.4, p_cross=0.1, max_ticks=40)
    config = ExperimentConfig(**(base | fields))
    final, drafts = simulate(config)
    tally = EventLogTally.of(EventEmitter(uuid4()).emit(drafts))
    metrics = all_metrics(final, build_security_graph(final, config), tally)
    return final, drafts, metrics


def _of(drafts, event_type):
    return [d for d in drafts if d.event_type.value == event_type]


def test_defaults_keep_single_step_quarantine():
    final, drafts, metrics = _run()
    assert all(n.security_state != S for n in final.nodes.values())
    assert all("response" not in d.metadata for d in _of(drafts, "ANOMALY_DETECTED"))
    assert all("false_positive" not in d.metadata for d in drafts)
    assert not _of(drafts, "AGENT_RELEASED")
    assert metrics["containment_latency"] is None


def test_the_ramp_raises_detection_linearly_to_the_sensitivity():
    config = ExperimentConfig(seed=1, detector_sensitivity=0.8, detector_ramp_ticks=4)
    node = AgentNode("a", "sw-a", C, (), tick_compromised=10)
    assert [detection_probability(node, config, t) for t in (10, 12, 14, 20)] == [
        0.0, 0.4, 0.8, 0.8,
    ]
    flat = config.model_copy(update={"detector_ramp_ticks": 0})
    assert detection_probability(node, flat, 10) == 0.8


def test_a_ramp_delays_detection():
    def latency(ramp):
        return mean(
            _run(seed=seed, detector_sensitivity=0.6, detector_ramp_ticks=ramp)[2][
                "detection_latency"
            ] or 0
            for seed in range(8)
        )

    assert latency(6) > latency(0)


def test_false_positives_quarantine_healthy_agents_without_counting_as_detections():
    final, drafts, metrics = _run(
        detector_sensitivity=0.0, detector_false_positive_rate=0.05, max_ticks=10
    )
    detected = _of(drafts, "ANOMALY_DETECTED")
    assert detected and all(d.metadata["false_positive"] is True for d in detected)
    quarantined = _of(drafts, "AGENT_QUARANTINED")
    assert {d.agent_id for d in quarantined} == {d.agent_id for d in detected}
    assert all(d.metadata == {"false_positive": True} for d in quarantined)
    assert all(final.nodes[d.agent_id].tick_compromised is None for d in detected)
    # Nothing infected was ever detected, so there is no latency to report.
    assert metrics["detection_latency"] is None
    assert metrics["false_quarantine_rate"] == 0.0  # the detector's error, not the attack


def test_a_false_positive_publishes_benign_behaviour_so_autoimmunity_emerges():
    _, drafts, metrics = _run(
        detector_sensitivity=0.0, detector_false_positive_rate=0.05, immunity_enabled=True,
        signature_radius=6, strain_benign_distance=12, benign_probes_per_tick=3,
    )
    assert _of(drafts, "THREAT_SIGNATURE_PUBLISHED")
    assert metrics["benign_block_rate"] > 0
    assert metrics["signature_block_rate"] == 0.0  # it stops no worm


def _graduated(**fields):
    return _run(**({"response_mode": "graduated", "detector_sensitivity": 0.4} | fields))


def test_a_first_detection_flags_and_a_second_quarantines():
    _, drafts, metrics = _graduated()
    responses: dict[str, list[str]] = {}
    for d in _of(drafts, "ANOMALY_DETECTED"):
        responses.setdefault(d.agent_id, []).append(d.metadata["response"])
    assert responses
    for agent, sequence in responses.items():
        assert sequence[0] == "suspicious"
        if "quarantine" in sequence:
            quarantine = sequence.index("quarantine")
            assert sequence[quarantine - 1] == "suspicious"
    # Detection and quarantine are now separate steps.
    assert metrics["containment_latency"] is not None and metrics["containment_latency"] >= 1


def test_an_agent_not_detected_again_is_released_to_what_it_was():
    final, drafts, _ = _graduated(detector_sensitivity=0.15, review_ticks=3)
    released = _of(drafts, "AGENT_RELEASED")
    assert released
    for d in released:
        assert d.metadata["from"] == "suspicious"
        # Without false positives, everything flagged is infected.
        assert d.metadata["to"] == "compromised"


def test_a_released_false_positive_is_healthy_again():
    _, drafts, _ = _graduated(
        detector_sensitivity=0.0, detector_false_positive_rate=0.05, review_ticks=2, max_ticks=15
    )
    released = _of(drafts, "AGENT_RELEASED")
    assert released and all(d.metadata["to"] == "healthy" for d in released)


def _suspicious_source(
    factor: float, kind: str = "simulated"
) -> tuple[WorldState, ExperimentConfig]:
    config = ExperimentConfig(
        seed=1, p_same=1.0, p_cross=1.0, response_mode="graduated",
        suspicious_transmission_factor=factor,
    )
    nodes = {
        "s": AgentNode("s", "sw-a", S, ("t",), tick_compromised=0, suspicious_since=1,
                       agent_kind=kind),
        "t": AgentNode("t", "sw-a", H, ("s",), agent_kind=kind,
                       confidential_token="TOKEN-0123" if kind == "real" else None),
    }
    return WorldState(tick=1, nodes=nodes, edges=(("s", "t"),)), config


def test_a_suspicious_source_transmits_at_a_scaled_probability():
    world, config = _suspicious_source(0.0)
    after, drafts = propagation_step(world, config)
    assert after.nodes["t"].security_state == H
    assert drafts[0].metadata == {"probability": 0.0, "suspicious_source": True}

    world, config = _suspicious_source(1.0)
    after, _ = propagation_step(world, config)
    assert after.nodes["t"].security_state == C


def test_a_suspicious_real_agents_message_is_throttled_before_the_model():
    world, config = _suspicious_source(0.0, kind="real")
    gateway = ModelGateway(
        MockProvider(), timeout_s=5.0, max_retries=0, max_concurrency=4,
        max_requests_per_experiment=10,
    )
    after, drafts = asyncio.run(real_agent_step(world, config, gateway, tick=1))
    assert after.nodes["t"].security_state == H
    assert gateway.requests_used == 0
    assert drafts[-1].metadata["throttled_suspicious"] is True


def test_an_uninfected_suspicious_agent_can_still_be_infected():
    config = ExperimentConfig(seed=1, p_same=1.0, p_cross=1.0, response_mode="graduated")
    nodes = {
        "s": AgentNode("s", "sw-a", C, ("t",), tick_compromised=0),
        "t": AgentNode("t", "sw-a", S, ("s",), suspicious_since=0),
    }
    after, _ = propagation_step(WorldState(tick=1, nodes=nodes, edges=(("s", "t"),)), config)
    assert after.nodes["t"].security_state == C
    assert after.nodes["t"].suspicious_since is None


def test_compromise_metrics_count_infected_suspicious_agents():
    config = ExperimentConfig(seed=1, response_mode="graduated")
    nodes = {
        "a": AgentNode("a", "sw-a", S, ("b",), tick_compromised=0, suspicious_since=1),
        "b": AgentNode("b", "sw-a", H, ("a", "c")),
        "c": AgentNode("c", "sw-a", S, ("b",), suspicious_since=1),  # a false positive
        "d": AgentNode("d", "sw-a", H, ()),
    }
    world = WorldState(tick=2, nodes=nodes, edges=(("a", "b"), ("b", "c")))
    assert compromise_fraction(world) == 0.25
    assert retained_utility(world) == 0.75
    assert blast_radius_fraction(build_security_graph(world, config)) == 0.75


def test_a_second_detection_of_a_flagged_agent_quarantines_it():
    config = ExperimentConfig(seed=1, response_mode="graduated", detector_sensitivity=1.0)
    nodes = {"a": AgentNode("a", "sw-a", S, (), tick_compromised=0, suspicious_since=1)}
    after, drafts = detection_step(WorldState(tick=2, nodes=nodes, edges=()), config)
    assert after.nodes["a"].security_state == Q
    assert [d.event_type.value for d in drafts] == ["ANOMALY_DETECTED", "AGENT_QUARANTINED"]
    assert drafts[0].metadata["response"] == "quarantine"
