import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from app.benchmark import cli
from app.benchmark.cli import Finding, evaluate
from app.engine.state import SecurityState
from app.remediation.analyze import Recommendation
from app.security import detection

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "agentshield_test.py"


@pytest.fixture(scope="module")
def script():
    """The CI gate's contract is the script's exit code and stdout, not just
    evaluate() -- .github/workflows/ci.yml runs the script directly, so a
    regression in either is a broken gate."""
    spec = importlib.util.spec_from_file_location("agentshield_test_script", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stub_findings(*passed: bool) -> list[Finding]:
    return [
        Finding(name=f"finding-{i}", passed=p, detail="detail", duration_s=0.5)
        for i, p in enumerate(passed)
    ]


@pytest.mark.parametrize(
    ("passed", "expected_exit"),
    [((True, True), 0), ((True, False), 1), ((False, False), 1)],
)
def test_cli_exit_code_is_zero_only_when_every_finding_passes(
    script, monkeypatch, passed, expected_exit
):
    monkeypatch.setattr(script, "evaluate", lambda: _stub_findings(*passed))
    monkeypatch.setattr(sys, "argv", ["agentshield_test.py"])
    assert script.main() == expected_exit


def test_cli_text_output_marks_each_finding_and_summarizes(script, monkeypatch, capsys):
    monkeypatch.setattr(script, "evaluate", lambda: _stub_findings(True, False))
    monkeypatch.setattr(sys, "argv", ["agentshield_test.py"])
    assert script.main() == 1
    out = capsys.readouterr().out
    assert "[PASS] finding-0" in out
    assert "[FAIL] finding-1" in out
    assert "1/2 findings passed" in out


def test_cli_json_output_is_one_parseable_line_with_the_documented_shape(
    script, monkeypatch, capsys
):
    monkeypatch.setattr(script, "evaluate", lambda: _stub_findings(True, False))
    monkeypatch.setattr(sys, "argv", ["agentshield_test.py", "--json"])
    assert script.main() == 1
    out = capsys.readouterr().out.strip()
    assert "\n" not in out, "JSON mode must emit exactly one line for CI log parsers"
    payload = json.loads(out)
    assert payload["ok"] is False
    assert isinstance(payload["duration_s"], float)
    assert [f["name"] for f in payload["findings"]] == ["finding-0", "finding-1"]
    for finding in payload["findings"]:
        assert set(finding) == {"name", "passed", "detail", "duration_s"}


def test_cli_json_output_reports_ok_true_when_all_pass(script, monkeypatch, capsys):
    monkeypatch.setattr(script, "evaluate", lambda: _stub_findings(True, True))
    monkeypatch.setattr(sys, "argv", ["agentshield_test.py", "--json"])
    assert script.main() == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


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


# The gate is only meaningful if it fails when the mechanism a check covers
# stops working -- the earlier `>=` checks passed with detection disabled.


def _finding(findings: list[Finding], name_prefix: str) -> Finding:
    return next(f for f in findings if f.name.startswith(name_prefix))


def test_gate_fails_when_detection_never_quarantines(monkeypatch):
    monkeypatch.setattr(detection, "step", lambda state, config: (state, []))
    assert not _finding(evaluate(), "high-sensitivity defense").passed


def test_gate_fails_when_detection_quarantines_every_agent(monkeypatch):
    def quarantine_everyone(state, config):
        if not config.defense_enabled:
            return state, []
        nodes = {
            node_id: replace(node, security_state=SecurityState.QUARANTINED)
            for node_id, node in state.nodes.items()
        }
        return replace(state, nodes=nodes), []

    monkeypatch.setattr(detection, "step", quarantine_everyone)
    assert not _finding(evaluate(), "high-sensitivity defense").passed


def test_gate_fails_when_the_recommended_remediation_changes_nothing(monkeypatch):
    monkeypatch.setattr(
        cli, "recommend", lambda *args, **kwargs: [Recommendation(description="no-op")]
    )
    assert not _finding(evaluate(), "recommended remediation").passed


def test_gate_fails_when_no_remediation_is_recommended(monkeypatch):
    monkeypatch.setattr(cli, "recommend", lambda *args, **kwargs: [])
    assert not _finding(evaluate(), "recommended remediation").passed
