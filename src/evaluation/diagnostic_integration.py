"""Track B: diagnostic evidence boundary integration.

This module is intentionally independent of the Track A planner, synthesizer,
scenarios, and metrics, and of benchmark core. It converts typed
:class:`DiagnosticEvidence` into citable :class:`EvidenceItem` instances and
integrates them into an :class:`AgentState` without ever producing a root-cause
claim or a proposed action.
"""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from src.contracts import (
    AgentState,
    AgentStatus,
    Confidence,
    DiagnosticEvidence,
    EvidenceSourceType,
    Hypothesis,
)

# --- integration -------------------------------------------------------------


def integrate_diagnostic_evidence(
    state: AgentState, diagnostics: List[DiagnosticEvidence]
) -> AgentState:
    """Attach diagnostic evidence and synthesize a non-causal hypothesis.

    Rules:
    - Append one :class:`EvidenceItem` per unique diagnostic source id; duplicate
      source ids fail closed.
    - With no diagnostics, mark the state COMPLETE and abstain explicitly with no
      hypothesis and no proposed action.
    - Contradictory predicted condition codes for the same component abstain for
      that component (no hypothesis is produced for it).
    - Consistent diagnostics produce one :class:`Hypothesis` per component whose
      cause states the condition classification (not a root cause), supported only
       by that component's evidence ids. Hypothesis confidence remains LOW because
       uncalibrated model scores are not mapped to ordinal confidence categories.
       No proposed action is set.
    """
    state.hypotheses = []
    state.pending_action = None

    if not diagnostics:
        state.status = AgentStatus.COMPLETE
        state.final_answer = (
            "No diagnostic evidence was supplied. Abstaining from any condition "
            "classification; no hypothesis is produced."
        )
        return state

    seen_ids = {e.source_id for e in state.evidence}
    unique: List[DiagnosticEvidence] = []
    for diagnostic in diagnostics:
        source_id = diagnostic.source_id()
        if source_id in seen_ids:
            raise ValueError(f"duplicate diagnostic evidence source id: {source_id}")
        seen_ids.add(source_id)
        unique.append(diagnostic)
        state.evidence.append(diagnostic.to_evidence_item())

    by_component: Dict[str, List[DiagnosticEvidence]] = {}
    for diagnostic in unique:
        by_component.setdefault(diagnostic.component, []).append(diagnostic)

    parts: List[str] = []
    for component, items in by_component.items():
        component_ids = [item.source_id() for item in items]
        codes = {item.predicted_condition_code for item in items}

        if len(codes) > 1:
            parts.append(
                f"Abstaining for component '{component}': contradictory condition "
                f"classifications ({', '.join(str(c) for c in sorted(codes))}) "
                "across model versions."
            )
            continue

        representative = items[0]
        state.hypotheses.append(
            Hypothesis(
                cause=(
                    f"Condition classification: component '{component}' predicted "
                    f"as {representative.predicted_condition_label} "
                    f"(code {representative.predicted_condition_code})."
                ),
                confidence=Confidence.LOW,
                supporting_evidence_ids=component_ids,
                rationale=(
                    "Non-causal diagnostic classifier result; states the predicted "
                    "condition, not a root cause. Its uncalibrated model score is "
                    "not converted into an ordinal confidence category."
                ),
                recommended_checks=[],
            )
        )
        parts.append(
            f"Component '{component}': predicted condition "
            f"{representative.predicted_condition_label} "
            f"(code {representative.predicted_condition_code})."
        )

    state.status = AgentStatus.COMPLETE
    state.final_answer = " ".join(parts)
    return state


# --- deterministic 12-scenario evaluation ------------------------------------


@dataclass(frozen=True)
class DiagnosticScenario:
    name: str
    diagnostics: List[DiagnosticEvidence]


def build_diagnostic_scenarios(
    diagnostics: List[DiagnosticEvidence],
) -> List[DiagnosticScenario]:
    """Build exactly 12 deterministic scenarios from supplied diagnostic items.

    Positional layout of the supplied ``diagnostics`` (12 items):
    - scenarios 1..8: normal attachment/citation (``diagnostics[0:8]``)
    - scenarios 9..10: missing evidence (empty input)
    - scenarios 11..12: contradiction pairs (``diagnostics[8:10]`` and
      ``diagnostics[10:12]``); each pair shares a component but carries different
      predicted condition codes from alternate model versions.
    """
    if len(diagnostics) != 12:
        raise ValueError("exactly 12 diagnostic items are required")

    scenarios: List[DiagnosticScenario] = [
        DiagnosticScenario(name=f"normal_{i + 1}", diagnostics=[diagnostics[i]])
        for i in range(8)
    ]
    scenarios.append(DiagnosticScenario(name="missing_1", diagnostics=[]))
    scenarios.append(DiagnosticScenario(name="missing_2", diagnostics=[]))
    scenarios.append(
        DiagnosticScenario(name="contradiction_1", diagnostics=list(diagnostics[8:10]))
    )
    scenarios.append(
        DiagnosticScenario(name="contradiction_2", diagnostics=list(diagnostics[10:12]))
    )
    return scenarios


def evaluate_diagnostic_integration(
    diagnostics: List[DiagnosticEvidence],
) -> Dict[str, Any]:
    """Evaluate the 12 integration scenarios and return counts/metrics.

    Returns a dict with keys ``evidence_attached``, ``citation_valid``,
    ``abstention_correct``, ``contradiction_handled``, ``unique_ids``, and an
    evidence-ID presence rate. Semantic unsupported-claim entailment is explicitly
    not measured because this track has no independent claim annotations.
    """
    scenarios = build_diagnostic_scenarios(diagnostics)

    evidence_attached = 0
    citation_valid = 0
    abstention_correct = 0
    contradiction_handled = 0
    all_source_ids: List[str] = []
    total_hypotheses = 0
    hypotheses_with_evidence_ids = 0

    for scenario in scenarios:
        state = AgentState(request_id=f"diag-{scenario.name}", user_question="")
        integrate_diagnostic_evidence(state, scenario.diagnostics)

        for evidence in state.evidence:
            evidence_attached += 1
            all_source_ids.append(evidence.source_id)
            if (
                evidence.source_type == EvidenceSourceType.DIAGNOSTIC
                and evidence.citation == evidence.source_id
                and evidence.source_id
            ):
                citation_valid += 1

        explicit_abstain = "abstain" in state.final_answer.lower()
        if scenario.name.startswith("missing_"):
            if (
                not state.hypotheses
                and state.status == AgentStatus.COMPLETE
                and explicit_abstain
            ):
                abstention_correct += 1
        elif scenario.name.startswith("contradiction_"):
            if (
                not state.hypotheses
                and state.status == AgentStatus.COMPLETE
                and explicit_abstain
            ):
                abstention_correct += 1
                contradiction_handled += 1

        for hypothesis in state.hypotheses:
            total_hypotheses += 1
            if hypothesis.supporting_evidence_ids:
                hypotheses_with_evidence_ids += 1

    evidence_id_presence_rate = (
        round(hypotheses_with_evidence_ids / total_hypotheses, 4)
        if total_hypotheses
        else 0.0
    )

    return {
        "evidence_attached": evidence_attached,
        "citation_valid": citation_valid,
        "abstention_correct": abstention_correct,
        "contradiction_handled": contradiction_handled,
        "unique_ids": len(set(all_source_ids)),
        "hypothesis_evidence_id_presence_rate": evidence_id_presence_rate,
        "semantic_unsupported_claim_rate": "not_measured_no_entailment_annotations",
    }


def _selection_key(seed: int, target: str, cycle: int) -> str:
    return hashlib.sha256(f"{seed}:{target}:{cycle}".encode("utf-8")).hexdigest()


def _diagnostic_from_prediction(
    row: Dict[str, Any], dataset_sha256: str, run_id: str
) -> DiagnosticEvidence:
    return DiagnosticEvidence(
        dataset_id="uci-hydraulic-systems-447",
        component=str(row["target"]),
        predicted_condition_code=int(row["pred_code"]),
        predicted_condition_label=str(row["pred_label"]),
        model_score=float(row["model_score"]),
        global_top_feature_values=json.loads(row["global_top_feature_values"]),
        model_version=str(row["model_version"]),
        source_cycle=int(row["cycle"]),
        provenance={
            "dataset_sha256": dataset_sha256,
            "run_id": run_id,
            "split": "test",
            "model_sha256": str(row["model_sha256"]),
            "feature_value_selection_method": str(row["feature_value_selection_method"]),
            "selection": "seeded_cycle_hash_with_true_class_coverage",
        },
    )


def evaluate_hydraulic_prediction_evidence(
    predictions_path: Path,
    metrics_path: Path,
    run_manifest_path: Path,
    output_path: Path,
    report_path: Path,
    seed: int = 447,
) -> Dict[str, Any]:
    """Create and evaluate 12 Track B evidence-integration scenarios.

    Eight real held-out predictions are selected without using prediction
    correctness or score: one cycle per true target class, then one additional
    seeded cycle. Two empty scenarios and two synthetic contradiction scenarios
    exercise fail-closed Agent-side behavior. Evaluation labels stay in the
    selection record and are never copied into Agent evidence provenance.
    """
    predictions = pd.read_csv(predictions_path)
    metrics = json.loads(Path(metrics_path).read_text(encoding="utf-8"))
    run_manifest = json.loads(Path(run_manifest_path).read_text(encoding="utf-8"))

    required = {
        "cycle",
        "target",
        "family",
        "true_code",
        "true_label",
        "pred_code",
        "pred_label",
        "model_score",
        "model_version",
        "model_sha256",
        "global_top_feature_values",
        "feature_value_selection_method",
    }
    missing = required - set(predictions.columns)
    if missing:
        raise ValueError(f"prediction artifact missing columns: {sorted(missing)}")

    selected_rows: List[Dict[str, Any]] = []
    selected_keys = set()
    for target in sorted(metrics):
        preferred = metrics[target]["preferred_family"]
        candidates = predictions[
            (predictions["target"] == target)
            & (predictions["family"] == preferred)
        ].copy()
        if candidates.empty:
            raise ValueError(f"no preferred-family test predictions for {target}")
        candidates["_selection_key"] = candidates["cycle"].map(
            lambda cycle: _selection_key(seed, target, int(cycle))
        )
        for true_code in sorted(candidates["true_code"].unique()):
            row = (
                candidates[candidates["true_code"] == true_code]
                .sort_values("_selection_key")
                .iloc[0]
                .to_dict()
            )
            key = (target, int(row["cycle"]))
            selected_rows.append(row)
            selected_keys.add(key)

    remaining = predictions[
        predictions.apply(
            lambda row: row["family"] == metrics[row["target"]]["preferred_family"]
            and (row["target"], int(row["cycle"])) not in selected_keys,
            axis=1,
        )
    ].copy()
    remaining["_selection_key"] = remaining.apply(
        lambda row: _selection_key(seed, str(row["target"]), int(row["cycle"])),
        axis=1,
    )
    for _, row in remaining.sort_values("_selection_key").iterrows():
        if len(selected_rows) >= 8:
            break
        selected_rows.append(row.to_dict())
    if len(selected_rows) != 8:
        raise ValueError(f"expected 8 real evidence scenarios, got {len(selected_rows)}")

    dataset_sha256 = run_manifest["dataset"]["sha256"]
    run_id = run_manifest["config_sha256"][:12]
    normal_items = [
        _diagnostic_from_prediction(row, dataset_sha256, run_id)
        for row in selected_rows
    ]

    contradiction_items: List[DiagnosticEvidence] = []
    for index, (base, row) in enumerate(zip(normal_items[:2], selected_rows[:2])):
        class_options = metrics[base.component]["classes"]
        alternate = next(
            item for item in class_options
            if int(item["code"]) != base.predicted_condition_code
        )
        common = base.model_copy(
            update={
                "model_score": 0.0,
                "model_version": f"{base.model_version}-edge-{index}-a",
                "provenance": {
                    **base.provenance,
                    "scenario_edge_case": "synthetic_contradiction",
                    "score_semantics": "not_applicable_synthetic_edge_case",
                },
            }
        )
        conflicting = base.model_copy(
            update={
                "predicted_condition_code": int(alternate["code"]),
                "predicted_condition_label": str(alternate["label"]),
                "model_score": 0.0,
                "model_version": f"{base.model_version}-edge-{index}-b",
                "provenance": {
                    **base.provenance,
                    "scenario_edge_case": "synthetic_contradiction",
                    "score_semantics": "not_applicable_synthetic_edge_case",
                },
            }
        )
        contradiction_items.extend([common, conflicting])

    scenario_items = normal_items + contradiction_items
    scenario_metrics = evaluate_diagnostic_integration(scenario_items)
    scenarios = build_diagnostic_scenarios(scenario_items)
    payload = {
        "scenario_count": len(scenarios),
        "real_prediction_scenarios": 8,
        "missing_evidence_scenarios": 2,
        "synthetic_contradiction_scenarios": 2,
        "selection_seed": seed,
        "selection_records": [
            {
                "target": row["target"],
                "cycle": int(row["cycle"]),
                "true_code": int(row["true_code"]),
                "true_label": row["true_label"],
                "pred_code": int(row["pred_code"]),
                "pred_label": row["pred_label"],
                "correct": int(row["true_code"]) == int(row["pred_code"]),
            }
            for row in selected_rows
        ],
        "metrics": scenario_metrics,
        "evidence": [item.model_dump(mode="json") for item in scenario_items],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    run_manifest["evidence_integration"] = {
        "artifact": str(output_path.name),
        "artifact_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "scenario_count": payload["scenario_count"],
        "metrics": scenario_metrics,
    }
    run_manifest_path.write_text(
        json.dumps(run_manifest, indent=2), encoding="utf-8"
    )

    marker = "\n## Evidence Integration"
    report_text = report_path.read_text(encoding="utf-8").split(marker)[0]
    report_lines = [
        report_text.rstrip(),
        marker,
        "",
        "Twelve deterministic Agent-side contract scenarios were evaluated: "
        "8 seeded profile-group-held-out test predictions, 2 missing-evidence abstentions, and 2 "
        "synthetic contradiction edge cases. Ground truth was used only for "
        "scenario coverage and was not placed in Agent evidence provenance.",
        "",
        "| check | result |",
        "|---|---:|",
    ]
    report_lines.extend(
        f"| {name} | {value} |" for name, value in scenario_metrics.items()
    )
    report_lines.extend(
        [
            "",
            "These checks validate typed evidence attachment, citation-ID presence, "
            "abstention and contradiction handling. Semantic unsupported claims are "
            "not measured because no independent entailment annotations exist. They "
            "do not validate full RCA, work-order reasoning, or causal correctness.",
            "",
        ]
    )
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    return payload
