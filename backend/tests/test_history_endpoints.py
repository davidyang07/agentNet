"""Postgres-backed coverage for the read-only history API: pagination
cursors, filtering, 404s, replay-snapshot's last_seq covering exactly the
initial events (so snapshot + later events folds to the final state), and
event-log pagination across a full run with no gaps or duplicates."""

import asyncio
import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from app.db import create_pool
from app.gateway.factory import build_gateway
from app.main import app
from app.orchestrator.registry import registry
from app.orchestrator.runner import ExperimentRunner
from app.persistence.registry import writer_registry
from app.persistence.writer import PostgresWriter
from app.schemas.experiment import ExperimentConfig
from app.version import APP_VERSION

from .conftest import TEST_SETTINGS, requires_postgres

pytestmark = requires_postgres


def _make_runner(**overrides) -> ExperimentRunner:
    defaults = {"seed": 42, "node_count": 25, "max_ticks": 5}
    defaults.update(overrides)
    runner = ExperimentRunner(ExperimentConfig(**defaults))
    runner.tick_interval = 0
    return runner


async def _persist_completed_run(
    pool, runner: ExperimentRunner | None = None, **config_overrides
) -> ExperimentRunner:
    if runner is None:
        runner = _make_runner(**config_overrides)
    # Mirrors the exact production call site in routes_experiments.py --
    # writer_registry.add() happens at the call site, not inside
    # PostgresWriter itself.
    writer = PostgresWriter(pool, runner.experiment_id, runner.bus, runner)
    await writer.start()
    writer_registry.add(runner.experiment_id, writer)
    await runner.publish_initial()
    await runner._run_loop()

    deadline = asyncio.get_event_loop().time() + 5.0
    while not writer._task.done():
        if asyncio.get_event_loop().time() > deadline:
            raise AssertionError("writer did not finalize within the timeout")
        await asyncio.sleep(0.01)
    return runner


async def _cleanup(*experiment_ids: object) -> None:
    # Self-contained: creates and closes its own pool within this single
    # asyncio.run() call. asyncpg pools/connections are bound to the event
    # loop that created them, so a pool created in an earlier, separate
    # asyncio.run() call (whose loop is already closed by the time this
    # runs) cannot be reused here.
    pool = await create_pool(TEST_SETTINGS)
    try:
        for experiment_id in experiment_ids:
            await pool.execute("DELETE FROM experiments WHERE experiment_id = $1", experiment_id)
    finally:
        await pool.close()


def test_detail_and_events_and_replay_snapshot_for_a_persisted_run():
    async def setup() -> ExperimentRunner:
        pool = await create_pool(TEST_SETTINGS)
        try:
            return await _persist_completed_run(pool)
        finally:
            await pool.close()

    runner = asyncio.run(setup())
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

            # replay-snapshot's last_seq is the last of the initial events the
            # snapshot already reflects (EXPERIMENT_STARTED, one AGENT_CREATED
            # per node, the seed compromise) -- so the next /events page never
            # re-delivers the seed compromise and starts at the first tick.
            assert snap_body["last_seq"] == 25 + 1
            events_page = client.get(
                f"/api/experiments/{exp_id}/events",
                params={"since_seq": snap_body["last_seq"]},
            )
            assert events_page.status_code == 200
            later = events_page.json()["events"]
            assert later[0]["seq"] == snap_body["last_seq"] + 1
            assert not any(
                e["event_type"] in ("EXPERIMENT_STARTED", "AGENT_CREATED")
                or e["metadata"].get("initial_compromise")
                for e in later
            )

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
        asyncio.run(_cleanup(runner.experiment_id))


def test_replay_snapshot_plus_later_events_reproduces_the_final_state():
    """The replay contract the history UI relies on (loadReplayData.ts):
    replay-snapshot, then every event with seq > its last_seq, folds to the
    run's final state. The first tick's propagation events are stamped
    sim_tick=0 (SPEC §3.4 stamps the pre-increment tick), so a boundary of
    MAX(seq) WHERE sim_tick=0 hid them and those nodes replayed as healthy.
    p=1.0 guarantees first-tick compromises exist."""

    async def setup() -> ExperimentRunner:
        pool = await create_pool(TEST_SETTINGS)
        try:
            return await _persist_completed_run(pool, p_same=1.0, p_cross=1.0)
        finally:
            await pool.close()

    runner = asyncio.run(setup())
    try:
        with TestClient(app) as client:
            exp_id = runner.experiment_id
            snapshot = client.get(f"/api/experiments/{exp_id}/replay-snapshot").json()

            later: list[dict] = []
            since_seq = snapshot["last_seq"]
            while True:
                page = client.get(
                    f"/api/experiments/{exp_id}/events",
                    params={"since_seq": since_seq, "limit": 500},
                ).json()
                later.extend(page["events"])
                if page["next_seq"] is None:
                    break
                since_seq = page["next_seq"]

            assert any(
                e["event_type"] == "COMPROMISE_SUCCEEDED" and e["sim_tick"] == 0 for e in later
            ), "fixture must compromise nodes on the first tick"

            states = {n["id"]: n["security_state"] for n in snapshot["nodes"]}
            for e in later:
                if e["event_type"] == "COMPROMISE_SUCCEEDED" and not e["metadata"].get(
                    "already_compromised"
                ):
                    states[e["target_agent_id"]] = "compromised"
                elif e["event_type"] == "AGENT_QUARANTINED":
                    states[e["agent_id"]] = "quarantined"

            assert states == {
                node_id: node.security_state.value for node_id, node in runner.state.nodes.items()
            }
    finally:
        asyncio.run(_cleanup(runner.experiment_id))


def test_incidents_endpoint_only_returns_incident_event_types():
    async def setup() -> ExperimentRunner:
        pool = await create_pool(TEST_SETTINGS)
        try:
            return await _persist_completed_run(pool, p_same=1.0, p_cross=1.0)
        finally:
            await pool.close()

    runner = asyncio.run(setup())
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
        asyncio.run(_cleanup(runner.experiment_id))


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
        asyncio.run(_cleanup(on_runner.experiment_id, off_runner.experiment_id))


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


@pytest.mark.parametrize(
    "extra",
    [
        {},
        # Shared immune memory, strains and poisoning (PLAN 14.4 C.3-C.4),
        # whose metrics come from both the state and the event log.
        {
            "immunity_enabled": True,
            "immunity_coverage": 0.6,
            "mutation_rate": 0.4,
            "signature_radius": 2,
            "preseed_patient_zero_signature": True,
            "sentinel_compromise_rate": 0.5,
            "active_scenarios": ["propagation", "sentinel_compromise"],
        },
    ],
    ids=["default", "immune_memory"],
)
def test_replay_graph_metrics_remediation_match_a_live_equivalent_run(extra):
    # Same config run twice: once through the live path (registry + /graph,
    # /metrics, /remediation), once persisted and read back through the new
    # /replay/* endpoints -- since both reconstruct the exact same
    # deterministic (seed, config) run, their outputs must be identical.
    config_kwargs = {
        "seed": 9,
        "node_count": 30,
        "p_same": 0.3,
        "max_ticks": 10,
        "sentinel_count": 1,
        **extra,
    }

    async def setup() -> ExperimentRunner:
        pool = await create_pool(TEST_SETTINGS)
        try:
            return await _persist_completed_run(pool, **config_kwargs)
        finally:
            await pool.close()

    runner = asyncio.run(setup())
    try:
        with TestClient(app) as client:
            live = ExperimentRunner(ExperimentConfig(**config_kwargs))
            live.tick_interval = 0

            async def run_live() -> None:
                await live.publish_initial()
                await live._run_loop()

            asyncio.run(run_live())
            from app.orchestrator.registry import registry

            registry.add(live)
            try:
                live_graph = client.get(f"/api/experiments/{live.experiment_id}/graph").json()
                live_metrics = client.get(f"/api/experiments/{live.experiment_id}/metrics").json()
                live_remediation = client.get(
                    f"/api/experiments/{live.experiment_id}/remediation"
                ).json()
                live_epidemic = client.get(f"/api/experiments/{live.experiment_id}/epidemic").json()
            finally:
                registry.remove(live.experiment_id)

            exp_id = runner.experiment_id
            replay_graph = client.get(f"/api/experiments/{exp_id}/replay/graph")
            assert replay_graph.status_code == 200
            replay_metrics = client.get(f"/api/experiments/{exp_id}/replay/metrics")
            assert replay_metrics.status_code == 200
            replay_remediation = client.get(f"/api/experiments/{exp_id}/replay/remediation")
            assert replay_remediation.status_code == 200
            replay_epidemic = client.get(f"/api/experiments/{exp_id}/replay/epidemic")
            assert replay_epidemic.status_code == 200

            assert replay_graph.json() == live_graph
            assert replay_metrics.json() == live_metrics
            assert replay_remediation.json() == live_remediation
            assert replay_epidemic.json() == live_epidemic
            assert live_epidemic["prevalence"], "the comparison must cover a real curve"
            if extra:
                assert live_metrics["immunity_coverage"] is not None
                assert any(p["immune"] for p in live_epidemic["prevalence"])
    finally:
        asyncio.run(_cleanup(runner.experiment_id))


def test_replay_matches_live_for_a_mock_real_agent_run():
    """A real_agent_count > 0 run under the mock provider is the one config
    whose replay goes through engine/replay.py's async path -- which used to
    call asyncio.run() from inside the server's running event loop and 500
    on every /replay/* route."""
    config = ExperimentConfig(
        seed=11, node_count=25, max_ticks=8, real_agent_count=6, p_same=0.6, p_cross=0.3
    )

    async def setup() -> ExperimentRunner:
        pool = await create_pool(TEST_SETTINGS)
        try:
            async with httpx.AsyncClient() as http_client:
                gateway = build_gateway(config, TEST_SETTINGS, http_client)
                assert gateway is not None
                runner = ExperimentRunner(config, gateway=gateway)
                runner.tick_interval = 0
                await _persist_completed_run(pool, runner=runner)
                assert gateway.requests_used > 0, "fixture must exercise the LLM path"
                return runner
        finally:
            await pool.close()

    runner = asyncio.run(setup())
    exp_id = runner.experiment_id
    try:
        with TestClient(app) as client:
            registry.add(runner)
            try:
                live = {
                    path: client.get(f"/api/experiments/{exp_id}/{path}").json()
                    for path in ("graph", "metrics", "remediation")
                }
            finally:
                registry.remove(exp_id)

            for path, live_body in live.items():
                resp = client.get(f"/api/experiments/{exp_id}/replay/{path}")
                assert resp.status_code == 200, resp.text
                assert resp.json() == live_body, path
    finally:
        asyncio.run(_cleanup(exp_id))


def test_replay_reconstructs_a_finished_run_once_for_many_requests(monkeypatch):
    """A persisted run's (config, final tick) never changes, and a replay page
    fires several /replay/* requests: each used to re-simulate the whole run
    (seconds for a long one)."""
    from app.api import routes_history

    routes_history._replay_world.cache_clear()
    calls = []
    real = routes_history.reconstruct_final_state

    def counting(config, target_tick):
        calls.append(target_tick)
        return real(config, target_tick)

    monkeypatch.setattr(routes_history, "reconstruct_final_state", counting)

    async def setup() -> ExperimentRunner:
        pool = await create_pool(TEST_SETTINGS)
        try:
            return await _persist_completed_run(pool, seed=8, node_count=25, p_same=0.4)
        finally:
            await pool.close()

    runner = asyncio.run(setup())
    try:
        with TestClient(app) as client:
            base = f"/api/experiments/{runner.experiment_id}/replay"
            for path in ("/graph", "/metrics", "/remediation", "/analysis/blast-radius"):
                assert client.get(base + path).status_code == 200
        assert len(calls) == 1
    finally:
        asyncio.run(_cleanup(runner.experiment_id))


def test_replay_analysis_endpoints_return_200_for_a_persisted_run():
    async def setup() -> ExperimentRunner:
        pool = await create_pool(TEST_SETTINGS)
        try:
            return await _persist_completed_run(pool, seed=4, node_count=25, p_same=0.4)
        finally:
            await pool.close()

    runner = asyncio.run(setup())
    try:
        with TestClient(app) as client:
            exp_id = runner.experiment_id
            graph = client.get(f"/api/experiments/{exp_id}/replay/graph").json()
            edge = graph["edges"][0]

            resp = client.get(
                f"/api/experiments/{exp_id}/replay/analysis/attack-paths",
                params={"source": edge["source"], "target": edge["target"]},
            )
            assert resp.status_code == 200

            resp = client.get(f"/api/experiments/{exp_id}/replay/analysis/blast-radius")
            assert resp.status_code == 200
            assert 0.0 <= resp.json()["fraction"] <= 1.0

            resp = client.get(
                f"/api/experiments/{exp_id}/replay/analysis/critical-nodes", params={"top_n": 2}
            )
            assert resp.status_code == 200
            assert len(resp.json()["nodes"]) <= 2

            node_id = graph["nodes"][0]["id"]
            resp = client.get(
                f"/api/experiments/{exp_id}/replay/analysis/provenance",
                params={"node_id": node_id},
            )
            assert resp.status_code == 200
            assert resp.json()["chain"][0] == node_id
    finally:
        asyncio.run(_cleanup(runner.experiment_id))


def test_replay_warns_when_the_run_was_recorded_by_another_build():
    """Replay re-simulates a run with this server's code, so a run recorded
    by a different build may not reproduce exactly. Replay used to answer as
    if it always did (PLAN 14.3 B.8)."""

    async def setup() -> ExperimentRunner:
        pool = await create_pool(TEST_SETTINGS)
        try:
            return await _persist_completed_run(pool, seed=5, node_count=25)
        finally:
            await pool.close()

    async def set_recorded_version(experiment_id, version: str) -> None:
        pool = await create_pool(TEST_SETTINGS)
        try:
            await pool.execute(
                "UPDATE experiments SET app_version = $2 WHERE experiment_id = $1",
                experiment_id,
                version,
            )
        finally:
            await pool.close()

    runner = asyncio.run(setup())
    exp_id = runner.experiment_id
    paths = [
        "replay-snapshot",
        "replay/graph",
        "replay/analysis/blast-radius",
        "replay/analysis/critical-nodes",
        "replay/metrics",
        "replay/remediation",
        "replay/epidemic",
    ]
    try:
        with TestClient(app) as client:
            for path in paths:
                resp = client.get(f"/api/experiments/{exp_id}/{path}")
                assert resp.status_code == 200, path
                assert "x-replay-version-mismatch" not in resp.headers, path

            asyncio.run(set_recorded_version(exp_id, "0123abc"))
            for path in paths:
                resp = client.get(
                    f"/api/experiments/{exp_id}/{path}",
                    headers={"Origin": "http://localhost:3000"},
                )
                assert resp.status_code == 200, path
                assert resp.headers["x-replay-version-mismatch"] == (
                    f"recorded=0123abc; server={APP_VERSION}"
                ), path
                # Readable by the browser UI, which is on another origin.
                exposed = resp.headers["access-control-expose-headers"].lower()
                assert "x-replay-version-mismatch" in exposed, path
    finally:
        asyncio.run(_cleanup(exp_id))


def test_replay_endpoints_404_for_unknown_experiment():
    with TestClient(app) as client:
        fake_id = uuid.uuid4()
        assert client.get(f"/api/experiments/{fake_id}/replay/graph").status_code == 404
        assert client.get(f"/api/experiments/{fake_id}/replay/metrics").status_code == 404
        assert client.get(f"/api/experiments/{fake_id}/replay/remediation").status_code == 404


def test_replay_endpoints_409_when_experiment_never_finished():
    async def setup() -> uuid.UUID:
        pool = await create_pool(TEST_SETTINGS)
        try:
            exp_id = uuid.uuid4()
            await pool.execute(
                "INSERT INTO experiments (experiment_id, seed, config, app_version, "
                "schema_version) VALUES ($1, $2, $3, 'test', 1)",
                exp_id,
                1,
                json.dumps({"seed": 1, "node_count": 25}),
            )
            return exp_id
        finally:
            await pool.close()

    exp_id = asyncio.run(setup())
    try:
        with TestClient(app) as client:
            resp = client.get(f"/api/experiments/{exp_id}/replay/graph")
            assert resp.status_code == 409
    finally:
        asyncio.run(_cleanup(exp_id))


def test_replay_endpoints_409_for_real_provider_config():
    # A real vLLM run can't actually complete without a reachable endpoint in
    # this environment, so this test only exercises the config-level guard by
    # inserting a finished-looking row directly, mirroring the prior test's
    # approach, rather than trying to run one to completion.
    async def insert_finished_vllm_row() -> uuid.UUID:
        pool = await create_pool(TEST_SETTINGS)
        try:
            exp_id = uuid.uuid4()
            await pool.execute(
                "INSERT INTO experiments (experiment_id, seed, config, app_version, "
                "schema_version, final_sim_tick, final_status) "
                "VALUES ($1, $2, $3, 'test', 1, $4, 'finished')",
                exp_id,
                1,
                json.dumps(
                    {
                        "seed": 1,
                        "node_count": 25,
                        "real_agent_count": 1,
                        "model_provider": "vllm",
                    }
                ),
                3,
            )
            return exp_id
        finally:
            await pool.close()

    exp_id = asyncio.run(insert_finished_vllm_row())
    try:
        with TestClient(app) as client:
            resp = client.get(f"/api/experiments/{exp_id}/replay/metrics")
            assert resp.status_code == 409
    finally:
        asyncio.run(_cleanup(exp_id))
