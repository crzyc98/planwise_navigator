"""Tests for census path validation in SimulationService._validate_census().

Covers:
- US1: Valid census file path → success (no error)
- US2: Missing/empty/whitespace/None census_parquet_path → ConfigurationError
- US3: Non-existent file at configured path → ConfigurationError
- US4: Relative paths resolve against the workspace directory
- US5: Stale scenario path falls back to the workspace base-config census
"""

from pathlib import Path

import pytest

from planalign_api.services.simulation.service import SimulationService
from planalign_api.storage.workspace_storage import WorkspaceStorage
from planalign_orchestrator.exceptions import ConfigurationError


def make_service(tmp_path) -> SimulationService:
    """Build a SimulationService with storage rooted at tmp_path (no workspaces)."""
    service = SimulationService.__new__(SimulationService)
    service.storage = WorkspaceStorage(Path(tmp_path))
    return service


# ---------------------------------------------------------------------------
# US1: Happy path — valid census file
# ---------------------------------------------------------------------------


@pytest.mark.fast
def test_validate_census_valid_path(tmp_path):
    """Valid census file path passes validation without error."""
    census_file = tmp_path / "census.parquet"
    census_file.write_bytes(b"PAR1dummy")

    config = {"setup": {"census_parquet_path": str(census_file)}}
    # Should not raise
    make_service(tmp_path)._validate_census(
        config, scenario_id="test_scenario", workspace_id="test_workspace"
    )


@pytest.mark.fast
def test_validate_census_valid_path_rewritten_absolute(tmp_path):
    """Validation persists the resolved absolute path back into the config."""
    census_file = tmp_path / "census.parquet"
    census_file.write_bytes(b"PAR1dummy")

    config = {"setup": {"census_parquet_path": str(census_file)}}
    make_service(tmp_path)._validate_census(
        config, scenario_id="test_scenario", workspace_id="test_workspace"
    )
    assert Path(config["setup"]["census_parquet_path"]).is_absolute()


# ---------------------------------------------------------------------------
# US2: Missing / empty / whitespace / None census_parquet_path
# ---------------------------------------------------------------------------


@pytest.mark.fast
def test_validate_census_missing_key(tmp_path):
    """Missing census_parquet_path key raises ConfigurationError."""
    config = {"setup": {}}

    with pytest.raises(ConfigurationError, match="census_parquet_path is required"):
        make_service(tmp_path)._validate_census(
            config, scenario_id="test_scenario", workspace_id="test_workspace"
        )


@pytest.mark.fast
def test_validate_census_empty_string(tmp_path):
    """Empty string census_parquet_path raises ConfigurationError."""
    config = {"setup": {"census_parquet_path": ""}}

    with pytest.raises(ConfigurationError, match="census_parquet_path is required"):
        make_service(tmp_path)._validate_census(
            config, scenario_id="test_scenario", workspace_id="test_workspace"
        )


@pytest.mark.fast
def test_validate_census_whitespace_only(tmp_path):
    """Whitespace-only census_parquet_path raises ConfigurationError."""
    config = {"setup": {"census_parquet_path": "   "}}

    with pytest.raises(ConfigurationError, match="census_parquet_path is required"):
        make_service(tmp_path)._validate_census(
            config, scenario_id="test_scenario", workspace_id="test_workspace"
        )


@pytest.mark.fast
def test_validate_census_none_value(tmp_path):
    """None census_parquet_path raises ConfigurationError."""
    config = {"setup": {"census_parquet_path": None}}

    with pytest.raises(ConfigurationError, match="census_parquet_path is required"):
        make_service(tmp_path)._validate_census(
            config, scenario_id="test_scenario", workspace_id="test_workspace"
        )


@pytest.mark.fast
def test_validate_census_error_context(tmp_path):
    """ConfigurationError includes metadata with missing_field info."""
    config = {"setup": {}}

    with pytest.raises(ConfigurationError) as exc_info:
        make_service(tmp_path)._validate_census(
            config, scenario_id="test_scenario", workspace_id="test_workspace"
        )

    err = exc_info.value
    assert err.context.scenario_id == "test_scenario"
    assert err.context.metadata["missing_field"] == "setup.census_parquet_path"
    assert err.context.metadata["workspace_id"] == "test_workspace"


# ---------------------------------------------------------------------------
# US3: File not found at configured path
# ---------------------------------------------------------------------------


@pytest.mark.fast
def test_validate_census_file_not_found(tmp_path):
    """Non-existent file path raises ConfigurationError."""
    config = {"setup": {"census_parquet_path": "/nonexistent/path/census.parquet"}}

    with pytest.raises(ConfigurationError, match="Census file not found at"):
        make_service(tmp_path)._validate_census(
            config, scenario_id="test_scenario", workspace_id="test_workspace"
        )


@pytest.mark.fast
def test_validate_census_file_not_found_includes_path(tmp_path):
    """Error message includes the actual configured path for debugging."""
    bad_path = "/nonexistent/path/census.parquet"
    config = {"setup": {"census_parquet_path": bad_path}}

    with pytest.raises(ConfigurationError, match=bad_path):
        make_service(tmp_path)._validate_census(
            config, scenario_id="test_scenario", workspace_id="test_workspace"
        )


@pytest.mark.fast
def test_validate_census_file_not_found_context(tmp_path):
    """ConfigurationError for missing file includes expected_path in context."""
    bad_path = "/nonexistent/path/census.parquet"
    config = {"setup": {"census_parquet_path": bad_path}}

    with pytest.raises(ConfigurationError) as exc_info:
        make_service(tmp_path)._validate_census(
            config, scenario_id="test_scenario", workspace_id="test_workspace"
        )

    err = exc_info.value
    assert err.context.scenario_id == "test_scenario"
    assert err.context.metadata["expected_path"] == bad_path
    assert err.context.metadata["workspace_id"] == "test_workspace"


# ---------------------------------------------------------------------------
# US4: Relative paths resolve against the workspace directory
# ---------------------------------------------------------------------------


@pytest.mark.fast
def test_validate_census_relative_path_resolves_to_workspace(tmp_path):
    """A workspace-relative path (e.g. data/census.parquet) resolves and passes."""
    workspace_dir = tmp_path / "ws1"
    (workspace_dir / "data").mkdir(parents=True)
    census_file = workspace_dir / "data" / "census.parquet"
    census_file.write_bytes(b"PAR1dummy")

    config = {"setup": {"census_parquet_path": "data/census.parquet"}}
    make_service(tmp_path)._validate_census(
        config, scenario_id="test_scenario", workspace_id="ws1"
    )
    assert config["setup"]["census_parquet_path"] == str(census_file.resolve())


# ---------------------------------------------------------------------------
# US5: Stale scenario path falls back to workspace base-config census
# ---------------------------------------------------------------------------


@pytest.mark.fast
def test_validate_census_stale_path_falls_back_to_workspace_census(tmp_path):
    """A stale/placeholder scenario path falls back to the workspace census."""
    import json

    import yaml

    workspace_dir = tmp_path / "ws1"
    (workspace_dir / "data").mkdir(parents=True)
    census_file = workspace_dir / "data" / "census.parquet"
    census_file.write_bytes(b"PAR1dummy")
    (workspace_dir / "workspace.json").write_text(
        json.dumps(
            {
                "id": "ws1",
                "name": "ws1",
                "description": "",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            }
        )
    )
    (workspace_dir / "base_config.yaml").write_text(
        yaml.dump({"setup": {"census_parquet_path": str(census_file)}})
    )

    # Stale placeholder persisted by older studio builds
    config = {"setup": {"census_parquet_path": "data/census_preprocessed.parquet"}}
    make_service(tmp_path)._validate_census(
        config, scenario_id="test_scenario", workspace_id="ws1"
    )
    assert config["setup"]["census_parquet_path"] == str(census_file.resolve())
