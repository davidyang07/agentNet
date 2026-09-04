from app.engine.propagation import step as propagation_step
from app.engine.state import AgentNode, SecurityState, WorldState
from app.scenarios.registry import SYNC_SCENARIOS, run_sync_scenarios
from app.schemas.experiment import ExperimentConfig


def _two_node_world() -> WorldState:
    nodes = {
        "agent-000": AgentNode(
            id="agent-000",
            software_type="sw-a",
            security_state=SecurityState.COMPROMISED,
            neighbors=("agent-001",),
            tick_compromised=0,
        ),
        "agent-001": AgentNode(
            id="agent-001",
            software_type="sw-a",
            security_state=SecurityState.HEALTHY,
            neighbors=("agent-000",),
        ),
    }
    return WorldState(tick=0, nodes=nodes, edges=(("agent-000", "agent-001"),))


def test_default_active_scenarios_matches_propagation_step_alone():
    world = _two_node_world()
    config = ExperimentConfig(seed=42, node_count=25, p_same=1.0)

    expected_world, expected_drafts = propagation_step(world, config)
    actual_world, actual_drafts = run_sync_scenarios(world, config)

    assert actual_world == expected_world
    assert actual_drafts == expected_drafts


def test_empty_active_scenarios_produces_no_drafts_and_unchanged_state():
    world = _two_node_world()
    config = ExperimentConfig(seed=42, node_count=25, active_scenarios=[])

    result_world, drafts = run_sync_scenarios(world, config)

    assert drafts == []
    assert result_world == world


def test_unknown_scenario_name_is_skipped_not_fatal():
    world = _two_node_world()
    config = ExperimentConfig(seed=42, node_count=25, active_scenarios=["not-a-real-scenario"])

    result_world, drafts = run_sync_scenarios(world, config)

    assert drafts == []
    assert result_world == world


def test_propagation_registered_under_its_name():
    assert "propagation" in SYNC_SCENARIOS
    assert SYNC_SCENARIOS["propagation"].name == "propagation"
