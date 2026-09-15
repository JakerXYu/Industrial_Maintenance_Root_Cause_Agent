"""Track B core: condition monitoring of hydraulic systems (UCI #447).

This module implements the deterministic, external-benchmark pipeline for the
hydraulic systems dataset. It is self-contained and does not import any Track A
module (``src.agent``, ``src.evaluation``, ``src.contracts``, ``src.db``).

Pipeline
--------
1. ``load_config``    — strict YAML parsing + Pydantic validation.
2. ``download_and_extract`` — std-lib download, SHA-256 hard fail, atomic replace,
   zip-slip-safe extraction, idempotent required-file validation.
3. ``prepare``        — validate profile/sensor shapes, code sets, cycle alignment,
   stable counts; extract one sensor at a time; write features CSV + manifests.
4. ``run``            — train fixed sklearn pipelines, select preferred family on
   validation macro-F1, report untouched test results for both families, serialize
   models/metrics/predictions, and emit the external evaluation report.

Verified dataset facts (UCI #447, flat 20-file zip):
- 2205 cycles; profile.txt is 2205 x 5 with columns
  ``cooler, valve, pump, accumulator, stable``.
- Stable flag code 0 means "conditions were stable" (1449 of 2205 cycles).
- Sensors: PS1-6 + EPS1 at 100 Hz / 6000 samples, FS1-2 at 10 Hz / 600 samples,
  TS1-4 + VS1 (+ CE/CP/SE, excluded) at 1 Hz / 60 samples.
- Primary benchmark targets cooler (3 classes) and valve (4 classes) over the
  stable cycles only, using the 14 physical sensors, 4 summary statistics each
  (mean, std ddof=0, min, max) => 56 features.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

# --------------------------------------------------------------------------
# Verified dataset facts
# --------------------------------------------------------------------------

# Official code sets for every profile column (from description.txt /
# documentation.txt shipped with the dataset).
PROFILE_CODE_SETS: Dict[str, set] = {
    "cooler": {3, 20, 100},
    "valve": {100, 90, 80, 73},
    "pump": {0, 1, 2},
    "accumulator": {130, 115, 100, 90},
    "stable": {0, 1},
}

FEATURE_FUNCTIONS = ("mean", "std", "min", "max")
N_PHYSICAL_SENSORS = 14
N_FEATURES = 56
GROUP_BOOTSTRAP_SAMPLES = 1000


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------
# Strict YAML config
# --------------------------------------------------------------------------

class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader variant that rejects duplicate mapping keys."""


def _construct_mapping(loader: yaml.SafeLoader, node: yaml.nodes.MappingNode, deep: bool = False) -> dict:
    mapping: Dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"duplicate key {key!r} in YAML config")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


class ProfileSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file: str
    columns: List[str]
    n_rows: int
    n_cols: int
    stable_code: int

    @model_validator(mode="after")
    def _check_profile(self) -> "ProfileSpec":
        if self.n_cols != len(self.columns):
            raise ValueError("profile.n_cols must equal len(profile.columns)")
        if self.n_cols != 5:
            raise ValueError("profile must describe exactly 5 columns")
        if self.columns != ["cooler", "valve", "pump", "accumulator", "stable"]:
            raise ValueError(
                "profile columns must be cooler, valve, pump, accumulator, stable"
            )
        if self.stable_code != 0:
            raise ValueError("profile.stable_code must be 0 (stable cycles)")
        return self


class SensorSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    file: str
    sample_rate_hz: int
    samples_per_cycle: int


class TargetSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    column: str
    labels: Dict[int, str]

    @model_validator(mode="after")
    def _check_labels(self) -> "TargetSpec":
        if not self.labels:
            raise ValueError("target labels must not be empty")
        if any(not isinstance(k, int) for k in self.labels):
            raise ValueError("target label keys must be integer condition codes")
        if any(not isinstance(v, str) or not v for v in self.labels.values()):
            raise ValueError("target label values must be non-empty strings")
        return self


class FeatureSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    functions: List[str]
    std_ddof: int = 0
    expected_count: int

    @model_validator(mode="after")
    def _check_functions(self) -> "FeatureSpec":
        if self.functions != list(FEATURE_FUNCTIONS):
            raise ValueError("features.functions must be mean, std, min, max")
        if self.std_ddof != 0:
            raise ValueError("features.std_ddof must be 0 (population std)")
        return self


class SplitSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ratios: Dict[str, float]
    seed: int = 0
    group_columns: List[str]
    max_attempts: int = 1000

    @model_validator(mode="after")
    def _check_split(self) -> "SplitSpec":
        if set(self.ratios) != {"train", "val", "test"}:
            raise ValueError("split.ratios must contain exactly train, val, test")
        total = sum(self.ratios.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError("split.ratios must sum to 1.0")
        if any(v <= 0 for v in self.ratios.values()):
            raise ValueError("split.ratios must be positive")
        if self.group_columns != ["cooler", "valve", "pump", "accumulator"]:
            raise ValueError(
                "split.group_columns must be cooler, valve, pump, accumulator"
            )
        if self.max_attempts < 1:
            raise ValueError("split.max_attempts must be >= 1")
        return self


class LogisticSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    imputer_strategy: str = "median"
    scaler: str = "standard"
    max_iter: int = 2000
    class_weight: str = "balanced"


class RandomForestSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    imputer_strategy: str = "median"
    n_estimators: int = 300
    class_weight: str = "balanced_subsample"


class ModelsSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seed: int = 0
    logistic: LogisticSpec
    random_forest: RandomForestSpec


class ReportSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str


class DatasetSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    url: str
    sha256: str
    zip_name: str
    zip_member_count: int
    cycle_count: int
    stable_cycle_count: int
    raw_dir: Path
    processed_dir: Path
    artifacts_dir: Path
    profile: ProfileSpec

    @model_validator(mode="after")
    def _check_dataset(self) -> "DatasetSpec":
        if len(self.sha256) != 64:
            raise ValueError("dataset.sha256 must be a 64-char hex digest")
        if self.zip_member_count < 1:
            raise ValueError("dataset.zip_member_count must be >= 1")
        if self.cycle_count < 1:
            raise ValueError("dataset.cycle_count must be >= 1")
        if self.stable_cycle_count < 0:
            raise ValueError("dataset.stable_cycle_count must be >= 0")
        return self


class HydraulicConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_config_sha256: str = Field(default="", exclude=True)
    dataset: DatasetSpec
    sensors: List[SensorSpec]
    features: FeatureSpec
    targets: Dict[str, TargetSpec]
    split: SplitSpec
    models: ModelsSpec
    report: ReportSpec

    @model_validator(mode="after")
    def _check_config(self) -> "HydraulicConfig":
        if not self.sensors:
            raise ValueError("at least one sensor must be configured")
        names = [s.name for s in self.sensors]
        if len(set(names)) != len(names):
            raise ValueError("sensor names must be unique")
        files = [s.file for s in self.sensors]
        if len(set(files)) != len(files):
            raise ValueError("sensor file names must be unique")

        n_features = len(self.sensors) * len(self.features.functions)
        if n_features != self.features.expected_count:
            raise ValueError(
                "features.expected_count must equal len(sensors) * len(functions)"
            )

        if set(self.targets) != {"cooler", "valve"}:
            raise ValueError("targets must contain exactly cooler and valve")
        profile_cols = set(self.dataset.profile.columns)
        for name, target in self.targets.items():
            if target.column not in profile_cols:
                raise ValueError(f"target {name!r} column {target.column!r} not in profile")
            if set(target.labels.keys()) != PROFILE_CODE_SETS[target.column]:
                raise ValueError(
                    f"target {name!r} labels must match official codes "
                    f"{sorted(PROFILE_CODE_SETS[target.column])}"
                )
        for col in self.split.group_columns:
            if col not in profile_cols:
                raise ValueError(f"split group column {col!r} not in profile")
        return self


def load_config(config_path: os.PathLike, root: Optional[os.PathLike] = None) -> HydraulicConfig:
    """Load and strictly validate a benchmark YAML config.

    Relative paths inside the config are resolved against ``root`` (defaults to
    the project root, i.e. two levels above this module).
    """
    config_path = Path(config_path)
    if root is None:
        root = Path(__file__).resolve().parents[2]
    root = Path(root)

    text = config_path.read_text(encoding="utf-8")
    data = yaml.load(text, Loader=_UniqueKeyLoader)
    if data is None:
        raise ValueError(f"config is empty: {config_path}")
    if not isinstance(data, dict):
        raise ValueError(f"config must be a mapping, got {type(data).__name__}")

    canonical_config = json.dumps(data, sort_keys=True, separators=(",", ":"))
    cfg = HydraulicConfig.model_validate(
        {
            **data,
            "source_config_sha256": hashlib.sha256(
                canonical_config.encode("utf-8")
            ).hexdigest(),
        }
    )

    for attr in ("raw_dir", "processed_dir", "artifacts_dir"):
        value = getattr(cfg.dataset, attr)
        if not value.is_absolute():
            setattr(cfg.dataset, attr, (root / value).resolve())
    if not Path(cfg.report.path).is_absolute():
        cfg.report.path = str((root / cfg.report.path).resolve())
    return cfg


# --------------------------------------------------------------------------
# Download / extract
# --------------------------------------------------------------------------

def sha256_file(path: os.PathLike) -> str:
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def required_file_names(cfg: HydraulicConfig) -> List[str]:
    return [cfg.dataset.profile.file] + [s.file for s in cfg.sensors]


def required_files_present(cfg: HydraulicConfig) -> bool:
    raw = cfg.dataset.raw_dir
    return all((raw / name).exists() for name in required_file_names(cfg))


def _download(url: str, expected_sha256: str, dest_path: Path) -> None:
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest_path.with_name(dest_path.name + ".part")
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            with tmp.open("wb") as out:
                shutil.copyfileobj(response, out, length=1024 * 1024)
        actual = sha256_file(tmp)
        if actual.lower() != expected_sha256.lower():
            tmp.unlink(missing_ok=True)
            raise RuntimeError(
                f"SHA256 mismatch for {url}: expected {expected_sha256}, got {actual}"
            )
        os.replace(tmp, dest_path)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def _safe_extract(zip_path: Path, dest_dir: Path) -> List[str]:
    """Extract a zip without path traversal (zip-slip safe)."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_root = dest_dir.resolve()
    extracted: List[str] = []
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            member_path = Path(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise RuntimeError(f"unsafe zip member path: {member.filename!r}")
            target = (dest_dir / member.filename).resolve()
            try:
                target.relative_to(dest_root)
            except ValueError:
                raise RuntimeError(f"unsafe zip member path: {member.filename!r}") from None
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            extracted.append(member.filename)
    return extracted


def _validate_required_files(cfg: HydraulicConfig) -> None:
    raw = cfg.dataset.raw_dir
    missing = [n for n in required_file_names(cfg) if not (raw / n).exists()]
    if missing:
        raise RuntimeError(f"missing required files after extraction: {missing}")


def download_and_extract(cfg: HydraulicConfig) -> Dict[str, Any]:
    """Download (idempotently) and extract the raw dataset.

    Returns a small status manifest. Hard-fails on SHA-256 mismatch, on an
    unexpected zip member count, or when any required file is still missing.
    """
    raw = cfg.dataset.raw_dir
    raw.mkdir(parents=True, exist_ok=True)
    zip_path = raw / cfg.dataset.zip_name

    zip_ok = zip_path.exists() and (
        sha256_file(zip_path).lower() == cfg.dataset.sha256.lower()
    )
    files_ok = required_files_present(cfg)

    if zip_ok and files_ok:
        return {"status": "already-present", "zip": str(zip_path)}

    if not zip_ok:
        _download(cfg.dataset.url, cfg.dataset.sha256, zip_path)

    if not files_ok:
        members = _safe_extract(zip_path, raw)
    else:
        with zipfile.ZipFile(zip_path) as archive:
            members = [m.filename for m in archive.infolist() if not m.is_dir()]

    if len(members) != cfg.dataset.zip_member_count:
        raise RuntimeError(
            f"expected {cfg.dataset.zip_member_count} zip members, got {len(members)}"
        )

    _validate_required_files(cfg)
    return {"status": "ready", "zip": str(zip_path), "members": len(members)}


# --------------------------------------------------------------------------
# Prepare
# --------------------------------------------------------------------------

def _read_profile(cfg: HydraulicConfig) -> pd.DataFrame:
    spec = cfg.dataset.profile
    path = cfg.dataset.raw_dir / spec.file
    if not path.exists():
        raise FileNotFoundError(f"profile file not found: {path}")
    frame = pd.read_csv(path, sep="\t", header=None)
    if frame.shape != (spec.n_rows, spec.n_cols):
        raise ValueError(
            f"profile shape is {frame.shape}, expected {(spec.n_rows, spec.n_cols)}"
        )
    frame.columns = spec.columns
    return frame


def _validate_profile_codes(frame: pd.DataFrame, cfg: HydraulicConfig) -> Dict[str, Dict[int, int]]:
    stats: Dict[str, Dict[int, int]] = {}
    for col in frame.columns:
        expected = PROFILE_CODE_SETS[col]
        unique = set(int(v) for v in frame[col].dropna().unique())
        unexpected = unique - expected
        if unexpected:
            raise ValueError(
                f"profile column {col!r} has unexpected codes {sorted(unexpected)}"
            )
        counts = frame[col].value_counts()
        stats[col] = {int(code): int(counts.get(code, 0)) for code in sorted(expected)}
    for name, target in cfg.targets.items():
        if set(target.labels.keys()) != PROFILE_CODE_SETS[target.column]:
            raise ValueError(
                f"target {name!r} labels mismatch official codes for {target.column!r}"
            )
    return stats


def read_sensor_matrix(path: os.PathLike, n_rows: int, n_cols: int) -> np.ndarray:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"sensor file not found: {path}")
    matrix = pd.read_csv(path, sep="\t", header=None).to_numpy(dtype=np.float64)
    if matrix.shape != (n_rows, n_cols):
        raise ValueError(
            f"{path.name}: expected shape {(n_rows, n_cols)}, got {matrix.shape}"
        )
    return matrix


def compute_features(matrix: np.ndarray, functions: List[str], std_ddof: int = 0) -> np.ndarray:
    blocks: List[np.ndarray] = []
    for fn in functions:
        if fn == "mean":
            blocks.append(matrix.mean(axis=1))
        elif fn == "std":
            blocks.append(matrix.std(axis=1, ddof=std_ddof))
        elif fn == "min":
            blocks.append(matrix.min(axis=1))
        elif fn == "max":
            blocks.append(matrix.max(axis=1))
        else:
            raise ValueError(f"unsupported feature function: {fn!r}")
    return np.column_stack(blocks)


def feature_names(sensors: List[SensorSpec], functions: List[str]) -> List[str]:
    return [f"{s.name}__{fn}" for s in sensors for fn in functions]


def _key_col(key: Tuple[Any, ...], group_cols: List[str], col: str) -> Any:
    return key[group_cols.index(col)]


def _greedy_group_split(
    ordered: List[Tuple[Tuple[Any, ...], List[int]]],
    val_target: int,
    test_target: int,
    cooler_classes: List[int],
    valve_classes: List[int],
    group_cols: List[str],
) -> Tuple[List, List, List]:
    """Greedily assign groups to val/test (train takes the remainder).

    Every split must cover all cooler and valve classes. Returns
    ``(val, test, train)`` lists of ``(key, cycles)``.
    """
    val: List[Tuple[Tuple[Any, ...], List[int]]] = []
    test: List[Tuple[Tuple[Any, ...], List[int]]] = []
    val_keys = set()
    test_keys = set()

    def _size(split) -> int:
        return sum(len(cycles) for _, cycles in split)

    def _pick(split, split_keys, excluded, target):
        size = _size(split)
        for col, classes in (("cooler", cooler_classes), ("valve", valve_classes)):
            for cls in classes:
                if any(_key_col(k, group_cols, col) == cls for k, _ in split):
                    continue
                for key, cycles in ordered:
                    if key in split_keys or key in excluded:
                        continue
                    if _key_col(key, group_cols, col) == cls:
                        split.append((key, cycles))
                        split_keys.add(key)
                        size += len(cycles)
                        break
        for key, cycles in ordered:
            if size >= target:
                break
            if key in split_keys or key in excluded:
                continue
            split.append((key, cycles))
            split_keys.add(key)
            size += len(cycles)
        return size

    _pick(val, val_keys, set(), val_target)
    _pick(test, test_keys, val_keys, test_target)
    train = [(key, cycles) for key, cycles in ordered if key not in val_keys and key not in test_keys]
    return val, test, train


def _split_covers(split, cooler_classes, valve_classes, group_cols) -> bool:
    coolers = {_key_col(k, group_cols, "cooler") for k, _ in split}
    valves = {_key_col(k, group_cols, "valve") for k, _ in split}
    return set(cooler_classes) <= coolers and set(valve_classes) <= valves


def split_groups(df: pd.DataFrame, cfg: HydraulicConfig) -> Dict[str, Any]:
    """Deterministically split complete-profile groups into train/val/test.

    Groups are the full ``(cooler, valve, pump, accumulator)`` tuples. No group
    or cycle is ever split across sets. Search is deterministic (seeded); if no
    valid split covering every target class in every set is found it raises
    explicitly — never falling back to a random cycle-level split.
    """
    group_cols = cfg.split.group_columns
    keys = list(zip(*(df[col].to_numpy() for col in group_cols)))
    groups: Dict[Tuple[Any, ...], List[int]] = {}
    for idx, key in enumerate(keys):
        key = tuple(int(v) for v in key)  # normalize numpy ints to Python ints
        groups.setdefault(key, []).append(int(df["cycle"].iloc[idx]))

    ordered = sorted(groups.items(), key=lambda kv: kv[0])

    total = len(df)
    ratios = cfg.split.ratios
    val_target = round(total * ratios["val"])
    test_target = round(total * ratios["test"])

    cooler_classes = sorted(cfg.targets["cooler"].labels.keys())
    valve_classes = sorted(cfg.targets["valve"].labels.keys())

    val = test = train = None
    for attempt in range(cfg.split.max_attempts):
        rng = random.Random(cfg.split.seed + attempt)
        shuffled = ordered[:]
        rng.shuffle(shuffled)
        val, test, train = _greedy_group_split(
            shuffled, val_target, test_target, cooler_classes, valve_classes, group_cols
        )
        if (
            _split_covers(val, cooler_classes, valve_classes, group_cols)
            and _split_covers(test, cooler_classes, valve_classes, group_cols)
            and _split_covers(train, cooler_classes, valve_classes, group_cols)
        ):
            break
    else:
        raise RuntimeError(
            "could not produce a valid group split (60/20/20 with all target "
            "classes represented in every set); no random-cycle fallback is allowed"
        )

    cycle_to_split: Dict[int, str] = {}
    split_cycle_counts: Dict[str, int] = {"train": 0, "val": 0, "test": 0}
    split_group_counts: Dict[str, int] = {"train": 0, "val": 0, "test": 0}
    assignments: List[Dict[str, Any]] = []

    for split_name, split in (("val", val), ("test", test), ("train", train)):
        for key, cycles in split:
            split_group_counts[split_name] += 1
            for cycle in cycles:
                cycle_to_split[cycle] = split_name
                split_cycle_counts[split_name] += 1
                assignments.append(
                    {"cycle": cycle, "group": list(key), "split": split_name}
                )

    # Integrity: every cycle assigned exactly once, no overlap.
    if set(cycle_to_split) != set(int(c) for c in df["cycle"]):
        raise RuntimeError("split does not cover every cycle exactly once")
    if sum(split_cycle_counts.values()) != total:
        raise RuntimeError("split cycle counts do not sum to the total")

    def _coverage(split):
        coolers = sorted({int(_key_col(k, group_cols, "cooler")) for k, _ in split})
        valves = sorted({int(_key_col(k, group_cols, "valve")) for k, _ in split})
        return {"cooler": coolers, "valve": valves}

    assignments.sort(key=lambda a: a["cycle"])
    return {
        "seed": cfg.split.seed,
        "ratios": ratios,
        "total_cycles": total,
        "group_columns": group_cols,
        "n_groups": len(ordered),
        "attempts": attempt + 1,
        "split_cycle_counts": split_cycle_counts,
        "split_group_counts": split_group_counts,
        "class_coverage": {
            "train": _coverage(train),
            "val": _coverage(val),
            "test": _coverage(test),
        },
        "cycle_to_split": cycle_to_split,
        "assignments": assignments,
    }


def prepare(cfg: HydraulicConfig) -> Dict[str, Any]:
    """Validate raw data and produce the prepared features CSV + manifests."""
    processed = cfg.dataset.processed_dir
    processed.mkdir(parents=True, exist_ok=True)

    profile = _read_profile(cfg)
    code_stats = _validate_profile_codes(profile, cfg)

    stable_code = cfg.dataset.profile.stable_code
    stable_mask = (profile["stable"] == stable_code).to_numpy()
    stable_count = int(stable_mask.sum())
    if stable_count != cfg.dataset.stable_cycle_count:
        raise ValueError(
            f"expected {cfg.dataset.stable_cycle_count} stable cycles, got {stable_count}"
        )

    n_rows = cfg.dataset.cycle_count
    sensors_report: List[Dict[str, Any]] = []
    feature_blocks: List[np.ndarray] = []
    for sensor in cfg.sensors:
        path = cfg.dataset.raw_dir / sensor.file
        matrix = read_sensor_matrix(path, n_rows, sensor.samples_per_cycle)
        features = compute_features(
            matrix[stable_mask], cfg.features.functions, cfg.features.std_ddof
        )
        feature_blocks.append(features)
        sensors_report.append(
            {
                "name": sensor.name,
                "file": sensor.file,
                "sample_rate_hz": sensor.sample_rate_hz,
                "samples_per_cycle": sensor.samples_per_cycle,
                "shape": list(matrix.shape),
                "ok": True,
            }
        )
        del matrix, features

    x_matrix = np.column_stack(feature_blocks)
    fnames = feature_names(cfg.sensors, cfg.features.functions)
    if x_matrix.shape != (stable_count, len(fnames)):
        raise ValueError(
            f"feature matrix shape {x_matrix.shape} != {(stable_count, len(fnames))}"
        )

    stable_profile = profile[stable_mask].reset_index(drop=True)
    # UCI documents row numbers as cycle numbers, so public provenance is 1-based.
    cycle_ids = np.flatnonzero(stable_mask) + 1

    frame = pd.DataFrame(x_matrix, columns=fnames)
    frame.insert(0, "cycle", cycle_ids)
    for col in cfg.dataset.profile.columns:
        frame[col] = stable_profile[col].to_numpy()
    for name, target in cfg.targets.items():
        frame[f"{name}_label"] = frame[target.column].map(target.labels)

    split_result = split_groups(frame, cfg)
    frame["split"] = frame["cycle"].map(split_result["cycle_to_split"])

    features_path = processed / "features.csv"
    frame.to_csv(features_path, index=False)

    prepare_manifest = {
        "generated_at": utcnow_iso(),
        "dataset": {
            "name": cfg.dataset.name,
            "url": cfg.dataset.url,
            "sha256": cfg.dataset.sha256,
            "zip_member_count": cfg.dataset.zip_member_count,
            "cycle_count": cfg.dataset.cycle_count,
            "stable_cycle_count": cfg.dataset.stable_cycle_count,
        },
        "profile": {
            "shape": [cfg.dataset.profile.n_rows, cfg.dataset.profile.n_cols],
            "columns": cfg.dataset.profile.columns,
            "code_counts": code_stats,
        },
        "sensors": sensors_report,
        "features": {
            "functions": cfg.features.functions,
            "std_ddof": cfg.features.std_ddof,
            "n_features": len(fnames),
            "feature_names": fnames,
        },
        "targets": {
            name: {"column": t.column, "labels": t.labels}
            for name, t in cfg.targets.items()
        },
        "prepared": {
            "stable_only": True,
            "n_cycles": int(stable_count),
            "output": str(features_path),
        },
    }
    (processed / "prepare_manifest.json").write_text(
        json.dumps(prepare_manifest, indent=2), encoding="utf-8"
    )
    (processed / "split_manifest.json").write_text(
        json.dumps(split_result, indent=2), encoding="utf-8"
    )
    return prepare_manifest


# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------

def make_logistic_pipeline(
    seed: int, spec: Optional[LogisticSpec] = None
) -> Pipeline:
    spec = spec or LogisticSpec()
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy=spec.imputer_strategy)),
            ("scaler", StandardScaler()),
            (
                "clf",
                LogisticRegression(
                    max_iter=spec.max_iter,
                    class_weight=spec.class_weight,
                    random_state=seed,
                ),
            ),
        ]
    )


def make_random_forest_pipeline(
    seed: int, spec: Optional[RandomForestSpec] = None
) -> Pipeline:
    spec = spec or RandomForestSpec()
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy=spec.imputer_strategy)),
            (
                "clf",
                RandomForestClassifier(
                    n_estimators=spec.n_estimators,
                    class_weight=spec.class_weight,
                    random_state=seed,
                ),
            ),
        ]
    )


FAMILY_BUILDERS = ("logistic", "random_forest")


def _encode(y_codes: np.ndarray, classes: List[int]) -> np.ndarray:
    index = {code: i for i, code in enumerate(classes)}
    return np.asarray([index[code] for code in y_codes], dtype=np.int64)


def compute_test_metrics(
    y_true_codes: np.ndarray,
    y_pred_codes: np.ndarray,
    classes: List[int],
    labels: Dict[int, str],
) -> Dict[str, Any]:
    y_true = _encode(np.asarray(y_true_codes), classes)
    y_pred = _encode(np.asarray(y_pred_codes), classes)
    class_indices = list(range(len(classes)))
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=class_indices, zero_division=0
    )
    per_class = {}
    for i, code in enumerate(classes):
        per_class[labels[code]] = {
            "code": int(code),
            "precision": float(precision[i]),
            "recall": float(recall[i]),
            "f1": float(f1[i]),
            "support": int(support[i]),
        }
    matrix = confusion_matrix(y_true, y_pred, labels=class_indices)
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "macro_f1": float(
            f1_score(y_true, y_pred, average="macro", zero_division=0)
        ),
        "weighted_f1": float(
            f1_score(y_true, y_pred, average="weighted", zero_division=0)
        ),
        "per_class": per_class,
        "confusion_matrix": matrix.tolist(),
    }


def grouped_bootstrap_macro_f1(
    y_true_codes: np.ndarray,
    y_pred_codes: np.ndarray,
    group_ids: np.ndarray,
    classes: List[int],
    seed: int,
    n_samples: int = GROUP_BOOTSTRAP_SAMPLES,
) -> List[float]:
    """Return a group-clustered 95% bootstrap interval for macro-F1."""
    unique_groups = np.unique(group_ids)
    if len(unique_groups) < 2:
        raise ValueError("group bootstrap requires at least two test groups")
    rng = np.random.RandomState(seed)
    class_indices = list(range(len(classes)))
    scores = []
    for _ in range(n_samples):
        sampled_groups = rng.choice(unique_groups, size=len(unique_groups), replace=True)
        sampled_indices = np.concatenate(
            [np.flatnonzero(group_ids == group) for group in sampled_groups]
        )
        scores.append(
            f1_score(
                _encode(y_true_codes[sampled_indices], classes),
                _encode(y_pred_codes[sampled_indices], classes),
                labels=class_indices,
                average="macro",
                zero_division=0,
            )
        )
    return [float(value) for value in np.quantile(scores, [0.025, 0.975])]


# --------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------

def _load_prepared(cfg: HydraulicConfig) -> Tuple[pd.DataFrame, List[str]]:
    features_path = cfg.dataset.processed_dir / "features.csv"
    if not features_path.exists():
        raise FileNotFoundError(
            f"prepared features not found: {features_path} (run prepare first)"
        )
    frame = pd.read_csv(features_path)
    fnames = feature_names(cfg.sensors, cfg.features.functions)
    missing = [name for name in fnames if name not in frame.columns]
    if missing:
        raise ValueError(f"prepared features missing columns: {missing}")
    required = {"cycle", "split"} | set(cfg.dataset.profile.columns)
    missing_meta = [name for name in required if name not in frame.columns]
    if missing_meta:
        raise ValueError(f"prepared features missing meta columns: {missing_meta}")
    return frame, fnames


def run(cfg: HydraulicConfig) -> Dict[str, Any]:
    """Train both model families per target, select preferred on val macro-F1,
    report untouched test results, and serialize all artifacts + the report."""
    artifacts = cfg.dataset.artifacts_dir
    artifacts.mkdir(parents=True, exist_ok=True)
    models_dir = artifacts / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    frame, fnames = _load_prepared(cfg)
    x_all = frame[fnames].to_numpy()
    seed = cfg.models.seed

    split_masks = {
        name: (frame["split"] == name).to_numpy() for name in ("train", "val", "test")
    }

    results: Dict[str, Any] = {}
    prediction_rows: List[Dict[str, Any]] = []
    preferred: Dict[str, str] = {}

    for target_name, target in cfg.targets.items():
        classes = sorted(target.labels.keys())
        y_codes = frame[target.column].to_numpy()
        target_result: Dict[str, Any] = {
            "classes": [{"code": c, "label": target.labels[c]} for c in classes],
            "families": {},
            "preferred_family": None,
            "selection_note": None,
        }
        best_family = None
        best_val_f1 = -1.0

        x_train = x_all[split_masks["train"]]
        y_train = y_codes[split_masks["train"]]
        x_val = x_all[split_masks["val"]]
        y_val = y_codes[split_masks["val"]]
        x_test = x_all[split_masks["test"]]
        y_test = y_codes[split_masks["test"]]
        test_frame = frame.loc[split_masks["test"]]
        test_group_ids = (
            test_frame[cfg.split.group_columns]
            .astype(str)
            .agg("|".join, axis=1)
            .to_numpy()
        )

        majority_code = int(pd.Series(y_train).value_counts().idxmax())
        majority_predictions = np.full(len(y_test), majority_code, dtype=np.int64)
        majority_metrics = compute_test_metrics(
            y_test, majority_predictions, classes, target.labels
        )
        majority_metrics["macro_f1_group_bootstrap_95_ci"] = grouped_bootstrap_macro_f1(
            y_test,
            majority_predictions,
            test_group_ids,
            classes,
            seed + 10_000,
        )
        target_result["majority_baseline"] = {
            "train_majority_code": majority_code,
            "test": majority_metrics,
        }

        for family_name in FAMILY_BUILDERS:
            pipeline = (
                make_logistic_pipeline(seed, cfg.models.logistic)
                if family_name == "logistic"
                else make_random_forest_pipeline(seed, cfg.models.random_forest)
            )
            pipeline.fit(x_train, _encode(y_train, classes))

            val_pred_encoded = pipeline.predict(x_val)
            val_f1 = float(
                f1_score(
                    _encode(y_val, classes),
                    val_pred_encoded,
                    average="macro",
                    zero_division=0,
                )
            )

            test_pred_encoded = pipeline.predict(x_test)
            test_pred_codes = np.asarray(classes, dtype=np.int64)[test_pred_encoded]
            test_scores = pipeline.predict_proba(x_test)
            test_metrics = compute_test_metrics(y_test, test_pred_codes, classes, target.labels)
            test_metrics["macro_f1_group_bootstrap_95_ci"] = grouped_bootstrap_macro_f1(
                y_test,
                test_pred_codes,
                test_group_ids,
                classes,
                seed + (0 if family_name == "logistic" else 1),
            )

            model_file = f"{target_name}_{family_name}.joblib"
            model_path = models_dir / model_file
            joblib.dump(pipeline, model_path)
            model_sha256 = sha256_file(model_path)
            model_version = f"uci447-{target_name}-{family_name}-v1"

            classifier = pipeline.named_steps["clf"]
            if family_name == "logistic":
                feature_importance = np.mean(np.abs(classifier.coef_), axis=0)
            else:
                feature_importance = classifier.feature_importances_
            top_feature_indices = np.argsort(feature_importance)[::-1][:5]

            target_result["families"][family_name] = {
                "val_macro_f1": val_f1,
                "test": test_metrics,
                "model_file": model_file,
                "model_sha256": model_sha256,
                "model_version": model_version,
            }

            test_cycles = frame["cycle"][split_masks["test"]].to_numpy()
            for i in range(len(test_cycles)):
                prediction_rows.append(
                    {
                        "cycle": int(test_cycles[i]),
                        "split": "test",
                        "target": target_name,
                        "family": family_name,
                        "true_code": int(y_test[i]),
                        "true_label": target.labels[int(y_test[i])],
                        "pred_code": int(test_pred_codes[i]),
                        "pred_label": target.labels[int(test_pred_codes[i])],
                        "model_score": float(test_scores[i, int(test_pred_encoded[i])]),
                        "model_version": model_version,
                        "model_sha256": model_sha256,
                        "global_top_feature_values": json.dumps(
                            {
                                fnames[j]: float(x_test[i, j])
                                for j in top_feature_indices
                            },
                            sort_keys=True,
                        ),
                        "feature_value_selection_method": "model_global_importance_with_cycle_value_no_local_attribution",
                    }
                )

            if val_f1 > best_val_f1:
                best_val_f1 = val_f1
                best_family = family_name

        target_result["preferred_family"] = best_family
        tied_families = [
            name
            for name, family in target_result["families"].items()
            if abs(family["val_macro_f1"] - best_val_f1) < 1e-12
        ]
        target_result["selection_note"] = (
            f"validation tie resolved by configured family order: {', '.join(tied_families)}"
            if len(tied_families) > 1
            else "highest validation macro-F1"
        )
        preferred[target_name] = best_family
        results[target_name] = target_result

    predictions = pd.DataFrame(prediction_rows)
    predictions.to_csv(artifacts / "test_predictions.csv", index=False)

    split_manifest_path = cfg.dataset.processed_dir / "split_manifest.json"
    split_manifest = json.loads(split_manifest_path.read_text(encoding="utf-8"))
    run_manifest = {
        "generated_at": utcnow_iso(),
        "config_sha256": cfg.source_config_sha256,
        "dataset": {
            "name": cfg.dataset.name,
            "url": cfg.dataset.url,
            "sha256": cfg.dataset.sha256,
        },
        "prepared_features": str(cfg.dataset.processed_dir / "features.csv"),
        "prepared_features_sha256": sha256_file(cfg.dataset.processed_dir / "features.csv"),
        "split_manifest_sha256": sha256_file(cfg.dataset.processed_dir / "split_manifest.json"),
        "split": {
            name: int(int(split_masks[name].sum())) for name in ("train", "val", "test")
        },
        "split_groups": split_manifest["split_group_counts"],
        "seed": seed,
        "targets": list(cfg.targets),
        "families": list(FAMILY_BUILDERS),
        "preferred_family": preferred,
    }
    (artifacts / "metrics.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    (artifacts / "run_manifest.json").write_text(
        json.dumps(run_manifest, indent=2), encoding="utf-8"
    )

    report_path = Path(cfg.report.path)
    report_text = generate_report(cfg, results, run_manifest)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text, encoding="utf-8")

    return {
        "results": results,
        "run_manifest": run_manifest,
        "artifacts_dir": str(artifacts),
        "report": str(report_path),
    }


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def _round(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def _confusion_table(classes: List[Dict[str, Any]], matrix: List[List[int]]) -> str:
    header = ["true\\pred"] + [f"{c['label']} ({c['code']})" for c in classes]
    rows = [header, ["---"] * len(header)]
    for i, cls in enumerate(classes):
        rows.append([f"{cls['label']} ({cls['code']})"] + [str(v) for v in matrix[i]])
    return "\n".join("| " + " | ".join(r) + " |" for r in rows)


def _per_class_table(per_class: Dict[str, Dict[str, Any]]) -> str:
    header = ["class", "code", "precision", "recall", "f1", "support"]
    rows = [header, ["---"] * len(header)]
    for label, stats in per_class.items():
        rows.append(
            [
                label,
                str(stats["code"]),
                f"{_round(stats['precision'])}",
                f"{_round(stats['recall'])}",
                f"{_round(stats['f1'])}",
                str(stats["support"]),
            ]
        )
    return "\n".join("| " + " | ".join(r) + " |" for r in rows)


def generate_report(
    cfg: HydraulicConfig, results: Dict[str, Any], run_manifest: Dict[str, Any]
) -> str:
    lines: List[str] = []
    add = lines.append

    add("# External Evaluation Report — Hydraulic Systems (UCI #447)")
    add("")
    add(
        "Track B external benchmark. This report documents an independent, "
        "deterministic evaluation of the hydraulic-systems condition-monitoring "
        "dataset. It is generated by `scripts/run_hydraulic_benchmark.py`."
    )
    add("")
    add("## Scope and disclaimers")
    add("")
    add("- **Not a root-cause-analysis (RCA) result.** This benchmark classifies")
    add("  component condition codes; it does not diagnose failure causes, recommend")
    add("  work orders, or propose maintenance actions.")
    add("- **No work-order or CMMS integration.** No work orders are generated, and")
    add("  nothing is written to any maintenance system.")
    add("- **Not field deployment.** Results are offline benchmark scores on a public")
    add("  dataset and must not be read as production or on-rig performance.")
    add("- **Narrow estimand.** Results measure complete-profile-group-held-out")
    add("  interpolation for stable cycles from one laboratory rig, not unseen assets,")
    add("  rigs, future time periods, transient operation, or operating domains.")
    add("- **Uncalibrated scores.** All metrics are computed from hard class")
    add("  predictions; model decision outputs are not calibrated probability")
    add("  estimates and must not be interpreted as such.")
    add("")
    add("## Dataset")
    add("")
    add(f"- Name: `{cfg.dataset.name}`")
    add(f"- Source: [{cfg.dataset.url}]({cfg.dataset.url})")
    add(f"- SHA-256: `{cfg.dataset.sha256}`")
    add(
        f"- Cycles: {cfg.dataset.cycle_count} total; "
        f"{cfg.dataset.stable_cycle_count} stable (primary benchmark subset)"
    )
    add("- Stable-only scope: 756 non-steady cycles are excluded because their official")
    add("  flag says static conditions might not have been reached; reported performance")
    add("  therefore does not cover start-up or transition behavior.")
    add(
        "- Sensors (primary benchmark): PS1-6, EPS1 (100 Hz / 6000 samples), "
        "FS1-2 (10 Hz / 600 samples), TS1-4, VS1 (1 Hz / 60 samples); "
        "CE/CP/SE excluded as derived target-proxy controls."
    )
    add("- Targets: cooler (3 classes) and valve (4 classes).")
    add("")
    add("## Methodology")
    add("")
    add("- **Features:** per-sensor mean, std (population, ddof=0), min, max over the")
    add("  stable cycle window → 14 sensors × 4 = 56 features.")
    add("- **Split:** complete-profile groups `(cooler, valve, pump, accumulator)` are")
    add("  partitioned into train/val/test with no group or cycle overlap, targeting")
    add("  ~60/20/20, with every target class represented in every set (deterministic;")
    add("  no random-cycle fallback).")
    add("  This is not a chronological split; temporal autocorrelation within the rig may")
    add("  remain, so the result is described as group-held-out interpolation.")
    add("- **Models:** fixed-hyperparameter sklearn pipelines.")
    add(
        f"  - Logistic: SimpleImputer(median) → StandardScaler → "
        f"LogisticRegression(max_iter={cfg.models.logistic.max_iter}, "
        f"class_weight={cfg.models.logistic.class_weight!r})."
    )
    add(
        f"  - Random forest: SimpleImputer(median) → "
        f"RandomForestClassifier(n_estimators={cfg.models.random_forest.n_estimators}, "
        f"class_weight={cfg.models.random_forest.class_weight!r})."
    )
    add(f"- **Selection:** preferred family per target = highest validation macro-F1;")
    add("  test results for **both** families are reported untouched.")
    add(f"- **Seed:** {cfg.models.seed} (models), {cfg.split.seed} (split).")
    add("")
    add("## Results")
    add("")

    for target_name in sorted(results):
        target_result = results[target_name]
        classes = target_result["classes"]
        add(f"### Target: `{target_name}`")
        add("")
        add(
            f"Preferred family: **{target_result['preferred_family']}** "
            f"({target_result['selection_note']})."
        )
        add("")
        add("| family | val macro-F1 | test accuracy | test balanced acc | test macro-F1 | group-bootstrap 95% CI | test weighted-F1 |")
        add("|---|---|---|---|---|---|---|")
        baseline = target_result["majority_baseline"]["test"]
        baseline_ci = baseline["macro_f1_group_bootstrap_95_ci"]
        add(
            f"| train-majority baseline | - | {_round(baseline['accuracy'])} "
            f"| {_round(baseline['balanced_accuracy'])} | {_round(baseline['macro_f1'])} "
            f"| [{_round(baseline_ci[0])}, {_round(baseline_ci[1])}] "
            f"| {_round(baseline['weighted_f1'])} |"
        )
        for family_name in FAMILY_BUILDERS:
            fam = target_result["families"][family_name]
            test = fam["test"]
            interval = test["macro_f1_group_bootstrap_95_ci"]
            add(
                f"| {family_name} | {_round(fam['val_macro_f1'])} "
                f"| {_round(test['accuracy'])} | {_round(test['balanced_accuracy'])} "
                f"| {_round(test['macro_f1'])} "
                f"| [{_round(interval[0])}, {_round(interval[1])}] "
                f"| {_round(test['weighted_f1'])} |"
            )
        add("")
        if all(
            abs(target_result["families"][name]["test"]["macro_f1"] - 1.0)
            < 1e-12
            for name in FAMILY_BUILDERS
        ):
            add(
                "Both fixed model configurations reached 1.0. This indicates separability "
                "under this representation/split, not stronger causal or field diagnostic "
                "evidence; no repeated-split or sensor-family ablation is claimed."
            )
            add("")

        for family_name in FAMILY_BUILDERS:
            fam = target_result["families"][family_name]
            test = fam["test"]
            add(f"#### `{target_name}` / `{family_name}` — test metrics")
            add("")
            add(_per_class_table(test["per_class"]))
            add("")
            add("Confusion matrix (rows = true, columns = predicted):")
            add("")
            add(_confusion_table(classes, test["confusion_matrix"]))
            add("")

    add("## Reproducibility")
    add("")
    add(f"- Config: `configs/benchmarks/hydraulic_systems.yaml`")
    add(f"- Config SHA-256: `{run_manifest['config_sha256']}`")
    add("- Prepared features: `data/processed/hydraulic/features.csv`")
    add(f"- Prepared features SHA-256: `{run_manifest['prepared_features_sha256']}`")
    add(f"- Split manifest SHA-256: `{run_manifest['split_manifest_sha256']}`")
    add(
        "- Split cycles (train / val / test): "
        f"{run_manifest['split']['train']} / {run_manifest['split']['val']} / "
        f"{run_manifest['split']['test']}"
    )
    add(
        "- Split groups (train / val / test): "
        f"{run_manifest['split_groups']['train']} / "
        f"{run_manifest['split_groups']['val']} / "
        f"{run_manifest['split_groups']['test']}"
    )
    add(f"- Generated: {run_manifest['generated_at']}")
    add("")
    add("## Citation")
    add("")
    add(
        "Helwig, N., Pignanelli, E., & Schütze, A. (2015). Condition monitoring "
        "of hydraulic systems [Dataset]. UCI Machine Learning Repository. "
        "https://doi.org/10.24432/C5CW21. Licensed CC BY 4.0."
    )
    add("")
    return "\n".join(lines)
