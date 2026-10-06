"""Regression test for a bug found while building the benchmark harness:
app/engine/propagation.py, app/security/detection.py (quarantine path), and
app/scenarios/adaptive_attacker_scenario.py all constructed a fresh
WorldState without carrying forward `compromised_graph_nodes`, silently
resetting any sentinel/credential/security-control compromise to empty
every tick they ran -- which broke the sentinel_compromise/
byzantine_collusion scenarios' documented "stays compromised" persistence
whenever composed with propagation (their intended, documented use, per
docs/PLAN.md §5's own worked examples). No existing test caught this because
the runner integration test only asserted "finished" and "deterministic",
never accumulated graph-node compromise across ticks.
"""

import asyncio

from app.agents.runtime import real_agent_step
from app.engine.state import AgentNode, SecurityState, WorldState
from app.engine.tick import advance
from app.engine.topology import build_world
from app.gateway.gateway import ModelGateway
from app.gateway.mock_provider import MockProvider
from app.schemas.experiment import ExperimentConfig


def test_sentinel_compromise_persists_across_propagation_ticks():
    config = ExperimentConfig(
        seed=42,
        node_count=25,
        max_ticks=15,
        sentinel_count=1,
        active_scenarios=["propagation", "sentinel_compromise"],
        sentinel_compromise_rate=1.0,
        defense_enabled=False,
    )
    state, _ = build_world(config)
    for _ in range(15):
        state, _ = advance(state, config)
    assert "sentinel-000" in state.compromised_graph_nodes


def test_sentinel_compromise_persists_through_a_legitimate_quarantine_tick():
    """detection.step's quarantine branch (defense_enabled=True) must not
    wipe an already-recorded sentinel/credential compromise either."""
    config = ExperimentConfig(
        seed=42,
        node_count=25,
        max_ticks=15,
        sentinel_count=1,
        active_scenarios=["propagation", "sentinel_compromise"],
        sentinel_compromise_rate=1.0,
        defense_enabled=True,
        detector_sensitivity=1.0,
    )
    state, _ = build_world(config)
    for _ in range(15):
        state, _ = advance(state, config)
    assert "sentinel-000" in state.compromised_graph_nodes


def test_real_agent_step_preserves_compromised_graph_nodes_when_it_compromises():
    """app/agents/runtime.py::real_agent_step had the same bug the three sync
    step functions above were fixed for: on any tick where a real agent won a
    target, it rebuilt WorldState without `compromised_graph_nodes`, silently
    un-subverting every sentinel/credential compromised so far."""

    def real(node_id: str, state: SecurityState, neighbor: str) -> AgentNode:
        return AgentNode(
            id=node_id,
            software_type="sw-a",
            security_state=state,
            neighbors=(neighbor,),
            agent_kind="real",
            confidential_token=f"TOKEN-{node_id}",
        )

    state = WorldState(
        tick=3,
        nodes={
            "agent-000": real("agent-000", SecurityState.COMPROMISED, "agent-001"),
            "agent-001": real("agent-001", SecurityState.HEALTHY, "agent-000"),
        },
        edges=(("agent-000", "agent-001"),),
        compromised_graph_nodes=frozenset({"sentinel-000", "credential-000"}),
    )
    config = ExperimentConfig(seed=42, p_same=1.0, p_cross=1.0)
    gateway = ModelGateway(
        MockProvider(),
        timeout_s=5.0,
        max_retries=0,
        max_concurrency=4,
        max_requests_per_experiment=10,
    )

    new_state, _ = asyncio.run(real_agent_step(state, config, gateway, tick=3))

    assert new_state.nodes["agent-001"].security_state == SecurityState.COMPROMISED
    assert new_state.compromised_graph_nodes == {"sentinel-000", "credential-000"}
