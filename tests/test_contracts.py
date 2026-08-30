"""Tests for Phase 0 contracts."""

from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import Settings
from src.contracts import (
    ActionType,
    ApprovalStatus,
    Asset,
    AssetCriticality,
    AssetStatus,
    AssetType,
    EvidenceItem,
    EvidenceSourceType,
    MeterReading,
    MeterSummary,
    Priority,
    ProposedAction,
    SignalName,
    SignalSummary,
    ToolError,
    ToolErrorCode,
    ToolResult,
    WorkOrder,
    WorkOrderSearchRequest,
    WorkOrderStatus,
    WorkOrderType,
)


def test_asset_roundtrip():
    asset = Asset(
        asset_id="A001",
        asset_name="Hydraulic Press P-101",
        asset_type=AssetType.HYDRAULIC_PRESS,
        line="Line 1",
        department="Stamping",
        manufacturer="Acme",
        model="HP-9000",
        install_date=date(2020, 1, 15),
        criticality=AssetCriticality.HIGH,
        status=AssetStatus.ACTIVE,
    )
    assert asset.asset_id == "A001"
    assert asset.model_dump()["asset_type"] == "hydraulic_press"
    assert Asset.model_validate_json(asset.model_dump_json()) == asset


def test_asset_rejects_unknown_enum_value():
    with pytest.raises(ValidationError):
        Asset(
            asset_id="A1",
            asset_name="x",
            asset_type="hydraulic_press",
            line="L",
            department="D",
            manufacturer="M",
            model="M1",
            install_date="2020-01-01",
            criticality="extreme",
        )


def test_work_order_search_request_bounds():
    assert WorkOrderSearchRequest(asset_id="A1").days == 30
    assert WorkOrderSearchRequest(asset_id="A1").limit == 20

    for kwargs in (
        {"asset_id": "A1", "days": 0},
        {"asset_id": "A1", "days": 366},
        {"asset_id": "A1", "limit": 0},
        {"asset_id": "A1", "limit": 101},
        {"asset_id": "", "days": 30},
    ):
        with pytest.raises(ValidationError):
            WorkOrderSearchRequest(**kwargs)


def test_work_order_validates_and_serializes():
    wo = WorkOrder(
        wo_id="WO-1048",
        asset_id="A001",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        wo_type=WorkOrderType.CORRECTIVE,
        priority=Priority.HIGH,
        symptom="elevated friction",
    )
    dumped = wo.model_dump()
    assert dumped["priority"] == "high"
    assert dumped["wo_type"] == "corrective"
    assert wo.status == WorkOrderStatus.OPEN


def test_work_order_rejects_negative_downtime():
    with pytest.raises(ValidationError):
        WorkOrder(
            wo_id="WO-1",
            asset_id="A1",
            created_at=datetime(2026, 1, 1),
            wo_type="corrective",
            priority="medium",
            symptom="x",
            downtime_min=-1.0,
        )


def test_meter_reading_optional_and_non_negative():
    reading = MeterReading(
        reading_id="R1",
        asset_id="A001",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        cycle_count=100,
        temperature_c=60.5,
    )
    assert reading.pressure_bar is None
    assert reading.cycle_count == 100

    with pytest.raises(ValidationError):
        MeterReading(
            reading_id="R2", asset_id="A1", timestamp=datetime(2026, 1, 1), cycle_count=-1
        )

    with pytest.raises(ValidationError):
        MeterReading(
            reading_id="R3",
            asset_id="A1",
            timestamp=datetime(2026, 1, 1),
            vibration_rms=-0.1,
        )


def test_meter_summary_structure():
    summary = SignalSummary(
        signal=SignalName.TEMPERATURE_C,
        baseline_mean=60.8,
        recent_mean=69.7,
        relative_change_pct=14.6,
        trend_slope=0.31,
    )
    meter = MeterSummary(
        asset_id="A001",
        computed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        signals={"temperature_c": summary},
    )
    assert meter.signals["temperature_c"].recent_mean == 69.7
    assert meter.model_dump()["signals"]["temperature_c"]["signal"] == "temperature_c"


def test_evidence_item_optional_timestamp():
    item = EvidenceItem(
        source_type=EvidenceSourceType.WORK_ORDER,
        source_id="WO-1048",
        summary="elevated friction noted",
    )
    assert item.timestamp is None
    assert item.source_type == EvidenceSourceType.WORK_ORDER

    with pytest.raises(ValidationError):
        EvidenceItem(source_type="unknown", source_id="WO-1", summary="x")


def test_tool_result_success_empty_error():
    ok = ToolResult.success(data=[1, 2, 3])
    assert ok.ok and ok.is_ok
    assert ok.data == [1, 2, 3]
    assert not ok.empty

    empty = ToolResult.success(data=None, empty=True)
    assert empty.ok and empty.empty

    error = ToolError(code=ToolErrorCode.NOT_FOUND, message="asset not found")
    failed = ToolResult.failure(error)
    assert not failed.ok
    assert not failed.is_ok
    assert failed.error is not None
    assert failed.error.code == ToolErrorCode.NOT_FOUND
    assert failed.error.message == "asset not found"


def test_proposed_action_defaults_and_approval_transition():
    action = ProposedAction(
        action_type=ActionType.CREATE_WORK_ORDER,
        asset_id="A001",
        summary="Inspect lubrication pressure and filter condition",
    )
    assert action.status == ApprovalStatus.PENDING_APPROVAL
    assert action.priority == Priority.MEDIUM

    approved = action.model_copy(
        update={
            "status": ApprovalStatus.APPROVED,
            "approved_by": "operator-1",
            "approved_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
        }
    )
    assert approved.status == ApprovalStatus.APPROVED
    assert approved.approved_by == "operator-1"


def test_settings_from_env_hides_secret(monkeypatch):
    monkeypatch.setenv("DATA_DIR", "tmp_data")
    monkeypatch.setenv("DB_PATH", "tmp_data/test.db")
    monkeypatch.setenv("LLM_MODEL", "deepseek-reasoner")
    monkeypatch.setenv("LLM_API_KEY", "sk-secret-123")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)

    settings = Settings.from_env()
    assert settings.data_dir == Path("tmp_data")
    assert settings.db_path == Path("tmp_data") / "test.db"
    assert settings.llm_model == "deepseek-reasoner"
    assert settings.llm_api_key is not None
    assert "sk-secret-123" not in repr(settings)
