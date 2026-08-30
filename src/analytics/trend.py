"""Deterministic trend and baseline-vs-recent analytics."""

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from src.contracts import MeterReading, MeterSummary, MeterSummaryRequest, SignalSummary


def _as_frame(readings: List[MeterReading]) -> pd.DataFrame:
    df = pd.DataFrame([r.model_dump() for r in readings])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def _slope(values: np.ndarray, seconds: np.ndarray) -> Optional[float]:
    if len(values) < 2 or np.isnan(values).all():
        return None
    mask = ~np.isnan(values)
    x = seconds[mask].astype(float)
    y = values[mask].astype(float)
    if len(x) < 2:
        return None
    return float(np.polyfit(x, y, 1)[0])


def _signal_stats(
    df: pd.DataFrame,
    signal: str,
    baseline_mask: pd.Series,
    recent_mask: pd.Series,
    baseline_days: int,
    recent_days: int,
) -> Optional[SignalSummary]:
    baseline = df.loc[baseline_mask, signal]
    recent = df.loc[recent_mask, signal]
    baseline_mean = float(baseline.mean()) if baseline.notna().any() else None
    recent_mean = float(recent.mean()) if recent.notna().any() else None

    if baseline_mean is None or recent_mean is None:
        return None

    relative_change_pct: Optional[float] = None
    if baseline_mean != 0:
        relative_change_pct = float((recent_mean - baseline_mean) / baseline_mean * 100.0)

    seconds = df.loc[recent_mask, "timestamp"].astype("int64").to_numpy() / 1e9
    slope = _slope(recent.to_numpy(dtype=float), seconds)

    return SignalSummary(
        signal=signal,
        baseline_mean=baseline_mean,
        recent_mean=recent_mean,
        relative_change_pct=relative_change_pct,
        trend_slope=slope,
        baseline_window_days=baseline_days,
        recent_window_days=recent_days,
        missing_count=int(recent.isna().sum()),
    )


def compute_meter_summary(
    readings: List[MeterReading], request: MeterSummaryRequest
) -> MeterSummary:
    """Compare the latest ``recent_days`` against the preceding ``baseline_days``."""
    recent_days = 7
    baseline_days = request.days

    if not readings:
        return MeterSummary(
            asset_id=request.asset_id,
            baseline_days=baseline_days,
            recent_days=recent_days,
            signals={},
        )

    df = _as_frame(readings)
    now = df["timestamp"].max()
    recent_mask = df["timestamp"] >= (now - pd.Timedelta(days=recent_days))
    baseline_mask = (
        (df["timestamp"] < (now - pd.Timedelta(days=recent_days)))
        & (df["timestamp"] >= (now - pd.Timedelta(days=recent_days + baseline_days)))
    )

    signals: Dict[str, SignalSummary] = {}
    for signal in request.signals:
        key = signal.value
        if key not in df.columns:
            continue
        summary = _signal_stats(
            df, key, baseline_mask, recent_mask, baseline_days, recent_days
        )
        if summary is not None:
            signals[key] = summary

    return MeterSummary(
        asset_id=request.asset_id,
        baseline_days=baseline_days,
        recent_days=recent_days,
        signals=signals,
    )
