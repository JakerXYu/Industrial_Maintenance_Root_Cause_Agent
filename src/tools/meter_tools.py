"""Read-only meter tools."""

from typing import List

from src.contracts import MeterReading, ToolError, ToolErrorCode, ToolResult
from src.db.repository import Repository


def get_meter_history_tool(
    repo: Repository, asset_id: str, days: int = 30, limit: int = 2000
) -> ToolResult[List[MeterReading]]:
    if not asset_id or not asset_id.strip():
        return ToolResult.failure(
            ToolError(
                code=ToolErrorCode.INVALID_ARGUMENT,
                message="asset_id must be a non-empty string",
            )
        )
    if not (1 <= days <= 365):
        return ToolResult.failure(
            ToolError(
                code=ToolErrorCode.INVALID_ARGUMENT,
                message="days must be between 1 and 365",
            )
        )
    if not (1 <= limit <= 10000):
        return ToolResult.failure(
            ToolError(
                code=ToolErrorCode.INVALID_ARGUMENT,
                message="limit must be between 1 and 10000",
            )
        )
    try:
        readings = repo.get_recent_meter_readings(asset_id, days, limit)
    except Exception as exc:
        return ToolResult.failure(
            ToolError(
                code=ToolErrorCode.UPSTREAM_UNAVAILABLE,
                message=f"meter history failed: {exc}",
                retryable=True,
            )
        )
    return ToolResult.success(data=readings, empty=not readings)
