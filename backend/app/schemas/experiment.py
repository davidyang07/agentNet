from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.engine.state import SecurityState

# experiments.seed is BIGINT: a seed outside it could run but never be saved.
SEED_MIN = -(2**63)
SEED_MAX = 2**63 - 1


class ExperimentConfig(BaseModel):
    seed: int = Field(ge=SEED_MIN, le=SEED_MAX)
    node_count: int = Field(60, ge=25, le=100)
    edge_density: int = Field(2, ge=1, le=5)
    software_type_count: int = Field(3, ge=1, le=5)
    p_same: float = Field(0.15, ge=0.0, le=1.0)
    p_cross: float = Field(0.03, ge=0.0, le=1.0)
    max_ticks: int = Field(200, ge=1, le=2000)
    detector_sensitivity: float = Field(0.2, ge=0.0, le=1.0)
    defense_enabled: bool = Field(True)
    initial_compromised: Literal["highest_degree", "random_node"] = "highest_degree"

    # Phase 2: opt-in, defaults preserve the
    # synthetic baseline exactly. Deliberately NOT here: vLLM base_url/api
    # key -- those are infra/credentials, kept in app/config.py::Settings so
    # they never round-trip through this persisted, API-returned config.
    real_agent_count: int = Field(0, ge=0, le=20)
    model_provider: Literal["mock", "vllm"] = "mock"
    model_name: str = "qwen-mock"
    model_max_tokens: int = Field(64, ge=1, le=512)
    model_timeout_s: float = Field(20.0, ge=1.0, le=120.0)
    model_max_retries: int = Field(1, ge=0, le=3)
    model_max_concurrency: int = Field(4, ge=1, le=16)
    model_max_requests_per_experiment: int = Field(500, ge=1, le=5000)

    # Security graph (docs/PLAN.md §2.4): all default to 0, which yields a
    # graph containing only AGENT nodes + COMMUNICATES_WITH/TRUSTS edges --
    # i.e. every existing behavior stays byte-for-byte unchanged unless a
    # caller opts in.
    tool_count: int = Field(0, ge=0, le=20)
    credential_count: int = Field(0, ge=0, le=20)
    resource_count: int = Field(0, ge=0, le=20)
    sentinel_count: int = Field(0, ge=0, le=5)
    # "prompt_injection" (the real-agent lateral prompt-injection scenario)
    # is in the default so real_agent_count > 0
    # keeps working exactly as before this field started gating async
    # scenarios too (docs/PLAN.md §3) -- every existing real-agent test
    # relies on it running whenever eligible without setting this field.
    # Excluding it from an explicit active_scenarios list now genuinely
    # disables it, which was not previously possible short of
    # real_agent_count=0.
    active_scenarios: list[str] = Field(
        default_factory=lambda: ["propagation", "prompt_injection"]
    )

    # Adaptive attacker (docs/PLAN.md §4): only consulted by the
    # "adaptive_attacker" scenario, which is opt-in via active_scenarios --
    # this default has no effect unless that scenario is selected.
    adaptive_detection_threshold: float = Field(0.3, ge=0.0, le=1.0)

    # False quarantine / subverted quarantine authority (docs/PLAN.md §5).
    # Defaults to 0.0, a strict no-op preserving every existing behavior.
    false_quarantine_rate: float = Field(0.0, ge=0.0, le=1.0)

    # Sentinel compromise (docs/PLAN.md §5): per-tick probability that a
    # SENTINEL monitoring at least one currently-COMPROMISED agent is itself
    # subverted. Defaults to 0.0 (no-op); only meaningful with sentinel_count > 0.
    sentinel_compromise_rate: float = Field(0.0, ge=0.0, le=1.0)

    # Attestation replay (docs/PLAN.md §5): per-tick probability a
    # COMPROMISED agent presents a stale nonce instead of the current tick's.
    # Defaults to 0.0 (no-op); only meaningful with sentinel_count > 0 (the
    # attestation_service control node is part of the security plane).
    attestation_replay_rate: float = Field(0.0, ge=0.0, le=1.0)

    # Byzantine collusion (docs/PLAN.md §5): per-tick probability that a pair
    # of COMPROMISED agents jointly exceed credential access scope on a
    # CREDENTIAL neither legitimately holds. Defaults to 0.0 (no-op); only
    # meaningful with credential_count > 0.
    byzantine_collusion_rate: float = Field(0.0, ge=0.0, le=1.0)

    # Inference capability (docs/PLAN.md §14.4 C.2, after [S2]): only agents
    # that can run inference propagate; a compromised agent that can't is a
    # dead end. The defaults make every agent capable and draw nothing.
    inference_fraction: float = Field(1.0, ge=0.0, le=1.0)
    inference_placement: Literal["random", "hubs", "periphery"] = "random"
    # erdos_renyi draws the same number of edges barabasi_albert would, so
    # edge_density keeps one meaning across both.
    topology: Literal["barabasi_albert", "erdos_renyi"] = "barabasi_albert"

    # Worm strains (docs/PLAN.md §14.4 C.3, after [S1]): k-bit vectors, with
    # Hamming distance standing for semantic distance. Patient zero sits
    # strain_benign_distance bits from the benign centroid; each successful
    # transmission flips mutation_bits keyed bits with probability
    # mutation_rate. Strains are tracked only while mutation_rate > 0.
    signature_bits: int = Field(64, ge=8, le=256)
    strain_benign_distance: int = Field(32, ge=0, le=256)
    mutation_rate: float = Field(0.0, ge=0.0, le=1.0)
    mutation_bits: int = Field(1, ge=1, le=64)

    # Shared immune memory (docs/PLAN.md §14.4 C.4, after [S1] and [S2]): a
    # detection publishes the detected strain as a signature; participants
    # (immunity_coverage of the agents, placed by immunity_placement) hold it
    # signature_delay_ticks later and block attacks whose strain is within
    # signature_radius bits of a held signature. Each tick every healthy
    # participant also screens benign_probes_per_tick benign vectors, which
    # measures the autoimmune cost. Off by default.
    immunity_enabled: bool = False
    immunity_coverage: float = Field(1.0, ge=0.0, le=1.0)
    immunity_placement: Literal["random", "hubs", "periphery"] = "random"
    signature_radius: int = Field(0, ge=0, le=256)
    signature_delay_ticks: int = Field(1, ge=0, le=50)
    # [S1]'s red-team pre-seeding: patient zero's strain is held from tick 0.
    preseed_patient_zero_signature: bool = False
    benign_probes_per_tick: int = Field(1, ge=0, le=10)

    # Realistic detection and graduated response (docs/PLAN.md §14.4 C.5,
    # after [S1]: change-point detection needs evidence, and false positives
    # are "autoimmune"). detector_ramp_ticks: detection probability rises
    # linearly to detector_sensitivity over that many ticks after
    # compromise. detector_false_positive_rate: the detector's own error on
    # uninfected agents -- distinct from the false_quarantine_rate attack.
    # response_mode="graduated": a first detection makes an agent SUSPICIOUS
    # (its transmission scaled by suspicious_transmission_factor), a second
    # quarantines it, and with no repeat detection within review_ticks it
    # is released. The defaults keep today's single-step quarantine.
    detector_ramp_ticks: int = Field(0, ge=0, le=50)
    detector_false_positive_rate: float = Field(0.0, ge=0.0, le=1.0)
    response_mode: Literal["quarantine", "graduated"] = "quarantine"
    suspicious_transmission_factor: float = Field(0.5, ge=0.0, le=1.0)
    review_ticks: int = Field(5, ge=1, le=100)

    @model_validator(mode="after")
    def _distances_fit_the_strain_length(self) -> "ExperimentConfig":
        for name in ("strain_benign_distance", "mutation_bits", "signature_radius"):
            if getattr(self, name) > self.signature_bits:
                raise ValueError(f"{name} cannot exceed signature_bits ({self.signature_bits})")
        return self


class NodeView(BaseModel):
    id: str
    software_type: str
    security_state: SecurityState
    compromised_by: str | None = None
    tick_compromised: int | None = None
    # Never confidential_token: exposing
    # it here would hand every client the synthetic secret the experiment is
    # testing whether real agents leak.
    agent_kind: Literal["simulated", "real"] = "simulated"


class EdgeView(BaseModel):
    source: str
    target: str


class ExperimentSummary(BaseModel):
    experiment_id: UUID
    status: Literal["running", "paused", "finished", "stopped"]
    sim_tick: int
    last_seq: int
    config: ExperimentConfig


class SpeedRequest(BaseModel):
    multiplier: float = Field(..., ge=0.25, le=8.0)
