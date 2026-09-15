"""Evidence contracts.

An EvidenceItem is a grounded, citable observation that the agent can attach to
a hypothesis. It is data, not prose, and always carries a stable source id.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class EvidenceSourceType(str, Enum):
    ASSET = "asset"
    WORK_ORDER = "work_order"
    METER = "meter"
    MAINTENANCE_PLAN = "maintenance_plan"
    PART = "part"
    EVENT = "event"
    DOCUMENT = "document"
    DIAGNOSTIC = "diagnostic"


class EvidenceItem(BaseModel):
    source_type: EvidenceSourceType
    source_id: str = Field(min_length=1)
    asset_id: Optional[str] = None
    summary: str
    timestamp: Optional[datetime] = None
    citation: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DiagnosticEvidence(BaseModel):
    """Typed diagnostic classifier prediction.

    This is a non-causal condition classification, not a root-cause claim. The
    ``model_score`` is an uncalibrated classifier output in ``[0, 1]`` and is
    deliberately not mapped to an ordinal Agent confidence level.
    """

    dataset_id: str = Field(min_length=1)
    component: str = Field(min_length=1)
    predicted_condition_code: int
    predicted_condition_label: str = Field(min_length=1)
    model_score: float = Field(ge=0.0, le=1.0)
    global_top_feature_values: Dict[str, float] = Field(default_factory=dict)
    model_version: str = Field(min_length=1)
    source_cycle: int = Field(ge=1)
    provenance: Dict[str, Any] = Field(default_factory=dict)

    def source_id(self) -> str:
        """Stable source id unique across components and model versions.

        Includes dataset, component, cycle, and model version so two diagnostics
        for the same component from different model versions never collide.
        """
        return (
            f"diagnostic:{self.dataset_id}:{self.component}:"
            f"{self.source_cycle}:{self.model_version}"
        )

    def to_evidence_item(self) -> "EvidenceItem":
        """Convert to a citable, non-causal :class:`EvidenceItem`."""
        return EvidenceItem(
            source_type=EvidenceSourceType.DIAGNOSTIC,
            source_id=self.source_id(),
            asset_id=None,
            summary=(
                f"Diagnostic classifier condition result: component "
                f"'{self.component}' predicted as {self.predicted_condition_label} "
                f"(code {self.predicted_condition_code}) with uncalibrated score "
                f"{self.model_score:.4f} (model {self.model_version}, cycle "
                f"{self.source_cycle})."
            ),
            citation=self.source_id(),
            metadata={
                "causal_status": "non_causal_condition_classification",
                "score_qualifier": "uncalibrated",
                "provenance": dict(self.provenance),
                "dataset_id": self.dataset_id,
                "component": self.component,
                "predicted_condition_code": self.predicted_condition_code,
                "predicted_condition_label": self.predicted_condition_label,
                "model_score": self.model_score,
                "global_top_feature_values": dict(self.global_top_feature_values),
                "feature_semantics": "global_model_importance_with_cycle_value_not_local_attribution",
                "model_version": self.model_version,
                "source_cycle": self.source_cycle,
            },
        )
