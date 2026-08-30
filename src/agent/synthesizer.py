"""Deterministic evidence aggregation and hypothesis generation.

This is a rule-based baseline that will later be replaced by an LLM synthesizer.
It keeps observed facts, retrieved guidance, and inference separated in the
output contracts (evidence ids on every hypothesis).
"""

from typing import Dict, List, Optional, Tuple

from src.analytics.trend import compute_meter_summary
from src.contracts import (
    ActionType,
    AgentState,
    AgentStatus,
    Confidence,
    EvidenceItem,
    EvidenceSourceType,
    Hypothesis,
    MeterSummary,
    MeterSummaryRequest,
    Priority,
    ProposedAction,
)

MODE_LABELS = {
    "lubrication_degradation": "Lubrication degradation",
    "hydraulic_leakage": "Hydraulic leakage",
    "position_sensor_instability": "Position sensor instability",
    "bearing_degradation": "Bearing degradation",
    "cooling_degradation": "Cooling degradation",
    "normal_or_false_alarm": "Normal operation / false alarm",
}

MODE_KEYWORDS = {
    "lubrication_degradation": ["friction", "lubricat", "squeal"],
    "hydraulic_leakage": ["pressure drop", "seal", "leak", "fluid"],
    "position_sensor_instability": ["intermittent", "readout", "connector", "dropout", "position"],
    "bearing_degradation": ["bearing", "rough rotation", "vibration"],
    "cooling_degradation": ["overheat", "coolant", "cooling"],
    "normal_or_false_alarm": ["routine", "suspected", "occasional", "false", "no issue", "no fault"],
}

MODE_CHECKS = {
    "lubrication_degradation": [
        "Inspect lubrication pressure and filter condition",
        "Verify lubrication flow rate",
        "Run 20 controlled cycles and compare temperature/friction trend",
    ],
    "hydraulic_leakage": [
        "Inspect hydraulic seals and connections for leakage",
        "Verify hydraulic pressure during a controlled cycle",
    ],
    "position_sensor_instability": [
        "Inspect sensor wiring and connector",
        "Verify sensor mount and compare to a reference sensor",
    ],
    "bearing_degradation": [
        "Measure bearing temperature and vibration trend",
        "Inspect bearing condition and lubrication",
    ],
    "cooling_degradation": [
        "Check coolant level and flow",
        "Inspect cooling fan and heat exchanger",
    ],
    "normal_or_false_alarm": [
        "Continue monitoring for recurrence",
        "Verify instrumentation before escalating",
    ],
}


def _deltas(meter_summary: Optional[MeterSummary]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if meter_summary is None:
        return None, None, None
    temp = meter_summary.signals.get("temperature_c")
    pressure = meter_summary.signals.get("pressure_bar")
    vibration = meter_summary.signals.get("vibration_rms")
    return (
        temp.relative_change_pct if temp else None,
        pressure.relative_change_pct if pressure else None,
        vibration.relative_change_pct if vibration else None,
    )


def _rank(
    wo_text: str,
    temp_change: Optional[float],
    pressure_change: Optional[float],
    vibration_change: Optional[float],
) -> List[Tuple[str, float]]:
    scores: Dict[str, float] = {mode: 0.0 for mode in MODE_LABELS}

    for mode, keywords in MODE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in wo_text:
                scores[mode] += 2.0

    if pressure_change is not None and pressure_change < -5:
        scores["hydraulic_leakage"] += 4.0
    if temp_change is not None and temp_change > 3:
        scores["cooling_degradation"] += 2.0
        scores["lubrication_degradation"] += 1.0
        scores["bearing_degradation"] += 1.0
    if temp_change is not None and temp_change > 2:
        scores["lubrication_degradation"] += 1.0
    if vibration_change is not None and vibration_change > 5:
        scores["bearing_degradation"] += 3.0
    if vibration_change is not None and 0 < vibration_change <= 5:
        scores["lubrication_degradation"] += 1.0

    has_anomaly = (
        (temp_change is not None and temp_change > 3)
        or (pressure_change is not None and pressure_change < -5)
        or (vibration_change is not None and vibration_change > 3)
    )
    if not has_anomaly:
        scores["normal_or_false_alarm"] += 4.0

    return sorted(scores.items(), key=lambda kv: -kv[1])


def _confidence(score: float) -> Confidence:
    if score >= 8:
        return Confidence.HIGH
    if score >= 5:
        return Confidence.MEDIUM_HIGH
    if score >= 3:
        return Confidence.MEDIUM
    return Confidence.LOW


def _rationale(
    mode: str,
    temp_change: Optional[float],
    pressure_change: Optional[float],
    vibration_change: Optional[float],
) -> str:
    parts = []
    if mode == "hydraulic_leakage" and pressure_change is not None:
        parts.append(f"hydraulic pressure is {pressure_change:+.1f}% vs baseline")
    if mode in ("lubrication_degradation", "cooling_degradation") and temp_change is not None:
        parts.append(f"temperature is {temp_change:+.1f}% vs baseline")
    if mode in ("bearing_degradation", "lubrication_degradation") and vibration_change is not None:
        parts.append(f"vibration is {vibration_change:+.1f}% vs baseline")
    if not parts:
        parts.append("no decisive signal deviation; classification based on work-order notes")
    return "; ".join(parts)


def synthesize(
    state: AgentState,
    meter_readings: Optional[List],
    repo,
) -> None:
    meter_summary: Optional[MeterSummary] = None
    if meter_readings:
        request = MeterSummaryRequest(asset_id=state.asset_id, days=30)
        meter_summary = compute_meter_summary(meter_readings, request)
        for signal, summary in meter_summary.signals.items():
            if summary.relative_change_pct is not None and abs(summary.relative_change_pct) > 1.0:
                state.evidence.append(
                    EvidenceItem(
                        source_type=EvidenceSourceType.METER,
                        source_id=f"meter_summary:{state.asset_id}",
                        asset_id=state.asset_id,
                        summary=f"{signal} recent {summary.relative_change_pct:+.1f}% vs {summary.baseline_window_days}d baseline",
                        citation="meter_summary",
                    )
                )

    wo_text = " ".join(
        e.summary.lower()
        for e in state.evidence
        if e.source_type == EvidenceSourceType.WORK_ORDER
    )
    temp_change, pressure_change, vibration_change = _deltas(meter_summary)
    ranked = _rank(wo_text, temp_change, pressure_change, vibration_change)

    supporting_ids = list({e.source_id for e in state.evidence})
    contradicting_ids = [
        e.source_id
        for e in state.evidence
        if e.source_type == EvidenceSourceType.WORK_ORDER
        and any(k in e.summary.lower() for k in ("routine", "no issue", "false", "spurious"))
    ]

    for mode, score in ranked[:3]:
        if score <= 0:
            continue
        cause = MODE_LABELS[mode]
        state.hypotheses.append(
            Hypothesis(
                cause=cause,
                confidence=_confidence(score),
                supporting_evidence_ids=(
                    [] if mode == "normal_or_false_alarm" else supporting_ids
                ),
                contradicting_evidence_ids=(
                    contradicting_ids if mode != "normal_or_false_alarm" else []
                ),
                rationale=_rationale(mode, temp_change, pressure_change, vibration_change),
                recommended_checks=MODE_CHECKS[mode],
            )
        )

    top = state.hypotheses[0] if state.hypotheses else None
    if top is not None and top.cause != MODE_LABELS["normal_or_false_alarm"]:
        state.pending_action = ProposedAction(
            action_type=ActionType.CREATE_WORK_ORDER,
            asset_id=state.asset_id,
            summary=f"Inspect for {top.cause}",
            priority=(
                Priority.HIGH
                if top.confidence in (Confidence.HIGH, Confidence.MEDIUM_HIGH)
                else Priority.MEDIUM
            ),
        )

    state.final_answer = _answer(state)
    state.status = AgentStatus.COMPLETE


def _answer(state: AgentState) -> str:
    if not state.hypotheses:
        return "Insufficient evidence to form a hypothesis."
    lines = []
    for hypothesis in state.hypotheses:
        lines.append(f"{hypothesis.cause} (confidence: {hypothesis.confidence.value})")
        lines.append(
            "  supporting: " + (", ".join(hypothesis.supporting_evidence_ids) or "none")
        )
        if hypothesis.contradicting_evidence_ids:
            lines.append("  contradicting: " + ", ".join(hypothesis.contradicting_evidence_ids))
        lines.append("  checks: " + ", ".join(hypothesis.recommended_checks))
    if state.pending_action:
        lines.append(
            f"Proposed action: {state.pending_action.action_type.value} ({state.pending_action.status.value})"
        )
    else:
        lines.append("No work order has been proposed.")
    return "\n".join(lines)
