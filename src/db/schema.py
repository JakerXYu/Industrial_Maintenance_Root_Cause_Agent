"""SQLite schema for the synthetic CMMS dataset."""

TABLE_NAMES = [
    "events",
    "part_usage",
    "asset_parts",
    "parts",
    "task_groups",
    "maintenance_plans",
    "meter_readings",
    "work_orders",
    "assets",
]

CREATE_TABLES = [
    """
    CREATE TABLE assets (
        asset_id TEXT PRIMARY KEY,
        asset_name TEXT NOT NULL,
        asset_type TEXT NOT NULL,
        line TEXT NOT NULL,
        department TEXT NOT NULL,
        manufacturer TEXT NOT NULL,
        model TEXT NOT NULL,
        install_date TEXT NOT NULL,
        criticality TEXT NOT NULL,
        status TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE work_orders (
        wo_id TEXT PRIMARY KEY,
        asset_id TEXT NOT NULL REFERENCES assets(asset_id),
        created_at TEXT NOT NULL,
        completed_at TEXT,
        wo_type TEXT NOT NULL,
        priority TEXT NOT NULL,
        symptom TEXT NOT NULL,
        diagnosis TEXT,
        action_taken TEXT,
        downtime_min REAL,
        status TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE meter_readings (
        reading_id TEXT PRIMARY KEY,
        asset_id TEXT NOT NULL REFERENCES assets(asset_id),
        timestamp TEXT NOT NULL,
        cycle_count INTEGER,
        runtime_hours REAL,
        temperature_c REAL,
        pressure_bar REAL,
        vibration_rms REAL,
        current_a REAL
    )
    """,
    """
    CREATE TABLE maintenance_plans (
        plan_id TEXT PRIMARY KEY,
        asset_id TEXT NOT NULL REFERENCES assets(asset_id),
        task_group_id TEXT NOT NULL,
        trigger_type TEXT NOT NULL,
        interval_value REAL NOT NULL,
        interval_unit TEXT NOT NULL,
        last_completed_at TEXT,
        next_due_at TEXT,
        active INTEGER
    )
    """,
    """
    CREATE TABLE task_groups (
        task_group_id TEXT NOT NULL,
        task_seq INTEGER NOT NULL,
        task_text TEXT NOT NULL,
        safety_critical INTEGER,
        PRIMARY KEY (task_group_id, task_seq)
    )
    """,
    """
    CREATE TABLE parts (
        part_id TEXT PRIMARY KEY,
        part_name TEXT NOT NULL,
        category TEXT NOT NULL,
        unit_cost REAL,
        stock_qty INTEGER,
        reorder_point INTEGER
    )
    """,
    """
    CREATE TABLE asset_parts (
        asset_id TEXT NOT NULL REFERENCES assets(asset_id),
        part_id TEXT NOT NULL REFERENCES parts(part_id),
        quantity INTEGER,
        relationship_type TEXT
    )
    """,
    """
    CREATE TABLE part_usage (
        event_id TEXT PRIMARY KEY,
        wo_id TEXT NOT NULL,
        asset_id TEXT NOT NULL REFERENCES assets(asset_id),
        part_id TEXT NOT NULL REFERENCES parts(part_id),
        quantity INTEGER,
        timestamp TEXT
    )
    """,
    """
    CREATE TABLE events (
        event_id TEXT PRIMARY KEY,
        asset_id TEXT NOT NULL REFERENCES assets(asset_id),
        timestamp TEXT NOT NULL,
        event_type TEXT NOT NULL,
        severity TEXT NOT NULL,
        description TEXT
    )
    """,
]
