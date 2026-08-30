"""Work-order contracts."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from .common import Priority


class WorkOrderType(str, Enum):
    CORRECTIVE = "corrective"
    PREVENTIVE = "preventive"
    INSPECTION = "inspection"
    EMERGENCY = "emergency"


class WorkOrderStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class WorkOrder(BaseModel):
    wo_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    created_at: datetime
    completed_at: Optional[datetime] = None
    wo_type: WorkOrderType
    priority: Priority
    symptom: str
    diagnosis: Optional[str] = None
    action_taken: Optional[str] = None
    downtime_min: Optional[float] = Field(default=None, ge=0)
    status: WorkOrderStatus = WorkOrderStatus.OPEN


class WorkOrderSearchRequest(BaseModel):
    asset_id: str = Field(min_length=1)
    days: int = Field(default=30, ge=1, le=365)
    limit: int = Field(default=20, ge=1, le=100)


class WorkOrderSearchResult(BaseModel):
    asset_id: str
    days: int
    total: int = Field(ge=0)
    items: List[WorkOrder] = Field(default_factory=list)
