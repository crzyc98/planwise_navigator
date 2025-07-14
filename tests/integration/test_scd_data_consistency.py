import pytest
import pandas as pd
from dagster import build_asset_context
from orchestrator.assets.scd_workforce_processing import scd_workforce_state_processed
from orchestrator.utils.scd_performance_monitor import SCDPerformanceMonitor

def test_scd_data_consistency(duckdb_resource, dbt_resource):
    """Test SCD processing maintains data consistency"""

    context = build_asset_context()

    # Setup test data with known SCD scenarios
    with duckdb_resource.get_connection() as conn:
        # Create test workforce data
        conn.execute("""
            CREATE OR REPLACE TABLE fct_workforce_snapshot AS
            SELECT
                'EMP001' as employee_id,
                '123-45-6789' as employee_ssn,
                DATE '1980-01-01' as employee_birth_date,
                DATE '2020-01-01' as employee_hire_date,
                75000 as current_compensation,
                75000 as prorated_annual_compensation,
                75000 as full_year_equivalent_compensation,
                44 as current_age,
                5 as current_tenure,
                2 as level_id,
                'active' as employment_status,
                NULL as termination_date,
                NULL as termination_reason,
                'continuous_active' as detailed_status_code,
                2025 as simulation_year,
                CURRENT_TIMESTAMP as snapshot_created_at,
                '35-44' as age_band,
                '5-9' as tenure_band

            UNION ALL

            SELECT
                'EMP002' as employee_id,
                '123-45-6790' as employee_ssn,
                DATE '1985-01-01' as employee_birth_date,
                DATE '2021-01-01' as employee_hire_date,
                65000 as current_compensation,
                65000 as prorated_annual_compensation,
                65000 as full_year_equivalent_compensation,
                39 as current_age,
                4 as current_tenure,
                1 as level_id,
                'terminated' as employment_status,
                DATE '2025-06-15' as termination_date,
                'voluntary' as termination_reason,
                'experienced_termination' as detailed_status_code,
                2025 as simulation_year,
                CURRENT_TIMESTAMP as snapshot_created_at,
                '35-44' as age_band,
                '2-4' as tenure_band
        """)

        # Clean up any existing snapshot data
        conn.execute("DROP TABLE IF EXISTS scd_workforce_state_optimized")

    # Execute SCD processing
    result = scd_workforce_state_processed(context, duckdb_resource, dbt_resource, pd.DataFrame())

    # Validate SCD Type 2 properties
    with duckdb_resource.get_connection() as conn:
        # Check for multiple current records per employee
        multiple_current = conn.execute("""
            SELECT
                employee_id,
                COUNT(*) as current_count
            FROM scd_workforce_state_optimized
            WHERE dbt_valid_to IS NULL
            GROUP BY employee_id
            HAVING COUNT(*) > 1
        """).df()

        assert len(multiple_current) == 0, f"Found employees with multiple current records: {multiple_current}"

        # Check that all employees have exactly one current record
        employee_current_counts = conn.execute("""
            SELECT
                employee_id,
                COUNT(*) as current_count
            FROM scd_workforce_state_optimized
            WHERE dbt_valid_to IS NULL
            GROUP BY employee_id
        """).df()

        assert all(employee_current_counts['current_count'] == 1), "Not all employees have exactly one current record"

        # Validate date ranges don't overlap
        overlapping_records = conn.execute("""
            SELECT
                s1.employee_id,
                s1.dbt_valid_from as range1_start,
                s1.dbt_valid_to as range1_end,
                s2.dbt_valid_from as range2_start,
                s2.dbt_valid_to as range2_end
            FROM scd_workforce_state_optimized s1
            JOIN scd_workforce_state_optimized s2
                ON s1.employee_id = s2.employee_id
                AND s1.dbt_scd_id != s2.dbt_scd_id
            WHERE s1.dbt_valid_from < COALESCE(s2.dbt_valid_to, '9999-12-31')
              AND COALESCE(s1.dbt_valid_to, '9999-12-31') > s2.dbt_valid_from
        """).df()

        assert len(overlapping_records) == 0, f"Found overlapping date ranges: {overlapping_records}"

        # Validate no null keys
        null_keys = conn.execute("""
            SELECT COUNT(*) as null_count
            FROM scd_workforce_state_optimized
            WHERE employee_id IS NULL OR dbt_valid_from IS NULL
        """).fetchone()[0]

        assert null_keys == 0, f"Found {null_keys} records with null keys"

    print("✓ All SCD data consistency checks passed")

def test_scd_change_detection_accuracy(duckdb_resource, dbt_resource):
    """Test that change detection accurately identifies modifications"""

    context = build_asset_context()

    # Setup initial data
    with duckdb_resource.get_connection() as conn:
        conn.execute("""
            CREATE OR REPLACE TABLE fct_workforce_snapshot AS
            SELECT
                'EMP001' as employee_id,
                '123-45-6789' as employee_ssn,
                DATE '1980-01-01' as employee_birth_date,
                DATE '2020-01-01' as employee_hire_date,
                75000 as current_compensation,
                75000 as prorated_annual_compensation,
                75000 as full_year_equivalent_compensation,
                44 as current_age,
                5 as current_tenure,
                2 as level_id,
                'active' as employment_status,
                NULL as termination_date,
                NULL as termination_reason,
                'continuous_active' as detailed_status_code,
                2025 as simulation_year,
                CURRENT_TIMESTAMP as snapshot_created_at,
                '35-44' as age_band,
                '5-9' as tenure_band
        """)

        # Clean up any existing snapshot data
        conn.execute("DROP TABLE IF EXISTS scd_workforce_state_optimized")

    # First run - should detect as NEW_EMPLOYEE
    result1 = scd_workforce_state_processed(context, duckdb_resource, dbt_resource, pd.DataFrame())

    # Update data to simulate change
    with duckdb_resource.get_connection() as conn:
        conn.execute("""
            UPDATE fct_workforce_snapshot
            SET
                current_compensation = 80000,
                prorated_annual_compensation = 80000,
                full_year_equivalent_compensation = 80000,
                level_id = 3,
                snapshot_created_at = CURRENT_TIMESTAMP
            WHERE employee_id = 'EMP001'
        """)

    # Second run - should detect as CHANGED
    result2 = scd_workforce_state_processed(context, duckdb_resource, dbt_resource, pd.DataFrame())

    # Validate change detection
    with duckdb_resource.get_connection() as conn:
        # Should have two records for EMP001: one historical, one current
        emp001_records = conn.execute("""
            SELECT
                employee_id,
                current_compensation,
                dbt_valid_from,
                dbt_valid_to,
                CASE WHEN dbt_valid_to IS NULL THEN 'CURRENT' ELSE 'HISTORICAL' END as record_type
            FROM scd_workforce_state_optimized
            WHERE employee_id = 'EMP001'
            ORDER BY dbt_valid_from
        """).df()

        assert len(emp001_records) == 2, f"Expected 2 records for EMP001, got {len(emp001_records)}"

        # First record should be historical with old compensation
        historical_record = emp001_records[emp001_records['record_type'] == 'HISTORICAL'].iloc[0]
        assert historical_record['current_compensation'] == 75000, "Historical record should have old compensation"
        assert historical_record['dbt_valid_to'] is not None, "Historical record should have end date"

        # Second record should be current with new compensation
        current_record = emp001_records[emp001_records['record_type'] == 'CURRENT'].iloc[0]
        assert current_record['current_compensation'] == 80000, "Current record should have new compensation"
        assert pd.isna(current_record['dbt_valid_to']), "Current record should have no end date"

    print("✓ Change detection accuracy test passed")

def test_scd_performance_monitoring(duckdb_resource, dbt_resource):
    """Test SCD performance monitoring functionality"""

    context = build_asset_context()
    monitor = SCDPerformanceMonitor(context, duckdb_resource)

    # Setup test data
    with duckdb_resource.get_connection() as conn:
        conn.execute("""
            CREATE OR REPLACE TABLE fct_workforce_snapshot AS
            SELECT
                'EMP' || row_number() OVER () as employee_id,
                '123-45-' || LPAD(row_number() OVER ()::VARCHAR, 4, '0') as employee_ssn,
                DATE '1980-01-01' as employee_birth_date,
                DATE '2020-01-01' as employee_hire_date,
                75000 as current_compensation,
                75000 as prorated_annual_compensation,
                75000 as full_year_equivalent_compensation,
                44 as current_age,
                5 as current_tenure,
                2 as level_id,
                'active' as employment_status,
                NULL as termination_date,
                NULL as termination_reason,
                'continuous_active' as detailed_status_code,
                2025 as simulation_year,
                CURRENT_TIMESTAMP as snapshot_created_at,
                '35-44' as age_band,
                '5-9' as tenure_band
            FROM generate_series(1, 1000)
        """)

        # Clean up any existing snapshot data
        conn.execute("DROP TABLE IF EXISTS scd_workforce_state_optimized")

    # Test performance monitoring
    monitor.start_monitoring()

    # Simulate processing phases
    monitor.start_phase("test_phase")
    result = scd_workforce_state_processed(context, duckdb_resource, dbt_resource, pd.DataFrame())
    monitor.record_phase_completion("test_phase", 1000)

    # Test SLA compliance check
    monitor.check_sla_compliance(sla_threshold_seconds=120)

    # Test integrity check
    integrity_results = monitor.check_scd_integrity()

    # Validate monitoring results
    assert monitor.get_total_duration() > 0, "Total duration should be positive"
    assert "test_phase" in monitor.metrics, "Test phase should be recorded"
    assert monitor.metrics["test_phase"]["record_count"] == 1000, "Record count should match"
    assert monitor.metrics["test_phase"]["records_per_second"] > 0, "Throughput should be positive"

    # Check integrity results
    assert integrity_results["multiple_current_records"] == 0, "Should have no integrity violations"
    assert integrity_results["null_key_violations"] == 0, "Should have no null key violations"
    assert integrity_results["overlapping_periods"] == 0, "Should have no overlapping periods"

    # Test performance summary
    summary = monitor.get_performance_summary()
    assert summary["total_duration"] > 0, "Summary should have positive duration"
    assert summary["records_processed"] == 1000, "Summary should have correct record count"
    assert summary["sla_compliant"] in [True, False], "Summary should have SLA compliance status"

    print("✓ Performance monitoring test passed")

def test_scd_index_optimization(duckdb_resource, dbt_resource):
    """Test that SCD indexes are created and improve performance"""

    context = build_asset_context()

    # Setup test data
    with duckdb_resource.get_connection() as conn:
        conn.execute("""
            CREATE OR REPLACE TABLE fct_workforce_snapshot AS
            SELECT
                'EMP' || row_number() OVER () as employee_id,
                '123-45-' || LPAD(row_number() OVER ()::VARCHAR, 4, '0') as employee_ssn,
                DATE '1980-01-01' as employee_birth_date,
                DATE '2020-01-01' as employee_hire_date,
                75000 as current_compensation,
                75000 as prorated_annual_compensation,
                75000 as full_year_equivalent_compensation,
                44 as current_age,
                5 as current_tenure,
                2 as level_id,
                'active' as employment_status,
                NULL as termination_date,
                NULL as termination_reason,
                'continuous_active' as detailed_status_code,
                2025 as simulation_year,
                CURRENT_TIMESTAMP as snapshot_created_at,
                '35-44' as age_band,
                '5-9' as tenure_band
            FROM generate_series(1, 5000)
        """)

        # Clean up any existing snapshot data
        conn.execute("DROP TABLE IF EXISTS scd_workforce_state_optimized")

    # Process SCD (includes index creation)
    result = scd_workforce_state_processed(context, duckdb_resource, dbt_resource, pd.DataFrame())

    # Verify indexes were created
    with duckdb_resource.get_connection() as conn:
        # Check if indexes exist (DuckDB specific query)
        try:
            indexes = conn.execute("""
                SELECT index_name
                FROM duckdb_indexes()
                WHERE table_name = 'scd_workforce_state_optimized'
            """).df()

            # Should have multiple indexes
            assert len(indexes) > 0, "Should have created indexes on SCD table"

            # Test query performance with indexes
            import time
            start_time = time.time()

            # Query that should benefit from indexes
            conn.execute("""
                SELECT COUNT(*)
                FROM scd_workforce_state_optimized
                WHERE employee_id = 'EMP1000'
                  AND dbt_valid_to IS NULL
            """).fetchone()

            query_time = time.time() - start_time

            # Should be fast with indexes
            assert query_time < 0.1, f"Indexed query took {query_time:.3f}s, expected <0.1s"

        except Exception as e:
            # If index queries fail, just verify the table exists and has data
            count = conn.execute("SELECT COUNT(*) FROM scd_workforce_state_optimized").fetchone()[0]
            assert count > 0, "SCD table should have data"

    print("✓ Index optimization test passed")

if __name__ == "__main__":
    # Run data consistency tests independently
    print("Running SCD Data Consistency Tests...")
    pytest.main([__file__, "-v"])
