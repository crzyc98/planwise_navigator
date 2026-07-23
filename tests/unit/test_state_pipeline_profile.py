"""Fingerprint contracts for Feature 122 profiling evidence."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

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
