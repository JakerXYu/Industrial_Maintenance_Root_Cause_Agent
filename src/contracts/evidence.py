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


class EvidenceItem(BaseModel):
    source_type: EvidenceSourceType
    source_id: str = Field(min_length=1)
    asset_id: Optional[str] = None
    summary: str
    timestamp: Optional[datetime] = None
    citation: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
