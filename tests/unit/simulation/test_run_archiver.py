"""Tests for run_archiver module."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
import duckdb

from planalign_api.services.simulation.run_archiver import (
    archive_run,
    prune_old_runs,
    _save_config,
    _save_metadata,
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
class TestArchivedConfigStatesEffectiveDesign:
    """Issue #523: the archived config must state the design that actually ran.

    Studio writes its plan design into ``dc_plan``, leaving
    ``employer_core_contribution`` at the base-config defaults. Archiving the
    merged config verbatim recorded a design the run never used.
    """

    def _archived(self, tmp_path, config):
        _save_config(tmp_path, config)
        return yaml.safe_load((tmp_path / "config.yaml").read_text())

    def test_dc_plan_rate_wins_over_nested_default(self, tmp_path):
        """The 2026-07-10 case: nested 3% / dc_plan 1% must archive as 1%."""
        archived = self._archived(
            tmp_path,
            {
                "employer_core_contribution": {
                    "status": "flat",
                    "contribution_rate": 0.03,
                },
                "dc_plan": {"core_status": "flat", "core_contribution_rate_percent": 1},
            },
        )
        assert archived["employer_core_contribution"]["contribution_rate"] == 0.01

    def test_integrated_design_archives_its_integration(self, tmp_path):
        """An SS-integrated design must not archive as integration: null."""
        archived = self._archived(
            tmp_path,
            {
                "employer_core_contribution": {
                    "status": "flat",
                    "contribution_rate": 0.03,
                    "integration": None,
                },
                "dc_plan": {
                    "core_contribution_rate_percent": 5.7,
                    "core_integration_enabled": True,
                    "core_integration_level_mode": "ss_wage_base",
                    "core_integration_disparity_rate": 0.05,
                },
            },
        )
        core = archived["employer_core_contribution"]
        assert core["contribution_rate"] == 0.057
        assert core["integration"]["enabled"] is True
        assert core["integration"]["level_mode"] == "ss_wage_base"
        assert core["integration"]["disparity_rate"] == 0.05

    def test_yaml_configured_design_is_untouched(self, tmp_path):
        """A non-Studio design must archive byte-identically to before the fix."""
        config = {
            "employer_core_contribution": {"status": "flat", "contribution_rate": 0.03},
            "dc_plan": {"match_template": "tiered"},
        }
        expected = yaml.dump(config, default_flow_style=False, sort_keys=False)
        _save_config(tmp_path, config)
        assert (tmp_path / "config.yaml").read_text() == expected

    def test_archived_config_round_trips_to_the_same_effective_design(self, tmp_path):
        """The archive and the engine must not drift apart again.

        Re-resolving the archived config must be a fixed point: it already
        states the effective design, so it resolves to the same core block the
        engine derived from the original merged config, and contradicts none of
        the engine's vars. The archived config may resolve to *more* vars than
        the original, because writing the resolved block makes nested
        eligibility explicit where the Studio config only had ``dc_plan``.
        """
        from types import SimpleNamespace

        from planalign_orchestrator.config.export import (
            _export_core_contribution_vars,
        )

        config = {
            "employer_core_contribution": {
                "status": "flat",
                "contribution_rate": 0.03,
                "integration": None,
            },
            "dc_plan": {
                "core_status": "graded_by_service",
                "core_contribution_rate_percent": 5.7,
                "core_integration_enabled": True,
                "core_integration_level_mode": "ss_wage_base",
                "core_integration_disparity_rate": 0.05,
                "core_min_hours_annual": 1000,
            },
        }
        archived = self._archived(tmp_path, config)

        engine_vars = _export_core_contribution_vars(SimpleNamespace(**config))
        archived_vars = _export_core_contribution_vars(SimpleNamespace(**archived))

        assert (
            archived_vars["employer_core_contribution"]
            == engine_vars["employer_core_contribution"]
        )
        assert archived_vars.items() >= engine_vars.items()


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
@pytest.mark.fast
class TestArchiveRun:
    """Test archive_run orchestration."""

    @patch("planalign_api.services.simulation.run_archiver.export_results_to_excel")
    def test_creates_run_directory(self, mock_export, tmp_path):
        mock_export.return_value = None

        scenario_path = tmp_path / "scenario"
        scenario_path.mkdir()
        run_dir = scenario_path / "runs" / "run-abc"
        run_dir.mkdir(parents=True)
        with duckdb.connect(str(run_dir / "simulation.duckdb")) as connection:
            connection.execute("CREATE TABLE marker (value INTEGER)")

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
            run_dir=run_dir,
        )

        assert run_dir.exists()
        assert (run_dir / "config.yaml").exists()
        assert (run_dir / "run_metadata.json").exists()
        with duckdb.connect(
            str(run_dir / "simulation.duckdb"), read_only=True
        ) as connection:
            assert connection.execute("SELECT COUNT(*) FROM marker").fetchone()[0] == 0
        assert not (scenario_path / "simulation.duckdb").exists()

    def test_requires_existing_run_local_database(self, tmp_path):
        scenario_path = tmp_path / "scenario"
        run_dir = scenario_path / "runs" / "run-abc"
        run_dir.mkdir(parents=True)

        with pytest.raises(FileNotFoundError, match="run-local"):
            archive_run(
                scenario_path=scenario_path,
                run_id="run-abc",
                scenario_id="sc-1",
                scenario_name="Test",
                workspace_id="ws-1",
                config={},
                start_time=datetime.now(),
                elapsed_seconds=1,
                start_year=2025,
                end_year=2025,
                events_generated=0,
                seed=42,
                run_dir=run_dir,
            )

    def test_terminal_metadata_is_installed_atomically(self, tmp_path):
        with patch(
            "planalign_api.services.simulation.run_archiver.os.replace"
        ) as replace:
            _save_metadata(
                tmp_path,
                run_id="run-1",
                scenario_id="sc-1",
                scenario_name="Baseline",
                workspace_id="ws-1",
                start_time=datetime.now(),
                elapsed_seconds=1,
                start_year=2025,
                end_year=2025,
                events_generated=0,
                seed=42,
            )
            replace.assert_called_once()


@pytest.mark.fast
class TestPruneOldRuns:
    """Test prune_old_runs function."""

    def test_calls_storage_cleanup(self):
        mock_storage = MagicMock()
        mock_storage.cleanup_old_runs.return_value = {
            "removed_count": 2,
            "bytes_freed": 1024 * 1024 * 50,
        }

        prune_old_runs(
            mock_storage, "ws-1", "sc-1", {"storage": {"max_runs_per_scenario": 3}}
        )

        mock_storage.cleanup_old_runs.assert_called_once_with(
            "ws-1", "sc-1", max_runs=3
        )

    def test_uses_default_max_runs(self):
        mock_storage = MagicMock()
        mock_storage.cleanup_old_runs.return_value = {
            "removed_count": 0,
            "bytes_freed": 0,
        }

        prune_old_runs(mock_storage, "ws-1", "sc-1", {})

        mock_storage.cleanup_old_runs.assert_called_once_with(
            "ws-1", "sc-1", max_runs=3
        )

    def test_handles_cleanup_error(self):
        """Should not raise on cleanup failure."""
        mock_storage = MagicMock()
        mock_storage.cleanup_old_runs.side_effect = RuntimeError("disk full")

        prune_old_runs(mock_storage, "ws-1", "sc-1", {})


@pytest.mark.fast
class TestArchiveFailedRun:
    """Failed/cancelled runs must persist metadata so run history shows
    the error message and simulation.log (feature 094)."""

    def _archive(self, scenario_path, **overrides):
        from planalign_api.services.simulation.run_archiver import archive_failed_run

        kwargs = dict(
            scenario_path=scenario_path,
            run_id="run-fail-1",
            scenario_id="sc-1",
            scenario_name="Test Scenario",
            workspace_id="ws-1",
            config={"simulation": {"start_year": 2025, "random_seed": 42}},
            start_time=datetime(2026, 6, 11, 8, 0, 0),
            run_status="failed",
            error_message="census file not found",
            start_year=2025,
            end_year=2027,
        )
        kwargs.update(overrides)
        archive_failed_run(**kwargs)
        return scenario_path / "runs" / kwargs["run_id"] / "run_metadata.json"

    def test_writes_metadata_with_failed_status_and_error(self, tmp_path):
        metadata_path = self._archive(tmp_path)
        assert metadata_path.exists()
        metadata = json.loads(metadata_path.read_text())
        assert metadata["status"] == "failed"
        assert metadata["error_message"] == "census file not found"
        assert metadata["start_year"] == 2025
        assert metadata["run_id"] == "run-fail-1"
        assert metadata["seed"] == 42

    def test_creates_run_dir_when_missing(self, tmp_path):
        """Preparation failures happen before the run dir exists."""
        metadata_path = self._archive(tmp_path, run_dir=None)
        assert metadata_path.parent.exists()

    def test_cancelled_status_without_error(self, tmp_path):
        metadata_path = self._archive(
            tmp_path, run_status="cancelled", error_message=None
        )
        metadata = json.loads(metadata_path.read_text())
        assert metadata["status"] == "cancelled"
        assert metadata["error_message"] is None

    def test_no_database_copy_or_excel(self, tmp_path):
        metadata_path = self._archive(tmp_path)
        files = {f.name for f in metadata_path.parent.iterdir()}
        assert files == {"run_metadata.json", "config.yaml"}
