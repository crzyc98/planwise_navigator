"""Fingerprint contracts for Feature 122 profiling evidence."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import json

import pytest

from scripts.perf_profile.dbt_timing import InvocationRecorder, _target_directory

from scripts.perf_profile import run_matrix
from scripts.perf_profile.profile_config import (
    canonical_payload_fingerprint,
    fingerprint_file,
    fingerprint_seed_tree,
    normalized_yaml_fingerprint,
)


def test_canonical_config_fingerprint_ignores_mapping_and_yaml_key_order(
    tmp_path: Path,
):
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"
    first.write_text("simulation:\n  end_year: 2029\n  start_year: 2025\n")
    second.write_text("simulation:\n  start_year: 2025\n  end_year: 2029\n")

    assert normalized_yaml_fingerprint(first) == normalized_yaml_fingerprint(second)


def test_census_database_and_code_fingerprints_track_bytes(tmp_path: Path):
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"first")
    first = fingerprint_file(artifact)
    artifact.write_bytes(b"second")

    assert first != fingerprint_file(artifact)
    assert fingerprint_file(tmp_path / "absent") is None


def test_seed_tree_fingerprint_tracks_names_and_content(tmp_path: Path):
    (tmp_path / "b.csv").write_text("id\n2\n")
    (tmp_path / "a.csv").write_text("id\n1\n")
    first = fingerprint_seed_tree(tmp_path)
    (tmp_path / "a.csv").write_text("id\n3\n")

    assert first != fingerprint_seed_tree(tmp_path)


def test_construction_invocation_and_per_node_payloads_are_canonical():
    first = {"stage": "STATE_ACCUMULATION", "nodes": ["a", "b"], "year": 2025}
    reordered = {"year": 2025, "nodes": ["a", "b"], "stage": "STATE_ACCUMULATION"}

    assert canonical_payload_fingerprint(first) == canonical_payload_fingerprint(
        reordered
    )
    assert canonical_payload_fingerprint(first) != canonical_payload_fingerprint(
        {**reordered, "nodes": ["b", "a"]}
    )


def test_peak_rss_monitor_falls_back_when_child_enumeration_is_denied(monkeypatch):
    process = MagicMock()
    process.children.side_effect = PermissionError("sandbox")
    process.memory_info.return_value = SimpleNamespace(rss=64 * 1024 * 1024)
    monkeypatch.setattr(run_matrix.psutil, "Process", lambda: process)
    monitor = run_matrix._PeakRssMonitor()
    monitor._stop = MagicMock()
    monitor._stop.wait.side_effect = [False, True]

    monitor._sample()

    assert monitor.peak_bytes == 64 * 1024 * 1024


def _results(path: Path, name: str, status: str = "success") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"results": [{"unique_id": name, "status": status, "timing": []}]})
    )


@pytest.mark.parametrize(
    "mode", ["default", "project", "artifacts", "command", "environment", "configured"]
)
def test_recorder_resolves_actual_target(
    tmp_path: Path, monkeypatch, mode: str
) -> None:
    monkeypatch.delenv("DBT_TARGET_PATH", raising=False)
    project = tmp_path / "project"
    project.mkdir()
    runner = SimpleNamespace(
        working_dir=tmp_path, project_dir=None, dbt_artifacts_dir=None
    )
    args = ["run"]
    target = tmp_path / "target"
    if mode in {"project", "configured"}:
        runner.project_dir = project
        target = project / "target"
    if mode == "configured":
        (project / "dbt_project.yml").write_text("target-path: custom\n")
        target = project / "custom"
    if mode == "artifacts":
        monkeypatch.setenv("DBT_TARGET_PATH", str(tmp_path / "wrong-env-target"))
        runner.dbt_artifacts_dir = tmp_path / "artifacts"
        runner.target_path = runner.dbt_artifacts_dir / "target"
        target = runner.target_path
    if mode == "command":
        args += ["--project-dir", str(project), "--target-path=override"]
        target = project / "override"
    if mode == "environment":
        monkeypatch.setenv("DBT_TARGET_PATH", str(tmp_path / "env-target"))
        target = tmp_path / "env-target"
    _results(tmp_path / "target/run_results.json", "wrong-stale-node")
    runner.execute_command = lambda *_args, **_kwargs: _results(
        target / "run_results.json", "correct-node"
    )
    recorder = InvocationRecorder(runner)
    runner.execute_command(args)
    assert recorder.invocations[0].models[0].unique_id == "correct-node"
    assert recorder.invocations[0].node_timing_status == "fresh"
    assert _target_directory(runner, args) == target
    recorder.unwrap()


@pytest.mark.parametrize("condition", ["missing", "stale", "malformed", "failed"])
def test_recorder_never_reuses_stale_or_invalid_results(
    tmp_path: Path, condition: str
) -> None:
    path = tmp_path / "target/run_results.json"
    if condition in {"stale", "failed"}:
        _results(path, "previous-node")

    def execute(*_args, **_kwargs):
        if condition == "malformed":
            path.parent.mkdir(exist_ok=True)
            path.write_text("[]")
        if condition == "failed":
            raise RuntimeError("dbt failed")

    runner = SimpleNamespace(
        working_dir=tmp_path,
        project_dir=None,
        dbt_artifacts_dir=None,
        execute_command=execute,
    )
    recorder = InvocationRecorder(runner)
    if condition == "failed":
        with pytest.raises(RuntimeError, match="dbt failed"):
            runner.execute_command(["run"])
    else:
        runner.execute_command(["run"])
    record = recorder.invocations[0]
    assert record.models == []
    assert record.wall_s >= 0
    assert record.node_timing_status == (
        "stale" if condition == "failed" else condition
    )


def test_recorder_retains_fresh_failure_nodes(tmp_path: Path) -> None:
    path = tmp_path / "target/run_results.json"

    def execute(*_args, **_kwargs):
        _results(path, "failed-node", "error")
        raise RuntimeError("dbt failed after writing results")

    runner = SimpleNamespace(
        working_dir=tmp_path,
        project_dir=None,
        dbt_artifacts_dir=None,
        execute_command=execute,
    )
    recorder = InvocationRecorder(runner)
    with pytest.raises(RuntimeError):
        runner.execute_command(["build"])
    assert recorder.invocations[0].models[0].unique_id == "failed-node"
    assert recorder.invocations[0].models[0].status == "error"
