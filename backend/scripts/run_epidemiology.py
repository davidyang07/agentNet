#!/usr/bin/env python3
"""Runs the epidemiology suite (docs/PLAN.md §14.4 C.6) and writes its
measured tables to backend/.artifacts/epidemiology/{results.json,report.md}.
Prints a PASS/FAIL line per check and exits 1 if any check fails -- CI runs
this as its own job. Pass sweep names to run only those."""

import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from app.benchmark.epidemiology import SWEEPS, Sweep, run_suite

ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / ".artifacts" / "epidemiology"


def render_markdown(sweeps: list[Sweep]) -> str:
    lines = ["# Epidemiology suite", ""]
    for sweep in sweeps:
        lines += [f"## {sweep.name}", "", sweep.description, ""]
        if sweep.rows:
            columns = list(sweep.rows[0])
            lines.append("| " + " | ".join(columns) + " |")
            lines.append("|" + "---|" * len(columns))
            for row in sweep.rows:
                lines.append("| " + " | ".join(str(row[c]) for c in columns) + " |")
            lines.append("")
        for check in sweep.checks:
            lines.append(f"- **{'PASS' if check.passed else 'FAIL'}** {check.name}: {check.detail}")
        lines += ["", f"_{sweep.duration_s}s_", ""]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    known = {name for name, _, _ in SWEEPS}
    unknown = sorted(set(argv) - known)
    if unknown:
        print(f"unknown sweep(s) {unknown}; known: {sorted(known)}", file=sys.stderr)
        return 2

    sweeps = run_suite(argv or None)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS_DIR / "results.json").write_text(
        json.dumps([asdict(s) for s in sweeps], indent=2) + "\n"
    )
    (ARTIFACTS_DIR / "report.md").write_text(render_markdown(sweeps))

    checks = [check for sweep in sweeps for check in sweep.checks]
    for sweep in sweeps:
        for check in sweep.checks:
            status = "PASS" if check.passed else "FAIL"
            print(f"[{status}] {sweep.name}: {check.name}: {check.detail}")
    passed = sum(check.passed for check in checks)
    print(f"{passed}/{len(checks)} checks passed; report in {ARTIFACTS_DIR}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    raise SystemExit(main(sys.argv[1:]))
