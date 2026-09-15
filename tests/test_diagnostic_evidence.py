"""Tests for Track B diagnostic evidence boundary.

Covers schema/conversion, stable unique source ids, serialization, state
attachment, citation, missing-evidence abstention, contradiction handling,
duplicate rejection, absence of proposed actions/unsupported claims, and the
exactly-12-scenario deterministic evaluation helper.
"""

import json

import pandas as pd
import pytest
from pydantic import ValidationError

from src.contracts import (
    AgentState,
    AgentStatus,
    Confidence,
    DiagnosticEvidence,
    EvidenceSourceType,
)
from src.evaluation.diagnostic_integration import (
    build_diagnostic_scenarios,
    evaluate_diagnostic_integration,
    evaluate_hydraulic_prediction_evidence,
    integrate_diagnostic_evidence,
)


def _diag(
    component,
    code,
    *,
    label=None,
    model_version="v1",
    cycle=10,
    dataset="ds1",
    score=0.9,
):
    return DiagnosticEvidence(
        dataset_id=dataset,
        component=component,
        predicted_condition_code=code,
        predicted_condition_label=label or f"condition_{code}",
        model_score=score,
        global_top_feature_values={"vibration_rms": 0.7, "temperature_c": 61.2},
        model_version=model_version,
        source_cycle=cycle,
        provenance={"experiment": "eval", "split": "test"},
    )


def _twelve_items():
    items = [_diag(f"component_{i}", i) for i in range(8)]
    items.append(_diag("motor_x", 1, model_version="v1", cycle=10))
    items.append(_diag("motor_x", 2, model_version="v2", cycle=10))
    items.append(_diag("motor_y", 3, model_version="v1", cycle=11))
    items.append(_diag("motor_y", 4, model_version="v2", cycle=11))
    return items


# --- schema / conversion ------------------------------------------------------


def test_diagnostic_schema_required_fields():
    d = _diag("pump_1", 1)
    assert d.dataset_id == "ds1"
    assert d.component == "pump_1"
    assert d.predicted_condition_code == 1
    assert d.predicted_condition_label == "condition_1"
    assert d.model_version == "v1"
    assert d.source_cycle == 10
    assert d.model_score == 0.9
    assert d.global_top_feature_values["vibration_rms"] == 0.7
    assert d.provenance == {"experiment": "eval", "split": "test"}


def test_diagnostic_schema_rejects_out_of_range_score():
    with pytest.raises(ValidationError):
        DiagnosticEvidence(
            dataset_id="ds1",
            component="c",
            predicted_condition_code=1,
            predicted_condition_label="l",
            model_score=1.5,
            model_version="v1",
            source_cycle=1,
        )


def test_diagnostic_schema_rejects_invalid_cycle():
    with pytest.raises(ValidationError):
        DiagnosticEvidence(
            dataset_id="ds1",
            component="c",
            predicted_condition_code=1,
            predicted_condition_label="l",
            model_score=0.5,
            model_version="v1",
            source_cycle=0,
        )


def test_conversion_returns_diagnostic_evidence_item():
    evidence = _diag("pump_1", 1).to_evidence_item()

    assert evidence.source_type == EvidenceSourceType.DIAGNOSTIC
    assert evidence.asset_id is None
    assert evidence.citation == evidence.source_id
    assert evidence.source_id.startswith("diagnostic:")
    assert "classifier" in evidence.summary.lower()
    assert "condition" in evidence.summary.lower()
    assert evidence.metadata["causal_status"] == "non_causal_condition_classification"
    assert evidence.metadata["score_qualifier"] == "uncalibrated"
    assert evidence.metadata["provenance"] == {"experiment": "eval", "split": "test"}
    assert evidence.metadata["component"] == "pump_1"
    assert evidence.metadata["model_version"] == "v1"


# --- unique source ids --------------------------------------------------------


def test_source_id_unique_across_components_and_model_versions():
    base = _diag("motor_x", 1, model_version="v1", cycle=10)
    other_component = _diag("motor_y", 1, model_version="v1", cycle=10)
    other_model = _diag("motor_x", 1, model_version="v2", cycle=10)
    other_cycle = _diag("motor_x", 1, model_version="v1", cycle=11)

    assert len({base.source_id(), other_component.source_id()}) == 2
    assert len({base.source_id(), other_model.source_id()}) == 2
    assert len({base.source_id(), other_cycle.source_id()}) == 2
    assert base.source_id() == _diag("motor_x", 1, model_version="v1", cycle=10).source_id()


# --- serialization ------------------------------------------------------------


def test_diagnostic_serialization_roundtrip():
    d = _diag("pump_1", 1)
    restored = DiagnosticEvidence.model_validate_json(d.model_dump_json())
    assert restored == d
    assert restored.source_id() == d.source_id()
    assert d.model_dump()["predicted_condition_code"] == 1


# --- state attachment / citation ----------------------------------------------


def test_state_attachment_and_citation():
    state = AgentState(request_id="r1", user_question="")
    integrate_diagnostic_evidence(state, [_diag("pump_1", 1)])

    assert len(state.evidence) == 1
    item = state.evidence[0]
    assert item.source_type == EvidenceSourceType.DIAGNOSTIC
    assert item.citation == item.source_id
    assert item.asset_id is None
    assert state.status == AgentStatus.COMPLETE


def test_consistent_evidence_produces_non_causal_hypothesis():
    state = AgentState(request_id="r1", user_question="")
    integrate_diagnostic_evidence(state, [_diag("pump_1", 1, score=0.9)])

    assert len(state.hypotheses) == 1
    hypothesis = state.hypotheses[0]
    assert "Condition classification" in hypothesis.cause
    assert "root cause" not in hypothesis.cause.lower()
    assert "non-causal" in hypothesis.rationale.lower()
    assert hypothesis.supporting_evidence_ids == [state.evidence[0].source_id]
    assert state.pending_action is None


def test_uncalibrated_score_does_not_raise_hypothesis_confidence():
    state = integrate_diagnostic_evidence(
        AgentState(request_id="confidence", user_question=""),
        [_diag("pump", 1, score=0.999)],
    )
    assert state.hypotheses[0].confidence == Confidence.LOW


# --- missing evidence abstain -------------------------------------------------


def test_missing_evidence_abstains():
    state = AgentState(request_id="r1", user_question="")
    integrate_diagnostic_evidence(state, [])

    assert state.status == AgentStatus.COMPLETE
    assert state.hypotheses == []
    assert state.pending_action is None
    assert "abstain" in state.final_answer.lower()


# --- contradiction ------------------------------------------------------------


def test_contradiction_abstains_for_component():
    state = AgentState(request_id="r1", user_question="")
    integrate_diagnostic_evidence(
        state,
        [
            _diag("motor_x", 1, model_version="v1"),
            _diag("motor_x", 2, model_version="v2"),
        ],
    )

    assert state.status == AgentStatus.COMPLETE
    assert state.hypotheses == []
    assert len(state.evidence) == 2
    assert "abstain" in state.final_answer.lower()
    assert "motor_x" in state.final_answer


# --- duplicate rejection ------------------------------------------------------


def test_duplicate_source_ids_rejected():
    state = AgentState(request_id="r1", user_question="")
    with pytest.raises(ValueError, match="duplicate diagnostic evidence source id"):
        integrate_diagnostic_evidence(
            state,
            [_diag("pump_1", 1), _diag("pump_1", 1)],
        )


# --- no proposed action / unsupported claims ----------------------------------


def test_no_proposed_action_and_no_unsupported_claims():
    state = AgentState(request_id="r1", user_question="")
    integrate_diagnostic_evidence(
        state,
        [_diag("pump_1", 1), _diag("pump_2", 2)],
    )

    assert state.pending_action is None
    assert len(state.hypotheses) == 2
    for hypothesis in state.hypotheses:
        assert hypothesis.supporting_evidence_ids
        # supporting ids are scoped to their own component only
        assert len(hypothesis.supporting_evidence_ids) == 1


# --- 12-scenario deterministic evaluation -------------------------------------


def test_builds_exactly_twelve_scenarios():
    scenarios = build_diagnostic_scenarios(_twelve_items())
    assert len(scenarios) == 12
    names = [s.name for s in scenarios]
    assert names.count("missing_1") == 1
    assert names.count("missing_2") == 1
    assert names.count("contradiction_1") == 1
    assert names.count("contradiction_2") == 1
    assert len([n for n in names if n.startswith("normal_")]) == 8


def test_build_diagnostic_scenarios_requires_twelve_items():
    with pytest.raises(ValueError):
        build_diagnostic_scenarios([_diag("only_one", 1)])


def test_evaluate_diagnostic_integration_metrics():
    metrics = evaluate_diagnostic_integration(_twelve_items())

    assert metrics == {
        "evidence_attached": 12,
        "citation_valid": 12,
        "abstention_correct": 4,
        "contradiction_handled": 2,
        "unique_ids": 12,
        "hypothesis_evidence_id_presence_rate": 1.0,
        "semantic_unsupported_claim_rate": "not_measured_no_entailment_annotations",
    }


def test_hydraulic_prediction_artifact_to_evidence_report(tmp_path):
    rows = []
    classes = {
        "cooler": [(3, "close"), (20, "reduced"), (100, "full")],
        "valve": [(73, "close"), (80, "severe"), (90, "small"), (100, "optimal")],
    }
    cycle = 1
    for target, target_classes in classes.items():
        for code, label in target_classes:
            rows.append(
                {
                    "cycle": cycle,
                    "split": "test",
                    "target": target,
                    "family": "logistic",
                    "true_code": code,
                    "true_label": label,
                    "pred_code": code,
                    "pred_label": label,
                    "model_score": 0.8,
                    "model_version": f"m-{target}",
                    "model_sha256": "a" * 64,
                    "global_top_feature_values": json.dumps({"PS1__mean": 1.0}),
                    "feature_value_selection_method": "test_no_local_attribution",
                }
            )
            cycle += 1
    rows.append({**rows[0], "cycle": cycle})
    predictions_path = tmp_path / "predictions.csv"
    pd.DataFrame(rows).to_csv(predictions_path, index=False)
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                target: {
                    "preferred_family": "logistic",
                    "classes": [
                        {"code": code, "label": label}
                        for code, label in target_classes
                    ],
                }
                for target, target_classes in classes.items()
            }
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "run_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "dataset": {"sha256": "b" * 64},
                "config_sha256": "c" * 64,
            }
        ),
        encoding="utf-8",
    )
    report_path = tmp_path / "report.md"
    report_path.write_text("# Report\n", encoding="utf-8")
    output_path = tmp_path / "evidence.json"

    result = evaluate_hydraulic_prediction_evidence(
        predictions_path,
        metrics_path,
        manifest_path,
        output_path,
        report_path,
    )

    assert result["scenario_count"] == 12
    assert result["metrics"]["citation_valid"] == 12
    assert result["metrics"]["hypothesis_evidence_id_presence_rate"] == 1.0
    assert (
        result["metrics"]["semantic_unsupported_claim_rate"]
        == "not_measured_no_entailment_annotations"
    )
    assert output_path.exists()
    assert "## Evidence Integration" in report_path.read_text(encoding="utf-8")
    updated_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert updated_manifest["evidence_integration"]["scenario_count"] == 12
    assert len(updated_manifest["evidence_integration"]["artifact_sha256"]) == 64
    for item in result["evidence"]:
        assert "true_code" not in item["provenance"]
