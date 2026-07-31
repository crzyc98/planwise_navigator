"""Storage accounting stays off the filesystem on navigation-path requests.

Workspace trees reach tens of gigabytes across thousands of files, so a
recursive walk on a per-request path made workspace listing and health checks
the slowest endpoints in the API. These tests pin the properties that keep
them fast: the walk is cached, listing never triggers it, and resolving a
scenario's owning workspace never walks at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from planalign_api.services import storage_usage
from planalign_api.storage.workspace_storage import WorkspaceStorage

pytestmark = pytest.mark.fast


@pytest.fixture(autouse=True)
def clear_size_cache():
    storage_usage.invalidate()
    yield
    storage_usage.invalidate()


def _make_workspace(root: Path, workspace_id: str, *, scenarios: int = 0) -> Path:
    workspace_dir = root / workspace_id
    (workspace_dir / "scenarios").mkdir(parents=True)
    (workspace_dir / "workspace.json").write_text(
        json.dumps(
            {
                "id": workspace_id,
                "name": f"Workspace {workspace_id}",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        )
    )
    for index in range(scenarios):
        scenario_id = f"{workspace_id}-scenario-{index}"
        scenario_dir = workspace_dir / "scenarios" / scenario_id
        scenario_dir.mkdir()
        (scenario_dir / "scenario.json").write_text(
            json.dumps(
                {
                    "id": scenario_id,
                    "workspace_id": workspace_id,
                    "name": scenario_id,
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            )
        )
    return workspace_dir


def test_directory_bytes_sums_nested_files(tmp_path: Path) -> None:
    (tmp_path / "nested" / "deeper").mkdir(parents=True)
    (tmp_path / "a.bin").write_bytes(b"x" * 100)
    (tmp_path / "nested" / "b.bin").write_bytes(b"x" * 20)
    (tmp_path / "nested" / "deeper" / "c.bin").write_bytes(b"x" * 3)

    assert storage_usage.directory_bytes(tmp_path) == 123


def test_directory_bytes_does_not_follow_symlinks(tmp_path: Path) -> None:
    """Parameter-pack overlays symlink out of the workspace; those bytes are
    not the workspace's, and following them would double-count."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "big.bin").write_bytes(b"x" * 5000)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "own.bin").write_bytes(b"x" * 10)
    (workspace / "link.bin").symlink_to(outside / "big.bin")

    assert storage_usage.directory_bytes(workspace) == 10


def test_directory_bytes_returns_cached_value_without_rescanning(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.bin").write_bytes(b"x" * 10)
    assert storage_usage.directory_bytes(tmp_path) == 10

    # A later write is not observed until the TTL expires; that staleness is
    # the deliberate trade for keeping requests off the filesystem.
    (tmp_path / "b.bin").write_bytes(b"x" * 999)
    assert storage_usage.directory_bytes(tmp_path) == 10

    storage_usage.invalidate(tmp_path)
    assert storage_usage.directory_bytes(tmp_path) == 1009


def test_directory_bytes_returns_none_on_cold_cache_when_scan_disallowed(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.bin").write_bytes(b"x" * 10)

    assert storage_usage.directory_bytes(tmp_path, allow_scan=False) is None

    storage_usage.directory_bytes(tmp_path)
    assert storage_usage.directory_bytes(tmp_path, allow_scan=False) == 10


def test_workspace_totals_counts_workspaces_and_scenarios(tmp_path: Path) -> None:
    _make_workspace(tmp_path, "ws-a", scenarios=2)
    _make_workspace(tmp_path, "ws-b", scenarios=3)
    (tmp_path / ".hidden").mkdir()

    totals = storage_usage.workspace_totals(tmp_path)

    assert totals is not None
    assert totals.workspace_count == 2
    assert totals.scenario_count == 5
    assert totals.total_bytes > 0


def test_workspace_totals_is_all_or_nothing_when_scan_disallowed(
    tmp_path: Path,
) -> None:
    """A partial total would understate usage without saying so."""
    _make_workspace(tmp_path, "ws-a")
    workspace_b = _make_workspace(tmp_path, "ws-b")

    storage_usage.directory_bytes(tmp_path / "ws-a")
    assert storage_usage.workspace_totals(tmp_path, allow_scan=False) is None

    storage_usage.directory_bytes(workspace_b)
    assert storage_usage.workspace_totals(tmp_path, allow_scan=False) is not None


def test_list_workspaces_never_scans_the_filesystem(tmp_path: Path) -> None:
    _make_workspace(tmp_path, "ws-a", scenarios=1)
    storage = WorkspaceStorage(tmp_path)

    def fail(_path: Path) -> int:
        raise AssertionError("list_workspaces must not walk workspace trees")

    original = storage_usage._scan_directory_bytes
    storage_usage._scan_directory_bytes = fail  # type: ignore[assignment]
    try:
        summaries = storage.list_workspaces()
    finally:
        storage_usage._scan_directory_bytes = original  # type: ignore[assignment]

    assert [summary.id for summary in summaries] == ["ws-a"]
    assert summaries[0].storage_used_mb is None
    assert summaries[0].scenario_count == 1


def test_list_workspaces_reports_size_once_cache_is_warm(tmp_path: Path) -> None:
    workspace_dir = _make_workspace(tmp_path, "ws-a")
    (workspace_dir / "blob.bin").write_bytes(b"x" * (2 * 1024 * 1024))
    storage = WorkspaceStorage(tmp_path)

    storage_usage.workspace_totals(tmp_path)
    summaries = storage.list_workspaces()

    assert summaries[0].storage_used_mb == pytest.approx(2.0, abs=0.01)


def test_find_workspace_id_for_scenario(tmp_path: Path) -> None:
    _make_workspace(tmp_path, "ws-a", scenarios=1)
    _make_workspace(tmp_path, "ws-b", scenarios=2)
    storage = WorkspaceStorage(tmp_path)

    assert storage.find_workspace_id_for_scenario("ws-b-scenario-1") == "ws-b"
    assert storage.find_workspace_id_for_scenario("ws-a-scenario-0") == "ws-a"
    assert storage.find_workspace_id_for_scenario("nonexistent") is None


def test_find_workspace_id_for_scenario_never_scans(tmp_path: Path) -> None:
    _make_workspace(tmp_path, "ws-a", scenarios=1)
    storage = WorkspaceStorage(tmp_path)

    def fail(_path: Path) -> int:
        raise AssertionError("scenario lookup must not walk workspace trees")

    original = storage_usage._scan_directory_bytes
    storage_usage._scan_directory_bytes = fail  # type: ignore[assignment]
    try:
        assert storage.find_workspace_id_for_scenario("ws-a-scenario-0") == "ws-a"
    finally:
        storage_usage._scan_directory_bytes = original  # type: ignore[assignment]
