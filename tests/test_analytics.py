"""Tests for deterministic analytics."""

import numpy as np
import pandas as pd

from src.analytics.anomaly import flag_anomalies, modified_zscore
from src.analytics.trend import compute_meter_summary
from src.contracts import MeterSummaryRequest


def test_compute_meter_summary_lubrication_trend(repository):
    readings = repository.get_recent_meter_readings("A001", 37, 100000)
    request = MeterSummaryRequest(asset_id="A001", days=30)
    summary = compute_meter_summary(readings, request)

    temperature = summary.signals["temperature_c"]
    assert temperature.recent_mean > temperature.baseline_mean
    assert temperature.relative_change_pct > 0


def test_compute_meter_summary_pressure_decline(repository):
    readings = repository.get_recent_meter_readings("A016", 37, 100000)
    request = MeterSummaryRequest(asset_id="A016", days=30)
    summary = compute_meter_summary(readings, request)

    pressure = summary.signals["pressure_bar"]
    assert pressure.recent_mean < pressure.baseline_mean
    assert pressure.relative_change_pct < 0


def test_compute_meter_summary_empty_returns_typed_summary():
    request = MeterSummaryRequest(asset_id="A001", days=45)
    summary = compute_meter_summary([], request)

    assert summary.asset_id == "A001"
    assert summary.baseline_days == 45
    assert summary.recent_days == 7
    assert summary.signals == {}


def test_signal_summary_propagates_window_values(repository):
    readings = repository.get_recent_meter_readings("A001", 37, 100000)
    request = MeterSummaryRequest(asset_id="A001", days=30)
    summary = compute_meter_summary(readings, request)

    assert summary.signals
    for signal_summary in summary.signals.values():
        assert signal_summary.baseline_window_days == 30
        assert signal_summary.recent_window_days == 7


def test_modified_zscore_flags_spike():
    values = pd.Series(np.r_[np.random.default_rng(0).normal(1.0, 0.2, 50), 8.0])
    z = modified_zscore(values)
    assert z.abs().idxmax() == 50
    assert flag_anomalies(values, threshold=3.0).iloc[50]
