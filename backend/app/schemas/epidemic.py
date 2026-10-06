from pydantic import BaseModel


class PrevalencePoint(BaseModel):
    tick: int
    infectious: int
    quarantined: int
    # Healthy agents holding a legitimate signature (§14.4 C.4); 0 without
    # immune memory.
    immune: int


class REffectivePoint(BaseModel):
    tick: int
    # Mean offspring of the agents infected at this tick.
    value: float
    # True while a member can still infect someone, so `value` may still rise.
    censored: bool


class GenerationStats(BaseModel):
    generation: int
    nodes: int
    mean_offspring: float


class EpidemicResponse(BaseModel):
    """docs/PLAN.md §14.4 C.1: the run's epidemic curve and infection tree."""

    prevalence: list[PrevalencePoint]
    r_effective: list[REffectivePoint]
    generations: list[GenerationStats]
