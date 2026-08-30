"""Robust, deterministic anomaly helpers (MAD / modified z-score)."""

from typing import List

import numpy as np
import pandas as pd


def median_absolute_deviation(values: pd.Series) -> float:
    return float(np.median(np.abs(values - np.median(values))))


def modified_zscore(values: pd.Series) -> pd.Series:
    med = values.median()
    scale = median_absolute_deviation(values) * 1.4826
    if scale == 0:
        return pd.Series(0.0, index=values.index)
    return 0.6745 * (values - med) / scale


def rolling_zscore(values: pd.Series, window: int = 24) -> pd.Series:
    rolling_mean = values.rolling(window, min_periods=max(2, window // 2)).mean()
    rolling_std = values.rolling(window, min_periods=max(2, window // 2)).std()
    return (values - rolling_mean) / rolling_std.replace(0, np.nan)


def flag_anomalies(values: pd.Series, threshold: float = 3.5) -> pd.Series:
    return modified_zscore(values).abs() > threshold
