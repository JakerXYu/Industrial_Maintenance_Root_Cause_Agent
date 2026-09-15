"""Download and extract the hydraulic systems dataset (Track B).

Thin CLI over :mod:`src.benchmarks.hydraulic`. Downloads via std-lib urllib with
SHA-256 hard fail and atomic replace, then extracts zip-slip-safe and validates
the required files. Idempotent: re-running skips work that is already done.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.benchmarks.hydraulic import download_and_extract, load_config  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="configs/benchmarks/hydraulic_systems.yaml",
        help="path to the benchmark YAML config (relative to the project root)",
    )
    args = parser.parse_args()

    config = load_config(ROOT / args.config, root=ROOT)
    result = download_and_extract(config)
    print("Download status:", result["status"])
    print("Zip:", result.get("zip", "-"))
    print("Zip members:", result.get("members", "-"))


if __name__ == "__main__":
    main()
