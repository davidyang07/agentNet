from dataclasses import replace

from app.engine.state import WorldState
from app.scenarios.registry import run_sync_scenarios
from app.schemas.events import EventDraft
from app.schemas.experiment import ExperimentConfig
from app.security import detection


def advance(state: WorldState, config: ExperimentConfig) -> tuple[WorldState, list[EventDraft]]:
    """One full tick: active scenarios (docs/PLAN.md §3), then
    detection/quarantine. Pure, synchronous, total."""
    start_tick = state.tick
    state, scenario_drafts = run_sync_scenarios(state, config)
    if state.tick == start_tick:
        # Only the attacker scenarios (propagation, adaptive_attacker) advance
        # the tick themselves (SPEC §3.4's step()). Without one -- an
        # observe-only run, or only composable security-plane scenarios --
        # the tick would never move, so the run could never reach max_ticks.
        state = replace(state, tick=start_tick + 1)
    state, security_drafts = detection.step(state, config)
    return state, scenario_drafts + security_drafts
