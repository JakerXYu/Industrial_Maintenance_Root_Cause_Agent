"""Tests for the synthetic dataset invariants."""

from pathlib import Path

import pandas as pd
import pytest

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
SIM_START = pd.Timestamp("2025-12-01 00:00:00")


@pytest.fixture(scope="module")
def assets() -> pd.DataFrame:
    return pd.read_csv(RAW / "assets.csv")


@pytest.fixture(scope="module")
def work_orders() -> pd.DataFrame:
    return pd.read_csv(RAW / "work_orders.csv", parse_dates=["created_at", "completed_at"])


@pytest.fixture(scope="module")
def meter_readings() -> pd.DataFrame:
    return pd.read_csv(RAW / "meter_readings.csv", parse_dates=["timestamp"])


@pytest.fixture(scope="module")
def parts() -> pd.DataFrame:
    return pd.read_csv(RAW / "parts.csv")


@pytest.fixture(scope="module")
def task_groups() -> pd.DataFrame:
    return pd.read_csv(RAW / "task_groups.csv")


def test_assets_count_and_pk(assets):
    assert len(assets) == 25
    assert assets["asset_id"].is_unique


def test_work_orders_pk_fk_and_scale(assets, work_orders):
    assert work_orders["wo_id"].is_unique
    assert work_orders["asset_id"].isin(assets["asset_id"]).all()
    assert 250 <= len(work_orders) <= 400


def test_meter_readings_bounds_and_nonnegative(assets, meter_readings):
    assert meter_readings["reading_id"].is_unique
    assert meter_readings["asset_id"].isin(assets["asset_id"]).all()
    assert (meter_readings["cycle_count"] >= 0).all()
    assert meter_readings["timestamp"].min() >= SIM_START
    assert meter_readings["timestamp"].max() < SIM_START + pd.Timedelta(days=180)


def test_meter_readings_have_missing_values(meter_readings):
    signal_cols = ["temperature_c", "pressure_bar", "vibration_rms", "current_a"]
    assert meter_readings[signal_cols].isna().any().any()


def test_meter_readings_have_duplicate_rows(meter_readings):
    duplicated = meter_readings.duplicated(subset=["asset_id", "timestamp"], keep=False)
    assert duplicated.sum() > 0


def test_parts_scale_and_pk(parts):
    assert 80 <= len(parts) <= 120
    assert parts["part_id"].is_unique


def test_task_groups_composite_pk(task_groups):
    assert not task_groups.duplicated(subset=["task_group_id", "task_seq"]).any()
    assert 10 <= task_groups["task_group_id"].nunique() <= 20


def test_related_foreign_keys(
    assets, work_orders, meter_readings, parts, task_groups
):
    maintenance_plans = pd.read_csv(RAW / "maintenance_plans.csv")
    asset_parts = pd.read_csv(RAW / "asset_parts.csv")
    part_usage = pd.read_csv(RAW / "part_usage.csv")
    events = pd.read_csv(RAW / "events.csv")

    assert maintenance_plans["asset_id"].isin(assets["asset_id"]).all()
    assert maintenance_plans["task_group_id"].isin(task_groups["task_group_id"]).all()
    assert asset_parts["asset_id"].isin(assets["asset_id"]).all()
    assert asset_parts["part_id"].isin(parts["part_id"]).all()
    assert part_usage["asset_id"].isin(assets["asset_id"]).all()
    assert part_usage["part_id"].isin(parts["part_id"]).all()
    assert events["asset_id"].isin(assets["asset_id"]).all()


def _recent_vs_baseline(meter_readings, asset_id, column):
    sub = meter_readings[meter_readings["asset_id"] == asset_id]
    cut = sub["timestamp"].quantile(0.75)
    baseline = sub[sub["timestamp"] < cut][column].mean()
    recent = sub[sub["timestamp"] >= cut][column].mean()
    return baseline, recent


def test_injected_failure_signal_patterns(meter_readings):
    base, recent = _recent_vs_baseline(meter_readings, "A001", "temperature_c")
    assert recent > base + 2.0  # lubrication -> temperature rises

    base, recent = _recent_vs_baseline(meter_readings, "A016", "pressure_bar")
    assert recent < base - 5.0  # hydraulic leak -> pressure declines

    base, recent = _recent_vs_baseline(meter_readings, "A011", "vibration_rms")
    assert recent > base + 0.1  # bearing -> vibration rises

    base, recent = _recent_vs_baseline(meter_readings, "A015", "temperature_c")
    assert recent > base + 2.0  # cooling -> temperature rises
