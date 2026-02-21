"""Tests for WorkspaceStorage.cleanup_old_runs() run retention."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from planalign_api.storage.workspace_storage import WorkspaceStorage


def _make_workspace(tmp_path: Path, workspace_id: str = "ws-1") -> Path:
    """Create a minimal workspace directory structure."""
    ws_dir = tmp_path / workspace_id
    ws_dir.mkdir()
    (ws_dir / "workspace.json").write_text(
        json.dumps({
            "id": workspace_id,
            "name": "Test",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        })
    )
    (ws_dir / "scenarios").mkdir()
    return ws_dir


def _make_scenario(ws_dir: Path, scenario_id: str = "sc-1") -> Path:
    """Create a minimal scenario directory with runs/ subdirectory."""
    sc_dir = ws_dir / "scenarios" / scenario_id
    sc_dir.mkdir(parents=True)
    (sc_dir / "scenario.json").write_text(
        json.dumps({
            "id": scenario_id,
            "workspace_id": ws_dir.name,
            "name": "Test Scenario",
            "created_at": datetime.utcnow().isoformat(),
        })
    )
    (sc_dir / "runs").mkdir()
    return sc_dir


def _make_run(
    sc_dir: Path,
    run_id: str,
    started_at: datetime,
    file_size_bytes: int = 1024,
) -> Path:
    """Create a run directory with metadata and a dummy file."""
    run_dir = sc_dir / "runs" / run_id
    run_dir.mkdir(parents=True)

    metadata = {
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "status": "completed",
    }
    (run_dir / "run_metadata.json").write_text(json.dumps(metadata, indent=2))

    # Create a dummy file to verify size calculation
    dummy = run_dir / "simulation.duckdb"
    dummy.write_bytes(b"\x00" * file_size_bytes)

    return run_dir


@pytest.fixture
def storage(tmp_path: Path) -> WorkspaceStorage:
    return WorkspaceStorage(workspaces_root=tmp_path)


class TestCleanupOldRuns:
    def test_no_pruning_when_under_limit(self, storage, tmp_path):
        ws = _make_workspace(tmp_path)
        sc = _make_scenario(ws)
        now = datetime.utcnow()

        _make_run(sc, "run-1", now - timedelta(hours=2))
        _make_run(sc, "run-2", now - timedelta(hours=1))

        result = storage.cleanup_old_runs(ws.name, "sc-1", max_runs=3)

        assert result["removed_count"] == 0
        assert result["bytes_freed"] == 0
        assert result["removed_runs"] == []
        assert (sc / "runs" / "run-1").exists()
        assert (sc / "runs" / "run-2").exists()

    def test_prunes_oldest_runs(self, storage, tmp_path):
        ws = _make_workspace(tmp_path)
        sc = _make_scenario(ws)
        now = datetime.utcnow()

        # Create 5 runs with staggered timestamps
        for i in range(5):
            _make_run(sc, f"run-{i}", now - timedelta(hours=5 - i))

        result = storage.cleanup_old_runs(ws.name, "sc-1", max_runs=3)

        assert result["removed_count"] == 2
        assert set(result["removed_runs"]) == {"run-0", "run-1"}

        # Newest 3 should survive
        assert (sc / "runs" / "run-2").exists()
        assert (sc / "runs" / "run-3").exists()
        assert (sc / "runs" / "run-4").exists()
        # Oldest 2 should be gone
        assert not (sc / "runs" / "run-0").exists()
        assert not (sc / "runs" / "run-1").exists()

    def test_unlimited_retention(self, storage, tmp_path):
        ws = _make_workspace(tmp_path)
        sc = _make_scenario(ws)
        now = datetime.utcnow()

        for i in range(5):
            _make_run(sc, f"run-{i}", now - timedelta(hours=i))

        result = storage.cleanup_old_runs(ws.name, "sc-1", max_runs=0)

        assert result["removed_count"] == 0
        # All 5 runs still present
        for i in range(5):
            assert (sc / "runs" / f"run-{i}").exists()

    def test_handles_missing_metadata(self, storage, tmp_path):
        ws = _make_workspace(tmp_path)
        sc = _make_scenario(ws)
        now = datetime.utcnow()

        # Run without metadata (should be treated as oldest)
        run_no_meta = sc / "runs" / "run-no-meta"
        run_no_meta.mkdir(parents=True)
        (run_no_meta / "simulation.duckdb").write_bytes(b"\x00" * 512)

        _make_run(sc, "run-new-1", now - timedelta(hours=1))
        _make_run(sc, "run-new-2", now)

        result = storage.cleanup_old_runs(ws.name, "sc-1", max_runs=2)

        assert result["removed_count"] == 1
        assert "run-no-meta" in result["removed_runs"]
        assert not run_no_meta.exists()
        assert (sc / "runs" / "run-new-1").exists()
        assert (sc / "runs" / "run-new-2").exists()

    def test_preserves_active_database(self, storage, tmp_path):
        ws = _make_workspace(tmp_path)
        sc = _make_scenario(ws)
        now = datetime.utcnow()

        # Create scenario-level simulation.duckdb (the active database)
        active_db = sc / "simulation.duckdb"
        active_db.write_bytes(b"\x00" * 2048)

        for i in range(4):
            _make_run(sc, f"run-{i}", now - timedelta(hours=4 - i))

        result = storage.cleanup_old_runs(ws.name, "sc-1", max_runs=2)

        assert result["removed_count"] == 2
        # Active database at scenario level must be untouched
        assert active_db.exists()
        assert active_db.stat().st_size == 2048

    def test_returns_bytes_freed(self, storage, tmp_path):
        ws = _make_workspace(tmp_path)
        sc = _make_scenario(ws)
        now = datetime.utcnow()

        file_size = 4096
        _make_run(sc, "run-old", now - timedelta(hours=2), file_size_bytes=file_size)
        _make_run(sc, "run-new", now)

        result = storage.cleanup_old_runs(ws.name, "sc-1", max_runs=1)

        assert result["removed_count"] == 1
        # bytes_freed should account for both metadata json + dummy file
        assert result["bytes_freed"] > file_size  # metadata json adds bytes

    def test_empty_runs_directory(self, storage, tmp_path):
        ws = _make_workspace(tmp_path)
        sc = _make_scenario(ws)

        result = storage.cleanup_old_runs(ws.name, "sc-1", max_runs=3)

        assert result["removed_count"] == 0
        assert result["bytes_freed"] == 0
        assert result["removed_runs"] == []

    def test_exact_limit_no_pruning(self, storage, tmp_path):
        """When run count exactly equals max_runs, nothing is pruned."""
        ws = _make_workspace(tmp_path)
        sc = _make_scenario(ws)
        now = datetime.utcnow()

        for i in range(3):
            _make_run(sc, f"run-{i}", now - timedelta(hours=i))

        result = storage.cleanup_old_runs(ws.name, "sc-1", max_runs=3)

        assert result["removed_count"] == 0
