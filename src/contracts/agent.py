"""Agent state, hypothesis, and trace contracts."""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .common import ProposedAction
from .evidence import EvidenceItem


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    MEDIUM_HIGH = "medium-high"
    HIGH = "high"


class Hypothesis(BaseModel):
    cause: str
    confidence: Confidence
    supporting_evidence_ids: List[str] = Field(default_factory=list)
    contradicting_evidence_ids: List[str] = Field(default_factory=list)
    rationale: str
    recommended_checks: List[str] = Field(default_factory=list)


class AgentStatus(str, Enum):
    INITIALIZED = "initialized"
    RESOLVED = "resolved"
    PLANNED = "planned"
    EXECUTED = "executed"
    SYNTHESIZED = "synthesized"
    COMPLETE = "complete"
    ERROR = "error"


class ToolCallTrace(BaseModel):
    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)
    status: str = "success"
    result_count: int = 0
    latency_ms: int = 0


class TraceRecord(BaseModel):
    request_id: str
    question: str
    asset_id: Optional[str] = None
    tool_calls: List[ToolCallTrace] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    hypothesis_causes: List[str] = Field(default_factory=list)
    pending_action_type: Optional[str] = None
    total_latency_ms: int = 0
    status: str = "complete"


class AgentState(BaseModel):
    request_id: str
    user_question: str
    asset_id: Optional[str] = None
    evidence: List[EvidenceItem] = Field(default_factory=list)
    tool_calls: List[ToolCallTrace] = Field(default_factory=list)
    hypotheses: List[Hypothesis] = Field(default_factory=list)
    pending_action: Optional[ProposedAction] = None
    status: AgentStatus = AgentStatus.INITIALIZED
    final_answer: Optional[str] = None
