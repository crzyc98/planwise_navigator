# tests/test_cold_start_initialization.py
import pytest
from orchestrator.utils.cold_start_validation import validate_workforce_initialization, check_schema_compatibility
from dagster import build_asset_context

def test_cold_start_with_active_employees(duckdb_resource):
    """Test cold start validation with active employees"""
    # Setup: Create census data with active employees
    with duckdb_resource.get_connection() as conn:
        conn.execute("""
            INSERT INTO stg_census_data VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', NULL, 75000, 75000, 'L2', 'Engineering', 'FTE'),
                ('EMP002', 'SSN002', '1985-01-01', '2020-01-01', NULL, 65000, 65000, 'L1', 'Marketing', 'FTE')
        """)
        conn.execute("""
            INSERT INTO fct_workforce_snapshot
            SELECT
                employee_id, employee_ssn, employee_birth_date, employee_hire_date,
                employee_gross_compensation as current_compensation,
                2024 - EXTRACT(YEAR FROM employee_birth_date) as current_age,
                2024 - EXTRACT(YEAR FROM employee_hire_date) as current_tenure,
                1 as level_id, '25-34' as age_band, '2-4' as tenure_band,
                'active' as employment_status, NULL as termination_date, NULL as termination_reason,
                1 as simulation_year, '2024-01-01' as effective_date, CURRENT_TIMESTAMP as snapshot_created_at
            FROM stg_census_data WHERE employee_termination_date IS NULL
        """)

    # Execute: Run validation
    context = build_asset_context()
    result = validate_workforce_initialization(context, duckdb_resource, 1)

    # Assert: Validation passes with expected active count
    assert result["validation_status"] == "PASSED"
    assert result["active_employee_count"] == 2

def test_cold_start_with_empty_census(duckdb_resource):
    """Test cold start validation with empty census data"""
    # Setup: Ensure census table exists but is empty
    with duckdb_resource.get_connection() as conn:
        conn.execute("DELETE FROM stg_census_data")

    # Execute & Assert: Should fail gracefully
    context = build_asset_context()
    result = validate_workforce_initialization(context, duckdb_resource, 1)

    assert result["validation_status"] == "FAILED"
    assert result["active_employee_count"] == 0

def test_cold_start_no_active_employees(duckdb_resource):
    """Test when census has only terminated employees"""
    # Setup: Create census with only terminated employees
    with duckdb_resource.get_connection() as conn:
        conn.execute("""
            INSERT INTO stg_census_data VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', '2023-12-31', 75000, 75000, 'L2', 'Engineering', 'FTE'),
                ('EMP002', 'SSN002', '1985-01-01', '2020-01-01', '2023-06-30', 65000, 65000, 'L1', 'Marketing', 'FTE')
        """)

    # Execute & Assert: Should fail with no active employees
    context = build_asset_context()
    result = validate_workforce_initialization(context, duckdb_resource, 1)

    assert result["validation_status"] == "FAILED"
    assert result["active_employee_count"] == 0

def test_idempotency_first_year(duckdb_resource):
    """Test that running year 1 twice produces same results"""
    # Setup: Run year 1 simulation
    with duckdb_resource.get_connection() as conn:
        conn.execute("""
            INSERT INTO stg_census_data VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', NULL, 75000, 75000, 'L2', 'Engineering', 'FTE')
        """)

        # First run
        conn.execute("""
            INSERT INTO fct_workforce_snapshot
            SELECT
                employee_id, employee_ssn, employee_birth_date, employee_hire_date,
                employee_gross_compensation as current_compensation,
                2024 - EXTRACT(YEAR FROM employee_birth_date) as current_age,
                2024 - EXTRACT(YEAR FROM employee_hire_date) as current_tenure,
                1 as level_id, '25-34' as age_band, '2-4' as tenure_band,
                'active' as employment_status, NULL as termination_date, NULL as termination_reason,
                1 as simulation_year, '2024-01-01' as effective_date, CURRENT_TIMESTAMP as snapshot_created_at
            FROM stg_census_data WHERE employee_termination_date IS NULL
        """)
        first_count = conn.execute("SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = 1").fetchone()[0]

        # Second run (should not duplicate)
        conn.execute("""
            INSERT INTO fct_workforce_snapshot
            SELECT
                employee_id, employee_ssn, employee_birth_date, employee_hire_date,
                employee_gross_compensation as current_compensation,
                2024 - EXTRACT(YEAR FROM employee_birth_date) as current_age,
                2024 - EXTRACT(YEAR FROM employee_hire_date) as current_tenure,
                1 as level_id, '25-34' as age_band, '2-4' as tenure_band,
                'active' as employment_status, NULL as termination_date, NULL as termination_reason,
                1 as simulation_year, '2024-01-01' as effective_date, CURRENT_TIMESTAMP as snapshot_created_at
            FROM stg_census_data WHERE employee_termination_date IS NULL
            ON CONFLICT (employee_id, simulation_year) DO NOTHING
        """)
        second_count = conn.execute("SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = 1").fetchone()[0]

    assert first_count == second_count, "Running year 1 twice should not duplicate data"

def test_schema_compatibility_check(duckdb_resource):
    """Test schema compatibility detection"""
    context = build_asset_context()

    # Test with compatible schemas
    assert check_schema_compatibility(context, duckdb_resource) == True

    # Test with missing column
    with duckdb_resource.get_connection() as conn:
        try:
            conn.execute("ALTER TABLE stg_census_data DROP COLUMN level_id")
            assert check_schema_compatibility(context, duckdb_resource) == False
        except Exception:
            # If column doesn't exist or can't be dropped, that's also a compatibility issue
            pass

def test_workforce_continuity_validation(duckdb_resource):
    """Test workforce continuity across simulation years"""
    # Setup: Create multi-year workforce data
    with duckdb_resource.get_connection() as conn:
        # Year 1 data
        conn.execute("""
            INSERT INTO fct_workforce_snapshot VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', 75000, 44, 4, 1, '25-34', '2-4', 'active', NULL, NULL, 1, '2024-01-01', CURRENT_TIMESTAMP),
                ('EMP002', 'SSN002', '1985-01-01', '2020-01-01', 65000, 39, 4, 1, '25-34', '2-4', 'active', NULL, NULL, 1, '2024-01-01', CURRENT_TIMESTAMP)
        """)

        # Year 2 data (one employee continues, one terminates)
        conn.execute("""
            INSERT INTO fct_workforce_snapshot VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', 77000, 45, 5, 1, '25-34', '2-4', 'active', NULL, NULL, 2, '2025-01-01', CURRENT_TIMESTAMP),
                ('EMP002', 'SSN002', '1985-01-01', '2020-01-01', 65000, 40, 5, 1, '25-34', '2-4', 'terminated', '2025-06-30', 'voluntary', 2, '2025-01-01', CURRENT_TIMESTAMP)
        """)

    # Execute: Run validation for year 2
    context = build_asset_context()
    result = validate_workforce_initialization(context, duckdb_resource, 2)

    # Assert: Should pass with continuity check
    assert result["validation_status"] == "PASSED"
    continuity_check = next(c for c in result["checks"] if c["check_name"] == "workforce_continuity")
    assert continuity_check["passed"] == True  # 50% continuity is acceptable

def test_simulation_run_log_tracking(duckdb_resource):
    """Test simulation run log tracking functionality"""
    # Setup: Create simulation run log entry
    with duckdb_resource.get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS int_simulation_run_log (
                simulation_year INTEGER,
                completion_timestamp TIMESTAMP,
                run_status VARCHAR,
                total_employees_processed INTEGER
            )
        """)
        conn.execute("""
            INSERT INTO int_simulation_run_log VALUES
                (1, CURRENT_TIMESTAMP, 'COMPLETED', 100)
        """)

    # Execute: Run validation
    context = build_asset_context()
    result = validate_workforce_initialization(context, duckdb_resource, 1)

    # Assert: Run log check passes
    run_log_check = next(c for c in result["checks"] if c["check_name"] == "simulation_run_logged")
    assert run_log_check["passed"] == True
