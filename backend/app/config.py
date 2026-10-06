from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "agentnet"
    postgres_password: str = "agentnet_dev"
    postgres_db: str = "agentnet"
    cors_origins: list[str] = ["http://localhost:3000"]

    # Phase 2 (docs/PHASE_2_PLAN.md §8): the vLLM server endpoint/credential
    # live here, env-var-driven like postgres_*, deliberately NOT in
    # ExperimentConfig -- ExperimentConfig is persisted verbatim into
    # Postgres and returned by multiple existing read endpoints, so putting
    # infra credentials there would leak them through code that already
    # exists. Deploying a RunPod GPU pod running vLLM and setting these is a
    # manual, owner-performed step (docs/BRIEF.md §12) -- both default to
    # None, which is exactly the "vLLM isn't configured" signal
    # POST /api/experiments checks for.
    vllm_base_url: str | None = None
    vllm_api_key: str | None = None

    # Run lifecycle (docs/PLAN.md §14.3 B.2): an ended run stays in memory
    # this long for late readers (its durable record is in Postgres), and at
    # most this many runs may be running or paused at once.
    finished_run_ttl_s: float = 900.0
    max_active_experiments: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()
