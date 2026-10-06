#!/usr/bin/env python3
"""Runs every config in CONFIGS under two different PYTHONHASHSEED values,
headless, and diffs the deterministic projection of their event sequences
(SPEC §6.2 step 5). Two processes with different hash seeds catch what two
runs in one process can't: anything that depends on set or dict-of-str
iteration order. Each opt-in feature gets a config here when it lands
(docs/PLAN.md §14.4), so the default config alone no longer stands for all
of them. The canonical run's two event logs are written to .artifacts/.
"""

import hashlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from app.benchmark.runner import run_preset
from app.schemas.experiment import ExperimentConfig

ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / ".artifacts"
HASH_SEEDS = ("1", "2")

CONFIGS: dict[str, ExperimentConfig] = {
    # SPEC §6.2's canonical demo config.
    "canonical": ExperimentConfig(seed=42, node_count=60),
    "adaptive_attacker": ExperimentConfig(seed=3, active_scenarios=["adaptive_attacker"]),
    "security_plane": ExperimentConfig(
        seed=5,
        active_scenarios=[
            "propagation",
            "sentinel_compromise",
            "attestation",
            "byzantine_collusion",
        ],
        sentinel_count=2,
        credential_count=3,
        sentinel_compromise_rate=0.3,
        attestation_replay_rate=0.3,
        byzantine_collusion_rate=0.3,
        false_quarantine_rate=0.01,
    ),
    "real_agents_mock": ExperimentConfig(seed=11, real_agent_count=8, p_same=0.5, p_cross=0.2),
    # docs/PLAN.md §14.4 C.2
    "inference_dead_ends": ExperimentConfig(
        seed=8, inference_fraction=0.4, p_same=0.5, p_cross=0.2, defense_enabled=False
    ),
    "erdos_renyi": ExperimentConfig(seed=8, topology="erdos_renyi", p_same=0.4),
    # docs/PLAN.md §14.4 C.3, real agents included
    "strain_mutation": ExperimentConfig(
        seed=12, mutation_rate=0.3, mutation_bits=2, real_agent_count=6, p_same=0.5, p_cross=0.2
    ),
}

DETERMINISM_FIELDS = (
    "seq",
    "sim_tick",
    "event_type",
    "agent_id",
    "source_agent_id",
    "target_agent_id",
    "metadata",
)


def _events(config: ExperimentConfig) -> list[dict]:
    return [json.loads(e.model_dump_json()) for e in run_preset("determinism", config).events]


def _projection(events: list[dict]) -> list[list]:
    return [[e[f] for f in DETERMINISM_FIELDS] for e in events]


def _digests() -> dict[str, tuple[str, int]]:
    out = {}
    for name, config in CONFIGS.items():
        projection = _projection(_events(config))
        encoded = json.dumps(projection, sort_keys=True).encode()
        out[name] = (hashlib.sha256(encoded).hexdigest(), len(projection))
    return out


def _digests_under(hash_seed: str) -> dict[str, tuple[str, int]]:
    env = {**os.environ, "PYTHONHASHSEED": hash_seed}
    result = subprocess.run(
        [sys.executable, __file__, "--digests"], env=env, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"digest run failed:\n{result.stderr}")
    return {name: tuple(value) for name, value in json.loads(result.stdout).items()}


def main() -> int:
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    canonical = CONFIGS["canonical"]
    for i in (1, 2):
        events = _events(canonical)
        (ARTIFACTS_DIR / f"run-{i}.jsonl").write_text("\n".join(map(json.dumps, events)) + "\n")

    first, second = (_digests_under(seed) for seed in HASH_SEEDS)
    failed = False
    for name in CONFIGS:
        (digest_a, count), (digest_b, _) = first[name], second[name]
        if digest_a == digest_b:
            print(f"PASS: {name}: {count} events identical")
        else:
            failed = True
            print(
                f"FAIL: {name}: event sequences differ between PYTHONHASHSEED="
                f"{HASH_SEEDS[0]} and {HASH_SEEDS[1]}",
                file=sys.stderr,
            )
    return 1 if failed else 0


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    if sys.argv[1:] == ["--digests"]:
        print(json.dumps(_digests()))
        raise SystemExit(0)
    raise SystemExit(main())
