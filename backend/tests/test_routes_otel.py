import asyncio

from fastapi.testclient import TestClient

from app.main import app
from app.orchestrator.registry import registry
from app.orchestrator.runner import ExperimentRunner
from app.schemas.experiment import ExperimentConfig


def _start_experiment(client: TestClient, **overrides) -> dict:
    body = {"seed": 7, "node_count": 25, "max_ticks": 1}
    body.update(overrides)
    resp = client.post("/api/experiments", json=body)
    assert resp.status_code == 201
    return resp.json()


def test_otel_trace_endpoint_returns_a_valid_resource_spans_shape():
    with TestClient(app) as client:
        exp_id = _start_experiment(client)["experiment_id"]
        resp = client.get(f"/api/experiments/{exp_id}/otel-trace")
        assert resp.status_code == 200

        body = resp.json()
        span = body["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        assert span["traceId"] == exp_id.replace("-", "")
        assert len(span["events"]) > 0
        assert any(e["name"] == "EXPERIMENT_STARTED" for e in span["events"])

        resource_attrs = {
            a["key"]: a["value"] for a in body["resourceSpans"][0]["resource"]["attributes"]
        }
        assert resource_attrs["service.name"] == {"stringValue": "agentnet"}
        assert resource_attrs["agentnet.experiment_id"] == {"stringValue": exp_id}


def test_otel_trace_404_for_unknown_experiment():
    with TestClient(app) as client:
        resp = client.get(
            "/api/experiments/00000000-0000-0000-0000-000000000000/otel-trace"
        )
        assert resp.status_code == 404


def test_otel_trace_409_once_the_in_memory_window_no_longer_holds_the_whole_log():
    """Past EventBus.RING_SIZE events the ring no longer holds the start of
    the run; the endpoint used to export an empty trace as if it were the
    whole history."""
    runner = ExperimentRunner(ExperimentConfig(seed=7, node_count=100, edge_density=5))
    runner.tick_interval = 0

    async def run() -> None:
        await runner.publish_initial()
        await runner._run_loop()

    asyncio.run(run())
    assert runner.bus.since(-1) is None

    with TestClient(app) as client:
        registry.add(runner)
        try:
            resp = client.get(f"/api/experiments/{runner.experiment_id}/otel-trace")
        finally:
            registry.remove(runner.experiment_id)
    assert resp.status_code == 409
