import uuid

from fastapi.testclient import TestClient

from app.main import app


def test_vllm_without_base_url_returns_400():
    with TestClient(app) as client:
        resp = client.post(
            "/api/experiments",
            json={
                "seed": 1,
                "node_count": 25,
                "max_ticks": 1,
                "real_agent_count": 2,
                "model_provider": "vllm",
            },
        )
        assert resp.status_code == 400
        assert "vllm" in resp.json()["detail"].lower()


def test_mock_provider_with_real_agents_succeeds_regardless_of_vllm_config():
    with TestClient(app) as client:
        resp = client.post(
            "/api/experiments",
            json={
                "seed": 1,
                "node_count": 25,
                "max_ticks": 1,
                "real_agent_count": 2,
                "model_provider": "mock",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["config"]["real_agent_count"] == 2
        assert body["config"]["model_provider"] == "mock"
        client.post(f"/api/experiments/{body['experiment_id']}/stop")


def test_vllm_with_zero_real_agents_never_triggers_validation():
    """real_agent_count=0 means no real agent ever exists -- the vLLM
    base_url check only matters when real_agent_count > 0 (docs/PHASE_2_PLAN.md
    §8), so this must succeed even with model_provider="vllm" and nothing
    configured."""
    with TestClient(app) as client:
        resp = client.post(
            "/api/experiments",
            json={
                "seed": 1,
                "node_count": 25,
                "max_ticks": 1,
                "real_agent_count": 0,
                "model_provider": "vllm",
            },
        )
        assert resp.status_code == 201
        client.post(f"/api/experiments/{resp.json()['experiment_id']}/stop")


def test_default_config_has_zero_real_agents_and_mock_provider():
    with TestClient(app) as client:
        resp = client.post(
            "/api/experiments",
            json={"seed": uuid.uuid4().int % 1000, "node_count": 25, "max_ticks": 1},
        )
        assert resp.status_code == 201
        config = resp.json()["config"]
        assert config["real_agent_count"] == 0
        assert config["model_provider"] == "mock"
        client.post(f"/api/experiments/{resp.json()['experiment_id']}/stop")
