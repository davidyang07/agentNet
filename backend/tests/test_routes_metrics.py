import asyncio

from fastapi.testclient import TestClient

from app.events.bus import EventBus
from app.main import app
from app.metrics import compute
from app.orchestrator.registry import registry
from app.orchestrator.runner import ExperimentRunner
from app.schemas.experiment import ExperimentConfig


def _start_experiment(client: TestClient, **overrides) -> dict:
    body = {"seed": 7, "node_count": 25, "max_ticks": 1}
    body.update(overrides)
    resp = client.post("/api/experiments", json=body)
    assert resp.status_code == 201
    return resp.json()


def test_metrics_endpoint_returns_all_fields_with_sane_bounds():
    with TestClient(app) as client:
        exp_id = _start_experiment(client)["experiment_id"]
        resp = client.get(f"/api/experiments/{exp_id}/metrics")
        assert resp.status_code == 200
        body = resp.json()

        for key in (
            "compromise_fraction",
            "retained_utility",
            "blast_radius_fraction",
            "security_plane_integrity",
            "attack_success_rate",
            "false_quarantine_rate",
        ):
            assert 0.0 <= body[key] <= 1.0, key
        assert body["privileged_exposure"] >= 0
        assert body["compromise_fraction"] > 0.0
        for key in ("detection_latency", "containment_latency"):
            assert key in body
            assert body[key] is None or body[key] >= 0.0


def test_metrics_endpoint_404_for_unknown_experiment():
    with TestClient(app) as client:
        resp = client.get(
            "/api/experiments/00000000-0000-0000-0000-000000000000/metrics"
        )
        assert resp.status_code == 404


def test_live_event_log_metrics_cover_the_whole_run_after_the_event_ring_wraps():
    """Live /metrics used to read the EventBus ring, which returns nothing
    once a run has emitted more than RING_SIZE events -- every event-log
    metric then silently read 0.0/None. They must match the full log."""
    runner = ExperimentRunner(ExperimentConfig(seed=7, node_count=100, edge_density=5))
    runner.tick_interval = 0
    queue = runner.bus.subscribe()

    async def run() -> None:
        await runner.publish_initial()
        await runner._run_loop()

    asyncio.run(run())
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    assert len(events) > EventBus.RING_SIZE

    with TestClient(app) as client:
        registry.add(runner)
        try:
            body = client.get(f"/api/experiments/{runner.experiment_id}/metrics").json()
        finally:
            registry.remove(runner.experiment_id)

    assert body["attack_success_rate"] == compute.attack_success_rate(events) > 0.0
    assert body["false_quarantine_rate"] == compute.false_quarantine_rate(events)
    assert body["detection_latency"] == compute.detection_latency(runner.state, events)
    assert body["detection_latency"] is not None
    # Withheld in quarantine mode, where detection and quarantine coincide (D1).
    assert body["containment_latency"] is None


def test_attack_success_rate_is_zero_when_no_attack_can_succeed():
    # p=0: every attempt fails. The seeded compromise used to count as a
    # success, so this read 1.0 before any tick ran, and stayed above 0.
    with TestClient(app) as client:
        exp_id = _start_experiment(
            client, p_same=0.0, p_cross=0.0, defense_enabled=False, max_ticks=5
        )["experiment_id"]
        body = client.get(f"/api/experiments/{exp_id}/metrics").json()
    assert body["attack_success_rate"] == 0.0
    assert body["gateway_failure_count"] == 0
    assert body["containment_latency"] is None
