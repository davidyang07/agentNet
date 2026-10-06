"""Epidemic metrics (PLAN 14.4 C.1) on hand-built worlds with known answers,
plus invariants that must hold on any simulated run."""

from uuid import uuid4

from app.engine.simulate import simulate
from app.engine.state import AgentNode, SecurityState, WorldState
from app.events.emitter import EventEmitter
from app.metrics.compute import EventLogTally
from app.metrics.epidemic import (
    epidemic_report,
    final_size,
    generation_stats,
    generations,
    offspring,
    r0_estimate,
    r_effective,
    serial_interval,
)
from app.schemas.events import Event, EventType
from app.schemas.experiment import ExperimentConfig

C, H, Q = SecurityState.COMPROMISED, SecurityState.HEALTHY, SecurityState.QUARANTINED


def _node(node_id, state, by=None, tick=None, neighbors=()):
    return AgentNode(
        id=node_id,
        software_type="sw-a",
        security_state=state,
        compromised_by=by,
        tick_compromised=tick,
        neighbors=tuple(neighbors),
    )


def _tree() -> WorldState:
    """s (seed, t0) -> a (t1), b (t1); a -> c (t3); b -> d (t2); d -> e (t4).
    c is quarantined; e still borders a healthy agent, h."""
    nodes = [
        _node("s", C, tick=0, neighbors=("a", "b")),
        _node("a", C, "s", 1, ("s", "c")),
        _node("b", C, "s", 1, ("s", "d")),
        _node("c", Q, "a", 3, ("a",)),
        _node("d", C, "b", 2, ("b", "e")),
        _node("e", C, "d", 4, ("d", "h")),
        _node("h", H, neighbors=("e",)),
    ]
    return WorldState(tick=5, nodes={n.id: n for n in nodes}, edges=())


def test_generations_follow_the_first_winner_chain():
    assert generations(_tree()) == {"s": 0, "a": 1, "b": 1, "c": 2, "d": 2, "e": 3}


def test_generations_do_not_depend_on_tick_or_id_order():
    """The seed infects from tick 0, so a source can share its target's tick.
    Here b also sorts before its source m."""
    nodes = [
        _node("z", C, tick=0),
        _node("m", C, "z", 1),
        _node("b", C, "m", 1),
        _node("c", C, "b", 2),
    ]
    world = WorldState(tick=3, nodes={n.id: n for n in nodes}, edges=())
    assert generations(world) == {"z": 0, "m": 1, "b": 2, "c": 3}


def test_offspring_counts_every_infected_agent_including_dead_ends():
    assert offspring(_tree()) == {"s": 2, "a": 1, "b": 1, "c": 0, "d": 1, "e": 0}


def test_r_effective_is_the_mean_offspring_of_each_tick_cohort():
    """Only e's cohort is censored: e can still infect h. a, b and d are
    still compromised too, but have no healthy neighbour left, so their
    offspring counts are final."""
    assert r_effective(_tree()) == [
        (0, 2.0, False),
        (1, 1.0, False),
        (2, 1.0, False),
        (3, 0.0, False),
        (4, 0.0, True),
    ]


def test_r0_serial_interval_and_final_size():
    world = _tree()
    assert r0_estimate(world) == 4 / 3  # s, a, b: (2 + 1 + 1) / 3
    assert serial_interval(world) == 7 / 5  # gaps 1, 1, 2, 1, 2
    assert final_size(world) == 6 / 7


def test_generation_stats():
    assert generation_stats(_tree()) == [(0, 1, 2.0), (1, 2, 1.0), (2, 2, 0.5), (3, 1, 0.0)]


def test_no_infection_has_no_r0_or_serial_interval():
    world = WorldState(tick=0, nodes={"h": _node("h", H)}, edges=())
    assert r0_estimate(world) is None
    assert serial_interval(world) is None
    assert final_size(world) == 0.0
    assert r_effective(world) == []


def _event(event_type, tick, *, agent=None, target=None, **metadata) -> Event:
    return Event(
        sim_tick=tick,
        event_type=event_type,
        agent_id=agent,
        target_agent_id=target,
        event_id=uuid4(),
        seq=0,
        experiment_id=uuid4(),
        wall_time="2026-01-01T00:00:00Z",
        metadata=metadata,
    )


def _prevalence_log() -> list[Event]:
    return [
        _event(EventType.COMPROMISE_SUCCEEDED, 0, target="s", initial_compromise=True),
        _event(EventType.COMPROMISE_SUCCEEDED, 0, target="a"),
        _event(EventType.COMPROMISE_SUCCEEDED, 0, target="b"),
        _event(EventType.AGENT_QUARANTINED, 1, agent="a"),
        _event(EventType.AGENT_QUARANTINED, 1, agent="h", legitimate=False),
        _event(EventType.COMPROMISE_SUCCEEDED, 2, target="b", already_compromised=True),
        _event(EventType.COMPROMISE_SUCCEEDED, 2, target="d"),
        # Nothing happens at tick 3; the run ends at tick 4.
    ]


def test_prevalence_is_folded_per_tick_and_fills_quiet_ticks():
    tally = EventLogTally.of(_prevalence_log())
    assert tally.prevalence(final_tick=4) == [
        (0, 3, 0),
        (1, 2, 2),  # a quarantined; h falsely quarantined while healthy
        (2, 3, 2),  # a duplicate win on b is not a new infection
        (3, 3, 2),
        (4, 3, 2),
    ]


def test_prevalence_does_not_depend_on_batching():
    log = _prevalence_log()
    tally = EventLogTally()
    for i in range(0, len(log), 2):
        tally.add(log[i : i + 2])
    assert tally.prevalence(4) == EventLogTally.of(log).prevalence(4)


def test_a_snapshot_does_not_see_later_events():
    log = _prevalence_log()
    tally = EventLogTally.of(log[:3])
    frozen = tally.snapshot()
    tally.add(log[3:])
    assert frozen.prevalence(1) == [(0, 3, 0), (1, 3, 0)]


def test_report_on_a_simulated_run_is_internally_consistent():
    config = ExperimentConfig(seed=11, node_count=60, p_same=0.3, p_cross=0.1, max_ticks=30)
    final, drafts = simulate(config)
    tally = EventLogTally.of(EventEmitter(uuid4()).emit(drafts))
    report = epidemic_report(final, tally)

    infected = [n for n in final.nodes.values() if n.tick_compromised is not None]
    assert sum(g["nodes"] for g in report["generations"]) == len(infected)
    assert sum(offspring(final).values()) == len(infected) - 1  # every infection but the seed
    assert [p["tick"] for p in report["prevalence"]] == list(range(final.tick + 1))
    # Every agent ever infected is infectious or quarantined at the end
    # (nothing recovers yet), and the fold agrees with the state.
    last = report["prevalence"][-1]
    assert last["infectious"] == sum(n.security_state == C for n in final.nodes.values())
    assert last["quarantined"] == sum(n.security_state == Q for n in final.nodes.values())


def test_the_live_endpoint_reports_the_runs_curve_and_tree():
    import asyncio

    from fastapi.testclient import TestClient

    from app.main import app
    from app.orchestrator.registry import registry
    from app.orchestrator.runner import ExperimentRunner

    runner = ExperimentRunner(ExperimentConfig(seed=3, node_count=30, p_same=0.4, max_ticks=8))
    runner.tick_interval = 0

    async def run() -> None:
        await runner.publish_initial()
        await runner._run_loop()

    asyncio.run(run())
    with TestClient(app) as client:
        registry.add(runner)
        try:
            body = client.get(f"/api/experiments/{runner.experiment_id}/epidemic").json()
            metrics = client.get(f"/api/experiments/{runner.experiment_id}/metrics").json()
        finally:
            registry.remove(runner.experiment_id)
        assert client.get(f"/api/experiments/{uuid4()}/epidemic").status_code == 404

    assert body == epidemic_report(runner.state, runner.event_tally)
    seed = next(n for n, g in generations(runner.state).items() if g == 0)
    assert body["generations"][0] == {
        "generation": 0,
        "nodes": 1,
        "mean_offspring": offspring(runner.state)[seed],
    }
    assert metrics["final_size"] == final_size(runner.state)
    assert metrics["r0_estimate"] == r0_estimate(runner.state)
