"""Run lifecycle (PLAN 14.3 B.2): ended runs leave memory after a TTL --
their durable record is in Postgres -- instead of every run ever created
staying in the registry (~3.4 MB each for a 100-agent run), and the number
of concurrently active runs is capped."""

import asyncio

from fastapi.testclient import TestClient

from app.api import routes_experiments
from app.config import Settings
from app.main import app
from app.orchestrator.registry import ExperimentRegistry
from app.orchestrator.runner import ExperimentRunner
from app.schemas.experiment import ExperimentConfig


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _runner(max_ticks: int = 3) -> ExperimentRunner:
    runner = ExperimentRunner(ExperimentConfig(seed=42, node_count=25, max_ticks=max_ticks))
    runner.tick_interval = 0
    return runner


async def _finish(runner: ExperimentRunner) -> None:
    await runner.publish_initial()
    await runner._run_loop()


def test_every_way_a_run_ends_records_when():
    finished = _runner()
    asyncio.run(_finish(finished))
    assert finished.status == "finished" and finished.ended_at is not None

    async def stop_one() -> ExperimentRunner:
        runner = _runner(max_ticks=2000)
        await runner.publish_initial()
        runner.start()
        await asyncio.sleep(0)
        await runner.stop()
        return runner

    stopped = asyncio.run(stop_one())
    assert stopped.status == "stopped" and stopped.ended_at is not None
    assert _runner().ended_at is None


def test_an_ended_run_is_evicted_after_the_ttl_and_an_active_one_never_is():
    clock = FakeClock()
    reg = ExperimentRegistry(finished_run_ttl_s=60, clock=clock)
    ended, active = _runner(), _runner(max_ticks=2000)
    ended.ended_at = clock.now
    reg.add(ended)
    reg.add(active)

    clock.now += 59
    assert reg.get(ended.experiment_id) is ended

    clock.now += 2
    assert reg.get(ended.experiment_id) is None
    assert reg.get(active.experiment_id) is active
    assert reg.active_count() == 1


def test_creating_beyond_the_active_run_cap_is_refused_with_429(monkeypatch):
    monkeypatch.setattr(
        routes_experiments, "get_settings", lambda: Settings(max_active_experiments=1)
    )
    with TestClient(app) as client:
        body = {"seed": 1, "node_count": 25, "max_ticks": 2000}
        first = client.post("/api/experiments", json=body)
        try:
            assert first.status_code == 201
            second = client.post("/api/experiments", json=body)
            assert second.status_code == 429, second.text
        finally:
            client.post(f"/api/experiments/{first.json()['experiment_id']}/stop")
        # Stopping the first run frees its slot.
        assert client.post("/api/experiments", json=body | {"max_ticks": 1}).status_code == 201
