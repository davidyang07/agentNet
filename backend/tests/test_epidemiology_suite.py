"""The epidemiology suite (PLAN 14.4 C.6). CI runs the whole suite as its own
job (scripts/run_epidemiology.py); these tests cover one real sweep and the
script's contract."""

import importlib.util
from pathlib import Path

import pytest

from app.benchmark import epidemiology
from app.benchmark.epidemiology import Check, Sweep, mean_degree, run_suite

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "run_epidemiology.py"


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("run_epidemiology_script", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mean_degree_matches_the_edge_count_both_generators_use():
    # 180 agents, edge_density 2: 2 * 2 * 178 / 180
    assert mean_degree(2, 180) == pytest.approx(3.956, abs=1e-3)


def test_a_real_sweep_measures_and_checks():
    [sweep] = run_suite(["signature_delay"])
    assert [row["delay_ticks"] for row in sweep.rows] == [0, 2, 5, 10, 20]
    assert sweep.checks and all(check.passed for check in sweep.checks), sweep.checks


def _stub(*passed: bool):
    def run(names=None):
        return [
            Sweep(
                name="stub",
                description="d",
                rows=[{"x": 1}],
                checks=[Check(f"check-{i}", p, "detail") for i, p in enumerate(passed)],
            )
        ]

    return run


@pytest.mark.parametrize(("passed", "code"), [((True, True), 0), ((True, False), 1)])
def test_the_script_fails_when_any_check_fails(script, monkeypatch, tmp_path, passed, code):
    monkeypatch.setattr(script, "run_suite", _stub(*passed))
    monkeypatch.setattr(script, "ARTIFACTS_DIR", tmp_path)
    assert script.main([]) == code
    report = (tmp_path / "report.md").read_text()
    assert ("**FAIL**" in report) is (code == 1)
    assert (tmp_path / "results.json").exists()


def test_the_script_refuses_an_unknown_sweep(script):
    assert script.main(["no_such_sweep"]) == 2


def test_every_sweep_is_registered_once():
    names = [name for name, _, _ in epidemiology.SWEEPS]
    assert len(names) == len(set(names)) == 5
