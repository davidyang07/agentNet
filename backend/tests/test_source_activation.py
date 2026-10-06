"""SPEC §3.4 rule 7: a newly compromised agent becomes a source only from the
next tick. Real-agent compromises are stamped with the post-increment tick
(they run after advance()), so without an explicit rule a node compromised by
a real agent at tick T was already attacking at tick T (PLAN 14.2 A.7)."""

import pytest

from app.benchmark.runner import run_headless_async
from app.engine import propagation
from app.engine.state import AgentNode, SecurityState, WorldState
from app.scenarios import adaptive_attacker_scenario
from app.schemas.experiment import ExperimentConfig


def _pair(*, tick: int, compromised_by: str | None, tick_compromised: int) -> WorldState:
    return WorldState(
        tick=tick,
        nodes={
            "agent-000": AgentNode(
                id="agent-000",
                software_type="sw-a",
                security_state=SecurityState.COMPROMISED,
                neighbors=("agent-001",),
                compromised_by=compromised_by,
                tick_compromised=tick_compromised,
            ),
            "agent-001": AgentNode(
                id="agent-001",
                software_type="sw-a",
                security_state=SecurityState.HEALTHY,
                neighbors=("agent-000",),
            ),
        },
        edges=(("agent-000", "agent-001"),),
    )


CONFIG = ExperimentConfig(seed=1, p_same=1.0, p_cross=1.0)


@pytest.mark.parametrize("attacker", [propagation.step, adaptive_attacker_scenario.step])
def test_an_agent_compromised_this_tick_does_not_attack_yet(attacker):
    _, drafts = attacker(_pair(tick=5, compromised_by="agent-009", tick_compromised=5), CONFIG)
    assert drafts == []


@pytest.mark.parametrize("attacker", [propagation.step, adaptive_attacker_scenario.step])
def test_an_agent_compromised_last_tick_attacks(attacker):
    _, drafts = attacker(_pair(tick=5, compromised_by="agent-009", tick_compromised=4), CONFIG)
    assert any(d.event_type.value == "COMPROMISE_ATTEMPTED" for d in drafts)


@pytest.mark.parametrize("attacker", [propagation.step, adaptive_attacker_scenario.step])
def test_the_seeded_compromise_attacks_from_tick_zero(attacker):
    _, drafts = attacker(_pair(tick=0, compromised_by=None, tick_compromised=0), CONFIG)
    assert any(d.event_type.value == "COMPROMISE_ATTEMPTED" for d in drafts)


@pytest.mark.parametrize("attacker", ["propagation", "adaptive_attacker"])
def test_no_agent_attacks_in_the_tick_it_was_compromised(attacker):
    """The invariant over a whole hybrid run's event log, through the same
    headless runner the benchmarks use."""
    run = run_headless_async(
        "rule7",
        ExperimentConfig(
            seed=42,
            node_count=40,
            real_agent_count=10,
            p_same=0.6,
            p_cross=0.2,
            max_ticks=60,
            active_scenarios=[attacker, "prompt_injection"],
        ),
    )
    compromised_at: dict[str, int] = {}
    seeded: set[str] = set()
    violations = []
    for e in run.events:
        etype = e.event_type.value
        if etype == "COMPROMISE_SUCCEEDED" and e.metadata.get("initial_compromise"):
            seeded.add(e.target_agent_id)
        elif etype == "COMPROMISE_SUCCEEDED" and not e.metadata.get("already_compromised"):
            compromised_at.setdefault(e.target_agent_id, e.sim_tick)
        elif etype == "COMPROMISE_ATTEMPTED" and e.source_agent_id not in seeded:
            if e.sim_tick <= compromised_at[e.source_agent_id]:
                violations.append((e.source_agent_id, e.sim_tick))
    assert any(e.metadata.get("real_agent") for e in run.events), "fixture must use real agents"
    assert violations == []
