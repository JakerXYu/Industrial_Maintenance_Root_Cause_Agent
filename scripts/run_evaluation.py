"""Run the offline evaluation and write a Markdown report."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db.repository import Repository
from src.evaluation.runner import run_evaluation


def main() -> None:
    repo = Repository(ROOT / "data" / "industrial.db")
    metrics, _ = run_evaluation(
        repo,
        ROOT / "traces",
        ROOT / "docs" / "EVALUATION_REPORT.md",
    )
    print("Metrics:", metrics.model_dump())
    print("Report written to", ROOT / "docs" / "EVALUATION_REPORT.md")


if __name__ == "__main__":
    main()
