"""agentshield test: runs a fixed, fast subset of the benchmark matrix -- the
defense comparison and the canonical remediation before/after -- and checks
concrete pass/fail criteria. Excludes the 2,500-agent scale run and the full
14-scenario attack matrix (too slow for a CI gate) -- those stay a manual
`make benchmark` command; see README's benchmark section.

Every check is strict, so it fails when the mechanism it covers stops
working: a defense that never quarantines (or quarantines every agent) ties
"no defense" rather than beating it, and a remediation that changes nothing
ties its own baseline. test_agentshield_cli.py breaks each mechanism to
prove the gate then fails. The golden demo is deliberately not a gate check:
its recommended remediation measurably backfires, and the demo reports that
(test_golden_demo.py) rather than this gate asserting otherwise.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.benchmark.matrix import DEFENSE_BASE_ATTACK, DEFENSE_VARIANTS, REMEDIATION_CASE
from app.benchmark.runner import run_preset
from app.remediation.analyze import recommend


@dataclass
class Finding:
    name: str
    passed: bool
    detail: str
    duration_s: float


def evaluate() -> list[Finding]:
    findings: list[Finding] = []

    start = time.monotonic()
    off = run_preset(
        "defense_off", DEFENSE_BASE_ATTACK.model_copy(update=DEFENSE_VARIANTS["defense_off"])
    )
    high = run_preset(
        "defense_high_sensitivity",
        DEFENSE_BASE_ATTACK.model_copy(update=DEFENSE_VARIANTS["defense_high_sensitivity"]),
    )
    # Strict on both: quarantined agents count as lost utility, so a defense
    # that quarantines everyone ties "no defense" on retained_utility, and one
    # that never quarantines ties it on both.
    passed = (
        high.metrics["compromise_fraction"] < off.metrics["compromise_fraction"]
        and high.metrics["retained_utility"] > off.metrics["retained_utility"]
    )
    findings.append(
        Finding(
            name="high-sensitivity defense contains the attack better than no defense",
            passed=passed,
            detail=(
                f"compromise_fraction off={off.metrics['compromise_fraction']:.2f} "
                f"high={high.metrics['compromise_fraction']:.2f}, "
                f"retained_utility off={off.metrics['retained_utility']:.2f} "
                f"high={high.metrics['retained_utility']:.2f}"
            ),
            duration_s=time.monotonic() - start,
        )
    )

    start = time.monotonic()
    before = run_preset("remediation_before", REMEDIATION_CASE)
    recs = recommend(
        REMEDIATION_CASE,
        compromise_fraction=before.metrics["compromise_fraction"],
        security_plane_integrity=before.metrics["security_plane_integrity"],
    )
    if recs:
        after = run_preset(
            "remediation_after", REMEDIATION_CASE.model_copy(update=recs[0].config_diff)
        )
        passed = (
            after.metrics["retained_utility"] > before.metrics["retained_utility"]
            and after.metrics["security_plane_integrity"]
            >= before.metrics["security_plane_integrity"]
        )
        detail = (
            f"applied {recs[0].config_diff}: retained_utility "
            f"{before.metrics['retained_utility']:.2f} -> {after.metrics['retained_utility']:.2f}, "
            f"security_plane_integrity {before.metrics['security_plane_integrity']:.2f} -> "
            f"{after.metrics['security_plane_integrity']:.2f}"
        )
    else:
        passed = False
        detail = "the remediation case triggered no recommendation"
    findings.append(
        Finding(
            name="recommended remediation measurably improves the remediation case",
            passed=passed,
            detail=detail,
            duration_s=time.monotonic() - start,
        )
    )

    return findings
