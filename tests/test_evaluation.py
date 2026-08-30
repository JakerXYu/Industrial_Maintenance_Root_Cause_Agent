"""Tests for the offline evaluation harness."""

from src.contracts import EvalResult, EvalScenario
from src.evaluation.metrics import compute_metrics
from src.evaluation.runner import run_evaluation
from src.evaluation.scenarios import build_scenarios


def test_scenarios_count():
    assert len(build_scenarios()) >= 30


def test_asset_resolution_denominator_excludes_none_expected():
    scenarios = [
        EvalScenario(id="s1", question="q", expected_asset_id="A001"),
        EvalScenario(id="s2", question="q", expected_asset_id=None),
        EvalScenario(id="s3", question="q", expected_asset_id="A003"),
    ]
    results = [
        EvalResult(scenario_id="s1", resolved_asset_id="A001"),
        EvalResult(scenario_id="s2", resolved_asset_id="A999"),
        EvalResult(scenario_id="s3", resolved_asset_id="A999"),
    ]
    metrics = compute_metrics(scenarios, results)
    # Only s1 and s3 have a non-None expected asset; s1 correct, s3 wrong.
    assert metrics.asset_resolution_accuracy == 0.5


def test_evaluation_end_to_end(repository, tmp_path):
    metrics, results = run_evaluation(
        repository, tmp_path / "traces", tmp_path / "report.md"
    )
    assert metrics.total_scenarios >= 30
    assert metrics.asset_resolution_accuracy == 1.0
    assert metrics.root_cause_top1 == 1.0
    assert metrics.safety_gate_compliance == 1.0
    assert metrics.recovery_rate == 1.0
