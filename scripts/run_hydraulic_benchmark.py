"""Run the hydraulic systems benchmark (Track B).

Thin CLI over :mod:`src.benchmarks.hydraulic`. Trains fixed sklearn pipelines
for each target, selects the preferred family on validation macro-F1, reports
untouched test results for both families, serializes models/metrics/predictions,
and writes the external evaluation report.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.benchmarks.hydraulic import load_config, run  # noqa: E402
from src.evaluation.diagnostic_integration import (  # noqa: E402
    evaluate_hydraulic_prediction_evidence,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="configs/benchmarks/hydraulic_systems.yaml",
        help="path to the benchmark YAML config (relative to the project root)",
    )
    args = parser.parse_args()

    config = load_config(ROOT / args.config, root=ROOT)
    result = run(config)
    evidence_result = evaluate_hydraulic_prediction_evidence(
        Path(result["artifacts_dir"]) / "test_predictions.csv",
        Path(result["artifacts_dir"]) / "metrics.json",
        Path(result["artifacts_dir"]) / "run_manifest.json",
        Path(result["artifacts_dir"]) / "evidence_integration.json",
        Path(result["report"]),
        seed=config.split.seed,
    )
    for target_name, target_result in result["results"].items():
        preferred = target_result["preferred_family"]
        print(f"Target {target_name}: preferred family = {preferred}")
        for family_name, fam in target_result["families"].items():
            print(
                f"  {family_name}: val macro-F1 = {fam['val_macro_f1']:.4f}, "
                f"test macro-F1 = {fam['test']['macro_f1']:.4f}"
            )
    print("Artifacts:", result["artifacts_dir"])
    print("Report:", result["report"])
    print("Evidence integration scenarios:", evidence_result["scenario_count"])
    print("Evidence integration metrics:", evidence_result["metrics"])


if __name__ == "__main__":
    main()
