"""Tests for the typed read-only tools."""

from src.contracts import ToolErrorCode, WorkOrderSearchRequest
from src.tools.asset_tools import get_asset_tool, list_assets_tool
from src.tools.meter_tools import get_meter_history_tool
from src.tools.work_order_tools import search_recent_work_orders_tool


def test_get_asset_tool_success_empty_invalid(repository):
    ok = get_asset_tool(repository, "A001")
    assert ok.is_ok and not ok.empty
    assert ok.data is not None and ok.data.asset_id == "A001"

    empty = get_asset_tool(repository, "DOES_NOT_EXIST")
    assert empty.ok and empty.empty and empty.data is None

    bad = get_asset_tool(repository, "")
    assert not bad.ok
    assert bad.error is not None
    assert bad.error.code == ToolErrorCode.INVALID_ARGUMENT


def test_list_assets_tool(repository):
    result = list_assets_tool(repository, limit=10)
    assert result.is_ok and not result.empty
    assert len(result.data) == 10


def test_search_recent_work_orders_tool(repository):
    request = WorkOrderSearchRequest(asset_id="A001", days=30, limit=10)
    result = search_recent_work_orders_tool(repository, request)
    assert result.is_ok and not result.empty
    assert all(order.asset_id == "A001" for order in result.data)


def test_meter_history_tool_success_empty_error(repository):
    ok = get_meter_history_tool(repository, "A001", 7, 10000)
    assert ok.is_ok and not ok.empty and ok.data

    empty = get_meter_history_tool(repository, "DOES_NOT_EXIST", 7, 100)
    assert empty.ok and empty.empty and empty.data == []

    bad = get_meter_history_tool(repository, "A001", 0, 100)
    assert not bad.ok
    assert bad.error is not None
    assert bad.error.code == ToolErrorCode.INVALID_ARGUMENT
