from app.engine import propagation
from app.engine.state import WorldState
from app.schemas.events import EventDraft
from app.schemas.experiment import ExperimentConfig
from app.security import detection


def advance(state: WorldState, config: ExperimentConfig) -> tuple[WorldState, list[EventDraft]]:
    """One full tick: propagation, then detection/quarantine. Pure, synchronous, total."""
    state, propagation_drafts = propagation.step(state, config)
    state, security_drafts = detection.step(state, config)
    return state, propagation_drafts + security_drafts
