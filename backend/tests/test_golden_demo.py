from app.benchmark.golden_demo import run_golden_demo


def test_golden_demo_is_deterministic():
    result1 = run_golden_demo()
    result2 = run_golden_demo()
    assert result1.baseline.metrics == result2.baseline.metrics
    assert result1.narrative == result2.narrative


def test_golden_demo_produces_all_narrative_beats():
    result = run_golden_demo()
    required_substrings = [
        "prompt injection",  # beat 1/2: indirect prompt injection + propagation
        "quarantined",  # beat 3: initial defense detects/quarantines
        "adaptive attacker",  # beat 4: strategy switch
        "sentinel",  # beat 5: attacker targets the security plane
        "false threat signature",  # beat 6: false report / trust manipulation
        "security_plane_integrity",  # beat 7: AgentShield identifies the failed control
        "remediation recommended",  # beat 8: remediation applied
        "re-ran",  # beat 9: same scenario re-run
    ]
    joined = "\n".join(result.narrative)
    for substring in required_substrings:
        assert substring in joined, f"missing beat evidence: {substring!r}\n\n{joined}"


def test_golden_demo_shows_measurable_resilience_improvement():
    result = run_golden_demo()
    assert result.recommendation is not None
    assert result.rerun is not None
    # security_plane_integrity is the metric the recommendation directly
    # targets (docs/PLAN.md §7); retained_utility is the downstream effect
    # of more agents keeping a healthy sentinel watching them.
    assert (
        result.rerun.metrics["security_plane_integrity"]
        >= result.baseline.metrics["security_plane_integrity"]
    )
    assert (
        result.rerun.metrics["retained_utility"] >= result.baseline.metrics["retained_utility"]
    )
