"""Deterministic interpreter and planner (LLM hooks will replace these)."""

import re
from typing import List, Tuple

from src.contracts import AgentState, AgentStatus
from src.db.repository import Repository

_ASSET_ID = re.compile(r"\bA\d{3}\b")


def interpret(state: AgentState, repo: Repository) -> None:
    match = _ASSET_ID.search(state.user_question)
    if not match:
        state.status = AgentStatus.ERROR
        state.final_answer = "Could not resolve an asset from the question."
        return
    asset_id = match.group(0).upper()
    if repo.get_asset(asset_id) is None:
        state.status = AgentStatus.ERROR
        state.final_answer = f"No asset found for {asset_id}."
        return
    state.asset_id = asset_id
    state.status = AgentStatus.RESOLVED


def plan(state: AgentState) -> List[Tuple[str, dict]]:
    if state.asset_id is None:
        return []
    state.status = AgentStatus.PLANNED
    return [
        ("get_asset", {"asset_id": state.asset_id}),
        (
            "search_recent_work_orders",
            {"asset_id": state.asset_id, "days": 30, "limit": 20},
        ),
        (
            "get_meter_history",
            {"asset_id": state.asset_id, "days": 37, "limit": 5000},
        ),
        ("search_docs", {"query": state.user_question, "top_k": 3}),
    ]
