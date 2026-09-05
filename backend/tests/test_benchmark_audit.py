from app.benchmark.audit import (
    audit_remediation_candidates,
    build_audit_report,
    render_audit_markdown,
    strongest_candidate,
)


def test_audit_finds_at_least_the_three_known_spi_candidates():
    # sentinel_compromise_attack, combined_byzantine_multi_vector, and
    # adaptive_plus_byzantine are already known (backend/.artifacts/
    # benchmark/results.json) to have security_plane_integrity < 1.0, so
    # recommend() must fire a sentinel_count recommendation for each.
    candidates = audit_remediation_candidates()
    names = {c.name for c in candidates}
    assert "sentinel_compromise_attack" in names
    assert "combined_byzantine_multi_vector" in names
    assert "adaptive_plus_byzantine" in names


def test_audit_finds_the_no_defense_candidate():
    # propagation_no_defense has compromise_fraction=1.0 and
    # defense_enabled=False, so recommend() must fire an "enable defense"
    # recommendation for it too.
    candidates = audit_remediation_candidates()
    names = {c.name for c in candidates}
    assert "propagation_no_defense" in names


def test_audit_produces_a_result_for_every_triggered_candidate():
    # Not every recommendation actually improves retained_utility once
    # re-tested for real: raising sentinel_count grows the security-plane
    # node pool that security_plane_integrity's denominator counts over, so
    # for the combined/adaptive Byzantine presets it can measurably worsen
    # both security_plane_integrity and retained_utility (a real, surprising
    # result this audit exists to surface honestly, not to hide) -- only the
    # "enable defense" branch (propagation_no_defense, defense_off) reliably
    # helps across the matrix. So this only asserts every triggered
    # candidate produced a real before/after measurement, not that all of
    # them improved.
    candidates = audit_remediation_candidates()
    assert candidates
    for c in candidates:
        assert isinstance(c.before.metrics["retained_utility"], float)
        assert isinstance(c.after.metrics["retained_utility"], float)


def test_strongest_candidate_has_the_largest_retained_utility_delta():
    candidates = audit_remediation_candidates()
    strongest = strongest_candidate(candidates)
    deltas = [
        c.after.metrics["retained_utility"] - c.before.metrics["retained_utility"]
        for c in candidates
    ]
    assert (
        strongest.after.metrics["retained_utility"] - strongest.before.metrics["retained_utility"]
        == max(deltas)
    )


def test_build_and_render_audit_report_is_json_and_markdown_safe():
    candidates = audit_remediation_candidates()
    strongest = strongest_candidate(candidates)
    report = build_audit_report(candidates, strongest)
    assert report["strongest"]["name"] == strongest.name
    assert len(report["candidates"]) == len(candidates)
    markdown = render_audit_markdown(report)
    assert strongest.name in markdown
    assert "|" in markdown  # a markdown table was rendered
