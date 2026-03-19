"""Tests for census path validation in SimulationService._validate_census().

Covers:
- US1: Valid census file path → success (no error)
- US2: Missing/empty/whitespace/None census_parquet_path → ConfigurationError
- US3: Non-existent file at configured path → ConfigurationError
"""

import pytest

from planalign_api.services.simulation.service import SimulationService
from planalign_orchestrator.exceptions import ConfigurationError


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
    SimulationService._validate_census(
        config, scenario_id="test_scenario", workspace_id="test_workspace"
    )


# ---------------------------------------------------------------------------
# US2: Missing / empty / whitespace / None census_parquet_path
# ---------------------------------------------------------------------------

@pytest.mark.fast
def test_validate_census_missing_key():
    """Missing census_parquet_path key raises ConfigurationError."""
    config = {"setup": {}}

    with pytest.raises(ConfigurationError, match="census_parquet_path is required"):
        SimulationService._validate_census(
            config, scenario_id="test_scenario", workspace_id="test_workspace"
        )


@pytest.mark.fast
def test_validate_census_empty_string():
    """Empty string census_parquet_path raises ConfigurationError."""
    config = {"setup": {"census_parquet_path": ""}}

    with pytest.raises(ConfigurationError, match="census_parquet_path is required"):
        SimulationService._validate_census(
            config, scenario_id="test_scenario", workspace_id="test_workspace"
        )


@pytest.mark.fast
def test_validate_census_whitespace_only():
    """Whitespace-only census_parquet_path raises ConfigurationError."""
    config = {"setup": {"census_parquet_path": "   "}}

    with pytest.raises(ConfigurationError, match="census_parquet_path is required"):
        SimulationService._validate_census(
            config, scenario_id="test_scenario", workspace_id="test_workspace"
        )


@pytest.mark.fast
def test_validate_census_none_value():
    """None census_parquet_path raises ConfigurationError."""
    config = {"setup": {"census_parquet_path": None}}

    with pytest.raises(ConfigurationError, match="census_parquet_path is required"):
        SimulationService._validate_census(
            config, scenario_id="test_scenario", workspace_id="test_workspace"
        )


@pytest.mark.fast
def test_validate_census_error_context():
    """ConfigurationError includes metadata with missing_field info."""
    config = {"setup": {}}

    with pytest.raises(ConfigurationError) as exc_info:
        SimulationService._validate_census(
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
def test_validate_census_file_not_found():
    """Non-existent file path raises ConfigurationError."""
    config = {"setup": {"census_parquet_path": "/nonexistent/path/census.parquet"}}

    with pytest.raises(ConfigurationError, match="Census file not found at"):
        SimulationService._validate_census(
            config, scenario_id="test_scenario", workspace_id="test_workspace"
        )


@pytest.mark.fast
def test_validate_census_file_not_found_includes_path():
    """Error message includes the actual configured path for debugging."""
    bad_path = "/nonexistent/path/census.parquet"
    config = {"setup": {"census_parquet_path": bad_path}}

    with pytest.raises(ConfigurationError, match=bad_path):
        SimulationService._validate_census(
            config, scenario_id="test_scenario", workspace_id="test_workspace"
        )


@pytest.mark.fast
def test_validate_census_file_not_found_context():
    """ConfigurationError for missing file includes expected_path in context."""
    bad_path = "/nonexistent/path/census.parquet"
    config = {"setup": {"census_parquet_path": bad_path}}

    with pytest.raises(ConfigurationError) as exc_info:
        SimulationService._validate_census(
            config, scenario_id="test_scenario", workspace_id="test_workspace"
        )

    err = exc_info.value
    assert err.context.scenario_id == "test_scenario"
    assert err.context.metadata["expected_path"] == bad_path
    assert err.context.metadata["workspace_id"] == "test_workspace"
