"""Database time bounds (PLAN 14.3 B.4): a database that accepts connections
but never answers used to block POST /api/experiments indefinitely (measured
>20 s through a freezing proxy), because pool operations had no timeouts and
the writer's first insert ran inline in the request."""

import asyncio
from types import SimpleNamespace

from app import db
from app.api.routes_experiments import create_experiment
from app.config import Settings
from app.orchestrator.registry import registry
from app.persistence import writer as writer_module
from app.persistence.registry import writer_registry
from app.schemas.experiment import ExperimentConfig


class HangingPool:
    """Accepts every call and never answers, like a frozen database."""

    async def execute(self, *args, **kwargs):
        await asyncio.Event().wait()


def test_the_pool_bounds_connect_and_command_time(monkeypatch):
    captured = {}

    async def fake_create_pool(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(db.asyncpg, "create_pool", fake_create_pool)
    asyncio.run(db.create_pool(Settings()))
    assert captured["timeout"] > 0
    assert captured["command_timeout"] > 0


def test_a_hung_database_does_not_block_experiment_creation(monkeypatch):
    monkeypatch.setattr(writer_module, "WRITER_START_TIMEOUT_S", 0.2)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(pg_pool=HangingPool(), http_client=None))
    )

    async def main():
        summary = await asyncio.wait_for(
            create_experiment(ExperimentConfig(seed=1, node_count=25, max_ticks=2000), request),
            timeout=3,
        )
        runner = registry.get(summary.experiment_id)
        try:
            return summary, runner.bus.subscriber_count
        finally:
            await runner.stop()
            registry.remove(summary.experiment_id)

    summary, subscribers = asyncio.run(main())
    assert summary.status == "running"
    # The run proceeds without persistence, and the failed writer left no
    # subscription behind on the run's bus.
    assert writer_registry.get(summary.experiment_id) is None
    assert subscribers == 0
