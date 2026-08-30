"""Read-only asset tools."""

from typing import List, Optional

from src.contracts import Asset, ToolError, ToolErrorCode, ToolResult
from src.db.repository import Repository


def get_asset_tool(repo: Repository, asset_id: str) -> ToolResult[Asset]:
    if not asset_id or not asset_id.strip():
        return ToolResult.failure(
            ToolError(
                code=ToolErrorCode.INVALID_ARGUMENT,
                message="asset_id must be a non-empty string",
            )
        )
    try:
        asset = repo.get_asset(asset_id)
    except Exception as exc:  # defensive: DB failure is not an empty result
        return ToolResult.failure(
            ToolError(
                code=ToolErrorCode.UPSTREAM_UNAVAILABLE,
                message=f"asset lookup failed: {exc}",
                retryable=True,
            )
        )
    if asset is None:
        return ToolResult.success(data=None, empty=True)
    return ToolResult.success(data=asset)


def list_assets_tool(repo: Repository, limit: int = 100) -> ToolResult[List[Asset]]:
    if limit < 1 or limit > 1000:
        return ToolResult.failure(
            ToolError(
                code=ToolErrorCode.INVALID_ARGUMENT,
                message="limit must be between 1 and 1000",
            )
        )
    try:
        assets = repo.list_assets(limit)
    except Exception as exc:
        return ToolResult.failure(
            ToolError(
                code=ToolErrorCode.UPSTREAM_UNAVAILABLE,
                message=f"asset listing failed: {exc}",
                retryable=True,
            )
        )
    return ToolResult.success(data=assets, empty=not assets)
