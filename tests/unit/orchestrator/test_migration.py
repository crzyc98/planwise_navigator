"""Tests for planalign_orchestrator.migration module.

Covers MigrationManager config-compatibility reporting, checkpoint directory
migration (including corrupt-file sweeping), and checkpoint listing.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from planalign_orchestrator.migration import MigrationManager, MigrationResult

pytestmark = pytest.mark.fast


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_config(*, scenario_id="s1", plan_design_id="p1", start=2025, end=2027):
    """Build a minimal stand-in for a loaded SimulationConfig."""
    return SimpleNamespace(
        scenario_id=scenario_id,
        plan_design_id=plan_design_id,
        simulation=SimpleNamespace(start_year=start, end_year=end),
    )


def _write_checkpoint(directory: Path, name: str, payload: dict | str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / name
    p.write_text(payload if isinstance(payload, str) else json.dumps(payload))
    return p


# ---------------------------------------------------------------------------
# validate_config_compatibility
# ---------------------------------------------------------------------------


def test_validate_config_compatibility_reports_identifiers_and_years():
    mgr = MigrationManager(checkpoints_dir=Path("unused"))
    with patch(
        "planalign_orchestrator.migration.load_simulation_config",
        return_value=_fake_config(),
    ) as loader:
        report = mgr.validate_config_compatibility("cfg.yaml")

    loader.assert_called_once()
    assert report["has_identifiers"] is True
    assert report["simulation_years"] == (2025, 2027)


def test_validate_config_compatibility_flags_missing_identifiers():
    mgr = MigrationManager(checkpoints_dir=Path("unused"))
    with patch(
        "planalign_orchestrator.migration.load_simulation_config",
        return_value=_fake_config(scenario_id="", plan_design_id=""),
    ):
        report = mgr.validate_config_compatibility("cfg.yaml")

    assert report["has_identifiers"] is False


# ---------------------------------------------------------------------------
# migrate_checkpoints
# ---------------------------------------------------------------------------


def test_migrate_checkpoints_creates_dir_when_missing(tmp_path):
    # mkdir(exist_ok=True) is used without parents=True, so the parent must exist.
    target = tmp_path / "checkpoints"
    mgr = MigrationManager(checkpoints_dir=target)

    result = mgr.migrate_checkpoints()

    assert result.success is True
    assert target.exists()
    assert result.completed_steps == ["checkpoints_dir"]


def test_migrate_checkpoints_sweeps_corrupt_json(tmp_path):
    cp = tmp_path / "cp"
    _write_checkpoint(cp, "year_2025.json", {"year": 2025})
    _write_checkpoint(cp, "year_2026.json", "{ not valid json")

    mgr = MigrationManager(checkpoints_dir=cp)
    result = mgr.migrate_checkpoints()

    assert result.success is True
    # Valid file retained, corrupt file removed and reported
    assert (cp / "year_2025.json").exists()
    assert not (cp / "year_2026.json").exists()
    assert "year_2026.json" in result.completed_steps


def test_migrate_checkpoints_returns_error_on_failure(tmp_path):
    mgr = MigrationManager(checkpoints_dir=tmp_path / "cp")
    with patch.object(Path, "mkdir", side_effect=OSError("disk full")):
        result = mgr.migrate_checkpoints()

    assert isinstance(result, MigrationResult)
    assert result.success is False
    assert "disk full" in result.error


# ---------------------------------------------------------------------------
# list_checkpoints
# ---------------------------------------------------------------------------


def test_list_checkpoints_returns_sorted_payloads(tmp_path):
    cp = tmp_path / "cp"
    _write_checkpoint(cp, "year_2026.json", {"completed": True})
    _write_checkpoint(cp, "year_2025.json", {"completed": False})

    mgr = MigrationManager(checkpoints_dir=cp)
    rows = mgr.list_checkpoints()

    assert [r["file"] for r in rows] == ["year_2025.json", "year_2026.json"]
    assert rows[0]["completed"] is False
    assert rows[1]["completed"] is True


def test_list_checkpoints_marks_unreadable_files(tmp_path):
    cp = tmp_path / "cp"
    _write_checkpoint(cp, "year_2025.json", "}{ broken")

    mgr = MigrationManager(checkpoints_dir=cp)
    rows = mgr.list_checkpoints()

    assert rows == [{"file": "year_2025.json", "error": "unreadable"}]


def test_list_checkpoints_empty_when_no_dir(tmp_path):
    mgr = MigrationManager(checkpoints_dir=tmp_path / "missing")
    assert mgr.list_checkpoints() == []
