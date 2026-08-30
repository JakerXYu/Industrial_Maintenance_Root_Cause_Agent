"""Read-only repository over the SQLite CMMS database.

Every query uses parameterized SQL. Outputs are typed Pydantic contracts, never
raw dicts. Empty results are returned as empty lists / ``None``, distinct from
errors which are raised or propagated by the tool layer.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from src.contracts import Asset, MeterReading, WorkOrder


class Repository:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{self.db_path.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def get_asset(self, asset_id: str) -> Optional[Asset]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM assets WHERE asset_id = ?", (asset_id,)
            ).fetchone()
        return Asset.model_validate(dict(row)) if row else None

    def list_assets(self, limit: int = 100) -> List[Asset]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM assets ORDER BY asset_id LIMIT ?", (limit,)
            ).fetchall()
        return [Asset.model_validate(dict(row)) for row in rows]

    def search_recent_work_orders(
        self, asset_id: str, days: int, limit: int
    ) -> List[WorkOrder]:
        with self._connect() as conn:
            now_s = conn.execute(
                "SELECT MAX(created_at) AS now FROM work_orders"
            ).fetchone()["now"]
            if not now_s:
                return []
            now = datetime.fromisoformat(now_s)
            cutoff = (now - timedelta(days=days)).isoformat(sep=" ")
            rows = conn.execute(
                "SELECT * FROM work_orders "
                "WHERE asset_id = ? AND created_at >= ? "
                "ORDER BY created_at DESC LIMIT ?",
                (asset_id, cutoff, limit),
            ).fetchall()
        return [WorkOrder.model_validate(dict(row)) for row in rows]

    def get_meter_history(
        self, asset_id: str, start: datetime, end: datetime, limit: int
    ) -> List[MeterReading]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM meter_readings "
                "WHERE asset_id = ? AND timestamp >= ? AND timestamp <= ? "
                "ORDER BY timestamp ASC LIMIT ?",
                (
                    asset_id,
                    start.isoformat(sep=" "),
                    end.isoformat(sep=" "),
                    limit,
                ),
            ).fetchall()
        return [MeterReading.model_validate(dict(row)) for row in rows]

    def get_recent_meter_readings(
        self, asset_id: str, days: int, limit: int
    ) -> List[MeterReading]:
        with self._connect() as conn:
            now_s = conn.execute(
                "SELECT MAX(timestamp) AS now FROM meter_readings"
            ).fetchone()["now"]
            if not now_s:
                return []
            now = datetime.fromisoformat(now_s)
            start = (now - timedelta(days=days)).isoformat(sep=" ")
            rows = conn.execute(
                "SELECT * FROM meter_readings "
                "WHERE asset_id = ? AND timestamp >= ? "
                "ORDER BY timestamp ASC LIMIT ?",
                (asset_id, start, limit),
            ).fetchall()
        return [MeterReading.model_validate(dict(row)) for row in rows]
