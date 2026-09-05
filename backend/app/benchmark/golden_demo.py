"""The canonical golden demo (Priority 2): one scenario, one config, whose
real event log narrates all ten brief beats -- indirect prompt injection,
propagation, initial quarantine, an adaptive attacker strategy switch, a
sentinel-compromise attack on the security plane, a false threat-memory
report, AgentNet identifying the resulting security_plane_integrity gap via
the existing remediation engine, applying the fix, and re-running to show
measurable improvement. No new scenario logic -- pure config selection over
app/scenarios/registry.py's existing scenarios, narrated by walking the
resulting event log.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.benchmark.runner import BenchmarkRun, run_headless_async
from app.remediation.analyze import Recommendation, recommend
from app.schemas.experiment import ExperimentConfig

GOLDEN_DEMO_CONFIG = ExperimentConfig(
    seed=42,
    node_count=40,
    real_agent_count=10,
    model_provider="mock",
    active_scenarios=[
        "adaptive_attacker", "prompt_injection", "sentinel_compromise", "attestation",
    ],
    adaptive_detection_threshold=0.3,
    detector_sensitivity=0.15,
    sentinel_count=1,
    sentinel_compromise_rate=0.08,
    attestation_replay_rate=0.3,
    defense_enabled=True,
    p_same=0.6,
    p_cross=0.2,
    max_ticks=150,
)


@dataclass
class GoldenDemoResult:
    baseline: BenchmarkRun
    narrative: list[str]
    recommendation: Recommendation | None
    rerun: BenchmarkRun | None


def _narrate(run: BenchmarkRun) -> list[str]:
    lines: list[str] = []
    for event in run.events:
        etype = event.event_type.value
        if etype == "COMPROMISE_SUCCEEDED" and event.metadata.get("real_agent"):
            lines.append(
                f"tick {event.sim_tick}: indirect prompt injection compromised "
                f"{event.target_agent_id} via a real LLM-backed lateral attempt from "
                f"{event.source_agent_id}"
            )
        elif etype == "COMPROMISE_SUCCEEDED" and event.metadata.get("initial_compromise"):
            lines.append(
                f"tick {event.sim_tick}: seeded initial compromise at {event.target_agent_id}"
            )
        elif etype == "COMPROMISE_SUCCEEDED":
            lines.append(
                f"tick {event.sim_tick}: compromise propagated to {event.target_agent_id}"
            )
        elif etype == "AGENT_QUARANTINED" and event.metadata.get("legitimate") is not False:
            lines.append(
                f"tick {event.sim_tick}: {event.agent_id} quarantined by initial defense"
            )
        elif (
            etype == "POLICY_VIOLATION"
            and event.metadata.get("violation_type") == "sentinel_subverted"
        ):
            lines.append(
                f"tick {event.sim_tick}: adaptive attacker subverted sentinel {event.agent_id} "
                "-- the attacker shifted from attacking agents to attacking the security "
                "plane itself"
            )
        elif etype == "THREAT_SIGNATURE_PUBLISHED" and event.metadata.get("legitimate") is False:
            lines.append(
                f"tick {event.sim_tick}: subverted sentinel {event.agent_id} published a false "
                "threat signature (false report / trust manipulation)"
            )
        elif etype == "ATTESTATION_VERIFIED" and event.metadata.get("replayed"):
            lines.append(
                f"tick {event.sim_tick}: a stale attestation nonce was replayed and accepted"
            )

    lines.append(
        "attacker strategy: the adaptive attacker recomputed its strategy every tick from the "
        "observed quarantine rate, switching between aggressive (highest-degree-neighbor) and "
        "stealthy (lowest-degree-neighbor) targeting"
    )
    lines.append(
        f"AgentShield identified the failed control: final security_plane_integrity="
        f"{run.metrics['security_plane_integrity']:.2f}"
    )
    return lines


def run_golden_demo(model_provider: str = "mock") -> GoldenDemoResult:
    config = GOLDEN_DEMO_CONFIG.model_copy(update={"model_provider": model_provider})
    baseline = run_headless_async("golden_demo_baseline", config)
    narrative = _narrate(baseline)

    recs = recommend(
        config,
        compromise_fraction=baseline.metrics["compromise_fraction"],
        security_plane_integrity=baseline.metrics["security_plane_integrity"],
    )
    if not recs:
        return GoldenDemoResult(
            baseline=baseline, narrative=narrative, recommendation=None, rerun=None
        )

    recommendation = recs[0]
    narrative.append(f"remediation recommended: {recommendation.description}")
    rerun_config = config.model_copy(update=recommendation.config_diff)
    rerun = run_headless_async("golden_demo_rerun", rerun_config)
    narrative.append(
        "re-ran the same scenario with the remediation applied: security_plane_integrity "
        f"{baseline.metrics['security_plane_integrity']:.2f} -> "
        f"{rerun.metrics['security_plane_integrity']:.2f}"
    )
    return GoldenDemoResult(
        baseline=baseline, narrative=narrative, recommendation=recommendation, rerun=rerun
    )
