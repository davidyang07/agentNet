"""Inputs the API used to accept but couldn't serve (PLAN 14.3 B.6): each
failed later, deep in the stack, as a 500 or a wrong answer, instead of a
422 at the edge."""

import asyncio
import time
import uuid

from fastapi.testclient import TestClient

from app.main import app

from .conftest import requires_postgres
from .test_history_endpoints import _cleanup

BIGINT_MAX = 2**63 - 1
INT_MAX = 2**31 - 1


def test_a_seed_outside_bigint_is_refused():
    """experiments.seed is BIGINT: a larger seed ran in memory but could
    never be saved, so the run silently had no history."""
    with TestClient(app) as client:
        for seed in (BIGINT_MAX + 1, -(2**63) - 1):
            resp = client.post("/api/experiments", json={"seed": seed, "node_count": 25})
            assert resp.status_code == 422, seed

        resp = client.post(
            "/api/experiments", json={"seed": BIGINT_MAX, "node_count": 25, "max_ticks": 1}
        )
        assert resp.status_code == 201


def test_since_seq_must_fit_the_seq_column():
    # experiment_events.seq is INT, so a larger cursor failed in asyncpg (500).
    with TestClient(app) as client:
        fake_id = uuid.uuid4()
        for path in ("events", "incidents"):
            for since_seq in (INT_MAX + 1, -2):
                resp = client.get(f"/api/experiments/{fake_id}/{path}?since_seq={since_seq}")
                assert resp.status_code == 422, (path, since_seq)


def test_top_n_must_be_at_least_one():
    """top_n=-1 sliced off the last node and returned the rest."""
    with TestClient(app) as client:
        created = client.post(
            "/api/experiments", json={"seed": 1, "node_count": 25, "max_ticks": 1}
        )
        exp_id = created.json()["experiment_id"]
        for top_n in (0, -1):
            for path in ("analysis/critical-nodes", "replay/analysis/critical-nodes"):
                resp = client.get(f"/api/experiments/{exp_id}/{path}?top_n={top_n}")
                assert resp.status_code == 422, (path, top_n)
        resp = client.get(f"/api/experiments/{exp_id}/analysis/critical-nodes?top_n=1")
        assert len(resp.json()["nodes"]) == 1


@requires_postgres
def test_replay_snapshot_reports_a_live_runs_actual_status():
    """It reported every run without a final status as "stopped", including
    one that was still running."""
    with TestClient(app) as client:
        created = client.post(
            "/api/experiments", json={"seed": 1, "node_count": 25, "max_ticks": 2000}
        )
        exp_id = created.json()["experiment_id"]
        try:
            deadline = time.monotonic() + 5.0
            while (
                snapshot := client.get(f"/api/experiments/{exp_id}/replay-snapshot")
            ).status_code != 200:
                assert time.monotonic() < deadline, snapshot.text
                time.sleep(0.05)
            assert snapshot.json()["status"] == "running"

            client.post(f"/api/experiments/{exp_id}/pause")
            snapshot = client.get(f"/api/experiments/{exp_id}/replay-snapshot")
            assert snapshot.json()["status"] == "paused"
        finally:
            client.post(f"/api/experiments/{exp_id}/stop")
    asyncio.run(_cleanup(uuid.UUID(exp_id)))
