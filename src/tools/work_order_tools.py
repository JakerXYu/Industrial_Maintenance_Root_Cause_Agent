"""Read-only work-order tools."""

from typing import List

from src.contracts import (
    ToolError,
    ToolErrorCode,
    ToolResult,
    WorkOrder,
    WorkOrderSearchRequest,
)
from src.db.repository import Repository


def search_recent_work_orders_tool(
    repo: Repository, request: WorkOrderSearchRequest
) -> ToolResult[List[WorkOrder]]:
    try:
        orders = repo.search_recent_work_orders(
            request.asset_id, request.days, request.limit
        )
    except Exception as exc:
        return ToolResult.failure(
            ToolError(
                code=ToolErrorCode.UPSTREAM_UNAVAILABLE,
                message=f"work-order search failed: {exc}",
                retryable=True,
            )
        )
    return ToolResult.success(data=orders, empty=not orders)
