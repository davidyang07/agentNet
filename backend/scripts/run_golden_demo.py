#!/usr/bin/env python3
"""Runs the golden demo (Priority 2) and writes a narrative report to
backend/.artifacts/golden_demo/. Pass --model-provider vllm to use a real
Qwen/vLLM endpoint (requires VLLM_BASE_URL set -- see README's "Real
(LLM-backed) agents" section); defaults to the deterministic mock provider.
"""

import argparse
import json
from pathlib import Path

from app.benchmark.golden_demo import run_golden_demo

ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / ".artifacts" / "golden_demo"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-provider", choices=["mock", "vllm"], default="mock")
    args = parser.parse_args()

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    result = run_golden_demo(model_provider=args.model_provider)

    lines = ["# AgentNet Golden Demo", ""]
    lines.extend(result.narrative)
    (ARTIFACTS_DIR / "report.md").write_text("\n".join(lines))

    summary = {
        "baseline_metrics": result.baseline.metrics,
        "recommendation": result.recommendation.description if result.recommendation else None,
        "rerun_metrics": result.rerun.metrics if result.rerun else None,
    }
    (ARTIFACTS_DIR / "result.json").write_text(json.dumps(summary, indent=2))

    print("\n".join(result.narrative))
    print(f"\nWrote {ARTIFACTS_DIR / 'report.md'} and {ARTIFACTS_DIR / 'result.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
