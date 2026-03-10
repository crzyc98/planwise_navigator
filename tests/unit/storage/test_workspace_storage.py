"""Tests for WorkspaceStorage: repair, cleanup, running check, deep merge, and seed injection."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from planalign_api.storage.workspace_storage import WorkspaceStorage


# --- Helpers ---


def _make_workspace(tmp_path: Path, workspace_id: str = "ws-1") -> Path:
    """Create a minimal workspace directory structure."""
    ws_dir = tmp_path / workspace_id
    ws_dir.mkdir()
    (ws_dir / "workspace.json").write_text(
        json.dumps({
            "id": workspace_id,
            "name": "Test",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    )
    (ws_dir / "scenarios").mkdir()
    return ws_dir


def _make_scenario(ws_dir: Path, scenario_id: str = "sc-1") -> Path:
    """Create a minimal scenario directory."""
    sc_dir = ws_dir / "scenarios" / scenario_id
    sc_dir.mkdir(parents=True)
    (sc_dir / "scenario.json").write_text(
        json.dumps({
            "id": scenario_id,
            "workspace_id": ws_dir.name,
            "name": "Test Scenario",
            "created_at": datetime.now(timezone.utc).isoformat(),
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
    (run_dir / "simulation.duckdb").write_bytes(b"\x00" * file_size_bytes)
    return run_dir


@pytest.fixture
def storage(tmp_path: Path) -> WorkspaceStorage:
    return WorkspaceStorage(workspaces_root=tmp_path)


# ==================== repair_workspaces ====================


@pytest.mark.fast
class TestRepairWorkspaces:
    """Tests for the repair_workspaces method."""

    def test_no_workspaces(self, storage):
        """Empty root returns zero counts."""
        report = storage.repair_workspaces()
        assert report["workspaces_scanned"] == 0
        assert report["scenarios_scanned"] == 0
        assert report["repairs"] == []

    def test_healthy_workspace_no_repairs(self, storage, tmp_path):
        """A valid workspace needs no repairs."""
        _make_workspace(tmp_path)
        report = storage.repair_workspaces()

        assert report["workspaces_scanned"] == 1
        assert report["repairs"] == []

    def test_healthy_workspace_with_scenario(self, storage, tmp_path):
        """Valid workspace + scenario yields zero repairs."""
        ws = _make_workspace(tmp_path)
        _make_scenario(ws)
        report = storage.repair_workspaces()

        assert report["workspaces_scanned"] == 1
        assert report["scenarios_scanned"] == 1
        assert report["repairs"] == []

    def test_repairs_missing_workspace_json(self, storage, tmp_path):
        """Should create workspace.json when missing."""
        ws_dir = tmp_path / "ws-missing"
        ws_dir.mkdir()
        (ws_dir / "scenarios").mkdir()

        report = storage.repair_workspaces()

        assert report["workspaces_scanned"] == 1
        assert len(report["repairs"]) == 1
        assert report["repairs"][0]["action"] == "created"
        # File should now be parseable
        with open(ws_dir / "workspace.json") as f:
            data = json.load(f)
        assert data["id"] == "ws-missing"

    def test_repairs_corrupted_workspace_json(self, storage, tmp_path):
        """Should repair a workspace.json with invalid JSON."""
        ws_dir = tmp_path / "ws-corrupt"
        ws_dir.mkdir()
        (ws_dir / "scenarios").mkdir()
        (ws_dir / "workspace.json").write_text("{invalid json content")

        report = storage.repair_workspaces()

        assert report["workspaces_scanned"] == 1
        assert len(report["repairs"]) == 1
        repair = report["repairs"][0]
        assert repair["action"] == "repaired"
        # Backup should exist
        assert (ws_dir / "workspace.json.corrupted").exists()
        # Repaired file should be valid
        with open(ws_dir / "workspace.json") as f:
            data = json.load(f)
        assert "id" in data

    def test_repairs_empty_workspace_json(self, storage, tmp_path):
        """Should repair an empty workspace.json file."""
        ws_dir = tmp_path / "ws-empty"
        ws_dir.mkdir()
        (ws_dir / "scenarios").mkdir()
        (ws_dir / "workspace.json").write_text("")

        report = storage.repair_workspaces()

        assert len(report["repairs"]) == 1
        assert report["repairs"][0]["action"] == "repaired"

    def test_repairs_workspace_json_missing_required_fields(self, storage, tmp_path):
        """Should repair workspace.json missing required fields."""
        ws_dir = tmp_path / "ws-partial"
        ws_dir.mkdir()
        (ws_dir / "scenarios").mkdir()
        (ws_dir / "workspace.json").write_text(json.dumps({"id": "ws-partial"}))

        report = storage.repair_workspaces()

        assert len(report["repairs"]) == 1
        assert report["repairs"][0]["action"] == "repaired"

    def test_repairs_missing_scenario_json(self, storage, tmp_path):
        """Should create scenario.json when missing."""
        ws = _make_workspace(tmp_path)
        sc_dir = ws / "scenarios" / "sc-missing"
        sc_dir.mkdir(parents=True)

        report = storage.repair_workspaces()

        assert report["scenarios_scanned"] == 1
        assert len(report["repairs"]) == 1
        assert report["repairs"][0]["action"] == "created"
        with open(sc_dir / "scenario.json") as f:
            data = json.load(f)
        assert data["id"] == "sc-missing"
        assert data["workspace_id"] == ws.name

    def test_repairs_corrupted_scenario_json(self, storage, tmp_path):
        """Should repair a scenario.json with invalid content."""
        ws = _make_workspace(tmp_path)
        sc_dir = ws / "scenarios" / "sc-corrupt"
        sc_dir.mkdir(parents=True)
        (sc_dir / "scenario.json").write_text("not valid json {{{")

        report = storage.repair_workspaces()

        assert report["scenarios_scanned"] == 1
        assert len(report["repairs"]) == 1
        assert report["repairs"][0]["action"] == "repaired"

    def test_skips_hidden_directories(self, storage, tmp_path):
        """Should skip directories starting with '.'."""
        hidden_dir = tmp_path / ".git"
        hidden_dir.mkdir()
        (hidden_dir / "workspace.json").write_text("{}")

        report = storage.repair_workspaces()
        assert report["workspaces_scanned"] == 0

    def test_skips_non_directory_entries(self, storage, tmp_path):
        """Should skip files in the workspaces root."""
        (tmp_path / "some_file.txt").write_text("hello")

        report = storage.repair_workspaces()
        assert report["workspaces_scanned"] == 0


# ==================== _repair_json_file ====================


@pytest.mark.fast
class TestRepairJsonFile:
    """Tests for the _repair_json_file helper."""

    def test_returns_none_if_file_ok(self, storage, tmp_path):
        """Returns None for a valid workspace.json."""
        ws = _make_workspace(tmp_path)
        ws_json = ws / "workspace.json"

        result = storage._repair_json_file(
            ws_json,
            storage._create_minimal_workspace_json,
            {"workspace_id": ws.name, "workspace_dir": ws},
        )
        assert result is None

    def test_returns_none_if_no_parent(self, storage, tmp_path):
        """Returns None when parent directory doesn't exist."""
        nonexistent = tmp_path / "nope" / "workspace.json"
        result = storage._repair_json_file(
            nonexistent,
            storage._create_minimal_workspace_json,
            {"workspace_id": "x", "workspace_dir": tmp_path},
        )
        assert result is None

    def test_creates_file_if_missing_but_parent_exists(self, storage, tmp_path):
        """Creates the JSON file if it doesn't exist but parent dir does."""
        ws_dir = tmp_path / "ws-new"
        ws_dir.mkdir()

        result = storage._repair_json_file(
            ws_dir / "workspace.json",
            storage._create_minimal_workspace_json,
            {"workspace_id": "ws-new", "workspace_dir": ws_dir},
        )
        assert result is not None
        assert result["action"] == "created"

    def test_backup_numbering_for_multiple_repairs(self, storage, tmp_path):
        """Multiple repairs should create numbered backups."""
        ws_dir = tmp_path / "ws-multi"
        ws_dir.mkdir()
        ws_json = ws_dir / "workspace.json"

        # First corrupt file + repair
        ws_json.write_text("{bad")
        storage._repair_json_file(
            ws_json,
            storage._create_minimal_workspace_json,
            {"workspace_id": "ws-multi", "workspace_dir": ws_dir},
        )
        assert (ws_dir / "workspace.json.corrupted").exists()

        # Second corrupt file + repair
        ws_json.write_text("{bad again")
        storage._repair_json_file(
            ws_json,
            storage._create_minimal_workspace_json,
            {"workspace_id": "ws-multi", "workspace_dir": ws_dir},
        )
        assert (ws_dir / "workspace.json.corrupted.1").exists()


# ==================== _try_salvage_json ====================


@pytest.mark.fast
class TestTrySalvageJson:
    """Tests for the _try_salvage_json helper."""

    def test_salvages_id_and_name(self, storage, tmp_path):
        """Should extract id and name from partially valid JSON."""
        f = tmp_path / "partial.json"
        f.write_text('{"id": "abc-123", "name": "My Workspace", broken}')

        salvaged = storage._try_salvage_json(f)
        assert salvaged["id"] == "abc-123"
        assert salvaged["name"] == "My Workspace"

    def test_salvages_workspace_id(self, storage, tmp_path):
        """Should extract workspace_id from scenario JSON."""
        f = tmp_path / "scenario.json"
        f.write_text('{"workspace_id": "ws-456" corrupt')

        salvaged = storage._try_salvage_json(f)
        assert salvaged["workspace_id"] == "ws-456"

    def test_salvages_description(self, storage, tmp_path):
        """Should extract description field."""
        f = tmp_path / "test.json"
        f.write_text('{"description": "A test workspace"')

        salvaged = storage._try_salvage_json(f)
        assert salvaged["description"] == "A test workspace"

    def test_salvages_dates(self, storage, tmp_path):
        """Should extract ISO date patterns."""
        f = tmp_path / "test.json"
        f.write_text('"created_at": "2025-06-15T10:30:00" broken')

        salvaged = storage._try_salvage_json(f)
        assert "2025-06-15T10:30:00" in salvaged["_salvaged_dates"]

    def test_returns_empty_dict_for_binary_content(self, storage, tmp_path):
        """Should return empty dict for unreadable content."""
        f = tmp_path / "binary.json"
        f.write_bytes(b"\x00\x01\x02\x03")

        salvaged = storage._try_salvage_json(f)
        assert isinstance(salvaged, dict)

    def test_returns_empty_dict_for_empty_file(self, storage, tmp_path):
        """Should return empty dict for empty file."""
        f = tmp_path / "empty.json"
        f.write_text("")

        salvaged = storage._try_salvage_json(f)
        assert salvaged == {}


# ==================== _create_minimal_workspace_json ====================


@pytest.mark.fast
class TestCreateMinimalWorkspaceJson:
    """Tests for _create_minimal_workspace_json."""

    def test_uses_context_workspace_id(self, storage):
        """Should use workspace_id from context."""
        context = {"workspace_id": "ws-abc", "workspace_dir": Path("/fake")}
        result = storage._create_minimal_workspace_json(context)

        assert result["id"] == "ws-abc"
        assert "Recovered Workspace" in result["name"]
        assert "created_at" in result
        assert "updated_at" in result

    def test_prefers_salvaged_data(self, storage):
        """Should prefer salvaged id and name over defaults."""
        context = {"workspace_id": "ws-fallback", "workspace_dir": Path("/fake")}
        salvaged = {
            "id": "ws-original",
            "name": "Original Name",
            "description": "Saved desc",
        }
        result = storage._create_minimal_workspace_json(context, salvaged)

        assert result["id"] == "ws-original"
        assert result["name"] == "Original Name"
        assert result["description"] == "Saved desc"

    def test_uses_salvaged_dates(self, storage):
        """Should use salvaged dates when available."""
        context = {"workspace_id": "ws-1", "workspace_dir": Path("/fake")}
        salvaged = {"_salvaged_dates": ["2024-01-01T00:00:00", "2024-06-15T12:00:00"]}

        result = storage._create_minimal_workspace_json(context, salvaged)

        assert result["created_at"] == "2024-01-01T00:00:00"
        assert result["updated_at"] == "2024-06-15T12:00:00"


# ==================== _create_minimal_scenario_json ====================


@pytest.mark.fast
class TestCreateMinimalScenarioJson:
    """Tests for _create_minimal_scenario_json."""

    def test_uses_context_ids(self, storage):
        """Should use scenario_id and workspace_id from context."""
        context = {
            "workspace_id": "ws-1",
            "scenario_id": "sc-1",
            "scenario_dir": Path("/fake"),
        }
        result = storage._create_minimal_scenario_json(context)

        assert result["id"] == "sc-1"
        assert result["workspace_id"] == "ws-1"
        assert result["status"] == "not_run"
        assert result["config_overrides"] == {}

    def test_prefers_salvaged_data(self, storage):
        """Should prefer salvaged values."""
        context = {
            "workspace_id": "ws-fallback",
            "scenario_id": "sc-fallback",
            "scenario_dir": Path("/fake"),
        }
        salvaged = {
            "id": "sc-original",
            "workspace_id": "ws-original",
            "name": "Orig Scenario",
        }
        result = storage._create_minimal_scenario_json(context, salvaged)

        assert result["id"] == "sc-original"
        assert result["workspace_id"] == "ws-original"
        assert result["name"] == "Orig Scenario"


# ==================== cleanup_old_runs ====================


@pytest.mark.fast
class TestCleanupOldRuns:
    """Tests for cleanup_old_runs (supplements test_run_cleanup.py)."""

    def test_no_runs_dir(self, storage, tmp_path):
        """Returns empty result when runs/ directory doesn't exist."""
        ws = _make_workspace(tmp_path)
        sc = _make_scenario(ws)
        # Remove runs dir
        (sc / "runs").rmdir()

        result = storage.cleanup_old_runs(ws.name, "sc-1", max_runs=1)
        assert result["removed_count"] == 0

    def test_negative_max_runs_treated_as_unlimited(self, storage, tmp_path):
        """max_runs <= 0 should not prune anything."""
        ws = _make_workspace(tmp_path)
        sc = _make_scenario(ws)
        now = datetime.now(timezone.utc)
        for i in range(5):
            _make_run(sc, f"run-{i}", now - timedelta(hours=i))

        result = storage.cleanup_old_runs(ws.name, "sc-1", max_runs=-1)
        assert result["removed_count"] == 0

    def test_skips_non_directory_entries_in_runs(self, storage, tmp_path):
        """Non-directory entries in runs/ should be ignored."""
        ws = _make_workspace(tmp_path)
        sc = _make_scenario(ws)
        now = datetime.now(timezone.utc)
        _make_run(sc, "run-1", now)
        # Create a stray file in runs/
        (sc / "runs" / "stray_file.txt").write_text("hello")

        result = storage.cleanup_old_runs(ws.name, "sc-1", max_runs=1)
        # Should not count the file as a run, so no pruning
        assert result["removed_count"] == 0


# ==================== is_simulation_running ====================


@pytest.mark.fast
class TestIsSimulationRunning:
    """Tests for is_simulation_running."""

    def test_returns_false_when_no_scenarios_dir(self, storage, tmp_path):
        """Should return False when scenarios directory doesn't exist."""
        ws_dir = tmp_path / "ws-no-scenarios"
        ws_dir.mkdir()

        assert storage.is_simulation_running("ws-no-scenarios") is False

    def test_returns_false_when_no_running_scenarios(self, storage, tmp_path):
        """Should return False when no scenarios are running."""
        ws = _make_workspace(tmp_path)
        _make_scenario(ws, "sc-1")

        assert storage.is_simulation_running(ws.name) is False

    def test_returns_true_when_scenario_is_running(self, storage, tmp_path):
        """Should return True when a scenario has 'running' status."""
        ws = _make_workspace(tmp_path)
        sc_dir = ws / "scenarios" / "sc-running"
        sc_dir.mkdir(parents=True)
        (sc_dir / "scenario.json").write_text(
            json.dumps({
                "id": "sc-running",
                "workspace_id": ws.name,
                "name": "Running Scenario",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "running",
            })
        )

        assert storage.is_simulation_running(ws.name) is True

    def test_ignores_corrupted_scenario_json(self, storage, tmp_path):
        """Should skip corrupted scenario.json files gracefully."""
        ws = _make_workspace(tmp_path)
        sc_dir = ws / "scenarios" / "sc-bad"
        sc_dir.mkdir(parents=True)
        (sc_dir / "scenario.json").write_text("not json")

        assert storage.is_simulation_running(ws.name) is False

    def test_ignores_non_directory_entries(self, storage, tmp_path):
        """Should skip files in the scenarios directory."""
        ws = _make_workspace(tmp_path)
        (ws / "scenarios" / "stray_file.txt").write_text("hello")

        assert storage.is_simulation_running(ws.name) is False

    def test_ignores_scenario_without_json(self, storage, tmp_path):
        """Should skip scenario directories without scenario.json."""
        ws = _make_workspace(tmp_path)
        (ws / "scenarios" / "sc-empty").mkdir()

        assert storage.is_simulation_running(ws.name) is False


# ==================== _deep_merge ====================


@pytest.mark.fast
class TestDeepMerge:
    """Tests for _deep_merge with _ATOMIC_SECTIONS support."""

    def test_basic_merge(self, storage):
        """Should merge non-overlapping keys."""
        base = {"a": 1}
        overrides = {"b": 2}
        result = storage._deep_merge(base, overrides)
        assert result == {"a": 1, "b": 2}

    def test_override_replaces_scalar(self, storage):
        """Override should replace scalar values."""
        base = {"a": 1}
        overrides = {"a": 99}
        result = storage._deep_merge(base, overrides)
        assert result == {"a": 99}

    def test_deep_merges_nested_dicts(self, storage):
        """Should recursively merge nested dictionaries."""
        base = {"simulation": {"start_year": 2025, "end_year": 2027}}
        overrides = {"simulation": {"start_year": 2026}}
        result = storage._deep_merge(base, overrides)
        assert result == {"simulation": {"start_year": 2026, "end_year": 2027}}

    def test_atomic_section_promotion_hazard(self, storage):
        """promotion_hazard should be replaced atomically, not deep-merged."""
        base = {
            "promotion_hazard": {
                "base_rate": 0.05,
                "level_dampener_factor": 0.1,
                "age_multipliers": [{"age_band": "25-34", "multiplier": 1.2}],
            }
        }
        overrides = {
            "promotion_hazard": {
                "base_rate": 0.08,
            }
        }
        result = storage._deep_merge(base, overrides)
        # Should be fully replaced, NOT merged
        assert result["promotion_hazard"] == {"base_rate": 0.08}
        assert "level_dampener_factor" not in result["promotion_hazard"]

    def test_atomic_section_age_bands(self, storage):
        """age_bands should be replaced atomically."""
        base = {"age_bands": [{"band_id": 1}]}
        overrides = {"age_bands": [{"band_id": 2}, {"band_id": 3}]}
        result = storage._deep_merge(base, overrides)
        assert result["age_bands"] == [{"band_id": 2}, {"band_id": 3}]

    def test_atomic_section_tenure_bands(self, storage):
        """tenure_bands should be replaced atomically."""
        base = {"tenure_bands": [{"band_id": 1}]}
        overrides = {"tenure_bands": [{"band_id": 5}]}
        result = storage._deep_merge(base, overrides)
        assert result["tenure_bands"] == [{"band_id": 5}]

    def test_non_atomic_dict_is_deep_merged(self, storage):
        """Regular dict sections should be deep-merged."""
        base = {"employer_match": {"active_formula": "simple", "match_rate": 0.5}}
        overrides = {"employer_match": {"match_rate": 0.75}}
        result = storage._deep_merge(base, overrides)
        assert result["employer_match"] == {
            "active_formula": "simple",
            "match_rate": 0.75,
        }

    def test_does_not_mutate_base(self, storage):
        """Should not mutate the base dictionary."""
        base = {"a": {"b": 1}}
        overrides = {"a": {"c": 2}}
        storage._deep_merge(base, overrides)
        assert base == {"a": {"b": 1}}

    def test_empty_overrides(self, storage):
        """Empty overrides should return a copy of base."""
        base = {"x": 1}
        result = storage._deep_merge(base, {})
        assert result == {"x": 1}
        assert result is not base


# ==================== _inject_seed_config_defaults ====================


@pytest.mark.fast
class TestInjectSeedConfigDefaults:
    """Tests for _inject_seed_config_defaults."""

    def test_skips_when_keys_already_present(self, storage):
        """Should not overwrite existing config keys."""
        merged = {
            "promotion_hazard": {"base_rate": 0.99},
            "age_bands": [{"band_id": 1}],
            "tenure_bands": [{"band_id": 1}],
        }

        # Even if the services raise, nothing should change since keys exist
        storage._inject_seed_config_defaults(merged)

        assert merged["promotion_hazard"]["base_rate"] == 0.99

    def test_injects_promotion_hazard_when_missing(self, storage):
        """Should inject promotion_hazard from CSV when key is absent."""
        mock_service = MagicMock()
        mock_config = MagicMock()
        mock_config.base.base_rate = 0.05
        mock_config.base.level_dampener_factor = 0.1
        mock_config.age_multipliers = []
        mock_config.tenure_multipliers = []
        mock_service.read_all.return_value = mock_config

        merged: Dict[str, Any] = {"age_bands": [], "tenure_bands": []}
        with patch(
            "planalign_api.services.promotion_hazard_service.PromotionHazardService",
            return_value=mock_service,
        ):
            storage._inject_seed_config_defaults(merged)

        assert "promotion_hazard" in merged
        assert merged["promotion_hazard"]["base_rate"] == 0.05

    def test_injects_bands_when_missing(self, storage):
        """Should inject age_bands and tenure_bands from CSV when absent."""
        mock_service = MagicMock()
        mock_band_config = MagicMock()
        mock_age_band = MagicMock()
        mock_age_band.band_id = 1
        mock_age_band.band_label = "25-34"
        mock_age_band.min_value = 25
        mock_age_band.max_value = 35
        mock_age_band.display_order = 1
        mock_band_config.age_bands = [mock_age_band]

        mock_tenure_band = MagicMock()
        mock_tenure_band.band_id = 1
        mock_tenure_band.band_label = "0-2"
        mock_tenure_band.min_value = 0
        mock_tenure_band.max_value = 2
        mock_tenure_band.display_order = 1
        mock_band_config.tenure_bands = [mock_tenure_band]

        mock_service.read_band_configs.return_value = mock_band_config

        merged: Dict[str, Any] = {"promotion_hazard": {}}
        with patch(
            "planalign_api.services.promotion_hazard_service.PromotionHazardService"
        ), patch(
            "planalign_api.services.band_service.BandService",
            return_value=mock_service,
        ):
            storage._inject_seed_config_defaults(merged)

        assert len(merged["age_bands"]) == 1
        assert merged["age_bands"][0]["band_label"] == "25-34"
        assert len(merged["tenure_bands"]) == 1
        assert merged["tenure_bands"][0]["band_label"] == "0-2"

    def test_handles_promotion_hazard_error_gracefully(self, storage):
        """Should not raise when promotion hazard service fails."""
        merged: Dict[str, Any] = {}
        with patch(
            "planalign_api.services.promotion_hazard_service.PromotionHazardService",
            side_effect=Exception("CSV not found"),
        ):
            storage._inject_seed_config_defaults(merged)
        assert "promotion_hazard" not in merged

    def test_handles_band_service_error_gracefully(self, storage):
        """Should not raise when band service fails."""
        merged: Dict[str, Any] = {"promotion_hazard": {}}
        with patch(
            "planalign_api.services.promotion_hazard_service.PromotionHazardService"
        ), patch(
            "planalign_api.services.band_service.BandService",
            side_effect=Exception("band CSV not found"),
        ):
            storage._inject_seed_config_defaults(merged)
        assert "age_bands" not in merged
        assert "tenure_bands" not in merged
