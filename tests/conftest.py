"""Shared fixtures: ensure the synthetic data and SQLite DB exist."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _ensure_synthetic_data() -> None:
    raw_assets = ROOT / "data" / "raw" / "assets.csv"
    db = ROOT / "data" / "industrial.db"
    python = sys.executable
    if not raw_assets.exists():
        subprocess.run(
            [python, "scripts/generate_synthetic_data.py"], cwd=ROOT, check=True
        )
    if not db.exists():
        subprocess.run(
            [python, "scripts/load_database.py"], cwd=ROOT, check=True
        )


@pytest.fixture(scope="session", autouse=True)
def ensure_synthetic_data() -> None:
    _ensure_synthetic_data()


@pytest.fixture(scope="session")
def repository():
    from src.db.repository import Repository

    _ensure_synthetic_data()
    return Repository(ROOT / "data" / "industrial.db")
