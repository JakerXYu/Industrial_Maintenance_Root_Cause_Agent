"""Tests for the shared request ID validator and trace path containment."""

import pytest

from src.agent.request_id import (
    InvalidRequestIdError,
    is_valid_request_id,
    request_id_path,
    validate_request_id,
)
from src.agent.runner import AgentRunner
from src.agent.tracing import TraceStore
from src.contracts import TraceRecord


def test_valid_ids_include_eval_and_underscore():
    valid = [
        "eval-asset_A001",
        "eval-missing_asset",
        "eval-prompt_injection",
        "eval-unauthorized_write",
        "eval-duplicate_records",
        "operator_1",
        "asset_A025",
        "a",
        "A",
        "0",
        "a" * 128,
    ]
    for rid in valid:
        assert is_valid_request_id(rid), rid
        assert validate_request_id(rid) == rid


def test_rejects_invalid_charset_and_length():
    invalid = [
        "",
        "a" * 129,
        " leading",
        "trailing ",
        "has space",
        "../etc/passwd",
        "..",
        "a/b",
        "a\\b",
        "a.b",
        "-leading",
        "_leading",
    ]
    for rid in invalid:
        assert not is_valid_request_id(rid), rid
        with pytest.raises(InvalidRequestIdError):
            validate_request_id(rid)


def test_rejects_windows_reserved_device_basenames():
    reserved = ["CON", "con", "PRN", "AUX", "NUL", "COM1", "com9", "LPT1", "lpt9"]
    for rid in reserved:
        assert not is_valid_request_id(rid), rid
        with pytest.raises(InvalidRequestIdError):
            validate_request_id(rid)

    # Similar but non-reserved names stay valid.
    assert is_valid_request_id("COM0")
    assert is_valid_request_id("LPT10")
    assert is_valid_request_id("CONSOLE")


def test_request_id_path_stays_inside_traces_dir(tmp_path):
    path = request_id_path(tmp_path, "eval-asset_A001")
    assert path == (tmp_path / "eval-asset_A001.json").resolve()
    assert path.parent == tmp_path.resolve()


def test_request_id_path_rejects_traversal_and_reserved(tmp_path):
    with pytest.raises(InvalidRequestIdError):
        request_id_path(tmp_path, "../etc/passwd")
    with pytest.raises(InvalidRequestIdError):
        request_id_path(tmp_path, "CON")


def test_trace_store_rejects_invalid_request_id(tmp_path):
    store = TraceStore(tmp_path / "traces")
    with pytest.raises(InvalidRequestIdError):
        store.load("../etc/passwd")
    with pytest.raises(InvalidRequestIdError):
        store.load("CON")
    with pytest.raises(InvalidRequestIdError):
        store.save(TraceRecord(request_id="../escape", question="test"))


def test_agent_runner_rejects_explicit_empty_request_id(repository, tmp_path):
    runner = AgentRunner(repository, tmp_path / "traces")
    with pytest.raises(InvalidRequestIdError):
        runner.run("A001 stopped this week.", request_id="")
