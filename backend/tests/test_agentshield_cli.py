from app.benchmark.cli import Finding, evaluate


def test_evaluate_returns_a_list_of_findings():
    findings = evaluate()
    assert isinstance(findings, list)
    assert len(findings) >= 2
    assert all(isinstance(f, Finding) for f in findings)


def test_evaluate_findings_all_pass():
    # A real, checkable claim: on this codebase's current defense/remediation
    # mechanisms, both findings evaluate() checks should currently pass. If
    # this ever fails, that's a genuine regression to investigate, not a
    # test to loosen.
    findings = evaluate()
    for finding in findings:
        assert finding.passed, f"{finding.name}: {finding.detail}"
