"""The epidemiology suite (docs/PLAN.md §14.4 C.6): five sweeps that test the
Phase C mechanisms against the predictions of the papers they follow --
[S2] "Stopping Agent Smith" and [S1] "Semantic Immunity" (§14.8).

Each sweep averages over seeds and states its checks as qualitative claims
(a threshold exists and moves the right way, a trade-off has both sides),
not as the papers' exact numbers: the model here is an abstraction of
theirs. A failed check is reported, never hidden -- `run_epidemiology.py`
exits non-zero on one, and the measured tables are documented in PLAN
§14.4 whether or not they agree with the papers.

"Reff" here is `r0_estimate` measured under the immune regime: the mean
offspring of generations 0-1 with immune memory in place, which is why the
immunity sweeps pre-seed patient zero's signature ([S1]'s red-team
pre-seeding). Detection-published signatures arrive only after a detection,
by which time a fast outbreak is already saturating.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from statistics import mean
from typing import Any

from app.benchmark.config import BenchmarkConfig
from app.benchmark.runner import run_preset

SEEDS = tuple(range(10))


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


@dataclass
class Sweep:
    name: str
    description: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    duration_s: float = 0.0


def averaged(config: dict[str, Any], seeds: Iterable[int] = SEEDS) -> dict[str, float]:
    """Mean of the epidemic and immunity metrics over `seeds`."""
    runs = [run_preset("epidemiology", BenchmarkConfig(**(config | {"seed": s}))) for s in seeds]
    out: dict[str, float] = {}
    for key in ("final_size", "r0_estimate", "signature_block_rate", "benign_block_rate"):
        values = [r.metrics[key] for r in runs if r.metrics[key] is not None]
        out[key] = round(mean(values), 3) if values else float("nan")
    return out


def _timed(build: Callable[[Sweep], None], sweep: Sweep) -> Sweep:
    start = time.monotonic()
    build(sweep)
    sweep.duration_s = round(time.monotonic() - start, 2)
    return sweep


# 1. [S2]: only inference-capable agents propagate, so the capable fraction
# has an epidemic threshold near 1/<k> on a random graph; hubs collapse it
# and the periphery contains it.

THRESHOLD_FRACTIONS = (0.0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.6, 1.0)
THRESHOLD_BASE = dict(
    node_count=180,
    max_ticks=30,
    p_same=1.0,
    p_cross=1.0,
    defense_enabled=False,
    initial_compromised="random_node",
)
# [S2]'s ER graph has <k> = 5, which no integer edge_density gives here:
# 2 and 3 bracket it (<k> = 2 * edge_density * (n - edge_density) / n).
THRESHOLD_GRAPHS = {
    "ER <k>~4.0, random": dict(topology="erdos_renyi", edge_density=2),
    "ER <k>~5.9, random": dict(topology="erdos_renyi", edge_density=3),
    "BA, random": dict(topology="barabasi_albert", edge_density=2),
    "BA, hubs": dict(topology="barabasi_albert", edge_density=2, inference_placement="hubs"),
    "BA, periphery": dict(
        topology="barabasi_albert", edge_density=2, inference_placement="periphery"
    ),
}


def mean_degree(edge_density: int, nodes: int) -> float:
    return 2 * edge_density * (nodes - edge_density) / nodes


def _threshold(sweep: Sweep) -> None:
    curves: dict[str, dict[float, float]] = {}
    for graph, fields in THRESHOLD_GRAPHS.items():
        curve = {
            rho: averaged(THRESHOLD_BASE | fields | {"inference_fraction": rho})["final_size"]
            for rho in THRESHOLD_FRACTIONS
        }
        curves[graph] = curve
        sweep.rows.append({"graph": graph, **{f"rho={rho}": v for rho, v in curve.items()}})

    er4, er6 = curves["ER <k>~4.0, random"], curves["ER <k>~5.9, random"]
    rho_c4 = 1 / mean_degree(2, THRESHOLD_BASE["node_count"])
    sweep.checks += [
        Check(
            "final size never falls as more agents can run inference",
            all(
                curve[b] >= curve[a] - 0.02
                for curve in curves.values()
                for a, b in zip(THRESHOLD_FRACTIONS, THRESHOLD_FRACTIONS[1:], strict=False)
            ),
            "every curve is non-decreasing in the capable fraction (tolerance 0.02)",
        ),
        Check(
            f"a random graph has a threshold: small below 1/<k> = {rho_c4:.2f}, large well above",
            er4[0.1] <= 0.1 and er4[0.6] >= 0.5,
            f"<k>~4: final size {er4[0.1]:.2f} at rho=0.1, {er4[0.6]:.2f} at rho=0.6",
        ),
        Check(
            "a denser random graph takes off at a lower capable fraction",
            er6[0.3] > er4[0.3],
            f"final size at rho=0.3: <k>~5.9 {er6[0.3]:.2f} vs <k>~4.0 {er4[0.3]:.2f}",
        ),
        Check(
            "capable hubs give a near-zero threshold",
            curves["BA, hubs"][0.1] >= 0.5,
            f"final size {curves['BA, hubs'][0.1]:.2f} with 10% capable, on the hubs",
        ),
        Check(
            "capable periphery agents keep outbreaks small",
            curves["BA, periphery"][0.6] <= 0.1,
            f"final size {curves['BA, periphery'][0.6]:.2f} with 60% capable, on the periphery",
        ),
    ]


# 2-5. [S1]/[S2] immune memory. A homogeneous random graph (<k>~5.9) with
# transmission 0.4 has R0 ~ 3.7, so herd immunity needs coverage above
# ~1 - 1/3.7 = 0.73.

IMMUNITY_BASE = dict(
    node_count=200,
    topology="erdos_renyi",
    edge_density=3,
    p_same=0.4,
    p_cross=0.4,
    max_ticks=60,
    defense_enabled=False,
    initial_compromised="random_node",
    immunity_enabled=True,
    preseed_patient_zero_signature=True,
    strain_benign_distance=12,
)


def _trade_off(sweep: Sweep) -> None:
    results: dict[tuple[float, int, float], dict[str, float]] = {}
    for mutation in (0.0, 0.5, 1.0):
        for radius in (0, 2, 6, 12):
            for coverage in (0.0, 0.5, 0.9):
                fields = dict(
                    immunity_coverage=coverage,
                    signature_radius=radius,
                    mutation_rate=mutation,
                    benign_probes_per_tick=2,
                )
                result = averaged(IMMUNITY_BASE | fields, seeds=SEEDS[:6])
                results[(mutation, radius, coverage)] = result
                sweep.rows.append(
                    {"mutation": mutation, "radius": radius, "coverage": coverage, **result}
                )

    def fs(m, r, c):
        return results[(m, r, c)]["final_size"]

    sweep.checks += [
        Check(
            "higher coverage gives smaller outbreaks without mutation",
            fs(0.0, 0, 0.0) > fs(0.0, 0, 0.5) > fs(0.0, 0, 0.9),
            f"final size {fs(0.0, 0, 0.0):.2f} > {fs(0.0, 0, 0.5):.2f} > {fs(0.0, 0, 0.9):.2f}",
        ),
        Check(
            "coverage above the herd-immunity threshold holds Reff below 1",
            results[(0.0, 0, 0.9)]["r0_estimate"] < 1 <= results[(0.0, 0, 0.0)]["r0_estimate"],
            f"Reff {results[(0.0, 0, 0.9)]['r0_estimate']:.2f} at 90% coverage, "
            f"{results[(0.0, 0, 0.0)]['r0_estimate']:.2f} at none",
        ),
        Check(
            "mutation escapes an exact-match signature",
            fs(1.0, 0, 0.9) > fs(0.0, 0, 0.9),
            f"final size at 90% coverage, radius 0: {fs(0.0, 0, 0.9):.2f} without mutation, "
            f"{fs(1.0, 0, 0.9):.2f} when every transmission mutates",
        ),
        Check(
            "a wider radius catches the variants back",
            fs(1.0, 6, 0.9) < fs(1.0, 0, 0.9),
            f"final size with full mutation at 90% coverage: radius 0 {fs(1.0, 0, 0.9):.2f}, "
            f"radius 6 {fs(1.0, 6, 0.9):.2f}",
        ),
        # Benign traffic sits 0-12 bits from the centroid and the worm 12
        # bits from it, so a radius well short of 12 never touches benign
        # traffic: the cost appears as the radius reaches the worm's disguise.
        Check(
            "a radius reaching the worm's distance from benign blocks benign traffic",
            results[(1.0, 6, 0.9)]["benign_block_rate"]
            < results[(1.0, 12, 0.9)]["benign_block_rate"],
            f"benign block rate radius 6 {results[(1.0, 6, 0.9)]['benign_block_rate']:.3f}, "
            f"radius 12 {results[(1.0, 12, 0.9)]['benign_block_rate']:.3f}",
        ),
    ]


def _delay(sweep: Sweep) -> None:
    # Signatures come from detections here, not pre-seeding, so the delay
    # between publication and adoption matters.
    base = IMMUNITY_BASE | dict(
        preseed_patient_zero_signature=False,
        defense_enabled=True,
        detector_sensitivity=0.3,
        immunity_coverage=0.9,
    )
    sizes = {}
    for delay in (0, 2, 5, 10, 20):
        result = averaged(base | {"signature_delay_ticks": delay})
        sizes[delay] = result["final_size"]
        sweep.rows.append({"delay_ticks": delay, **result})
    sweep.checks.append(
        Check(
            "a slower signature rollout lets the outbreak grow",
            sizes[20] > sizes[0],
            f"final size {sizes[0]:.2f} with immediate adoption, {sizes[20]:.2f} after 20 ticks",
        )
    )


def _placement(sweep: Sweep) -> None:
    # [S2] Figs. 6-7: on a hub-heavy graph, immunizing the hubs first
    # fragments the network.
    base = IMMUNITY_BASE | dict(topology="barabasi_albert", edge_density=2, p_same=0.5,
                                p_cross=0.5)
    sizes = {}
    for coverage in (0.2, 0.4):
        for placement in ("hubs", "random", "periphery"):
            result = averaged(
                base | {"immunity_coverage": coverage, "immunity_placement": placement}
            )
            sizes[(coverage, placement)] = result["final_size"]
            sweep.rows.append({"coverage": coverage, "placement": placement, **result})
    sweep.checks.append(
        Check(
            "immunizing hubs first beats random beats periphery",
            sizes[(0.2, "hubs")] < sizes[(0.2, "random")] < sizes[(0.2, "periphery")],
            "final size at 20% coverage: "
            + ", ".join(f"{p} {sizes[(0.2, p)]:.2f}" for p in ("hubs", "random", "periphery")),
        )
    )


def _poisoning(sweep: Sweep) -> None:
    base = IMMUNITY_BASE | dict(
        preseed_patient_zero_signature=False,
        defense_enabled=True,
        detector_sensitivity=0.3,
        signature_radius=4,
        sentinel_count=3,
        benign_probes_per_tick=2,
        active_scenarios=["propagation", "sentinel_compromise"],
    )
    results = {}
    for rate in (0.0, 0.2, 1.0):
        result = averaged(base | {"sentinel_compromise_rate": rate})
        results[rate] = result
        sweep.rows.append({"sentinel_compromise_rate": rate, **result})
    sweep.checks += [
        Check(
            "poisoned immune memory blocks benign traffic",
            results[1.0]["benign_block_rate"] > results[0.0]["benign_block_rate"],
            f"benign block rate {results[0.0]['benign_block_rate']:.3f} clean, "
            f"{results[1.0]['benign_block_rate']:.3f} poisoned",
        ),
        # Subverted sentinels also suppress detection of the agents they
        # watch, so this measures the whole attack on the security plane.
        Check(
            "and protects no one",
            results[1.0]["final_size"] >= results[0.0]["final_size"],
            f"final size {results[0.0]['final_size']:.2f} clean, "
            f"{results[1.0]['final_size']:.2f} poisoned",
        ),
    ]


SWEEPS: list[tuple[str, str, Callable[[Sweep], None]]] = [
    ("inference_threshold", "[S2] threshold: capable fraction x graph x placement, "
     "defense off, 30 ticks", _threshold),
    (
        "immunity_trade_off",
        "[S1] trade-off: coverage x signature radius x mutation rate",
        _trade_off,
    ),
    ("signature_delay", "signature delay vs outbreak size, detection-published", _delay),
    ("immunity_placement", "[S2] Figs. 6-7: hub-first vs periphery immunization", _placement),
    ("memory_poisoning", "immune-memory poisoning by subverted sentinels", _poisoning),
]


def run_suite(names: Iterable[str] | None = None) -> list[Sweep]:
    wanted = set(names) if names is not None else None
    return [
        _timed(build, Sweep(name=name, description=description))
        for name, description, build in SWEEPS
        if wanted is None or name in wanted
    ]
