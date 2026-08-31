"""FastAPI application for the industrial maintenance agent."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from src.agent.policy import approve_action, reject_action
from src.agent.request_id import InvalidRequestIdError, validate_request_id
from src.agent.runner import AgentRunner
from src.analytics.trend import compute_meter_summary
from src.config import get_settings
from src.contracts import (
    MeterSummaryRequest,
    ProposedAction,
    WorkOrderSearchRequest,
)
from src.db.repository import Repository

ROOT = Path(__file__).resolve().parents[2]


class QueryRequest(BaseModel):
    question: str
    request_id: Optional[str] = None


def _require_valid_request_id(value: str) -> None:
    """Reject an unsafe request ID at the API boundary with HTTP 400."""
    try:
        validate_request_id(value)
    except InvalidRequestIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def create_app(
    repo: Optional[Repository] = None,
    traces_dir: Optional[Path] = None,
) -> FastAPI:
    settings = get_settings()
    repo = repo or Repository(ROOT / settings.db_path)
    traces_dir = traces_dir or (ROOT / settings.traces_dir)
    runner = AgentRunner(repo, traces_dir)
    pending: Dict[str, ProposedAction] = {}

    app = FastAPI(title="Industrial Maintenance Agent API", version="0.1.0")

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/assets/{asset_id}")
    def get_asset(asset_id: str):
        asset = repo.get_asset(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="asset not found")
        return asset

    @app.get("/work-orders")
    def get_work_orders(
        asset_id: str = Query(...),
        days: int = Query(default=30, ge=1, le=365),
        limit: int = Query(default=20, ge=1, le=100),
    ):
        request = WorkOrderSearchRequest(asset_id=asset_id, days=days, limit=limit)
        return repo.search_recent_work_orders(request.asset_id, request.days, request.limit)

    @app.get("/meter-summary")
    def get_meter_summary(
        asset_id: str = Query(...),
        days: int = Query(default=30, ge=1, le=365),
    ):
        readings = repo.get_recent_meter_readings(asset_id, days + 7, 10000)
        if not readings:
            raise HTTPException(status_code=404, detail="no meter readings")
        return compute_meter_summary(
            readings, MeterSummaryRequest(asset_id=asset_id, days=days)
        )

    @app.post("/agent/query")
    def agent_query(body: QueryRequest):
        if body.request_id is not None:
            _require_valid_request_id(body.request_id)
        request_id = body.request_id or uuid.uuid4().hex
        state = runner.run(body.question, request_id=request_id)
        if state.pending_action is not None:
            pending[request_id] = state.pending_action
        return state

    @app.post("/actions/{action_id}/approve")
    def approve(action_id: str):
        _require_valid_request_id(action_id)
        if action_id not in pending:
            raise HTTPException(status_code=404, detail="action not found")
        pending[action_id] = approve_action(pending[action_id], "api")
        return pending[action_id]

    @app.post("/actions/{action_id}/reject")
    def reject(action_id: str):
        _require_valid_request_id(action_id)
        if action_id not in pending:
            raise HTTPException(status_code=404, detail="action not found")
        pending[action_id] = reject_action(pending[action_id], "api")
        return pending[action_id]

    @app.get("/traces/{request_id}")
    def get_trace(request_id: str):
        _require_valid_request_id(request_id)
        try:
            return runner.traces.load(request_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="trace not found")

    return app


app = create_app()
