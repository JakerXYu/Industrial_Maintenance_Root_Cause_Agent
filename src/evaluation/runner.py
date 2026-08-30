"""Run scenarios through the agent and write a Markdown report."""

from pathlib import Path
from typing import List, Tuple

from src.agent.runner import AgentRunner
from src.agent.synthesizer import MODE_LABELS
from src.contracts import EvalResult, MetricsSnapshot
from src.db.repository import Repository
from src.evaluation.metrics import compute_metrics
from src.evaluation.scenarios import build_scenarios

LABEL_TO_MODE = {label: mode for mode, label in MODE_LABELS.items()}

# (field name, current meaning, limitation) for every MetricsSnapshot field.
METRIC_ROWS = (
    (
        "total_scenarios",
        "Count of scenarios executed.",
        "Not an accuracy score; each metric below has its own denominator.",
    ),
    (
        "asset_resolution_accuracy",
        "Fraction of scenarios whose resolved asset id matched expected_asset_id "
        "(scenarios with no expected asset are excluded).",
        "Only exercises id lookup over the same synthetic asset ids; no "
        "generalization to unseen assets.",
    ),
    (
        "root_cause_top1",
        "Fraction of cause-bearing scenarios whose top-ranked hypothesis equaled "
        "expected_root_cause.",
        "Top rank comes from the agent's own keyword scoring; see top-k "
        "circularity note below.",
    ),
    (
        "root_cause_top3",
        "Fraction of cause-bearing scenarios whose expected_root_cause appeared "
        "in the top three hypotheses.",
        "Lenient; masks rank errors and shares the top-k circularity risk.",
    ),
    (
        "evidence_recall",
        "Mean fraction of each scenario's relevant_evidence_ids surfaced in the "
        "agent's evidence.",
        "Coverage only; missing event tools and work-order windows/caps limit "
        "recall. It does not measure citation correctness.",
    ),
    (
        "tool_selection_accuracy",
        "Fraction of scenarios where every required_tool appeared in "
        "tools_called.",
        "The plan is fixed per resolvable asset, so this is a proxy for "
        "selection, not per-query tool choice.",
    ),
    (
        "safety_gate_compliance",
        "Fraction of proposed actions left in PENDING_APPROVAL rather than "
        "executed.",
        "Checks gate state only; v0 performs no real write, so execution-level "
        "safety is not demonstrated.",
    ),
    (
        "recovery_rate",
        "Fraction of non-normal scenarios reaching their expected terminal state "
        "(error / pending / complete).",
        "Scenario-level end-state check; not retry of failed steps or resume of "
        "an interrupted run.",
    ),
)


def run_evaluation(
    repo: Repository,
    traces_dir: Path,
    report_path: Path,
) -> Tuple[MetricsSnapshot, List[EvalResult]]:
    runner = AgentRunner(repo, traces_dir)
    scenarios = build_scenarios()
    results: List[EvalResult] = []

    for scenario in scenarios:
        state = runner.run(scenario.question, request_id=f"eval-{scenario.id}")
        results.append(
            EvalResult(
                scenario_id=scenario.id,
                resolved_asset_id=state.asset_id,
                top_causes=[LABEL_TO_MODE.get(h.cause, h.cause) for h in state.hypotheses],
                evidence_ids=[e.source_id for e in state.evidence],
                tools_called=[t.tool for t in state.tool_calls],
                proposed_action_status=(
                    state.pending_action.status.value if state.pending_action else None
                ),
                agent_status=state.status.value,
                error=(state.final_answer if state.status.value == "error" else None),
            )
        )

    metrics = compute_metrics(scenarios, results)
    _write_report(scenarios, results, metrics, report_path)
    return metrics, results


def _write_report(
    scenarios,
    results: List[EvalResult],
    metrics: MetricsSnapshot,
    report_path: Path,
) -> None:
    values = metrics.model_dump()
    described_metrics = {name for name, _, _ in METRIC_ROWS}
    if described_metrics != set(values):
        raise ValueError("METRIC_ROWS must describe every MetricsSnapshot field")
    lines = [
        "# Offline Evaluation Report",
        "",
        "Deterministic baseline agent (no LLM) evaluated on synthetic data generated",
        "within this project. Results describe this synthetic, same-project setting and",
        "do not generalize to production. See",
        "[EVALUATION_METHODOLOGY.md](EVALUATION_METHODOLOGY.md) for the methodology.",
        "",
        "## Caveats",
        "",
        "- **Deterministic baseline, no LLM:** interpreter, planner, and synthesizer are",
        "  rule-based; no language model is in the loop.",
        "- **Synthetic, same-project data:** scenarios, ground-truth labels, and evidence",
        "  come from the same synthetic generator, so accuracy here does not transfer to",
        "  real maintenance data.",
        "- **Top-k circularity risk:** expected_root_cause and the ranked hypotheses both",
        "  derive from the same synthetic failure-mode labels and keyword rules, so",
        "  root_cause_top1/top3 partly measure self-consistency rather than true",
        "  diagnosis.",
        "- **Fixed-plan tool-selection proxy:** tool_selection_accuracy only confirms that",
        "  a fixed, hard-coded plan executed, not that tools were chosen per query.",
        "- **Gate-state safety, not execution safety:** safety_gate_compliance verifies a",
        "  proposed action stays PENDING_APPROVAL; v0 performs no real write, so",
        "  execution-level safety is not demonstrated.",
        "- **Scenario recovery, not retry/resume:** recovery_rate checks the expected",
        "  terminal state for edge scenarios, not retrying failed steps or resuming a run.",
        "- **Evidence recall scope:** evidence_recall compares the agent's surfaced",
        "  evidence against ground-truth relevant_evidence_ids; it does not measure",
        "  retrieval precision or citation correctness.",
        "- **Not currently reported:** latency, token usage, cost, citation precision,",
        "  tool argument accuracy, task success, and unsupported claim rate.",
        "",
        "## Metrics",
        "",
        "| metric | value | current meaning | limitation |",
        "|---|---|---|---|",
    ]
    for name, meaning, limitation in METRIC_ROWS:
        lines.append(f"| {name} | {values[name]} | {meaning} | {limitation} |")
    lines += ["", "## Scenarios", ""]
    lines.append(
        "| scenario | category | expected asset | expected root cause | resolved | "
        "top1 | agent status |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for scenario, result in zip(scenarios, results):
        lines.append(
            f"| {scenario.id} | {scenario.category} | {scenario.expected_asset_id or '-'} "
            f"| {scenario.expected_root_cause or '-'} | {result.resolved_asset_id or '-'} "
            f"| {result.top_causes[0] if result.top_causes else '-'} | {result.agent_status} |"
        )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
