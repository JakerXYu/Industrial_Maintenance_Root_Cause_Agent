"""Trace persistence and inspection."""

from pathlib import Path
from typing import List

from src.agent.request_id import request_id_path
from src.contracts import AgentState, TraceRecord


class TraceStore:
    def __init__(self, traces_dir: Path):
        self.dir = Path(traces_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, request_id: str) -> Path:
        return request_id_path(self.dir, request_id)

    def save(self, record: TraceRecord) -> None:
        self._path(record.request_id).write_text(
            record.model_dump_json(indent=2), encoding="utf-8"
        )

    def load(self, request_id: str) -> TraceRecord:
        return TraceRecord.model_validate_json(
            self._path(request_id).read_text(encoding="utf-8")
        )

    def list(self) -> List[str]:
        return sorted(p.stem for p in self.dir.glob("*.json"))


def to_trace_record(state: AgentState, total_latency_ms: int) -> TraceRecord:
    return TraceRecord(
        request_id=state.request_id,
        question=state.user_question,
        asset_id=state.asset_id,
        tool_calls=state.tool_calls,
        evidence_ids=[e.source_id for e in state.evidence],
        hypothesis_causes=[h.cause for h in state.hypotheses],
        pending_action_type=(
            state.pending_action.action_type.value if state.pending_action else None
        ),
        total_latency_ms=total_latency_ms,
        status=state.status.value,
    )
