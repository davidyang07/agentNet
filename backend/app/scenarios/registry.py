"""Scenario registry (docs/PLAN.md §3): maps a scenario name to its
implementation and runs the active set each tick. `run_sync_scenarios`
iterates `config.active_scenarios` in list order (deterministic --
order is a config value, not iteration over a dict/set); the default
`["propagation"]` reproduces engine/tick.py's pre-refactor two-line body
exactly. `run_async_scenarios` is not yet gated by `config.active_scenarios`
(docs/PLAN.md status: known simplification for this pass) -- it runs every
registered async scenario whenever a gateway is present, matching today's
unconditional call to real_agent_step; each async scenario already
no-ops when it finds no eligible source/target pair.
"""

from __future__ import annotations

import logging

from app.engine.state import WorldState
from app.gateway.gateway import ModelGateway
from app.scenarios.adaptive_attacker_scenario import adaptive_attacker_scenario
from app.scenarios.base import AsyncScenario, Scenario
from app.scenarios.prompt_injection_scenario import prompt_injection_scenario
from app.scenarios.propagation_scenario import propagation_scenario
from app.schemas.events import EventDraft
from app.schemas.experiment import ExperimentConfig

logger = logging.getLogger(__name__)

SYNC_SCENARIOS: dict[str, Scenario] = {
    propagation_scenario.name: propagation_scenario,
    adaptive_attacker_scenario.name: adaptive_attacker_scenario,
}

ASYNC_SCENARIOS: dict[str, AsyncScenario] = {
    prompt_injection_scenario.name: prompt_injection_scenario,
}


def run_sync_scenarios(
    state: WorldState, config: ExperimentConfig
) -> tuple[WorldState, list[EventDraft]]:
    drafts: list[EventDraft] = []
    for scenario_name in config.active_scenarios:
        scenario = SYNC_SCENARIOS.get(scenario_name)
        if scenario is None:
            logger.warning("unknown scenario %r in active_scenarios; skipping", scenario_name)
            continue
        state, scenario_drafts = scenario.step(state, config)
        drafts.extend(scenario_drafts)
    return state, drafts


async def run_async_scenarios(
    state: WorldState, config: ExperimentConfig, gateway: ModelGateway, tick: int
) -> tuple[WorldState, list[EventDraft]]:
    drafts: list[EventDraft] = []
    for scenario in ASYNC_SCENARIOS.values():
        state, scenario_drafts = await scenario.step(state, config, gateway, tick)
        drafts.extend(scenario_drafts)
    return state, drafts
