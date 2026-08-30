"""Offline evaluation contracts."""

from typing import List, Optional

from pydantic import BaseModel, Field


class EvalScenario(BaseModel):
    id: str
    category: str = "normal"
    question: str
    expected_asset_id: Optional[str] = None
    expected_root_cause: Optional[str] = None
    required_tools: List[str] = Field(default_factory=list)
    relevant_evidence_ids: List[str] = Field(default_factory=list)


class EvalResult(BaseModel):
    scenario_id: str
    resolved_asset_id: Optional[str] = None
    top_causes: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    tools_called: List[str] = Field(default_factory=list)
    proposed_action_status: Optional[str] = None
    agent_status: str = "complete"
    error: Optional[str] = None


class MetricsSnapshot(BaseModel):
    total_scenarios: int = 0
    asset_resolution_accuracy: float = 0.0
    root_cause_top1: float = 0.0
    root_cause_top3: float = 0.0
    evidence_recall: float = 0.0
    tool_selection_accuracy: float = 0.0
    safety_gate_compliance: float = 0.0
    recovery_rate: float = 0.0
