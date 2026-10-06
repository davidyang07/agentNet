from pydantic import BaseModel


class MetricsResponse(BaseModel):
    compromise_fraction: float
    retained_utility: float
    blast_radius_fraction: float
    privileged_exposure: int
    security_plane_integrity: float
    attack_success_rate: float
    false_quarantine_rate: float
    detection_latency: float | None = None
    containment_latency: float | None = None
    # Real-agent attempts that never reached the model (budget exhausted, or
    # every retry failed) -- reported separately so they aren't mistaken for
    # attacks the target defended against.
    gateway_failure_count: int = 0
    # Epidemic metrics (docs/PLAN.md §14.4 C.1, defined in §6), read from
    # the infection tree; None when there is nothing to measure.
    r0_estimate: float | None = None
    serial_interval: float | None = None
    final_size: float = 0.0
    peak_prevalence: float | None = None
    peak_tick: int | None = None
    # Distinct worm strains among infected agents (§14.4 C.3); None unless
    # strains are tracked.
    strains_observed: int | None = None
    # Shared immune memory (§14.4 C.4, defined in §6); None unless it is on.
    immunity_coverage: float | None = None
    signature_block_rate: float | None = None
    benign_block_rate: float | None = None
