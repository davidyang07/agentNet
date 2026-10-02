from app.engine.propagation import is_finished
from app.engine.state import AgentNode, SecurityState, WorldState
from app.engine.tick import advance
from app.engine.topology import build_world
from app.schemas.experiment import ExperimentConfig


def _two_node_world() -> WorldState:
    nodes = {
        "agent-000": AgentNode(
            id="agent-000",
            software_type="sw-a",
            security_state=SecurityState.COMPROMISED,
            neighbors=("agent-001",),
            compromised_by=None,
            tick_compromised=0,
        ),
        "agent-001": AgentNode(
            id="agent-001",
            software_type="sw-a",
            security_state=SecurityState.HEALTHY,
            neighbors=("agent-000",),
        ),
    }
    edges = (("agent-000", "agent-001"),)
    return WorldState(tick=0, nodes=nodes, edges=edges)


def test_advance_concatenates_propagation_then_security_drafts_in_order():
    world = _two_node_world()
    config = ExperimentConfig(
        seed=42, node_count=25, p_same=1.0, defense_enabled=True, detector_sensitivity=1.0
    )

    new_world, drafts = advance(world, config)

    event_types = [d.event_type.value for d in drafts]
    # propagation drafts (COMPROMISE_*) must precede security drafts
    # (ANOMALY_DETECTED / AGENT_QUARANTINED) within this single advance() call.
    last_propagation_index = max(
        i for i, t in enumerate(event_types) if t.startswith("COMPROMISE_")
    )
    first_security_index = min(
        i for i, t in enumerate(event_types) if t in ("ANOMALY_DETECTED", "AGENT_QUARANTINED")
    )
    assert last_propagation_index < first_security_index

    # detector_sensitivity=1.0 guarantees agent-000 is quarantined this tick.
    assert new_world.nodes["agent-000"].security_state == SecurityState.QUARANTINED


def test_advance_with_defense_disabled_matches_propagation_step_alone():
    from app.engine.propagation import step as propagation_step

    world = _two_node_world()
    config = ExperimentConfig(seed=42, node_count=25, defense_enabled=False)

    expected_world, expected_drafts = propagation_step(world, config)
    actual_world, actual_drafts = advance(world, config)

    assert actual_world == expected_world
    assert actual_drafts == expected_drafts


def test_advance_moves_the_tick_exactly_once_whatever_the_active_scenarios():
    """Only the attacker scenarios (propagation, adaptive_attacker) advance
    the tick themselves. Without one -- an observe-only run, or only the
    composable security-plane scenarios -- the tick used to stay frozen, so
    no loop driving advance() could ever reach max_ticks."""
    for scenarios in (
        [],
        ["sentinel_compromise"],
        ["attestation", "byzantine_collusion"],
        ["prompt_injection"],
        ["propagation"],
        ["adaptive_attacker", "sentinel_compromise"],
    ):
        config = ExperimentConfig(seed=42, node_count=25, active_scenarios=scenarios)
        new_world, _ = advance(_two_node_world(), config)
        assert new_world.tick == 1, scenarios


def test_a_run_without_a_tick_owning_scenario_reaches_max_ticks_unattacked():
    # Bounded loop rather than simulate(), so a regression fails instead of hanging.
    for scenarios in ([], ["sentinel_compromise"], ["prompt_injection"]):
        config = ExperimentConfig(
            seed=42,
            node_count=25,
            max_ticks=20,
            defense_enabled=False,
            sentinel_count=1,
            sentinel_compromise_rate=0.5,
            active_scenarios=scenarios,
        )
        state, _ = build_world(config)
        drafts = []
        for _ in range(config.max_ticks):
            if is_finished(state, config):
                break
            state, tick_drafts = advance(state, config)
            drafts.extend(tick_drafts)

        assert is_finished(state, config), scenarios
        assert state.tick == config.max_ticks, scenarios
        assert not any(d.event_type.value == "COMPROMISE_ATTEMPTED" for d in drafts), scenarios
