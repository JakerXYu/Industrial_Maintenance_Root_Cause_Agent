"""Human approval gate for write-like actions."""

from typing import Optional

from src.contracts import AgentState, ApprovalStatus, ProposedAction
from src.contracts.common import utcnow


def approve_action(action: ProposedAction, approved_by: str) -> ProposedAction:
    """Mark an action APPROVED, recording who approved and a tz-aware timestamp."""
    return action.model_copy(
        update={
            "status": ApprovalStatus.APPROVED,
            "approved_by": approved_by,
            "approved_at": utcnow(),
        }
    )


def reject_action(action: ProposedAction, approved_by: str) -> ProposedAction:
    """Mark an action REJECTED; ``approved_at`` remains ``None``."""
    return action.model_copy(
        update={
            "status": ApprovalStatus.REJECTED,
            "approved_by": approved_by,
            "approved_at": None,
        }
    )


def approve(state: AgentState, approved_by: str = "operator") -> AgentState:
    if state.pending_action is None:
        return state
    state.pending_action = approve_action(state.pending_action, approved_by)
    return state


def reject(state: AgentState, approved_by: str = "operator") -> AgentState:
    if state.pending_action is None:
        return state
    state.pending_action = reject_action(state.pending_action, approved_by)
    return state


def execute_pending_action(state: AgentState) -> Optional[ProposedAction]:
    """Return a proposed action only after explicit approval.

    Raises PermissionError if the action has not been APPROVED. In v0 there is
    no real database mutation: returning the action executes no external side
    effect; this function is the enforcement boundary.
    """
    if state.pending_action is None:
        return None
    if state.pending_action.status != ApprovalStatus.APPROVED:
        raise PermissionError("write-like action requires APPROVED status")
    return state.pending_action
