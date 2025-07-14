import pytest
import time
import pandas as pd
from tests.fixtures import large_workforce_dataset
from orchestrator.utils.scd_performance_monitor import SCDPerformanceMonitor
from orchestrator.assets.scd_workforce_processing import scd_workforce_state_processed
from dagster import build_asset_context

@pytest.mark.performance
def test_scd_processing_performance(duckdb_resource, dbt_resource, large_workforce_dataset):
    """Test SCD processing meets performance requirements"""

    context = build_asset_context()

    # Create large workforce dataset for testing
    with duckdb_resource.get_connection() as conn:
        # Insert test data
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fct_workforce_snapshot AS
            SELECT
                'EMP' || row_number() OVER () as employee_id,
                '123-45-' || LPAD(row_number() OVER ()::VARCHAR, 4, '0') as employee_ssn,
                DATE '1970-01-01' + (random() * 20000)::INTEGER as employee_birth_date,
                DATE '2000-01-01' + (random() * 8000)::INTEGER as employee_hire_date,
                50000 + (random() * 100000)::INTEGER as current_compensation,
                50000 + (random() * 100000)::INTEGER as prorated_annual_compensation,
                50000 + (random() * 100000)::INTEGER as full_year_equivalent_compensation,
                25 + (random() * 40)::INTEGER as current_age,
                (random() * 25)::INTEGER as current_tenure,
                1 + (random() * 5)::INTEGER as level_id,
                CASE WHEN random() > 0.8 THEN 'terminated' ELSE 'active' END as employment_status,
                CASE WHEN random() > 0.9 THEN CURRENT_DATE - (random() * 365)::INTEGER ELSE NULL END as termination_date,
                NULL as termination_reason,
                'continuous_active' as detailed_status_code,
                2025 as simulation_year,
                CURRENT_TIMESTAMP as snapshot_created_at,
                'A' as age_band,
                'B' as tenure_band
            FROM generate_series(1, 10000)
        """)

    start_time = time.time()

    # Execute SCD processing
    try:
        result = scd_workforce_state_processed(context, duckdb_resource, dbt_resource, pd.DataFrame())
        execution_time = time.time() - start_time

        # Assert performance requirements
        assert execution_time < 120, f"SCD processing took {execution_time:.2f}s, expected <120s"
        assert result['total_records'] > 0, "SCD processing produced no results"
        assert result['sla_compliant'] == True, "SCD processing failed SLA compliance"

        # Validate data consistency
        assert result['current_records'] > 0, "No current records found"

        print(f"✓ SCD processing completed in {execution_time:.2f}s (target: <120s)")
        print(f"✓ Processed {result['total_records']} records")
        print(f"✓ Average throughput: {result['avg_throughput']:.0f} records/second")

    except Exception as e:
        execution_time = time.time() - start_time
        print(f"✗ SCD processing failed after {execution_time:.2f}s: {e}")
        raise

@pytest.mark.performance
def test_scd_memory_usage(duckdb_resource, dbt_resource, large_workforce_dataset):
    """Test SCD processing memory efficiency"""

    import psutil
    process = psutil.Process()

    context = build_asset_context()

    memory_before = process.memory_info().rss / 1024 / 1024  # MB

    # Execute SCD processing
    try:
        result = scd_workforce_state_processed(context, duckdb_resource, dbt_resource, pd.DataFrame())

        memory_after = process.memory_info().rss / 1024 / 1024  # MB
        memory_used = memory_after - memory_before

        # Assert memory requirements
        assert memory_used < 4096, f"SCD processing used {memory_used:.2f}MB, expected <4096MB"

        print(f"✓ Memory usage: {memory_used:.2f}MB (target: <4096MB)")

    except Exception as e:
        memory_after = process.memory_info().rss / 1024 / 1024  # MB
        memory_used = memory_after - memory_before
        print(f"✗ SCD processing failed using {memory_used:.2f}MB: {e}")
        raise

@pytest.mark.performance
def test_scd_throughput_benchmark(duckdb_resource, dbt_resource):
    """Test SCD processing throughput benchmark"""

    context = build_asset_context()

    # Create test datasets of different sizes
    test_sizes = [1000, 5000, 10000]
    results = []

    for size in test_sizes:
        with duckdb_resource.get_connection() as conn:
            # Clean up previous test data
            conn.execute("DROP TABLE IF EXISTS fct_workforce_snapshot")

            # Create test dataset
            conn.execute(f"""
                CREATE TABLE fct_workforce_snapshot AS
                SELECT
                    'EMP' || row_number() OVER () as employee_id,
                    '123-45-' || LPAD(row_number() OVER ()::VARCHAR, 4, '0') as employee_ssn,
                    DATE '1970-01-01' + (random() * 20000)::INTEGER as employee_birth_date,
                    DATE '2000-01-01' + (random() * 8000)::INTEGER as employee_hire_date,
                    50000 + (random() * 100000)::INTEGER as current_compensation,
                    50000 + (random() * 100000)::INTEGER as prorated_annual_compensation,
                    50000 + (random() * 100000)::INTEGER as full_year_equivalent_compensation,
                    25 + (random() * 40)::INTEGER as current_age,
                    (random() * 25)::INTEGER as current_tenure,
                    1 + (random() * 5)::INTEGER as level_id,
                    'active' as employment_status,
                    NULL as termination_date,
                    NULL as termination_reason,
                    'continuous_active' as detailed_status_code,
                    2025 as simulation_year,
                    CURRENT_TIMESTAMP as snapshot_created_at,
                    'A' as age_band,
                    'B' as tenure_band
                FROM generate_series(1, {size})
            """)

        start_time = time.time()

        try:
            result = scd_workforce_state_processed(context, duckdb_resource, dbt_resource, pd.DataFrame())
            execution_time = time.time() - start_time

            throughput = size / execution_time if execution_time > 0 else 0

            results.append({
                'size': size,
                'execution_time': execution_time,
                'throughput': throughput
            })

            print(f"✓ Size {size}: {execution_time:.2f}s, {throughput:.0f} records/sec")

        except Exception as e:
            execution_time = time.time() - start_time
            print(f"✗ Size {size} failed after {execution_time:.2f}s: {e}")
            raise

    # Verify throughput targets
    for result in results:
        assert result['throughput'] >= 1000, f"Throughput {result['throughput']:.0f} below target of 1000 records/sec"

    print(f"✓ All throughput benchmarks passed (target: ≥1000 records/sec)")

@pytest.mark.performance
def test_scd_scalability(duckdb_resource, dbt_resource):
    """Test SCD processing scalability with large datasets"""

    context = build_asset_context()

    # Test with progressively larger datasets
    for size in [10000, 50000, 100000]:
        with duckdb_resource.get_connection() as conn:
            # Clean up previous test data
            conn.execute("DROP TABLE IF EXISTS fct_workforce_snapshot")

            # Create large test dataset
            conn.execute(f"""
                CREATE TABLE fct_workforce_snapshot AS
                SELECT
                    'EMP' || row_number() OVER () as employee_id,
                    '123-45-' || LPAD(row_number() OVER ()::VARCHAR, 4, '0') as employee_ssn,
                    DATE '1970-01-01' + (random() * 20000)::INTEGER as employee_birth_date,
                    DATE '2000-01-01' + (random() * 8000)::INTEGER as employee_hire_date,
                    50000 + (random() * 100000)::INTEGER as current_compensation,
                    50000 + (random() * 100000)::INTEGER as prorated_annual_compensation,
                    50000 + (random() * 100000)::INTEGER as full_year_equivalent_compensation,
                    25 + (random() * 40)::INTEGER as current_age,
                    (random() * 25)::INTEGER as current_tenure,
                    1 + (random() * 5)::INTEGER as level_id,
                    'active' as employment_status,
                    NULL as termination_date,
                    NULL as termination_reason,
                    'continuous_active' as detailed_status_code,
                    2025 as simulation_year,
                    CURRENT_TIMESTAMP as snapshot_created_at,
                    'A' as age_band,
                    'B' as tenure_band
                FROM generate_series(1, {size})
            """)

        start_time = time.time()

        try:
            result = scd_workforce_state_processed(context, duckdb_resource, dbt_resource, pd.DataFrame())
            execution_time = time.time() - start_time

            # Scalability should be roughly linear
            throughput = size / execution_time if execution_time > 0 else 0

            # Still meet performance targets even with large datasets
            assert execution_time < 300, f"Processing {size} records took {execution_time:.2f}s, expected <300s"
            assert throughput >= 500, f"Throughput {throughput:.0f} below minimum of 500 records/sec"

            print(f"✓ Scalability test {size} records: {execution_time:.2f}s, {throughput:.0f} records/sec")

        except Exception as e:
            execution_time = time.time() - start_time
            print(f"✗ Scalability test {size} failed after {execution_time:.2f}s: {e}")
            raise

if __name__ == "__main__":
    # Run performance tests independently
    print("Running SCD Performance Tests...")
    pytest.main([__file__, "-v", "-m", "performance"])
