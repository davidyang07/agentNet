"""Postgres-backed coverage for the read-only history API: pagination
cursors, filtering, 404s, replay-snapshot's last_seq matching
MAX(seq) WHERE sim_tick=0, and event-log pagination across a full run with
no gaps or duplicates."""

import asyncio
import uuid

from fastapi.testclient import TestClient

from app.db import create_pool
from app.main import app
from app.orchestrator.runner import ExperimentRunner
from app.persistence.registry import writer_registry
from app.persistence.writer import PostgresWriter
from app.schemas.experiment import ExperimentConfig

from .conftest import TEST_SETTINGS, requires_postgres

pytestmark = requires_postgres


def _make_runner(**overrides) -> ExperimentRunner:
    config = ExperimentConfig(seed=42, node_count=25, max_ticks=5, **overrides)
    runner = ExperimentRunner(config)
    runner.tick_interval = 0
    return runner


async def _persist_completed_run(pool, **config_overrides) -> ExperimentRunner:
    runner = _make_runner(**config_overrides)
    writer = PostgresWriter(pool, runner.experiment_id, runner.bus, runner)
    await writer.start()
    await runner.publish_initial()
    await runner._run_loop()

    deadline = asyncio.get_event_loop().time() + 5.0
    while writer_registry.get(runner.experiment_id) is not None:
        if asyncio.get_event_loop().time() > deadline:
            raise AssertionError("writer did not finalize within the timeout")
        await asyncio.sleep(0.01)
    return runner


async def _cleanup(pool, experiment_id) -> None:
    await pool.execute("DELETE FROM experiments WHERE experiment_id = $1", experiment_id)


def test_detail_and_events_and_replay_snapshot_for_a_persisted_run():
    async def setup() -> ExperimentRunner:
        pool = await create_pool(TEST_SETTINGS)
        try:
            return await _persist_completed_run(pool)
        finally:
            await pool.close()

    runner = asyncio.run(setup())
    pool_for_cleanup = asyncio.run(create_pool(TEST_SETTINGS))
    try:
        with TestClient(app) as client:
            exp_id = str(runner.experiment_id)

            detail = client.get(f"/api/experiments/{exp_id}/detail")
            assert detail.status_code == 200
            body = detail.json()
            assert body["experiment_id"] == exp_id
            assert body["final_status"] == "finished"
            assert body["is_complete"] is True

            snapshot = client.get(f"/api/experiments/{exp_id}/replay-snapshot")
            assert snapshot.status_code == 200
            snap_body = snapshot.json()
            assert snap_body["type"] == "snapshot"
            assert len(snap_body["nodes"]) == 25
            assert len(snap_body["edges"]) > 0

            # replay-snapshot's last_seq must equal MAX(seq) WHERE sim_tick=0
            # -- the exact boundary that prevents the seed compromise from
            # being double-delivered by the next /events page.
            events_page = client.get(
                f"/api/experiments/{exp_id}/events",
                params={"since_seq": snap_body["last_seq"]},
            )
            assert events_page.status_code == 200
            first_returned = events_page.json()["events"][0]
            assert first_returned["sim_tick"] >= 1 or first_returned["seq"] > snap_body["last_seq"]
            assert all(e["sim_tick"] != 0 for e in events_page.json()["events"])

            # Paginate the full log to completion via next_seq: no gaps, no dupes.
            all_seqs: list[int] = []
            since_seq = -1
            while True:
                page = client.get(
                    f"/api/experiments/{exp_id}/events",
                    params={"since_seq": since_seq, "limit": 50},
                )
                assert page.status_code == 200
                body = page.json()
                all_seqs.extend(e["seq"] for e in body["events"])
                if body["next_seq"] is None:
                    break
                since_seq = body["next_seq"]
            assert all_seqs == list(range(runner._emitter.last_seq + 1))
            assert len(all_seqs) == len(set(all_seqs))
    finally:
        asyncio.run(_cleanup(pool_for_cleanup, runner.experiment_id))
        asyncio.run(pool_for_cleanup.close())


def test_incidents_endpoint_only_returns_incident_event_types():
    async def setup() -> ExperimentRunner:
        pool = await create_pool(TEST_SETTINGS)
        try:
            return await _persist_completed_run(pool, p_same=1.0, p_cross=1.0)
        finally:
            await pool.close()

    runner = asyncio.run(setup())
    pool_for_cleanup = asyncio.run(create_pool(TEST_SETTINGS))
    try:
        with TestClient(app) as client:
            resp = client.get(f"/api/experiments/{runner.experiment_id}/incidents")
            assert resp.status_code == 200
            events = resp.json()["events"]
            assert events, "expected propagation to produce incident events"
            incident_types = {
                "COMPROMISE_ATTEMPTED",
                "COMPROMISE_SUCCEEDED",
                "COMPROMISE_FAILED",
                "ANOMALY_DETECTED",
                "AGENT_QUARANTINED",
            }
            assert all(e["event_type"] in incident_types for e in events)
    finally:
        asyncio.run(_cleanup(pool_for_cleanup, runner.experiment_id))
        asyncio.run(pool_for_cleanup.close())


def test_list_filters_and_paginates_by_status_and_defense_enabled():
    async def setup() -> tuple[ExperimentRunner, ExperimentRunner]:
        pool = await create_pool(TEST_SETTINGS)
        try:
            on = await _persist_completed_run(pool, seed=1, defense_enabled=True)
            off = await _persist_completed_run(pool, seed=2, defense_enabled=False)
            return on, off
        finally:
            await pool.close()

    on_runner, off_runner = asyncio.run(setup())
    pool_for_cleanup = asyncio.run(create_pool(TEST_SETTINGS))
    try:
        with TestClient(app) as client:
            resp = client.get("/api/experiments", params={"defense_enabled": "true", "limit": 100})
            assert resp.status_code == 200
            ids = {item["experiment_id"] for item in resp.json()["items"]}
            assert str(on_runner.experiment_id) in ids
            assert str(off_runner.experiment_id) not in ids

            resp = client.get("/api/experiments", params={"status": "finished", "limit": 1})
            assert resp.status_code == 200
            body = resp.json()
            assert len(body["items"]) == 1
            if body["next_cursor"]:
                params = {"status": "finished", "limit": 1, "cursor": body["next_cursor"]}
                resp2 = client.get("/api/experiments", params=params)
                assert resp2.status_code == 200
                next_id = resp2.json()["items"][0]["experiment_id"]
                assert next_id != body["items"][0]["experiment_id"]
    finally:
        asyncio.run(_cleanup(pool_for_cleanup, on_runner.experiment_id))
        asyncio.run(_cleanup(pool_for_cleanup, off_runner.experiment_id))
        asyncio.run(pool_for_cleanup.close())


def test_history_endpoints_404_for_unknown_experiment():
    with TestClient(app) as client:
        fake_id = uuid.uuid4()
        assert client.get(f"/api/experiments/{fake_id}/detail").status_code == 404
        assert client.get(f"/api/experiments/{fake_id}/events").status_code == 404
        assert client.get(f"/api/experiments/{fake_id}/incidents").status_code == 404
        assert client.get(f"/api/experiments/{fake_id}/replay-snapshot").status_code == 404


def test_history_endpoints_503_when_pool_unavailable():
    with TestClient(app) as client:
        client.app.state.pg_pool = None
        fake_id = uuid.uuid4()
        assert client.get("/api/experiments").status_code == 503
        assert client.get(f"/api/experiments/{fake_id}/detail").status_code == 503
