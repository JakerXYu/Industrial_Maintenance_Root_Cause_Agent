"""Load the synthetic CSVs into a SQLite database.

Run from the project root:
    .venv/Scripts/python scripts/load_database.py

The loader is idempotent: it drops and recreates the target tables each run.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import List

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db.schema import CREATE_TABLES, TABLE_NAMES

RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "industrial.db"


def _records(df: pd.DataFrame, columns: List[str]) -> List[tuple]:
    mask = df.notnull()
    obj = df.astype(object).where(mask, None)
    return [tuple(record[c] for c in columns) for record in obj.to_dict("records")]


def _load_table(
    conn: sqlite3.Connection,
    name: str,
    columns: List[str],
    df: pd.DataFrame,
) -> None:
    placeholders = ", ".join("?" for _ in columns)
    sql = f"INSERT INTO {name} ({', '.join(columns)}) VALUES ({placeholders})"
    conn.executemany(sql, _records(df, columns))


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        for name in TABLE_NAMES:
            conn.execute(f"DROP TABLE IF EXISTS {name}")
        for statement in CREATE_TABLES:
            conn.execute(statement)

        _load_table(
            conn,
            "assets",
            ["asset_id", "asset_name", "asset_type", "line", "department",
             "manufacturer", "model", "install_date", "criticality", "status"],
            pd.read_csv(RAW_DIR / "assets.csv"),
        )
        _load_table(
            conn,
            "work_orders",
            ["wo_id", "asset_id", "created_at", "completed_at", "wo_type",
             "priority", "symptom", "diagnosis", "action_taken", "downtime_min", "status"],
            pd.read_csv(RAW_DIR / "work_orders.csv"),
        )
        _load_table(
            conn,
            "meter_readings",
            ["reading_id", "asset_id", "timestamp", "cycle_count", "runtime_hours",
             "temperature_c", "pressure_bar", "vibration_rms", "current_a"],
            pd.read_csv(RAW_DIR / "meter_readings.csv"),
        )
        _load_table(
            conn,
            "maintenance_plans",
            ["plan_id", "asset_id", "task_group_id", "trigger_type", "interval_value",
             "interval_unit", "last_completed_at", "next_due_at", "active"],
            pd.read_csv(RAW_DIR / "maintenance_plans.csv"),
        )
        _load_table(
            conn,
            "task_groups",
            ["task_group_id", "task_seq", "task_text", "safety_critical"],
            pd.read_csv(RAW_DIR / "task_groups.csv"),
        )
        _load_table(
            conn,
            "parts",
            ["part_id", "part_name", "category", "unit_cost", "stock_qty", "reorder_point"],
            pd.read_csv(RAW_DIR / "parts.csv"),
        )
        _load_table(
            conn,
            "asset_parts",
            ["asset_id", "part_id", "quantity", "relationship_type"],
            pd.read_csv(RAW_DIR / "asset_parts.csv"),
        )
        _load_table(
            conn,
            "part_usage",
            ["event_id", "wo_id", "asset_id", "part_id", "quantity", "timestamp"],
            pd.read_csv(RAW_DIR / "part_usage.csv"),
        )
        _load_table(
            conn,
            "events",
            ["event_id", "asset_id", "timestamp", "event_type", "severity", "description"],
            pd.read_csv(RAW_DIR / "events.csv"),
        )
        conn.commit()
    finally:
        conn.close()

    print("Database written to", DB_PATH)


if __name__ == "__main__":
    main()
