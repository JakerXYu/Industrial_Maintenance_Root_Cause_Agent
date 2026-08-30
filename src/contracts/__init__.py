"""Typed Pydantic contracts for the industrial maintenance agent."""

from .assets import Asset, AssetCriticality, AssetStatus, AssetType
from .agent import (
    AgentState,
    AgentStatus,
    Confidence,
    Hypothesis,
    ToolCallTrace,
    TraceRecord,
)
from .common import (
    ActionType,
    ApprovalStatus,
    Priority,
    ProposedAction,
    ToolError,
    ToolErrorCode,
    ToolResult,
)
from .evidence import EvidenceItem, EvidenceSourceType
from .meter import (
    MeterReading,
    MeterSummary,
    MeterSummaryRequest,
    SignalName,
    SignalSummary,
)
from .rag import DocumentChunk, RetrievalResult
from .evaluation import EvalResult, EvalScenario, MetricsSnapshot
from .work_orders import (
    WorkOrder,
    WorkOrderSearchRequest,
    WorkOrderSearchResult,
    WorkOrderStatus,
    WorkOrderType,
)

__all__ = [
    "ActionType",
    "AgentState",
    "AgentStatus",
    "ApprovalStatus",
    "Asset",
    "AssetCriticality",
    "AssetStatus",
    "AssetType",
    "EvidenceItem",
    "EvidenceSourceType",
    "Confidence",
    "EvalResult",
    "EvalScenario",
    "Hypothesis",
    "MetricsSnapshot",
    "MeterReading",
    "MeterSummary",
    "MeterSummaryRequest",
    "Priority",
    "ProposedAction",
    "DocumentChunk",
    "RetrievalResult",
    "SignalName",
    "SignalSummary",
    "ToolError",
    "ToolErrorCode",
    "ToolResult",
    "ToolCallTrace",
    "TraceRecord",
    "WorkOrder",
    "WorkOrderSearchRequest",
    "WorkOrderSearchResult",
    "WorkOrderStatus",
    "WorkOrderType",
]
