"""Prepare the hydraulic systems benchmark features (Track B).

Thin CLI over :mod:`src.benchmarks.hydraulic`. Validates profile/sensor shapes,
code sets, cycle alignment and stable counts; extracts one sensor at a time to
bound memory; writes the prepared features CSV and manifests under the ignored
``data/processed/hydraulic`` directory.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.benchmarks.hydraulic import load_config, prepare  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="configs/benchmarks/hydraulic_systems.yaml",
        help="path to the benchmark YAML config (relative to the project root)",
    )
    args = parser.parse_args()

    config = load_config(ROOT / args.config, root=ROOT)
    manifest = prepare(config)
    print("Prepared cycles:", manifest["prepared"]["n_cycles"])
    print("Features:", manifest["prepared"]["output"])


if __name__ == "__main__":
    main()
