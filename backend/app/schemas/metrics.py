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
