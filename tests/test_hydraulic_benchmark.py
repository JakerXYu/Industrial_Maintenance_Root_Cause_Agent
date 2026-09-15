"""Tests for the Track B hydraulic benchmark core.

All tests run against a tiny, official-shaped fixture (multi-rate sensors,
5-column profile, official condition codes) and a custom temp config. No test
downloads the full dataset.
"""

import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from pydantic import ValidationError

from src.benchmarks import hydraulic
from src.benchmarks.hydraulic import (
    HydraulicConfig,
    SensorSpec,
    _download,
    _safe_extract,
    compute_features,
    compute_test_metrics,
    download_and_extract,
    feature_names,
    load_config,
    make_logistic_pipeline,
    make_random_forest_pipeline,
    prepare,
    required_files_present,
    run,
    sha256_file,
    split_groups,
)

COOLER_CODES = [3, 20, 100]
VALVE_CODES = [100, 90, 80, 73]
PUMP_CODES = [0, 1, 2]
ACCUM_CODES = [130, 115, 100, 90]

COOLER_LABELS = {
    3: "close_to_total_failure",
    20: "reduced_efficiency",
    100: "full_efficiency",
}
VALVE_LABELS = {
    100: "optimal_switching_behavior",
    90: "small_lag",
    80: "severe_lag",
    73: "close_to_total_failure",
}

SENSOR_SPECS = [
    ("PS1", "PS1.txt", 100, 6),
    ("FS1", "FS1.txt", 10, 3),
    ("TS1", "TS1.txt", 1, 2),
]


def _build_groups():
    """48 deterministic (cooler, valve, pump, accumulator) groups."""
    groups = []
    for ci, cooler in enumerate(COOLER_CODES):
        for vi, valve in enumerate(VALVE_CODES):
            for k in range(4):
                pump = PUMP_CODES[(ci + k) % 3]
                accum = ACCUM_CODES[(ci * 2 + k) % 4]
                groups.append((cooler, valve, pump, accum))
    return groups


def _make_tiny_dataset(tmp_path: Path, group_size: int = 3, n_unstable: int = 8):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    groups = _build_groups()
    stable_rows = [(*g, 0) for g in groups for _ in range(group_size)]
    unstable_rows = [
        (COOLER_CODES[i % 3], VALVE_CODES[i % 4], 0, 130, 1) for i in range(n_unstable)
    ]
    rows = stable_rows + unstable_rows
    total_cycles = len(rows)
    stable_count = len(stable_rows)

    (raw_dir / "profile.txt").write_text(
        "\n".join("\t".join(str(x) for x in row) for row in rows) + "\n",
        encoding="utf-8",
    )

    rng = np.random.RandomState(0)
    for _, fname, _, samples in SENSOR_SPECS:
        matrix = rng.uniform(0.0, 100.0, size=(total_cycles, samples))
        np.savetxt(raw_dir / fname, matrix, delimiter="\t", fmt="%.6f")

    return raw_dir, SENSOR_SPECS, total_cycles, stable_count


def _make_config_dict(tmp_path: Path, raw_dir: Path, sensors, total_cycles, stable_count):
    return {
        "dataset": {
            "name": "tiny-hydraulic",
            "url": "https://example.invalid/dataset.zip",
            "sha256": "0" * 64,
            "zip_name": "tiny.zip",
            "zip_member_count": 1 + len(sensors),
            "cycle_count": total_cycles,
            "stable_cycle_count": stable_count,
            "raw_dir": str(raw_dir),
            "processed_dir": str(tmp_path / "processed"),
            "artifacts_dir": str(tmp_path / "artifacts"),
            "profile": {
                "file": "profile.txt",
                "columns": ["cooler", "valve", "pump", "accumulator", "stable"],
                "n_rows": total_cycles,
                "n_cols": 5,
                "stable_code": 0,
            },
        },
        "sensors": [
            {"name": n, "file": f, "sample_rate_hz": r, "samples_per_cycle": s}
            for (n, f, r, s) in sensors
        ],
        "features": {
            "functions": ["mean", "std", "min", "max"],
            "std_ddof": 0,
            "expected_count": len(sensors) * 4,
        },
        "targets": {
            "cooler": {"column": "cooler", "labels": COOLER_LABELS},
            "valve": {"column": "valve", "labels": VALVE_LABELS},
        },
        "split": {
            "ratios": {"train": 0.6, "val": 0.2, "test": 0.2},
            "seed": 0,
            "group_columns": ["cooler", "valve", "pump", "accumulator"],
            "max_attempts": 500,
        },
        "models": {
            "seed": 0,
            "logistic": {
                "imputer_strategy": "median",
                "scaler": "standard",
                "max_iter": 2000,
                "class_weight": "balanced",
            },
            "random_forest": {
                "imputer_strategy": "median",
                "n_estimators": 300,
                "class_weight": "balanced_subsample",
            },
        },
        "report": {"path": str(tmp_path / "report.md")},
    }


def _write_config(tmp_path: Path, config_dict: dict) -> HydraulicConfig:
    path = tmp_path / "hydraulic_systems.yaml"
    path.write_text(yaml.safe_dump(config_dict, sort_keys=False), encoding="utf-8")
    return load_config(path, root=tmp_path)


@pytest.fixture
def tiny_cfg(tmp_path):
    raw_dir, sensors, total, stable = _make_tiny_dataset(tmp_path)
    config_dict = _make_config_dict(tmp_path, raw_dir, sensors, total, stable)
    return _write_config(tmp_path, config_dict)


# --------------------------------------------------------------------------
# Config parser: strict validation
# --------------------------------------------------------------------------

def test_duplicate_key_rejected(tmp_path):
    text = "dataset:\n  name: a\ndataset:\n  name: b\n"
    path = tmp_path / "dup.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate key"):
        load_config(path, root=tmp_path)


def test_unknown_key_rejected(tmp_path):
    raw_dir, sensors, total, stable = _make_tiny_dataset(tmp_path)
    config_dict = _make_config_dict(tmp_path, raw_dir, sensors, total, stable)
    config_dict["surprise"] = {"x": 1}
    path = tmp_path / "cfg.yaml"
    path.write_text(yaml.safe_dump(config_dict, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(path, root=tmp_path)


def test_missing_field_rejected(tmp_path):
    raw_dir, sensors, total, stable = _make_tiny_dataset(tmp_path)
    config_dict = _make_config_dict(tmp_path, raw_dir, sensors, total, stable)
    del config_dict["dataset"]["profile"]
    path = tmp_path / "cfg.yaml"
    path.write_text(yaml.safe_dump(config_dict, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(path, root=tmp_path)


def test_structural_invariant_rejected(tmp_path):
    raw_dir, sensors, total, stable = _make_tiny_dataset(tmp_path)
    config_dict = _make_config_dict(tmp_path, raw_dir, sensors, total, stable)
    config_dict["features"]["expected_count"] = 999  # != 3 sensors * 4
    path = tmp_path / "cfg.yaml"
    path.write_text(yaml.safe_dump(config_dict, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValidationError, match="expected_count"):
        load_config(path, root=tmp_path)


def test_load_config_resolves_paths(tmp_path):
    raw_dir, sensors, total, stable = _make_tiny_dataset(tmp_path)
    config_dict = _make_config_dict(tmp_path, raw_dir, sensors, total, stable)
    config_dict["dataset"]["raw_dir"] = "relative/raw"
    path = tmp_path / "cfg.yaml"
    path.write_text(yaml.safe_dump(config_dict, sort_keys=False), encoding="utf-8")
    cfg = load_config(path, root=tmp_path)
    assert cfg.dataset.raw_dir.is_absolute()
    assert cfg.dataset.raw_dir == (tmp_path / "relative/raw").resolve()


def test_config_hash_is_independent_of_machine_root(tmp_path):
    raw_dir, sensors, total, stable = _make_tiny_dataset(tmp_path)
    config_dict = _make_config_dict(tmp_path, raw_dir, sensors, total, stable)
    config_dict["dataset"]["raw_dir"] = "data/raw/hydraulic"
    config_dict["dataset"]["processed_dir"] = "data/processed/hydraulic"
    config_dict["dataset"]["artifacts_dir"] = "artifacts/benchmarks/hydraulic"
    config_dict["report"]["path"] = "docs/report.md"
    path = tmp_path / "portable.yaml"
    path.write_text(yaml.safe_dump(config_dict, sort_keys=False), encoding="utf-8")

    first = load_config(path, root=tmp_path / "machine-a")
    second = load_config(path, root=tmp_path / "machine-b")

    assert first.dataset.raw_dir != second.dataset.raw_dir
    assert first.source_config_sha256 == second.source_config_sha256


# --------------------------------------------------------------------------
# Features
# --------------------------------------------------------------------------

def test_compute_features_ddof0():
    matrix = np.array([[1.0, 2.0, 3.0, 4.0], [10.0, 20.0, 30.0, 40.0]])
    feats = compute_features(matrix, ["mean", "std", "min", "max"], std_ddof=0)
    assert feats.shape == (2, 4)
    np.testing.assert_allclose(feats[0], [2.5, np.std(matrix[0], ddof=0), 1.0, 4.0])
    np.testing.assert_allclose(feats[1], [25.0, np.std(matrix[1], ddof=0), 10.0, 40.0])


def test_feature_names(tiny_cfg):
    names = feature_names(tiny_cfg.sensors, tiny_cfg.features.functions)
    assert len(names) == len(tiny_cfg.sensors) * 4
    assert names[0] == "PS1__mean"
    assert names[-1] == "TS1__max"


# --------------------------------------------------------------------------
# Prepare: shapes, alignment, labels, missing/invalid
# --------------------------------------------------------------------------

def test_prepare_end_to_end(tiny_cfg):
    manifest = prepare(tiny_cfg)
    processed = tiny_cfg.dataset.processed_dir
    assert (processed / "features.csv").exists()
    assert (processed / "prepare_manifest.json").exists()
    assert (processed / "split_manifest.json").exists()

    df = pd.read_csv(processed / "features.csv")
    assert len(df) == manifest["prepared"]["n_cycles"]
    assert manifest["prepared"]["stable_only"] is True

    for name in feature_names(tiny_cfg.sensors, tiny_cfg.features.functions):
        assert name in df.columns
    assert set(df["split"].unique()) == {"train", "val", "test"}
    assert "cooler_label" in df.columns and "valve_label" in df.columns
    assert (df["stable"] == 0).all()

    # raw codes and labels preserved
    assert df.loc[df["cooler"] == 3, "cooler_label"].eq("close_to_total_failure").all()
    assert df.loc[df["valve"] == 100, "valve_label"].eq("optimal_switching_behavior").all()

    for split in ("train", "val", "test"):
        sub = df[df["split"] == split]
        assert set(sub["cooler"].unique()) == set(COOLER_CODES)
        assert set(sub["valve"].unique()) == set(VALVE_CODES)


def test_prepare_validates_sensor_shape(tiny_cfg):
    raw = tiny_cfg.dataset.raw_dir
    wrong = np.zeros((tiny_cfg.dataset.cycle_count, tiny_cfg.sensors[0].samples_per_cycle + 1))
    np.savetxt(raw / "PS1.txt", wrong, delimiter="\t", fmt="%.1f")
    with pytest.raises(ValueError, match="shape"):
        prepare(tiny_cfg)


def test_prepare_missing_sensor_file(tiny_cfg):
    (tiny_cfg.dataset.raw_dir / "PS1.txt").unlink()
    with pytest.raises(FileNotFoundError):
        prepare(tiny_cfg)


def test_prepare_invalid_profile_code(tiny_cfg):
    raw = tiny_cfg.dataset.raw_dir
    profile = raw / "profile.txt"
    lines = profile.read_text(encoding="utf-8").splitlines()
    lines[0] = "999\t100\t0\t130\t0"
    profile.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected codes"):
        prepare(tiny_cfg)


def test_prepare_records_stable_counts(tiny_cfg):
    manifest = prepare(tiny_cfg)
    code_counts = manifest["profile"]["code_counts"]
    assert code_counts["stable"] == {0: manifest["prepared"]["n_cycles"], 1: 8}


# --------------------------------------------------------------------------
# Group split integrity
# --------------------------------------------------------------------------

def test_split_groups_no_overlap_and_coverage(tiny_cfg):
    df = pd.read_csv(tiny_cfg.dataset.raw_dir / "profile.txt", sep="\t", header=None)
    df.columns = ["cooler", "valve", "pump", "accumulator", "stable"]
    stable = df[df["stable"] == 0].reset_index(drop=True)
    stable.insert(0, "cycle", np.flatnonzero(df["stable"] == 0) + 1)

    result = split_groups(stable, tiny_cfg)

    cycles = [a["cycle"] for a in result["assignments"]]
    assert len(cycles) == len(set(cycles)) == len(stable)  # no overlap, all covered
    assert sum(result["split_cycle_counts"].values()) == len(stable)

    for split in ("train", "val", "test"):
        cov = result["class_coverage"][split]
        assert set(cov["cooler"]) == set(COOLER_CODES)
        assert set(cov["valve"]) == set(VALVE_CODES)

    # roughly 60/20/20 within group-level tolerance
    total = len(stable)
    assert 0.4 <= result["split_cycle_counts"]["train"] / total <= 0.8
    assert 0.1 <= result["split_cycle_counts"]["val"] / total <= 0.4
    assert 0.1 <= result["split_cycle_counts"]["test"] / total <= 0.4


def test_split_groups_fails_when_impossible(tiny_cfg):
    df = pd.DataFrame(
        {
            "cycle": list(range(30)),
            "cooler": [3] * 30,
            "valve": [100] * 30,
            "pump": [0] * 30,
            "accumulator": [130] * 30,
            "stable": [0] * 30,
        }
    )
    with pytest.raises(RuntimeError, match="group split"):
        split_groups(df, tiny_cfg)


# --------------------------------------------------------------------------
# Train-only preprocessing and models/serialization
# --------------------------------------------------------------------------

def test_train_only_preprocessing(tiny_cfg):
    prepare(tiny_cfg)
    df = pd.read_csv(tiny_cfg.dataset.processed_dir / "features.csv")
    fnames = feature_names(tiny_cfg.sensors, tiny_cfg.features.functions)
    x_all = df[fnames].to_numpy()
    y_codes = df["cooler"].to_numpy()
    classes = sorted(COOLER_CODES)

    mask_train = (df["split"] == "train").to_numpy()
    mask_test = (df["split"] == "test").to_numpy()

    x_train = x_all[mask_train].copy()
    x_test = x_all[mask_test].copy()
    x_test[0, 0] = np.nan  # missing value only in test

    pipe = make_logistic_pipeline(0)
    pipe.fit(x_train, hydraulic._encode(y_codes[mask_train], classes))

    # imputer + scaler statistics come from train only
    np.testing.assert_allclose(
        pipe.named_steps["imputer"].statistics_, np.nanmedian(x_train, axis=0)
    )
    np.testing.assert_allclose(
        pipe.named_steps["scaler"].mean_, x_train.mean(axis=0), rtol=1e-6
    )
    pred = pipe.predict(x_test)
    assert len(pred) == mask_test.sum()


def test_model_serialization_roundtrip(tmp_path):
    import joblib

    pipe = make_random_forest_pipeline(0)
    rng = np.random.RandomState(0)
    x = rng.uniform(0, 1, size=(24, 12))
    y = np.array([0, 1, 2] * 8)
    pipe.fit(x, y)
    path = tmp_path / "model.joblib"
    joblib.dump(pipe, path)
    loaded = joblib.load(path)
    np.testing.assert_array_equal(loaded.predict(x), pipe.predict(x))


def test_compute_test_metrics():
    classes = COOLER_CODES
    y_true = np.array([3, 3, 20, 20, 100, 100])
    y_pred = np.array([3, 20, 20, 20, 100, 3])
    metrics = compute_test_metrics(y_true, y_pred, classes, COOLER_LABELS)
    assert metrics["accuracy"] == 4 / 6
    assert metrics["per_class"]["full_efficiency"]["support"] == 2
    assert len(metrics["confusion_matrix"]) == 3
    assert "macro_f1" in metrics and "weighted_f1" in metrics
    assert "balanced_accuracy" in metrics


# --------------------------------------------------------------------------
# Download / extract / sha
# --------------------------------------------------------------------------

def test_sha256_file(tmp_path):
    path = tmp_path / "x.bin"
    path.write_bytes(b"abc")
    assert sha256_file(path) == hashlib.sha256(b"abc").hexdigest()


def test_download_sha_mismatch_fails(tmp_path, monkeypatch):
    data = b"hello world"
    monkeypatch.setattr(
        hydraulic.urllib.request, "urlopen", lambda url, timeout=120: io.BytesIO(data)
    )
    dest = tmp_path / "out.zip"
    with pytest.raises(RuntimeError, match="SHA256 mismatch"):
        _download(
            "https://example.invalid/x.zip",
            hashlib.sha256(b"WRONG").hexdigest(),
            dest,
        )
    assert not dest.exists()
    assert not (tmp_path / "out.zip.part").exists()


def test_download_atomic_success(tmp_path, monkeypatch):
    data = b"hello world"
    monkeypatch.setattr(
        hydraulic.urllib.request, "urlopen", lambda url, timeout=120: io.BytesIO(data)
    )
    dest = tmp_path / "out.zip"
    _download("https://example.invalid/x.zip", hashlib.sha256(data).hexdigest(), dest)
    assert dest.exists()
    assert dest.read_bytes() == data
    assert not (tmp_path / "out.zip.part").exists()


def test_safe_extract_rejects_traversal(tmp_path):
    zpath = tmp_path / "evil.zip"
    with zipfile.ZipFile(zpath, "w") as archive:
        archive.writestr("../evil.txt", "boom")
    with pytest.raises(RuntimeError, match="unsafe"):
        _safe_extract(zpath, tmp_path / "out")


def test_safe_extract_normal(tmp_path):
    zpath = tmp_path / "ok.zip"
    with zipfile.ZipFile(zpath, "w") as archive:
        archive.writestr("a.txt", "1")
        archive.writestr("sub/b.txt", "2")
    extracted = _safe_extract(zpath, tmp_path / "out")
    assert (tmp_path / "out" / "a.txt").exists()
    assert (tmp_path / "out" / "sub" / "b.txt").exists()
    assert set(extracted) == {"a.txt", "sub/b.txt"}


def test_required_files_present(tiny_cfg):
    assert required_files_present(tiny_cfg)
    (tiny_cfg.dataset.raw_dir / "profile.txt").unlink()
    assert not required_files_present(tiny_cfg)


def test_download_and_extract_idempotent(tmp_path, monkeypatch):
    raw_dir, sensors, total, stable = _make_tiny_dataset(tmp_path)
    config_dict = _make_config_dict(tmp_path, raw_dir, sensors, total, stable)

    zpath = tmp_path / "tiny.zip"
    with zipfile.ZipFile(zpath, "w") as archive:
        for name in ["profile.txt"] + [s[1] for s in sensors]:
            archive.write(raw_dir / name, arcname=name)
    zip_bytes = zpath.read_bytes()
    monkeypatch.setattr(
        hydraulic.urllib.request, "urlopen", lambda url, timeout=120: io.BytesIO(zip_bytes)
    )

    config_dict["dataset"]["sha256"] = sha256_file(zpath)
    config_dict["dataset"]["zip_name"] = "tiny.zip"
    config_dict["dataset"]["zip_member_count"] = 1 + len(sensors)
    config_dict["dataset"]["raw_dir"] = str(tmp_path / "raw_extracted")

    cfg = _write_config(tmp_path, config_dict)

    first = download_and_extract(cfg)
    assert first["status"] == "ready"
    assert required_files_present(cfg)

    second = download_and_extract(cfg)
    assert second["status"] == "already-present"


# --------------------------------------------------------------------------
# Run: models, serialization, report
# --------------------------------------------------------------------------

def test_run_end_to_end(tiny_cfg):
    prepare(tiny_cfg)
    result = run(tiny_cfg)

    artifacts = tiny_cfg.dataset.artifacts_dir
    assert (artifacts / "metrics.json").exists()
    assert (artifacts / "test_predictions.csv").exists()
    assert (artifacts / "run_manifest.json").exists()
    for target in ("cooler", "valve"):
        for family in ("logistic", "random_forest"):
            assert (artifacts / "models" / f"{target}_{family}.joblib").exists()

    report = Path(tiny_cfg.report.path)
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "External Evaluation Report" in text
    assert "uncalibrated" in text.lower()

    for target in ("cooler", "valve"):
        assert result["results"][target]["preferred_family"] in {"logistic", "random_forest"}

    preds = pd.read_csv(artifacts / "test_predictions.csv")
    assert set(preds["target"].unique()) == {"cooler", "valve"}
    assert set(preds["family"].unique()) == {"logistic", "random_forest"}
    assert preds["cycle"].min() >= 1
    assert preds["model_score"].between(0, 1).all()
    assert preds["model_sha256"].str.len().eq(64).all()
    assert preds["global_top_feature_values"].map(json.loads).map(len).eq(5).all()
    assert preds["feature_value_selection_method"].str.contains("no_local_attribution").all()
