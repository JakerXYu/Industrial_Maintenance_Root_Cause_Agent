"""Tool executor with per-call tracing."""

import time
from typing import Any, List, Optional, Tuple

from src.contracts import (
    AgentState,
    AgentStatus,
    EvidenceItem,
    EvidenceSourceType,
    ToolCallTrace,
)


def _meta(result: Any) -> Tuple[str, int, Any]:
    if hasattr(result, "error") and result.error is not None:
        return "error", 0, None
    if hasattr(result, "chunks"):
        chunks = result.chunks
        return ("success" if chunks else "empty"), len(chunks), chunks
    data = getattr(result, "data", None)
    if data is None:
        return "empty", 0, None
    if isinstance(data, list):
        return ("success" if data else "empty"), len(data), data
    return "success", 1, data


def execute(
    state: AgentState, registry, plan
) -> Optional[List]:
    meter_readings: Optional[List] = None
    for name, args in plan:
        started = time.perf_counter()
        result = registry.call(name, args)
        latency_ms = int((time.perf_counter() - started) * 1000)
        status, count, payload = _meta(result)
        state.tool_calls.append(
            ToolCallTrace(
                tool=name,
                args=args,
                status=status,
                result_count=count,
                latency_ms=latency_ms,
            )
        )

        if name == "get_asset" and status == "success" and payload is not None:
            asset = payload
            state.evidence.append(
                EvidenceItem(
                    source_type=EvidenceSourceType.ASSET,
                    source_id=asset.asset_id,
                    asset_id=asset.asset_id,
                    summary=f"{asset.asset_name} ({asset.asset_type.value})",
                )
            )
        elif name == "search_recent_work_orders" and status == "success":
            for wo in (payload or [])[:10]:
                summary = wo.symptom or ""
                if wo.diagnosis:
                    summary += f" | diagnosis: {wo.diagnosis}"
                state.evidence.append(
                    EvidenceItem(
                        source_type=EvidenceSourceType.WORK_ORDER,
                        source_id=wo.wo_id,
                        asset_id=state.asset_id,
                        summary=summary,
                        timestamp=wo.created_at,
                    )
                )
        elif name == "get_meter_history" and status == "success":
            meter_readings = payload or []
        elif name == "search_docs" and status == "success":
            for chunk in payload:
                state.evidence.append(
                    EvidenceItem(
                        source_type=EvidenceSourceType.DOCUMENT,
                        source_id=chunk.chunk_id,
                        asset_id=state.asset_id,
                        summary=f"{chunk.section}: {chunk.text[:140]}",
                        citation=chunk.chunk_id,
                    )
                )
    state.status = AgentStatus.EXECUTED
    return meter_readings
