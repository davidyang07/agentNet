#!/usr/bin/env python3
"""agentshield test: CI-friendly pass/fail gate over a fast subset of the
benchmark suite + golden demo. Exit 0 if every finding passes, else 1."""

from app.benchmark.cli import evaluate


def main() -> int:
    findings = evaluate()
    ok = True
    for finding in findings:
        status = "PASS" if finding.passed else "FAIL"
        print(f"[{status}] {finding.name}: {finding.detail}")
        ok = ok and finding.passed
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
