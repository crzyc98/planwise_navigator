"""Tests for run_archiver module."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from planalign_api.services.simulation.run_archiver import (
    archive_run,
    prune_old_runs,
    _save_config,
    _save_metadata,
    _copy_database,
)


@pytest.mark.fast
class TestSaveConfig:
    """Test _save_config helper."""

    def test_writes_yaml(self, tmp_path):
        config = {"simulation": {"start_year": 2025}}
        _save_config(tmp_path, config)

        config_path = tmp_path / "config.yaml"
        assert config_path.exists()

        loaded = yaml.safe_load(config_path.read_text())
        assert loaded["simulation"]["start_year"] == 2025

    def test_handles_write_error(self, tmp_path):
        """Should not raise on write failure."""
        _save_config(Path("/nonexistent/path"), {"a": 1})


@pytest.mark.fast
class TestSaveMetadata:
    """Test _save_metadata helper."""

    def test_writes_json(self, tmp_path):
        _save_metadata(
            tmp_path,
            run_id="run-1",
            scenario_id="sc-1",
            scenario_name="Baseline",
            workspace_id="ws-1",
            start_time=datetime(2025, 1, 1, 10, 0, 0),
            elapsed_seconds=120.5,
            start_year=2025,
            end_year=2027,
            events_generated=500,
            seed=42,
        )

        metadata_path = tmp_path / "run_metadata.json"
        assert metadata_path.exists()

        data = json.loads(metadata_path.read_text())
        assert data["run_id"] == "run-1"
        assert data["scenario_name"] == "Baseline"
        assert data["duration_seconds"] == 120.5
        assert data["status"] == "completed"


@pytest.mark.fast
class TestCopyDatabase:
    """Test _copy_database helper."""

    def test_copies_db_file(self, tmp_path):
        scenario_path = tmp_path / "scenario"
        scenario_path.mkdir()
        db_src = scenario_path / "simulation.duckdb"
        db_src.write_text("fake-db-content")

        run_dir = tmp_path / "run"
        run_dir.mkdir()

        _copy_database(scenario_path, run_dir)

        db_dest = run_dir / "simulation.duckdb"
        assert db_dest.exists()
        assert db_dest.read_text() == "fake-db-content"

    def test_no_copy_when_db_missing(self, tmp_path):
        """Should not raise when source DB doesn't exist."""
        scenario_path = tmp_path / "scenario"
        scenario_path.mkdir()
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        _copy_database(scenario_path, run_dir)

        assert not (run_dir / "simulation.duckdb").exists()


@pytest.mark.fast
class TestArchiveRun:
    """Test archive_run orchestration."""

    @patch("planalign_api.services.simulation.run_archiver.export_results_to_excel")
    def test_creates_run_directory(self, mock_export, tmp_path):
        mock_export.return_value = None

        scenario_path = tmp_path / "scenario"
        scenario_path.mkdir()

        archive_run(
            scenario_path=scenario_path,
            run_id="run-abc",
            scenario_id="sc-1",
            scenario_name="Test",
            workspace_id="ws-1",
            config={"simulation": {"start_year": 2025}},
            start_time=datetime.now(),
            elapsed_seconds=10.0,
            start_year=2025,
            end_year=2027,
            events_generated=100,
            seed=42,
        )

        run_dir = scenario_path / "runs" / "run-abc"
        assert run_dir.exists()
        assert (run_dir / "config.yaml").exists()
        assert (run_dir / "run_metadata.json").exists()


@pytest.mark.fast
class TestPruneOldRuns:
    """Test prune_old_runs function."""

    def test_calls_storage_cleanup(self):
        mock_storage = MagicMock()
        mock_storage.cleanup_old_runs.return_value = {
            "removed_count": 2,
            "bytes_freed": 1024 * 1024 * 50,
        }

        prune_old_runs(mock_storage, "ws-1", "sc-1", {"storage": {"max_runs_per_scenario": 3}})

        mock_storage.cleanup_old_runs.assert_called_once_with("ws-1", "sc-1", max_runs=3)

    def test_uses_default_max_runs(self):
        mock_storage = MagicMock()
        mock_storage.cleanup_old_runs.return_value = {"removed_count": 0, "bytes_freed": 0}

        prune_old_runs(mock_storage, "ws-1", "sc-1", {})

        mock_storage.cleanup_old_runs.assert_called_once_with("ws-1", "sc-1", max_runs=3)

    def test_handles_cleanup_error(self):
        """Should not raise on cleanup failure."""
        mock_storage = MagicMock()
        mock_storage.cleanup_old_runs.side_effect = RuntimeError("disk full")

        prune_old_runs(mock_storage, "ws-1", "sc-1", {})
