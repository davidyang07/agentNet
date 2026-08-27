"""Selects and constructs the ModelGateway for one experiment
(docs/PHASE_2_PLAN.md §3, §8). Centralized here so routes_experiments.py
stays a thin wiring point and this selection logic is independently
testable.
"""

from __future__ import annotations

import httpx

from app.config import Settings
from app.gateway.gateway import ModelGateway
from app.gateway.mock_provider import MockProvider
from app.gateway.vllm_provider import VLLMProvider
from app.schemas.experiment import ExperimentConfig


def build_gateway(
    config: ExperimentConfig, settings: Settings, http_client: httpx.AsyncClient
) -> ModelGateway | None:
    """None whenever real_agent_count == 0 -- no gateway is constructed at
    all, so an experiment that never uses one never pays for one (no
    semaphore, no budget counter, nothing for ExperimentRunner to call)."""
    if config.real_agent_count <= 0:
        return None

    if config.model_provider == "vllm":
        # POST /api/experiments already rejected this combination with a 400
        # if vllm_base_url were unset (docs/PHASE_2_PLAN.md §8) -- this
        # assertion documents that invariant rather than re-checking it.
        assert settings.vllm_base_url is not None
        provider = VLLMProvider(
            http_client,
            base_url=settings.vllm_base_url,
            api_key=settings.vllm_api_key,
            model_name=config.model_name,
        )
    else:
        provider = MockProvider()

    return ModelGateway(
        provider,
        timeout_s=config.model_timeout_s,
        max_retries=config.model_max_retries,
        max_concurrency=config.model_max_concurrency,
        max_requests_per_experiment=config.model_max_requests_per_experiment,
    )
