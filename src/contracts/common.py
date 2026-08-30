"""Shared, cross-cutting contracts.

These types are used by tools, the agent state machine, and the approval/policy
layer. This module must not import any domain contract module; domain modules may
import from here.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


def utcnow() -> datetime:
    """Return the current UTC time with timezone information."""
    return datetime.now(timezone.utc)


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class ToolErrorCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    NOT_FOUND = "NOT_FOUND"
    TIMEOUT = "TIMEOUT"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    INTERNAL = "INTERNAL"


class ToolError(BaseModel):
    """A structured tool failure.

    Distinct from an empty result: an empty result means the tool ran
    successfully but returned zero rows, while a ToolError means the call failed.
    """

    code: ToolErrorCode
    message: str
    retryable: bool = False
    context: Dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel, Generic[T]):
    """Uniform envelope returned by every tool call.

    Invariants:
    - ``ok is False`` implies ``error`` is set and ``data`` is ``None``.
    - ``empty is True`` implies the call succeeded but produced zero rows.
    """

    ok: bool = True
    data: Optional[T] = None
    error: Optional[ToolError] = None
    empty: bool = False

    @classmethod
    def success(cls, data: T, *, empty: bool = False) -> "ToolResult[T]":
        return cls(ok=True, data=data, empty=empty)

    @classmethod
    def failure(cls, error: ToolError) -> "ToolResult[T]":
        return cls(ok=False, error=error)

    @property
    def is_ok(self) -> bool:
        return self.ok and self.error is None


class ActionType(str, Enum):
    CREATE_WORK_ORDER = "CREATE_WORK_ORDER"
    UPDATE_WORK_ORDER = "UPDATE_WORK_ORDER"
    CREATE_PART_ORDER = "CREATE_PART_ORDER"
    SCHEDULE_MAINTENANCE = "SCHEDULE_MAINTENANCE"


class ApprovalStatus(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ProposedAction(BaseModel):
    """A write-like action proposed by the agent.

    Every proposed action starts in ``PENDING_APPROVAL``. No execution layer may
    act on it until the status is explicitly transitioned to ``APPROVED``.
    """

    action_type: ActionType
    asset_id: str = Field(min_length=1)
    summary: str
    priority: Priority = Priority.MEDIUM
    status: ApprovalStatus = ApprovalStatus.PENDING_APPROVAL
    created_at: datetime = Field(default_factory=utcnow)
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
