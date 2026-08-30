"""Tool registry: registered read tools plus their JSON schemas."""

from typing import Any, Callable, Dict, List

from src.contracts import WorkOrderSearchRequest
from src.db.repository import Repository
from src.rag.retriever import KeywordRetriever
from src.tools.asset_tools import get_asset_tool
from src.tools.meter_tools import get_meter_history_tool
from src.tools.work_order_tools import search_recent_work_orders_tool


class ToolRegistry:
    def __init__(self, repo: Repository, retriever: KeywordRetriever):
        self._tools: Dict[str, Callable[..., Any]] = {}
        self._schemas: Dict[str, Dict[str, Any]] = {}

        self._register(
            "get_asset",
            lambda asset_id: get_asset_tool(repo, asset_id),
            {
                "name": "get_asset",
                "description": "Return metadata for one asset by asset_id.",
                "parameters": {
                    "type": "object",
                    "properties": {"asset_id": {"type": "string"}},
                    "required": ["asset_id"],
                },
            },
        )
        self._register(
            "search_recent_work_orders",
            lambda asset_id, days=30, limit=20: search_recent_work_orders_tool(
                repo,
                WorkOrderSearchRequest(asset_id=asset_id, days=days, limit=limit),
            ),
            {
                "name": "search_recent_work_orders",
                "description": "Retrieve recent maintenance work orders for one asset.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "asset_id": {"type": "string"},
                        "days": {"type": "integer", "minimum": 1, "maximum": 365},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                    "required": ["asset_id"],
                },
            },
        )
        self._register(
            "get_meter_history",
            lambda asset_id, days=30, limit=2000: get_meter_history_tool(
                repo, asset_id, days, limit
            ),
            {
                "name": "get_meter_history",
                "description": "Retrieve recent meter/sensor readings for one asset.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "asset_id": {"type": "string"},
                        "days": {"type": "integer", "minimum": 1, "maximum": 365},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 10000},
                    },
                    "required": ["asset_id"],
                },
            },
        )
        self._register(
            "search_docs",
            lambda query, top_k=5: retriever.search(query, top_k),
            {
                "name": "search_docs",
                "description": "Search unstructured maintenance documents by keyword.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer", "minimum": 1, "maximum": 20},
                    },
                    "required": ["query"],
                },
            },
        )

    def _register(
        self, name: str, func: Callable[..., Any], schema: Dict[str, Any]
    ) -> None:
        self._tools[name] = func
        self._schemas[name] = schema

    def call(self, name: str, args: Dict[str, Any]) -> Any:
        return self._tools[name](**args)

    def names(self) -> List[str]:
        return list(self._tools)

    def schemas(self) -> List[Dict[str, Any]]:
        return list(self._schemas.values())
