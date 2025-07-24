# tests/integration/test_multi_year_cold_start.py
import pytest
from orchestrator_mvp.core.multi_year_orchestrator import MultiYearSimulationOrchestrator
from orchestrator_mvp.core.multi_year_simulation import validate_multi_year_data_integrity

def test_multi_year_simulation_data_persistence(fresh_database):
    """Test multi-year simulation with data persistence across years"""
    # Setup: Configuration for 3-year simulation
    config = {
        'target_growth_rate': 0.03,
        'random_seed': 42,
        'workforce': {
            'total_termination_rate': 0.12,
            'new_hire_termination_rate': 0.25
        }
    }

    with fresh_database.get_connection() as conn:
        # Create baseline workforce data
        conn.execute("""
            INSERT INTO stg_census_data VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', NULL, 75000, 75000, 'L2', 'Engineering', 'FTE'),
                ('EMP002', 'SSN002', '1985-01-01', '2021-01-01', NULL, 65000, 65000, 'L1', 'Marketing', 'FTE'),
                ('EMP003', 'SSN003', '1975-01-01', '2018-01-01', NULL, 90000, 90000, 'L3', 'Sales', 'FTE'),
                ('EMP004', 'SSN004', '1990-01-01', '2022-01-01', NULL, 55000, 55000, 'L1', 'Support', 'FTE')
        """)

        # Create baseline workforce model data
        conn.execute("""
            INSERT INTO int_baseline_workforce
            SELECT
                employee_id, employee_ssn, employee_birth_date, employee_hire_date,
                employee_gross_compensation as current_compensation,
                2024 - EXTRACT(YEAR FROM employee_birth_date) as current_age,
                2024 - EXTRACT(YEAR FROM employee_hire_date) as current_tenure,
                1 as level_id, '25-34' as age_band, '2-4' as tenure_band,
                'active' as employment_status, NULL as termination_date, NULL as termination_reason,
                2025 as simulation_year, CURRENT_TIMESTAMP as snapshot_created_at,
                true as is_from_census, true as is_cold_start, 0 as last_completed_year
            FROM stg_census_data WHERE employee_termination_date IS NULL
        """)

    # Test 1: Create orchestrator with data preservation
    orchestrator = MultiYearSimulationOrchestrator(
        start_year=2025,
        end_year=2027,
        config=config,
        force_clear=False,
        preserve_data=True
    )

    # Test 2: Verify data accumulates across years by simulating year by year
    with fresh_database.get_connection() as conn:
        # Simulate Year 2025 data (first year)
        conn.execute("""
            INSERT INTO fct_yearly_events VALUES
                ('EMP001', 'SSN001', 'RAISE', 2025, '2025-01-01', 'Merit: 3.0%', 77250, 75000, 44, 5, 1, '25-34', '2-4', 0.03, 'RAISE', 1, CURRENT_TIMESTAMP, 'test_scenario', 'manual', 'VALID')
        """)

        conn.execute("""
            INSERT INTO fct_workforce_snapshot VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', 77250, 44, 5, 1, '25-34', '2-4', 'active', NULL, NULL, 2025, '2025-01-01', CURRENT_TIMESTAMP, false, false, 2024),
                ('EMP002', 'SSN002', '1985-01-01', '2021-01-01', 66950, 39, 4, 1, '25-34', '2-4', 'active', NULL, NULL, 2025, '2025-01-01', CURRENT_TIMESTAMP, false, false, 2024)
        """)

        # Simulate Year 2026 data (should accumulate, not replace)
        conn.execute("""
            INSERT INTO fct_yearly_events VALUES
                ('EMP001', 'SSN001', 'RAISE', 2026, '2026-01-01', 'Merit: 3.0%', 79568, 77250, 45, 6, 1, '25-34', '2-4', 0.03, 'RAISE', 1, CURRENT_TIMESTAMP, 'test_scenario', 'manual', 'VALID')
        """)

        conn.execute("""
            INSERT INTO fct_workforce_snapshot VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', 79568, 45, 6, 1, '25-34', '2-4', 'active', NULL, NULL, 2026, '2026-01-01', CURRENT_TIMESTAMP, false, false, 2025),
                ('EMP002', 'SSN002', '1985-01-01', '2021-01-01', 68959, 40, 5, 1, '25-34', '2-4', 'active', NULL, NULL, 2026, '2026-01-01', CURRENT_TIMESTAMP, false, false, 2025)
        """)

        # Verify data persistence - both years should be present
        events_count = conn.execute("""
            SELECT COUNT(*), COUNT(DISTINCT simulation_year)
            FROM fct_yearly_events
            WHERE simulation_year IN (2025, 2026)
        """).fetchone()

        snapshot_count = conn.execute("""
            SELECT COUNT(*), COUNT(DISTINCT simulation_year)
            FROM fct_workforce_snapshot
            WHERE simulation_year IN (2025, 2026)
        """).fetchone()

        # Assert: Data should accumulate across years
        assert events_count[0] == 2, f"Expected 2 events, found {events_count[0]}"
        assert events_count[1] == 2, f"Expected 2 distinct years in events, found {events_count[1]}"
        assert snapshot_count[0] == 4, f"Expected 4 snapshots, found {snapshot_count[0]}"
        assert snapshot_count[1] == 2, f"Expected 2 distinct years in snapshots, found {snapshot_count[1]}"

def test_selective_data_clearing(fresh_database):
    """Test selective data clearing functionality"""
    config = {
        'target_growth_rate': 0.03,
        'workforce': {'total_termination_rate': 0.12, 'new_hire_termination_rate': 0.25}
    }

    with fresh_database.get_connection() as conn:
        # Setup: Create multi-year data
        for year in [2025, 2026, 2027]:
            conn.execute(f"""
                INSERT INTO fct_yearly_events VALUES
                    ('EMP001', 'SSN001', 'RAISE', {year}, '{year}-01-01', 'Merit: 3.0%',
                     {75000 + (year-2025)*2250}, {75000 + (year-2025-1)*2250}, 44 + (year-2025),
                     5 + (year-2025), 1, '25-34', '2-4', 0.03, 'RAISE', 1,
                     CURRENT_TIMESTAMP, 'test_scenario', 'manual', 'VALID')
            """)

            conn.execute(f"""
                INSERT INTO fct_workforce_snapshot VALUES
                    ('EMP001', 'SSN001', '1980-01-01', '2020-01-01',
                     {75000 + (year-2025)*2250}, 44 + (year-2025), 5 + (year-2025),
                     1, '25-34', '2-4', 'active', NULL, NULL, {year}, '{year}-01-01',
                     CURRENT_TIMESTAMP, false, false, {year-1})
            """)

    # Create orchestrator and test selective clearing
    orchestrator = MultiYearSimulationOrchestrator(2025, 2027, config, force_clear=False, preserve_data=True)

    # Clear only year 2026
    orchestrator.clear_specific_years([2026])

    with fresh_database.get_connection() as conn:
        # Verify year 2026 is cleared but others remain
        events_by_year = conn.execute("""
            SELECT simulation_year, COUNT(*)
            FROM fct_yearly_events
            GROUP BY simulation_year
            ORDER BY simulation_year
        """).fetchall()

        snapshots_by_year = conn.execute("""
            SELECT simulation_year, COUNT(*)
            FROM fct_workforce_snapshot
            GROUP BY simulation_year
            ORDER BY simulation_year
        """).fetchall()

        # Assert: Only year 2026 should be cleared
        expected_years = [2025, 2027]  # 2026 should be missing
        actual_event_years = [row[0] for row in events_by_year]
        actual_snapshot_years = [row[0] for row in snapshots_by_year]

        assert actual_event_years == expected_years, f"Expected years {expected_years}, found {actual_event_years}"
        assert actual_snapshot_years == expected_years, f"Expected years {expected_years}, found {actual_snapshot_years}"


def test_data_integrity_validation(fresh_database):
    """Test comprehensive data integrity validation"""
    from orchestrator_mvp.core.multi_year_simulation import validate_multi_year_data_integrity

    # Test 1: Empty database
    result_empty = validate_multi_year_data_integrity(2025, 2027)
    assert not result_empty['baseline_available']
    assert not result_empty['can_proceed']
    assert len(result_empty['recommendations']) > 0

    with fresh_database.get_connection() as conn:
        # Setup: Create baseline workforce
        conn.execute("""
            INSERT INTO int_baseline_workforce VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', 75000, 44, 4, 1, '25-34', '2-4',
                 'active', NULL, NULL, 2025, CURRENT_TIMESTAMP, true, true, 0)
        """)

        # Create partial multi-year data
        conn.execute("""
            INSERT INTO fct_workforce_snapshot VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', 77250, 45, 5, 1, '25-34', '2-4',
                 'active', NULL, NULL, 2025, '2025-01-01', CURRENT_TIMESTAMP, false, false, 2024)
        """)

    # Test 2: With baseline but gaps
    result_partial = validate_multi_year_data_integrity(2025, 2027)
    assert result_partial['baseline_available']
    assert len(result_partial['existing_years']) == 1
    assert result_partial['data_gaps'] == [2026, 2027]
    assert result_partial['can_proceed']  # Should be able to proceed with baseline


def test_enhanced_year_transition_validation(fresh_database):
    """Test enhanced year transition validation with comprehensive checks"""
    from orchestrator_mvp.core.multi_year_simulation import validate_year_transition

    with fresh_database.get_connection() as conn:
        # Setup: Create year 2025 data with comprehensive details
        conn.execute("""
            INSERT INTO fct_workforce_snapshot VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', 77250, 45, 5, 1, '25-34', '2-4',
                 'active', NULL, NULL, 2025, '2025-01-01', CURRENT_TIMESTAMP, false, false, 2024),
                ('EMP002', 'SSN002', '1985-01-01', '2021-01-01', 66950, 40, 4, 1, '25-34', '2-4',
                 'active', NULL, NULL, 2025, '2025-01-01', CURRENT_TIMESTAMP, false, false, 2024),
                ('EMP003', 'SSN003', '1975-01-01', '2018-01-01', 92700, 50, 7, 1, '25-34', '2-4',
                 'terminated', '2025-06-30', 'voluntary', 2025, '2025-01-01', CURRENT_TIMESTAMP, false, false, 2024)
        """)

        conn.execute("""
            INSERT INTO fct_yearly_events VALUES
                ('EMP001', 'SSN001', 'RAISE', 2025, '2025-01-01', 'Merit: 3.0%', 77250, 75000, 45, 5, 1, '25-34', '2-4', 0.03, 'RAISE', 1, CURRENT_TIMESTAMP, 'test_scenario', 'manual', 'VALID'),
                ('EMP003', 'SSN003', 'termination', 2025, '2025-06-30', 'Voluntary resignation', 92700, NULL, 50, 7, 1, '25-34', '2-4', 0.1, 'experienced_termination', 1, CURRENT_TIMESTAMP, 'test_scenario', 'manual', 'VALID')
        """)

        # Create year 2026 data
        conn.execute("""
            INSERT INTO fct_workforce_snapshot VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', 79568, 46, 6, 1, '25-34', '2-4',
                 'active', NULL, NULL, 2026, '2026-01-01', CURRENT_TIMESTAMP, false, false, 2025),
                ('EMP002', 'SSN002', '1985-01-01', '2021-01-01', 68959, 41, 5, 1, '25-34', '2-4',
                 'active', NULL, NULL, 2026, '2026-01-01', CURRENT_TIMESTAMP, false, false, 2025)
        """)

    # Test enhanced validation
    validation_result = validate_year_transition(2025, 2026)
    assert validation_result == True, "Enhanced year transition validation should pass with comprehensive data"

    # Test validation with missing data
    validation_result_missing = validate_year_transition(2026, 2027)
    assert validation_result_missing == False, "Validation should fail when year 2026 data is missing"


def test_force_clear_vs_preserve_data_modes(fresh_database):
    """Test different data management modes"""
    config = {
        'target_growth_rate': 0.03,
        'workforce': {'total_termination_rate': 0.12, 'new_hire_termination_rate': 0.25}
    }

    with fresh_database.get_connection() as conn:
        # Setup: Create existing simulation data
        conn.execute("""
            INSERT INTO fct_yearly_events VALUES
                ('EMP001', 'SSN001', 'RAISE', 2025, '2025-01-01', 'Merit: 3.0%', 77250, 75000, 45, 5, 1, '25-34', '2-4', 0.03, 'RAISE', 1, CURRENT_TIMESTAMP, 'test_scenario', 'manual', 'VALID')
        """)

        conn.execute("""
            INSERT INTO fct_workforce_snapshot VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', 77250, 45, 5, 1, '25-34', '2-4', 'active', NULL, NULL, 2025, '2025-01-01', CURRENT_TIMESTAMP, false, false, 2024)
        """)

    # Test 1: Preserve data mode (default)
    orchestrator_preserve = MultiYearSimulationOrchestrator(
        2025, 2027, config, force_clear=False, preserve_data=True
    )

    with fresh_database.get_connection() as conn:
        # Data should still exist after initialization
        events_count = conn.execute("SELECT COUNT(*) FROM fct_yearly_events WHERE simulation_year = 2025").fetchone()[0]
        snapshots_count = conn.execute("SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = 2025").fetchone()[0]

        assert events_count == 1, "Events should be preserved in preserve_data mode"
        assert snapshots_count == 1, "Snapshots should be preserved in preserve_data mode"

    # Test 2: Force clear mode
    orchestrator_clear = MultiYearSimulationOrchestrator(
        2025, 2027, config, force_clear=True, preserve_data=False
    )

    with fresh_database.get_connection() as conn:
        # Data should be cleared after force_clear initialization
        events_count_after_clear = conn.execute("SELECT COUNT(*) FROM fct_yearly_events WHERE simulation_year BETWEEN 2025 AND 2027").fetchone()[0]
        snapshots_count_after_clear = conn.execute("SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year BETWEEN 2025 AND 2027").fetchone()[0]

        assert events_count_after_clear == 0, "Events should be cleared in force_clear mode"
        assert snapshots_count_after_clear == 0, "Snapshots should be cleared in force_clear mode"

def test_data_handoff_validation(fresh_database):
    """Test enhanced data handoff mechanism validation"""
    with fresh_database.get_connection() as conn:
        # Setup: Create int_baseline_workforce
        conn.execute("""
            INSERT INTO int_baseline_workforce VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', 75000, 44, 4, 1, '25-34', '2-4',
                 'active', NULL, NULL, 2025, CURRENT_TIMESTAMP, true, true, 0)
        """)

        # Create year 2025 snapshot
        conn.execute("""
            INSERT INTO fct_workforce_snapshot VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', 77250, 45, 5, 1, '25-34', '2-4',
                 'active', NULL, NULL, 2025, '2025-01-01', CURRENT_TIMESTAMP, false, false, 2024)
        """)

        # Test enhanced int_workforce_previous_year_v2 model
        # This should use previous year snapshot and include metadata
        conn.execute("DELETE FROM int_workforce_previous_year_v2")
        conn.execute("""
            INSERT INTO int_workforce_previous_year_v2
            SELECT
                employee_id, employee_ssn, employee_birth_date, employee_hire_date,
                current_compensation as employee_gross_compensation,
                current_age + 1 as current_age, current_tenure + 1 as current_tenure,
                level_id,
                CASE WHEN (current_age + 1) < 25 THEN '< 25'
                     WHEN (current_age + 1) < 35 THEN '25-34'
                     ELSE '35-44' END as age_band,
                CASE WHEN (current_tenure + 1) < 2 THEN '< 2'
                     ELSE '2-4' END as tenure_band,
                employment_status, termination_date, termination_reason,
                2026 as simulation_year, CURRENT_TIMESTAMP as snapshot_created_at,
                false as is_from_census, false as is_cold_start, 2025 as last_completed_year,
                'previous_year_snapshot' as data_source,
                'GOOD' as data_quality_flag,
                'VALID' as validation_flag,
                1 as total_employees, 1 as active_employees,
                1 as from_previous_year, 0 as from_baseline,
                1 as good_quality_records, 1 as valid_records,
                1 as previous_year_available_count, 77250 as previous_year_avg_compensation,
                CURRENT_TIMESTAMP as processing_timestamp, '2026' as target_simulation_year
            FROM fct_workforce_snapshot
            WHERE simulation_year = 2025 AND employment_status = 'active'
        """)

        # Validate enhanced data handoff
        result = conn.execute("""
            SELECT data_source, data_quality_flag, validation_flag,
                   from_previous_year, from_baseline, good_quality_records
            FROM int_workforce_previous_year_v2
            LIMIT 1
        """).fetchone()

        assert result[0] == 'previous_year_snapshot', "Should use previous year snapshot"
        assert result[1] == 'GOOD', "Data quality should be GOOD"
        assert result[2] == 'VALID', "Validation flag should be VALID"
        assert result[3] == 1, "Should show records from previous year"
        assert result[4] == 0, "Should not show baseline fallback"
        assert result[5] == 1, "Should have good quality records"


def test_fallback_mechanism(fresh_database):
    """Test fallback to baseline when previous year data is missing"""
    with fresh_database.get_connection() as conn:
        # Setup: Only baseline workforce, no previous year data
        conn.execute("""
            INSERT INTO int_baseline_workforce VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', 75000, 44, 4, 1, '25-34', '2-4',
                 'active', NULL, NULL, 2025, CURRENT_TIMESTAMP, true, true, 0)
        """)

        # Simulate the enhanced int_workforce_previous_year_v2 fallback logic
        # When no previous year data exists, should fall back to baseline
        conn.execute("DELETE FROM int_workforce_previous_year_v2")
        conn.execute("""
            INSERT INTO int_workforce_previous_year_v2
            SELECT
                employee_id, employee_ssn, employee_birth_date, employee_hire_date,
                current_compensation as employee_gross_compensation,
                current_age, current_tenure, level_id, age_band, tenure_band,
                employment_status, termination_date, termination_reason,
                simulation_year, snapshot_created_at, is_from_census, is_cold_start,
                last_completed_year, 'baseline_fallback' as data_source,
                'FALLBACK_WARNING' as data_quality_flag,
                'VALID' as validation_flag,
                1 as total_employees, 1 as active_employees,
                0 as from_previous_year, 1 as from_baseline,
                0 as good_quality_records, 1 as valid_records,
                0 as previous_year_available_count, NULL as previous_year_avg_compensation,
                CURRENT_TIMESTAMP as processing_timestamp, '2026' as target_simulation_year
            FROM int_baseline_workforce
            WHERE employment_status = 'active'
        """)

        # Validate fallback behavior
        result = conn.execute("""
            SELECT data_source, data_quality_flag, from_previous_year, from_baseline
            FROM int_workforce_previous_year_v2
            LIMIT 1
        """).fetchone()

        assert result[0] == 'baseline_fallback', "Should use baseline fallback"
        assert result[1] == 'FALLBACK_WARNING', "Should show fallback warning"
        assert result[2] == 0, "Should not show previous year data"
        assert result[3] == 1, "Should show baseline usage"

def test_performance_data_persistence(fresh_database):
    """Test performance of data persistence with large datasets"""
    import time

    config = {
        'target_growth_rate': 0.03,
        'workforce': {'total_termination_rate': 0.12, 'new_hire_termination_rate': 0.25}
    }

    # Setup: Create larger dataset for performance testing
    with fresh_database.get_connection() as conn:
        # Create 1000 employees across 3 years
        for year in [2025, 2026, 2027]:
            for i in range(1000):
                conn.execute(f"""
                    INSERT INTO fct_yearly_events VALUES
                        ('EMP{i:04d}', 'SSN{i:04d}', 'RAISE', {year}, '{year}-01-01', 'Merit: 3.0%',
                         {50000 + (year-2025)*1500 + (i % 10000)}, {50000 + (year-2025-1)*1500 + (i % 10000)},
                         35 + (i % 30), 5 + (year-2025) + (i % 10), {(i % 3) + 1}, '25-34', '2-4',
                         0.03, 'RAISE', 1, CURRENT_TIMESTAMP, 'test_scenario', 'manual', 'VALID')
                """)

                conn.execute(f"""
                    INSERT INTO fct_workforce_snapshot VALUES
                        ('EMP{i:04d}', 'SSN{i:04d}', '1980-01-01', '2020-01-01',
                         {50000 + (year-2025)*1500 + (i % 10000)}, 35 + (i % 30), 5 + (year-2025) + (i % 10),
                         {(i % 3) + 1}, '25-34', '2-4', 'active', NULL, NULL, {year}, '{year}-01-01',
                         CURRENT_TIMESTAMP, false, false, {year-1})
                """)

    # Test data persistence operations performance
    start_time = time.time()

    # Create orchestrator (this should be fast with data preservation)
    orchestrator = MultiYearSimulationOrchestrator(
        2025, 2027, config, force_clear=False, preserve_data=True
    )

    # Test selective clearing performance
    orchestrator.clear_specific_years([2026])

    end_time = time.time()
    operation_time = end_time - start_time

    # Verify data integrity after operations
    with fresh_database.get_connection() as conn:
        remaining_events = conn.execute("""
            SELECT COUNT(*), COUNT(DISTINCT simulation_year)
            FROM fct_yearly_events
        """).fetchone()

        remaining_snapshots = conn.execute("""
            SELECT COUNT(*), COUNT(DISTINCT simulation_year)
            FROM fct_workforce_snapshot
        """).fetchone()

    # Assert: Performance and correctness
    assert operation_time < 10.0, f"Data persistence operations took {operation_time:.2f}s, exceeding 10s target"
    assert remaining_events[0] == 2000, f"Expected 2000 remaining events, found {remaining_events[0]}"  # 2025 + 2027
    assert remaining_events[1] == 2, f"Expected 2 years remaining, found {remaining_events[1]}"
    assert remaining_snapshots[0] == 2000, f"Expected 2000 remaining snapshots, found {remaining_snapshots[0]}"


def test_circular_dependency_resolution(fresh_database):
    """Test that the new helper model successfully breaks circular dependency"""
    config = {
        'target_growth_rate': 0.02,
        'random_seed': 42,
        'workforce': {
            'total_termination_rate': 0.10,
            'new_hire_termination_rate': 0.20
        }
    }

    with fresh_database.get_connection() as conn:
        # Create baseline workforce data
        conn.execute("""
            INSERT INTO stg_census_data VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', NULL, 75000, 75000, 'L2', 'Engineering', 'FTE'),
                ('EMP002', 'SSN002', '1985-01-01', '2021-01-01', NULL, 65000, 65000, 'L1', 'Marketing', 'FTE'),
                ('EMP003', 'SSN003', '1975-01-01', '2018-01-01', NULL, 90000, 90000, 'L3', 'Sales', 'FTE')
        """)

        # Create baseline workforce model data
        conn.execute("""
            INSERT INTO int_baseline_workforce
            SELECT
                employee_id, employee_ssn, employee_birth_date, employee_hire_date,
                employee_gross_compensation as current_compensation,
                2024 - EXTRACT(YEAR FROM employee_birth_date) as current_age,
                2024 - EXTRACT(YEAR FROM employee_hire_date) as current_tenure,
                1 as level_id, '25-34' as age_band, '2-4' as tenure_band,
                'active' as employment_status, NULL as termination_date, NULL as termination_reason,
                2025 as simulation_year, CURRENT_TIMESTAMP as snapshot_created_at,
                true as is_from_census, true as is_cold_start, 0 as last_completed_year
            FROM stg_census_data WHERE employee_termination_date IS NULL
        """)

        # Simulate completed year 2025 workforce snapshot
        conn.execute("""
            INSERT INTO fct_workforce_snapshot VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', 77250, 44, 5, 1, '35-44', '5-9', 'active', NULL, NULL, 2025, '2025-12-31', CURRENT_TIMESTAMP, false, false, 2024),
                ('EMP002', 'SSN002', '1985-01-01', '2021-01-01', 66950, 39, 4, 1, '35-44', '2-4', 'active', NULL, NULL, 2025, '2025-12-31', CURRENT_TIMESTAMP, false, false, 2024),
                ('EMP003', 'SSN003', '1975-01-01', '2018-01-01', 92700, 49, 7, 1, '45-54', '5-9', 'active', NULL, NULL, 2025, '2025-12-31', CURRENT_TIMESTAMP, false, false, 2024)
        """)

    # Test 1: Validate helper model can be built for year 2026
    from orchestrator_mvp.loaders.staging_loader import run_dbt_model_with_vars
    
    helper_result = run_dbt_model_with_vars(
        "int_active_employees_prev_year_snapshot", 
        {"simulation_year": 2026}, 
        full_refresh=True
    )
    
    assert helper_result.get("success", False), f"Helper model build failed: {helper_result.get('error', 'Unknown error')}"

    # Test 2: Verify helper model produces expected data
    with fresh_database.get_connection() as conn:
        helper_data = conn.execute("""
            SELECT employee_id, current_age, current_tenure, age_band, tenure_band, data_source,
                   employee_ssn, employee_birth_date, employee_hire_date, termination_date
            FROM int_active_employees_prev_year_snapshot
            WHERE simulation_year = 2026
            ORDER BY employee_id
        """).fetchall()

        # Should have 3 employees with incremented age/tenure
        assert len(helper_data) == 3, f"Expected 3 employees in helper model, found {len(helper_data)}"
        
        # Verify age and tenure incrementation and additional fields
        emp001_data = next(row for row in helper_data if row[0] == 'EMP001')
        assert emp001_data[1] == 45, f"Expected age 45 for EMP001 (44+1), found {emp001_data[1]}"
        assert emp001_data[2] == 6, f"Expected tenure 6 for EMP001 (5+1), found {emp001_data[2]}"
        assert emp001_data[3] == '45-54', f"Expected age_band '45-54', found '{emp001_data[3]}'"
        assert emp001_data[4] == '5-9', f"Expected tenure_band '5-9', found '{emp001_data[4]}'"
        assert emp001_data[5] == 'previous_year_snapshot', f"Expected data_source 'previous_year_snapshot', found '{emp001_data[5]}'"
        assert emp001_data[6] == 'SSN001', f"Expected employee_ssn 'SSN001', found '{emp001_data[6]}'"
        assert emp001_data[9] is None, f"Expected termination_date to be None for active employee, found {emp001_data[9]}"

    # Test 3: Verify int_active_employees_by_year uses helper model correctly
    active_employees_result = run_dbt_model_with_vars(
        "int_active_employees_by_year",
        {"simulation_year": 2026},
        full_refresh=True
    )
    
    assert active_employees_result.get("success", False), f"int_active_employees_by_year build failed: {active_employees_result.get('error', 'Unknown error')}"

    # Test 4: Verify the circular dependency is broken
    with fresh_database.get_connection() as conn:
        active_employees_data = conn.execute("""
            SELECT employee_id, current_age, current_tenure, dependency_resolution_method
            FROM int_active_employees_by_year
            WHERE simulation_year = 2026
            ORDER BY employee_id
        """).fetchall()

        assert len(active_employees_data) == 3, f"Expected 3 active employees, found {len(active_employees_data)}"
        
        # Verify the dependency resolution method is marked
        for row in active_employees_data:
            assert row[3] == 'helper_model', f"Expected dependency resolution method 'helper_model', found '{row[3]}'"


def test_sequential_year_validation(fresh_database):
    """Test that orchestrator enforces sequential year execution"""
    config = {
        'target_growth_rate': 0.02,
        'random_seed': 42,
        'workforce': {
            'total_termination_rate': 0.10,
            'new_hire_termination_rate': 0.20
        }
    }

    with fresh_database.get_connection() as conn:
        # Create baseline data
        conn.execute("""
            INSERT INTO stg_census_data VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', NULL, 75000, 75000, 'L2', 'Engineering', 'FTE')
        """)

        conn.execute("""
            INSERT INTO int_baseline_workforce
            SELECT
                employee_id, employee_ssn, employee_birth_date, employee_hire_date,
                employee_gross_compensation as current_compensation,
                2024 - EXTRACT(YEAR FROM employee_birth_date) as current_age,
                2024 - EXTRACT(YEAR FROM employee_hire_date) as current_tenure,
                1 as level_id, '35-44' as age_band, '2-4' as tenure_band,
                'active' as employment_status, NULL as termination_date, NULL as termination_reason,
                2025 as simulation_year, CURRENT_TIMESTAMP as snapshot_created_at,
                true as is_from_census, true as is_cold_start, 0 as last_completed_year
            FROM stg_census_data WHERE employee_termination_date IS NULL
        """)

    # Test 1: Try to run year 2026 without year 2025 completed
    orchestrator = MultiYearSimulationOrchestrator(
        start_year=2026,  # Skip year 2025
        end_year=2026,
        config=config,
        force_clear=False,
        preserve_data=True
    )

    # This should fail with clear error message about sequential requirement
    with pytest.raises(ValueError) as exc_info:
        orchestrator.execute_single_year(2026)
    
    error_message = str(exc_info.value)
    assert "sequential" in error_message.lower(), f"Expected sequential execution error, got: {error_message}"
    assert "2025" in error_message, f"Expected error to mention year 2025, got: {error_message}"

    # Test 2: Complete year 2025 first, then year 2026 should work
    orchestrator_proper = MultiYearSimulationOrchestrator(
        start_year=2025,
        end_year=2025,
        config=config,
        force_clear=False,
        preserve_data=True
    )

    # This should succeed
    result_2025 = orchestrator_proper.execute_single_year(2025)
    assert result_2025.get("success", False), f"Year 2025 execution failed: {result_2025.get('error', 'Unknown error')}"

    # Now year 2026 should work
    result_2026 = orchestrator_proper.execute_single_year(2026)
    assert result_2026.get("success", False), f"Year 2026 execution failed after 2025: {result_2026.get('error', 'Unknown error')}"


def test_helper_model_data_consistency(fresh_database):
    """Test that helper model produces consistent results with previous approach"""
    config = {
        'target_growth_rate': 0.02,
        'random_seed': 42,
        'workforce': {
            'total_termination_rate': 0.10,
            'new_hire_termination_rate': 0.20
        }
    }

    with fresh_database.get_connection() as conn:
        # Create test data
        conn.execute("""
            INSERT INTO stg_census_data VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', NULL, 75000, 75000, 'L2', 'Engineering', 'FTE'),
                ('EMP002', 'SSN002', '1985-01-01', '2021-01-01', NULL, 65000, 65000, 'L1', 'Marketing', 'FTE')
        """)

        conn.execute("""
            INSERT INTO int_baseline_workforce
            SELECT
                employee_id, employee_ssn, employee_birth_date, employee_hire_date,
                employee_gross_compensation as current_compensation,
                2024 - EXTRACT(YEAR FROM employee_birth_date) as current_age,
                2024 - EXTRACT(YEAR FROM employee_hire_date) as current_tenure,
                1 as level_id, '35-44' as age_band, '2-4' as tenure_band,
                'active' as employment_status, NULL as termination_date, NULL as termination_reason,
                2025 as simulation_year, CURRENT_TIMESTAMP as snapshot_created_at,
                true as is_from_census, true as is_cold_start, 0 as last_completed_year
            FROM stg_census_data WHERE employee_termination_date IS NULL
        """)

        # Create year 2025 workforce snapshot with specific compensation values
        conn.execute("""
            INSERT INTO fct_workforce_snapshot VALUES
                ('EMP001', 'SSN001', '1980-01-01', '2020-01-01', 77250, 44, 5, 1, '35-44', '5-9', 'active', NULL, NULL, 2025, '2025-12-31', CURRENT_TIMESTAMP, false, false, 2024),
                ('EMP002', 'SSN002', '1985-01-01', '2021-01-01', 66950, 39, 4, 1, '35-44', '2-4', 'active', NULL, NULL, 2025, '2025-12-31', CURRENT_TIMESTAMP, false, false, 2024)
        """)

    # Build the helper model
    from orchestrator_mvp.loaders.staging_loader import run_dbt_model_with_vars
    
    helper_result = run_dbt_model_with_vars(
        "int_active_employees_prev_year_snapshot", 
        {"simulation_year": 2026}, 
        full_refresh=True
    )
    
    assert helper_result.get("success", False), f"Helper model build failed: {helper_result.get('error', 'Unknown error')}"

    # Test data consistency
    with fresh_database.get_connection() as conn:
        helper_data = conn.execute("""
            SELECT employee_id, current_age, current_tenure, employee_gross_compensation,
                   age_band, tenure_band, data_quality_valid, termination_date
            FROM int_active_employees_prev_year_snapshot
            WHERE simulation_year = 2026
            ORDER BY employee_id
        """).fetchall()

        # Verify data transformations are correct
        assert len(helper_data) == 2, f"Expected 2 employees, found {len(helper_data)}"
        
        emp001 = next(row for row in helper_data if row[0] == 'EMP001')
        emp002 = next(row for row in helper_data if row[0] == 'EMP002')
        
        # EMP001: Age should be 45 (44+1), tenure 6 (5+1)
        assert emp001[1] == 45, f"EMP001 age should be 45, got {emp001[1]}"
        assert emp001[2] == 6, f"EMP001 tenure should be 6, got {emp001[2]}"
        assert emp001[3] == 77250, f"EMP001 compensation should be preserved at 77250, got {emp001[3]}"
        assert emp001[4] == '45-54', f"EMP001 age_band should be '45-54', got '{emp001[4]}'"
        assert emp001[5] == '5-9', f"EMP001 tenure_band should be '5-9', got '{emp001[5]}'"
        assert emp001[6] == True, f"EMP001 data_quality_valid should be True, got {emp001[6]}"
        assert emp001[7] is None, f"EMP001 termination_date should be None for active employee, got {emp001[7]}"
        
        # EMP002: Age should be 40 (39+1), tenure 5 (4+1)
        assert emp002[1] == 40, f"EMP002 age should be 40, got {emp002[1]}"
        assert emp002[2] == 5, f"EMP002 tenure should be 5, got {emp002[2]}"
        assert emp002[3] == 66950, f"EMP002 compensation should be preserved at 66950, got {emp002[3]}"
        assert emp002[4] == '35-44', f"EMP002 age_band should be '35-44', got '{emp002[4]}'"
        assert emp002[5] == '5-9 years', f"EMP002 tenure_band should be '5-9 years', got '{emp002[5]}'"
        assert emp002[6] == True, f"EMP002 data_quality_valid should be True, got {emp002[6]}"
        assert emp002[7] is None, f"EMP002 termination_date should be None for active employee, got {emp002[7]}"
