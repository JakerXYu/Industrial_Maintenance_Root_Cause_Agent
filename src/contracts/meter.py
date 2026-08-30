"""Meter / time-series contracts.

These cover both raw readings (structured tool output) and the deterministic
summary produced by the analytics layer. The LLM should consume summaries, not
thousands of raw rows.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .common import utcnow


class SignalName(str, Enum):
    TEMPERATURE_C = "temperature_c"
    PRESSURE_BAR = "pressure_bar"
    VIBRATION_RMS = "vibration_rms"
    CURRENT_A = "current_a"


class MeterReading(BaseModel):
    reading_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    timestamp: datetime
    cycle_count: Optional[int] = Field(default=None, ge=0)
    runtime_hours: Optional[float] = Field(default=None, ge=0)
    temperature_c: Optional[float] = None
    pressure_bar: Optional[float] = None
    vibration_rms: Optional[float] = Field(default=None, ge=0)
    current_a: Optional[float] = None


class MeterSummaryRequest(BaseModel):
    asset_id: str = Field(min_length=1)
    days: int = Field(default=30, ge=1, le=365)
    signals: List[SignalName] = Field(
        default_factory=lambda: [
            SignalName.TEMPERATURE_C,
            SignalName.PRESSURE_BAR,
            SignalName.VIBRATION_RMS,
            SignalName.CURRENT_A,
        ]
    )


class SignalSummary(BaseModel):
    signal: SignalName
    baseline_mean: float
    recent_mean: float
    relative_change_pct: Optional[float] = None
    trend_slope: Optional[float] = None
    baseline_window_days: int = Field(default=30, ge=1)
    recent_window_days: int = Field(default=7, ge=1)
    missing_count: int = Field(default=0, ge=0)


class MeterSummary(BaseModel):
    asset_id: str = Field(min_length=1)
    baseline_days: int = Field(default=30, ge=1)
    recent_days: int = Field(default=7, ge=1)
    computed_at: datetime = Field(default_factory=utcnow)
    signals: Dict[str, SignalSummary] = Field(default_factory=dict)
