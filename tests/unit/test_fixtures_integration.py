"""
Test fixtures integration - verify new fixture library works correctly.

This test validates that the new tests/fixtures/ library is properly
integrated and functional for unit testing.
"""

import pytest
from tests.fixtures import (
    in_memory_db,
    populated_test_db,
    minimal_config,
    single_threaded_config,
    mock_dbt_runner,
    sample_employees,
    baseline_workforce_df,
)


@pytest.mark.fast
@pytest.mark.unit
def test_in_memory_db_fixture(in_memory_db):
    """Test in-memory database fixture creates clean database."""
    # Verify tables exist
    tables = in_memory_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = [t[0] for t in tables]

    assert "fct_yearly_events" in table_names
    assert "fct_workforce_snapshot" in table_names

    # Verify database is empty initially
    count = in_memory_db.execute("SELECT COUNT(*) FROM fct_yearly_events").fetchone()
    assert count[0] == 0


@pytest.mark.fast
@pytest.mark.unit
def test_populated_test_db_fixture(populated_test_db):
    """Test populated database fixture has sample data."""
    # Verify workforce snapshot has 100 employees
    workforce_count = populated_test_db.execute(
        "SELECT COUNT(*) FROM fct_workforce_snapshot"
    ).fetchone()
    assert workforce_count[0] == 100

    # Verify yearly events has 50 events
    events_count = populated_test_db.execute(
        "SELECT COUNT(*) FROM fct_yearly_events"
    ).fetchone()
    assert events_count[0] == 50

    # Verify event type distribution
    event_types = populated_test_db.execute(
        "SELECT DISTINCT event_type FROM fct_yearly_events ORDER BY event_type"
    ).fetchall()
    assert len(event_types) == 3
    assert {t[0] for t in event_types} == {"hire", "termination", "promotion"}


@pytest.mark.fast
@pytest.mark.unit
@pytest.mark.config
def test_minimal_config_fixture(minimal_config):
    """Test minimal configuration fixture is valid."""
    assert minimal_config.simulation.start_year == 2025
    assert minimal_config.simulation.end_year == 2026
    assert minimal_config.simulation.random_seed == 42
    assert minimal_config.scenario_id == "test_scenario"
    assert minimal_config.plan_design_id == "test_plan"


@pytest.mark.fast
@pytest.mark.unit
@pytest.mark.config
def test_single_threaded_config_fixture(single_threaded_config):
    """Test single-threaded configuration is properly configured."""
    # Config fixture loads from YAML and modifies optimization settings
    assert single_threaded_config.scenario_id == "test_scenario"
    assert single_threaded_config.plan_design_id == "test_plan"
    # Verify it's a valid configuration object
    assert hasattr(single_threaded_config, 'simulation')
    assert hasattr(single_threaded_config, 'compensation')


@pytest.mark.fast
@pytest.mark.unit
def test_mock_dbt_runner_fixture(mock_dbt_runner):
    """Test mock dbt runner returns successful results."""
    result = mock_dbt_runner.execute_command(["run", "--select", "test_model"])

    assert result.success is True
    assert result.return_code == 0
    assert "Completed successfully" in result.stdout
    mock_dbt_runner.execute_command.assert_called_once()


@pytest.mark.fast
@pytest.mark.unit
def test_sample_employees_fixture(sample_employees):
    """Test sample employees fixture generates correct data."""
    assert len(sample_employees) == 100

    # Verify all employees have required fields
    for emp in sample_employees:
        assert "employee_id" in emp
        assert "hire_date" in emp
        assert "base_salary" in emp
        assert "job_band" in emp
        assert "department" in emp
        assert "is_active" in emp

    # Verify employee IDs are unique
    employee_ids = [emp["employee_id"] for emp in sample_employees]
    assert len(set(employee_ids)) == 100


@pytest.mark.fast
@pytest.mark.unit
def test_baseline_workforce_df_fixture(baseline_workforce_df):
    """Test baseline workforce DataFrame fixture."""
    assert len(baseline_workforce_df) == 100
    assert "employee_id" in baseline_workforce_df.columns
    assert "base_salary" in baseline_workforce_df.columns
    assert "department" in baseline_workforce_df.columns

    # Verify data types (allow both object and StringDtype for pandas compatibility)
    assert str(baseline_workforce_df["employee_id"].dtype) in ["object", "str", "string"]
    assert baseline_workforce_df["base_salary"].dtype in [int, float]
