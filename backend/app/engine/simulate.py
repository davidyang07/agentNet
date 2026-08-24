from app.engine.propagation import is_finished, step
from app.engine.topology import build_world
from app.schemas.events import EventDraft, EventType
from app.schemas.experiment import ExperimentConfig


def run_full(config: ExperimentConfig) -> list[EventDraft]:
    """Batch-run one full deterministic experiment, synchronously.

    Used by tests and scripts/verify_determinism.py — no asyncio, no bus, no
    wall-clock pacing. ExperimentRunner drives the same build_world/step/
    is_finished calls one tick at a time for live streaming instead.
    """
    drafts: list[EventDraft] = [
        EventDraft(sim_tick=0, event_type=EventType.EXPERIMENT_STARTED)
    ]
    world, topology_drafts = build_world(config)
    drafts.extend(topology_drafts)

    while not is_finished(world, config):
        world, step_drafts = step(world, config)
        drafts.extend(step_drafts)

    return drafts
