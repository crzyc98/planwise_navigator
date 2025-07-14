# tests/integration/test_multi_year_cold_start.py
import pytest
from orchestrator.utils.cold_start_validation import validate_workforce_initialization
from dagster import build_asset_context

def test_multi_year_simulation_cold_start(fresh_database):
    """Test complete multi-year simulation on fresh database"""
    # Setup: Fresh database with census data only
    with fresh_database.get_connection() as conn:
        # Create census data with diverse employee profiles
        conn.execute("""
            INSERT INTO stg_census_data VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', NULL, 75000, 75000, 'L2', 'Engineering', 'FTE'),
                ('EMP002', 'SSN002', '1985-01-01', '2021-01-01', NULL, 65000, 65000, 'L1', 'Marketing', 'FTE'),
                ('EMP003', 'SSN003', '1975-01-01', '2018-01-01', NULL, 90000, 90000, 'L3', 'Sales', 'FTE'),
                ('EMP004', 'SSN004', '1990-01-01', '2022-01-01', NULL, 55000, 55000, 'L1', 'Support', 'FTE')
        """)

        # Simulate 3-year cold start progression
        for year in range(1, 4):
            # Create workforce snapshot for each year
            conn.execute(f"""
                INSERT INTO fct_workforce_snapshot
                SELECT
                    employee_id, employee_ssn, employee_birth_date, employee_hire_date,
                    employee_gross_compensation * (1 + 0.03 * ({year} - 1)) as current_compensation,
                    2024 + {year} - 1 - EXTRACT(YEAR FROM employee_birth_date) as current_age,
                    2024 + {year} - 1 - EXTRACT(YEAR FROM employee_hire_date) as current_tenure,
                    1 as level_id, '25-34' as age_band, '2-4' as tenure_band,
                    'active' as employment_status, NULL as termination_date, NULL as termination_reason,
                    {year} as simulation_year, '{2024 + year - 1}-01-01' as effective_date, CURRENT_TIMESTAMP as snapshot_created_at
                FROM stg_census_data WHERE employee_termination_date IS NULL
            """)

            # Execute: Run validation for each year
            context = build_asset_context()
            result = validate_workforce_initialization(context, fresh_database, year)

            # Assert: All years complete successfully with active employees
            assert result["validation_status"] == "PASSED", f"Year {year} validation failed"
            assert result["active_employee_count"] > 0, f"Year {year} has no active employees"

def test_workforce_continuity_across_years(fresh_database):
    """Test workforce state continuity across simulation years"""
    # Setup: Fresh database with census data
    with fresh_database.get_connection() as conn:
        conn.execute("""
            INSERT INTO stg_census_data VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', NULL, 75000, 75000, 'L2', 'Engineering', 'FTE'),
                ('EMP002', 'SSN002', '1985-01-01', '2021-01-01', NULL, 65000, 65000, 'L1', 'Marketing', 'FTE')
        """)

        # Year 1: Both employees active
        conn.execute("""
            INSERT INTO fct_workforce_snapshot VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', 75000, 44, 4, 1, '25-34', '2-4', 'active', NULL, NULL, 1, '2024-01-01', CURRENT_TIMESTAMP),
                ('EMP002', 'SSN002', '1985-01-01', '2021-01-01', 65000, 39, 3, 1, '25-34', '2-4', 'active', NULL, NULL, 1, '2024-01-01', CURRENT_TIMESTAMP)
        """)

        # Year 2: One employee terminates, one continues
        conn.execute("""
            INSERT INTO fct_workforce_snapshot VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', 77000, 45, 5, 1, '25-34', '2-4', 'active', NULL, NULL, 2, '2025-01-01', CURRENT_TIMESTAMP),
                ('EMP002', 'SSN002', '1985-01-01', '2021-01-01', 65000, 40, 4, 1, '25-34', '2-4', 'terminated', '2025-06-30', 'voluntary', 2, '2025-01-01', CURRENT_TIMESTAMP)
        """)

        # Year 3: Remaining employee continues
        conn.execute("""
            INSERT INTO fct_workforce_snapshot VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', 79000, 46, 6, 1, '25-34', '2-4', 'active', NULL, NULL, 3, '2026-01-01', CURRENT_TIMESTAMP)
        """)

    # Execute: Run multi-year validation
    context = build_asset_context()

    # Test year 1 (no continuity check)
    result_year1 = validate_workforce_initialization(context, fresh_database, 1)
    assert result_year1["validation_status"] == "PASSED"
    assert result_year1["active_employee_count"] == 2

    # Test year 2 (should have continuity)
    result_year2 = validate_workforce_initialization(context, fresh_database, 2)
    assert result_year2["validation_status"] == "PASSED"
    continuity_check = next(c for c in result_year2["checks"] if c["check_name"] == "workforce_continuity")
    assert continuity_check["passed"] == True  # 50% continuity is acceptable

    # Test year 3 (should maintain continuity)
    result_year3 = validate_workforce_initialization(context, fresh_database, 3)
    assert result_year3["validation_status"] == "PASSED"
    continuity_check = next(c for c in result_year3["checks"] if c["check_name"] == "workforce_continuity")
    assert continuity_check["passed"] == True  # 100% continuity from year 2 to 3

def test_cold_start_edge_cases(fresh_database):
    """Test edge cases for cold start scenarios"""
    context = build_asset_context()

    # Test 1: Empty database
    result_empty = validate_workforce_initialization(context, fresh_database, 1)
    assert result_empty["validation_status"] == "FAILED"
    assert result_empty["active_employee_count"] == 0

    # Test 2: Single employee
    with fresh_database.get_connection() as conn:
        conn.execute("""
            INSERT INTO stg_census_data VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', NULL, 75000, 75000, 'L2', 'Engineering', 'FTE')
        """)
        conn.execute("""
            INSERT INTO fct_workforce_snapshot VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', 75000, 44, 4, 1, '25-34', '2-4', 'active', NULL, NULL, 1, '2024-01-01', CURRENT_TIMESTAMP)
        """)

    result_single = validate_workforce_initialization(context, fresh_database, 1)
    assert result_single["validation_status"] == "PASSED"
    assert result_single["active_employee_count"] == 1

    # Test 3: All employees terminated
    with fresh_database.get_connection() as conn:
        conn.execute("UPDATE fct_workforce_snapshot SET employment_status = 'terminated', termination_date = '2024-06-30'")

    result_terminated = validate_workforce_initialization(context, fresh_database, 1)
    assert result_terminated["validation_status"] == "FAILED"
    assert result_terminated["active_employee_count"] == 0

def test_performance_benchmark_cold_start(fresh_database):
    """Test performance benchmarks for cold start initialization"""
    import time

    # Setup: Create 1000 employees for performance testing
    with fresh_database.get_connection() as conn:
        for i in range(1000):
            conn.execute(f"""
                INSERT INTO stg_census_data VALUES
                    ('EMP{i:04d}', 'SSN{i:04d}', '1980-01-01', '2020-01-01', NULL,
                     {50000 + (i % 50000)}, {50000 + (i % 50000)}, 'L{(i % 3) + 1}',
                     'Dept{i % 10}', 'FTE')
            """)

        # Measure cold start initialization time
        start_time = time.time()

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

        end_time = time.time()
        initialization_time = end_time - start_time

    # Execute: Run validation
    context = build_asset_context()
    result = validate_workforce_initialization(context, fresh_database, 1)

    # Assert: Performance benchmark (<30 seconds for 1000 employees)
    assert initialization_time < 30.0, f"Cold start initialization took {initialization_time:.2f}s, exceeding 30s target"
    assert result["validation_status"] == "PASSED"
    assert result["active_employee_count"] == 1000
