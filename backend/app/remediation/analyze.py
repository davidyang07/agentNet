"""Deterministic, rule-based remediation engine (docs/PLAN.md §7).

Every recommendation targets a config field with a *causally verified*
effect on this session's implemented scenarios/detection:
`detector_sensitivity` and `defense_enabled` are the only levers wired into
app/security/detection.py's actual quarantine behavior today. Structural
graph levers (sentinel placement, credential consolidation) are
deliberately NOT recommended here -- they have no causal effect on any
implemented scenario in this codebase yet (sentinel/security-control nodes
are analysis-only, not wired into detection or any scenario's behavior),
and recommending them would be an unverifiable, fabricated "fix" that
re-running the experiment could not actually confirm. Each recommendation's
`config_diff` is directly usable as a `POST /api/experiments` body field
for re-testing -- scoring the fix reuses the existing comparison flow, no
new re-test machinery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.schemas.experiment import ExperimentConfig

HIGH_COMPROMISE_THRESHOLD = 0.3
SENSITIVITY_INCREMENT = 0.2


@dataclass
class Recommendation:
    description: str
    config_diff: dict[str, Any] = field(default_factory=dict)


def recommend(config: ExperimentConfig, compromise_fraction: float) -> list[Recommendation]:
    if compromise_fraction <= HIGH_COMPROMISE_THRESHOLD:
        return []

    if not config.defense_enabled:
        return [
            Recommendation(
                description=(
                    f"{compromise_fraction:.0%} of agents are compromised and quarantine "
                    "defense is disabled -- enable it."
                ),
                config_diff={"defense_enabled": True},
            )
        ]

    if config.detector_sensitivity < 1.0:
        new_sensitivity = round(min(1.0, config.detector_sensitivity + SENSITIVITY_INCREMENT), 2)
        return [
            Recommendation(
                description=(
                    f"{compromise_fraction:.0%} of agents are compromised despite defense "
                    f"being enabled -- raise detector_sensitivity from "
                    f"{config.detector_sensitivity} to {new_sensitivity}."
                ),
                config_diff={"detector_sensitivity": new_sensitivity},
            )
        ]

    return []
