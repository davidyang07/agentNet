"""active_scenarios must be runnable: POST /api/experiments rejects unknown
names, duplicates, and both tick-owning attacker models together -- each of
which previously either hung the run at tick 0 (a typo leaves no attacker to
advance the tick) or advanced two ticks per tick (both attackers). Runs with
no attacker at all (observe-only) are valid and run to completion."""

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.gateway.factory import build_gateway
from app.main import app
from app.orchestrator.runner import ExperimentRunner
from app.scenarios.registry import active_scenarios_error
from app.schemas.experiment import ExperimentConfig


@pytest.mark.parametrize(
    "scenarios",
    [
        ["propogation"],
        ["propagation", "not-a-scenario"],
        ["propagation", "propagation"],
        ["sentinel_compromise", "sentinel_compromise"],
        ["propagation", "adaptive_attacker"],
    ],
)
def test_create_rejects_unrunnable_active_scenarios_with_422(scenarios):
    assert active_scenarios_error(scenarios) is not None
    with TestClient(app) as client:
        resp = client.post(
            "/api/experiments",
            json={"seed": 7, "node_count": 25, "max_ticks": 1, "active_scenarios": scenarios},
        )
    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize(
    "scenarios",
    [
        [],
        ["sentinel_compromise"],
        ["propagation", "prompt_injection"],
        ["adaptive_attacker", "sentinel_compromise", "attestation"],
    ],
)
def test_create_accepts_runnable_active_scenarios(scenarios):
    assert active_scenarios_error(scenarios) is None
    with TestClient(app) as client:
        resp = client.post(
            "/api/experiments",
            json={"seed": 7, "node_count": 25, "max_ticks": 1, "active_scenarios": scenarios},
        )
    assert resp.status_code == 201, resp.text


@pytest.mark.parametrize("scenarios", [[], ["prompt_injection"]])
def test_live_runner_without_an_attacker_scenario_runs_to_max_ticks(scenarios):
    """Through the live runner's own loop, including its async (real-agent)
    path -- the shape that used to spin at sim_tick 0 forever."""
    config = ExperimentConfig(
        seed=42,
        node_count=25,
        max_ticks=6,
        defense_enabled=False,
        real_agent_count=4,
        active_scenarios=scenarios,
    )

    async def run() -> ExperimentRunner:
        async with httpx.AsyncClient() as http_client:
            runner = ExperimentRunner(
                config, gateway=build_gateway(config, Settings(), http_client)
            )
            runner.tick_interval = 0
            await runner.publish_initial()
            await asyncio.wait_for(runner._run_loop(), timeout=10)
            return runner

    runner = asyncio.run(run())
    assert runner.status == "finished"
    assert runner.state.tick == config.max_ticks
