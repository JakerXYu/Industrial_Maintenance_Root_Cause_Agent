"""Generate a reproducible, fictional CMMS-like dataset.

Run from the project root:
    .venv/Scripts/python scripts/generate_synthetic_data.py

The generator is deterministic (fixed seed), idempotent (overwrites outputs),
and writes all files under data/raw plus fictional maintenance documents under
data/docs. The ground-truth file is evaluation-only and must not be exposed to
the agent at runtime.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

SEED = 42
N_ASSETS = 25
SIM_DAYS = 180
READING_HOURS = 2
SIM_START = pd.Timestamp("2025-12-01 00:00:00")
SIM_END = SIM_START + pd.Timedelta(days=SIM_DAYS)
READINGS_PER_DAY = 24 // READING_HOURS

ASSET_TYPES = [
    "hydraulic_press",
    "robotic_welding_cell",
    "cnc_machine",
    "industrial_pump",
]

BASE_SIGNALS: Dict[str, Dict[str, float]] = {
    "hydraulic_press": {
        "temperature_c": 65.0,
        "pressure_bar": 180.0,
        "vibration_rms": 1.5,
        "current_a": 120.0,
    },
    "robotic_welding_cell": {
        "temperature_c": 55.0,
        "pressure_bar": 6.0,
        "vibration_rms": 2.0,
        "current_a": 60.0,
    },
    "cnc_machine": {
        "temperature_c": 48.0,
        "pressure_bar": 4.0,
        "vibration_rms": 1.8,
        "current_a": 45.0,
    },
    "industrial_pump": {
        "temperature_c": 52.0,
        "pressure_bar": 8.0,
        "vibration_rms": 2.2,
        "current_a": 35.0,
    },
}

FAILURE_ASSIGNMENTS: Dict[str, str] = {
    "A001": "lubrication_degradation",
    "A006": "position_sensor_instability",
    "A011": "bearing_degradation",
    "A015": "cooling_degradation",
    "A016": "hydraulic_leakage",
    "A025": "normal_or_false_alarm",
}

FAILURE_START_DAYS: Dict[str, int] = {
    "lubrication_degradation": 158,
    "position_sensor_instability": 162,
    "bearing_degradation": 150,
    "cooling_degradation": 155,
    "hydraulic_leakage": 160,
    "normal_or_false_alarm": 150,
}

OVERDUE_DAYS: Dict[str, int] = {
    "lubrication_degradation": 9,
    "cooling_degradation": 7,
}

FAILURE_SEVERITY: Dict[str, str] = {
    "lubrication_degradation": "medium",
    "position_sensor_instability": "medium",
    "bearing_degradation": "high",
    "cooling_degradation": "high",
    "hydraulic_leakage": "high",
    "normal_or_false_alarm": "low",
}

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
DOCS_DIR = ROOT / "data" / "docs"

rng = np.random.default_rng(SEED)


def _asset_type(index_1_based: int) -> str:
    return ASSET_TYPES[(index_1_based - 1) % len(ASSET_TYPES)]


def _failure_mode(asset_id: str) -> Optional[str]:
    return FAILURE_ASSIGNMENTS.get(asset_id)


def _make_assets() -> pd.DataFrame:
    rows = []
    manufacturers = ["Nordvik", "Helios", "Atlas Robotics", "Ferroline"]
    for i in range(1, N_ASSETS + 1):
        asset_id = f"A{i:03d}"
        asset_type = _asset_type(i)
        rows.append(
            {
                "asset_id": asset_id,
                "asset_name": f"{asset_type.replace('_', ' ').title()} {asset_id}",
                "asset_type": asset_type,
                "line": f"Line {(i - 1) % 5 + 1}",
                "department": ["Stamping", "Welding", "Machining", "Utilities"][
                    (i - 1) % 4
                ],
                "manufacturer": manufacturers[(i - 1) % len(manufacturers)],
                "model": f"MOD-{100 + i}",
                "install_date": (SIM_START - pd.Timedelta(days=int(rng.integers(200, 3000)))).date(),
                "criticality": "critical" if i % 7 == 0 else "high" if i % 3 == 0 else "medium",
                "status": "under_maintenance" if i == 9 else "active",
            }
        )
    return pd.DataFrame(rows)


def _make_task_groups() -> pd.DataFrame:
    rows = []
    task_pool = [
        "Inspect lubrication pressure and filter condition",
        "Verify lubrication flow rate",
        "Inspect hydraulic seals for leakage",
        "Check coolant level and flow",
        "Tighten and inspect wiring connectors",
        "Measure bearing temperature and vibration",
        "Replace filter element",
        "Calibrate position sensor",
        "Run 20 controlled cycles and compare trend",
        "Inspect belt tension",
        "Verify emergency stop circuit",
        "Clean and inspect cooling fan",
    ]
    for g in range(1, 13):
        n_tasks = int(rng.integers(3, 13))
        tasks = list(rng.choice(task_pool, size=n_tasks, replace=False))
        for seq, text in enumerate(tasks, start=1):
            rows.append(
                {
                    "task_group_id": f"TG-{g:02d}",
                    "task_seq": seq,
                    "task_text": text,
                    "safety_critical": bool(rng.random() < 0.25),
                }
            )
    return pd.DataFrame(rows)


def _make_parts() -> Tuple[pd.DataFrame, pd.DataFrame]:
    categories = ["filter", "seal", "bearing", "sensor", "lubricant", "belt", "motor", "valve"]
    parts = []
    for i in range(1, 101):
        parts.append(
            {
                "part_id": f"P{i:03d}",
                "part_name": f"{categories[(i - 1) % len(categories)]} element {i:03d}",
                "category": categories[(i - 1) % len(categories)],
                "unit_cost": round(float(rng.uniform(5.0, 900.0)), 2),
                "stock_qty": int(rng.integers(0, 120)),
                "reorder_point": int(rng.integers(5, 30)),
            }
        )
    parts_df = pd.DataFrame(parts)

    asset_parts = []
    relationship_types = ["installed", "spare", "consumable"]
    for i in range(1, N_ASSETS + 1):
        asset_id = f"A{i:03d}"
        n_parts = int(rng.integers(3, 7))
        chosen = rng.choice(parts_df["part_id"].to_numpy(), size=n_parts, replace=False)
        for part_id in chosen:
            asset_parts.append(
                {
                    "asset_id": asset_id,
                    "part_id": str(part_id),
                    "quantity": int(rng.integers(1, 4)),
                    "relationship_type": str(
                        rng.choice(relationship_types, size=1)[0]
                    ),
                }
            )
    return parts_df, pd.DataFrame(asset_parts)


def _make_maintenance_plans(assets: pd.DataFrame) -> pd.DataFrame:
    rows = []
    plan_id = 0
    for _, asset in assets.iterrows():
        asset_id = asset["asset_id"]
        mode = _failure_mode(asset_id)
        n_plans = int(rng.integers(2, 5))
        for p in range(n_plans):
            plan_id += 1
            interval_value = float(rng.choice([30, 60, 90, 180]))
            trigger_type = "time_based" if rng.random() < 0.7 else "usage_based"

            if p == 0 and mode in OVERDUE_DAYS:
                next_due = SIM_END - pd.Timedelta(days=OVERDUE_DAYS[mode])
                last_completed = next_due - pd.Timedelta(days=interval_value)
            else:
                last_completed = SIM_START + pd.Timedelta(days=int(rng.integers(10, 150)))
                next_due = last_completed + pd.Timedelta(days=interval_value)
            rows.append(
                {
                    "plan_id": f"MP-{plan_id:04d}",
                    "asset_id": asset_id,
                    "task_group_id": f"TG-{int(rng.integers(1, 13)):02d}",
                    "trigger_type": trigger_type,
                    "interval_value": interval_value,
                    "interval_unit": "days" if trigger_type == "time_based" else "cycles",
                    "last_completed_at": last_completed,
                    "next_due_at": next_due,
                    "active": bool(rng.random() < 0.9),
                }
            )
    return pd.DataFrame(rows)


def _apply_failure(
    signals: Dict[str, np.ndarray],
    mode: str,
    start_idx: int,
    n: int,
) -> None:
    w = np.arange(n - start_idx)
    denom = max(int(w[-1]) if len(w) else 1, 1)
    if mode == "lubrication_degradation":
        signals["temperature_c"][start_idx:] += (w / denom) * 10.0
        signals["vibration_rms"][start_idx:] += (w / denom) * 0.4
    elif mode == "hydraulic_leakage":
        signals["pressure_bar"][start_idx:] -= (w / denom) * 25.0
    elif mode == "position_sensor_instability":
        spikes = rng.normal(0.0, 0.8, n - start_idx)
        signals["vibration_rms"][start_idx:] += np.where(np.abs(spikes) > 1.8, spikes, 0.0)
    elif mode == "bearing_degradation":
        signals["vibration_rms"][start_idx:] += (w / denom) * 0.8
        signals["temperature_c"][start_idx:] += (w / denom) * 6.0
    elif mode == "cooling_degradation":
        signals["temperature_c"][start_idx:] += (w / denom) * 12.0
    elif mode == "normal_or_false_alarm":
        for _ in range(3):
            idx = start_idx + int(rng.integers(0, n - start_idx))
            signals["vibration_rms"][idx] += 0.5
            signals["temperature_c"][idx] += 1.5


def _make_meter_readings(assets: pd.DataFrame) -> pd.DataFrame:
    n = SIM_DAYS * READINGS_PER_DAY
    timestamps = pd.date_range(SIM_START, periods=n, freq=f"{READING_HOURS}h")
    frames: List[pd.DataFrame] = []
    reading_seq = 0

    for _, asset in assets.iterrows():
        asset_id = asset["asset_id"]
        asset_type = asset["asset_type"]
        base = BASE_SIGNALS[asset_type]
        mode = _failure_mode(asset_id)

        signals = {
            "temperature_c": base["temperature_c"] + rng.normal(0, 0.6, n),
            "pressure_bar": base["pressure_bar"] + rng.normal(0, 0.4, n),
            "vibration_rms": base["vibration_rms"] + rng.normal(0, 0.05, n),
            "current_a": base["current_a"] + rng.normal(0, 0.5, n),
        }

        if mode is not None:
            start_idx = FAILURE_START_DAYS[mode] * READINGS_PER_DAY
            _apply_failure(signals, mode, start_idx, n)

        cycle_count = int(rng.integers(1000, 50000)) + np.cumsum(rng.integers(0, 3, n))
        runtime_hours = float(rng.integers(0, 1000)) + np.arange(n) * READING_HOURS

        df = pd.DataFrame(
            {
                "asset_id": asset_id,
                "timestamp": timestamps,
                "cycle_count": cycle_count.astype(int),
                "runtime_hours": runtime_hours,
                "temperature_c": signals["temperature_c"],
                "pressure_bar": signals["pressure_bar"],
                "vibration_rms": signals["vibration_rms"],
                "current_a": signals["current_a"],
            }
        )
        df.insert(0, "reading_id", [f"R-{reading_seq + k + 1:08d}" for k in range(n)])
        reading_seq += n
        frames.append(df)

    all_readings = pd.concat(frames, ignore_index=True)

    # Data quality imperfections: ~1.5% missing signal values.
    signal_cols = ["temperature_c", "pressure_bar", "vibration_rms", "current_a"]
    mask = rng.random(all_readings[signal_cols].shape) < 0.015
    all_readings[signal_cols] = all_readings[signal_cols].mask(mask)

    # Occasional duplicate meter rows.
    n_dupes = 24
    dup_idx = rng.choice(all_readings.index, size=n_dupes, replace=False)
    dupes = all_readings.loc[dup_idx].copy()
    dupes["reading_id"] = [f"R-DUP-{k:05d}" for k in range(n_dupes)]
    all_readings = pd.concat([all_readings, dupes], ignore_index=True)
    return all_readings


def _symptom_for(mode: Optional[str]) -> str:
    pool = {
        "lubrication_degradation": ["elevated friction", "lubrication noise", "squealing at load"],
        "hydraulic_leakage": ["pressure drop", "seal leak observed", "hydraulic fluid on floor"],
        "position_sensor_instability": ["intermittent position readout", "sensor signal dropout", "wiring connector issue"],
        "bearing_degradation": ["vibration increasing", "bearing noise", "rough rotation"],
        "cooling_degradation": ["overheating", "coolant temp high", "cooling fan intermittent"],
        "normal_or_false_alarm": ["suspected bearing wear", "occasional vibration spike", "routine inspection"],
    }
    if mode in pool:
        return str(rng.choice(pool[mode], size=1)[0])
    return str(rng.choice(["routine inspection", "worn belt noted", "minor leak", "no issue found"], size=1)[0])


def _make_work_orders(assets: pd.DataFrame) -> pd.DataFrame:
    rows = []
    wo_types = ["corrective", "preventive", "inspection", "emergency"]
    priorities = ["low", "medium", "high", "urgent"]
    wo_seq = 0

    # Failure-specific work orders first.
    for asset_id, mode in FAILURE_ASSIGNMENTS.items():
        start_day = FAILURE_START_DAYS[mode]
        for j in range(int(rng.integers(4, 8))):
            wo_seq += 1
            created = SIM_START + pd.Timedelta(days=start_day + int(rng.integers(0, 12)))
            completed = created + pd.Timedelta(hours=int(rng.integers(1, 72)))
            rows.append(
                {
                    "wo_id": f"WO-{wo_seq:04d}",
                    "asset_id": asset_id,
                    "created_at": created,
                    "completed_at": completed if j % 3 != 0 else pd.NaT,
                    "wo_type": "corrective",
                    "priority": str(rng.choice(["medium", "high"], size=1)[0]),
                    "symptom": _symptom_for(mode),
                    "diagnosis": "under investigation" if j % 2 == 0 else None,
                    "action_taken": "inspection" if j % 3 == 0 else None,
                    "downtime_min": float(rng.uniform(0, 180)),
                    "status": "open" if j % 3 == 0 else "completed",
                }
            )

    # Random work orders across all assets.
    target_total = int(rng.integers(280, 340))
    while wo_seq < target_total:
        wo_seq += 1
        asset_id = f"A{int(rng.integers(1, N_ASSETS + 1)):03d}"
        created = SIM_START + pd.Timedelta(days=int(rng.integers(0, SIM_DAYS)))
        completed = created + pd.Timedelta(hours=int(rng.integers(1, 168)))
        rows.append(
            {
                "wo_id": f"WO-{wo_seq:04d}",
                "asset_id": asset_id,
                "created_at": created,
                "completed_at": completed if rng.random() < 0.75 else pd.NaT,
                "wo_type": str(rng.choice(wo_types, size=1)[0]),
                "priority": str(rng.choice(priorities, size=1)[0]),
                "symptom": _symptom_for(None),
                "diagnosis": None,
                "action_taken": "closed without action" if rng.random() < 0.4 else None,
                "downtime_min": float(rng.uniform(0, 120)),
                "status": "completed" if rng.random() < 0.7 else "open",
            }
        )
    return pd.DataFrame(rows)


def _make_part_usage(
    parts: pd.DataFrame,
    asset_parts: pd.DataFrame,
    work_orders: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    event_seq = 0
    for _, wo in work_orders.iterrows():
        if rng.random() > 0.3:
            continue
        candidates = asset_parts[asset_parts["asset_id"] == wo["asset_id"]]
        if candidates.empty:
            continue
        part_id = str(rng.choice(candidates["part_id"].to_numpy(), size=1)[0])
        event_seq += 1
        rows.append(
            {
                "event_id": f"PU-{event_seq:06d}",
                "wo_id": wo["wo_id"],
                "asset_id": wo["asset_id"],
                "part_id": part_id,
                "quantity": int(rng.integers(1, 3)),
                "timestamp": wo["created_at"],
            }
        )
    return pd.DataFrame(rows)


def _make_events(assets: pd.DataFrame) -> pd.DataFrame:
    rows = []
    event_seq = 0
    for asset_id, mode in FAILURE_ASSIGNMENTS.items():
        start_day = FAILURE_START_DAYS[mode]
        event_type = "alarm"
        description = "scheduled inspection"
        severity = "low"
        if mode == "position_sensor_instability":
            event_type = "intermittent_stop"
            description = "intermittent stop attributed to sensor signal dropout"
            severity = "medium"
        elif mode == "cooling_degradation":
            event_type = "overheat_alarm"
            description = "coolant temperature exceeded threshold"
            severity = "high"
        elif mode == "normal_or_false_alarm":
            event_type = "spurious_alarm"
            description = "transient vibration alarm with no confirmed fault"
            severity = "low"

        for _ in range(int(rng.integers(2, 5))):
            event_seq += 1
            rows.append(
                {
                    "event_id": f"EV-{event_seq:06d}",
                    "asset_id": asset_id,
                    "timestamp": SIM_START + pd.Timedelta(days=start_day + int(rng.integers(0, 10))),
                    "event_type": event_type,
                    "severity": severity,
                    "description": description,
                }
            )
    return pd.DataFrame(rows)


def _make_ground_truth(
    work_orders: pd.DataFrame,
    events: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for asset_id, mode in FAILURE_ASSIGNMENTS.items():
        wo_ids = work_orders[work_orders["asset_id"] == asset_id]["wo_id"].tolist()
        ev_ids = events[events["asset_id"] == asset_id]["event_id"].tolist()
        start_day = FAILURE_START_DAYS[mode]
        rows.append(
            {
                "asset_id": asset_id,
                "failure_mode": mode,
                "start_date": (SIM_START + pd.Timedelta(days=start_day)).date(),
                "severity": FAILURE_SEVERITY[mode],
                "relevant_evidence_ids": ";".join(wo_ids + ev_ids),
            }
        )
    return pd.DataFrame(rows)


def _write_docs() -> None:
    docs = {
        "hydraulic_press_manual.md": (
            "# Hydraulic Press Manual\n\n"
            "## Normal Operation\n\nPress P-101 operates at a nominal hydraulic pressure of 180 bar.\n"
            "The system is designed for 20 controlled cycles per minute under load.\n\n"
            "## Lubrication\n\nLubrication must be checked every 30 days. Low lubrication causes elevated\n"
            "friction and a gradual rise in operating temperature.\n\n"
            "## Troubleshooting\n\nIf friction rises without a corresponding pressure change, inspect the\n"
            "lubrication circuit before replacing any hydraulic component.\n"
        ),
        "lubrication_sop.md": (
            "# Lubrication Standard Operating Procedure\n\n"
            "## Scope\n\nThis SOP applies to all rotating and sliding equipment.\n\n"
            "## Inspection Steps\n\n1. Verify lubrication flow rate.\n"
            "2. Inspect filter condition and replace if clogged.\n"
            "3. Record friction and temperature after service.\n\n"
            "## Safety\n\nLock out the drive before opening the lubrication circuit.\n"
        ),
        "sensor_troubleshooting.md": (
            "# Sensor Troubleshooting Guide\n\n"
            "## Intermittent Position Readout\n\nIntermittent readout is usually caused by a loose wiring connector\n"
            "or a failing sensor cable, not by a process fault.\n\n"
            "## Vibration Spikes\n\nIsolated vibration spikes with normal process pressure are typically a\n"
            "measurement artifact. Verify the sensor mount before suspecting a bearing.\n"
        ),
        "preventive_maintenance_policy.md": (
            "# Preventive Maintenance Policy\n\n"
            "## Frequency\n\nTime-based PM tasks run every 30, 60, 90, or 180 days by asset class.\n"
            "Usage-based tasks run by cycle count.\n\n"
            "## Overdue Work\n\nOverdue safety-critical PM must be escalated before the asset is cleared\n"
            "for continued production.\n"
        ),
        "safety_procedure.md": (
            "# Safety Procedure\n\n"
            "## Lockout / Tagout\n\nAlways isolate energy before maintenance.\n\n"
            "## Approval\n\nNo corrective work order may be executed without an approved work order\n"
            "in the CMMS.\n"
        ),
    }
    for filename, content in docs.items():
        (DOCS_DIR / filename).write_text(content, encoding="utf-8")


def _sanity_check(assets: pd.DataFrame, meter: pd.DataFrame) -> None:
    assert len(assets) == N_ASSETS, f"expected {N_ASSETS} assets, got {len(assets)}"
    assert meter["cycle_count"].min() >= 0, "negative cycle count found"
    assert meter["timestamp"].min() >= SIM_START
    assert meter["timestamp"].max() < SIM_START + pd.Timedelta(days=SIM_DAYS + 1)


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    assets = _make_assets()
    task_groups = _make_task_groups()
    parts, asset_parts = _make_parts()
    maintenance_plans = _make_maintenance_plans(assets)
    meter_readings = _make_meter_readings(assets)
    work_orders = _make_work_orders(assets)
    part_usage = _make_part_usage(parts, asset_parts, work_orders)
    events = _make_events(assets)
    ground_truth = _make_ground_truth(work_orders, events)

    _sanity_check(assets, meter_readings)

    outputs = {
        "assets.csv": assets,
        "work_orders.csv": work_orders,
        "meter_readings.csv": meter_readings,
        "maintenance_plans.csv": maintenance_plans,
        "task_groups.csv": task_groups,
        "parts.csv": parts,
        "asset_parts.csv": asset_parts,
        "part_usage.csv": part_usage,
        "events.csv": events,
        "ground_truth_failures.csv": ground_truth,
    }
    for filename, df in outputs.items():
        df.to_csv(RAW_DIR / filename, index=False)

    _write_docs()

    print("Synthetic dataset written to", RAW_DIR)
    print("Assets:", len(assets))
    print("Work orders:", len(work_orders))
    print("Meter readings:", len(meter_readings))
    print("Parts:", len(parts))
    print("Task groups:", task_groups["task_group_id"].nunique())
    print("Ground-truth failures:", len(ground_truth))


if __name__ == "__main__":
    main()
