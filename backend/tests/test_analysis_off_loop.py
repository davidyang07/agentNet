"""Heavy analysis stays off the event loop (PLAN 14.3 B.3). One
unreachable-target attack-paths query on the largest graph the API allows
used to take ~5 s of pure CPU inside an async route, freezing every live run
and WebSocket meanwhile."""

import asyncio
import time

import httpx

from app.api import routes_graph
from app.engine.simulate import simulate
from app.graph.analysis import attack_paths
from app.graph.builder import build_security_graph
from app.graph.types import NodeType
from app.main import app
from app.orchestrator.registry import registry
from app.orchestrator.runner import ExperimentRunner
from app.schemas.experiment import ExperimentConfig


def test_attack_paths_to_an_unreachable_target_return_at_once():
    # Defense off: no quarantined agents prune the search (which made the
    # defended case fast already), so this is the full ~5 s worst case.
    config = ExperimentConfig(
        seed=7, node_count=100, edge_density=5, sentinel_count=1, defense_enabled=False
    )
    final, _ = simulate(config)
    graph = build_security_graph(final, config)
    control = graph.nodes_of_type(NodeType.SECURITY_CONTROL)[0].id

    started = time.monotonic()
    assert attack_paths(graph, "agent-000", control) == []
    assert time.monotonic() - started < 1.0


def test_a_slow_analysis_request_does_not_block_other_requests(monkeypatch):
    def slow_critical_nodes(graph, *, top_n):
        time.sleep(0.5)  # stands in for heavy CPU work
        return []

    monkeypatch.setattr(routes_graph, "critical_nodes", slow_critical_nodes)
    runner = ExperimentRunner(ExperimentConfig(seed=1, node_count=25))
    registry.add(runner)
    finished: list[str] = []

    async def main() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            base = f"/api/experiments/{runner.experiment_id}"

            async def get(path: str, label: str) -> None:
                assert (await client.get(base + path)).status_code == 200
                finished.append(label)

            slow = asyncio.create_task(get("/analysis/critical-nodes", "slow"))
            await asyncio.sleep(0.05)
            await get("", "fast")
            await slow

    try:
        asyncio.run(main())
    finally:
        registry.remove(runner.experiment_id)
    assert finished == ["fast", "slow"]
