# Story S083-05: Integration Testing & Validation

## Story Overview

**Epic**: E027 - Multi-Year Simulation Reliability & Performance
**Points**: 3
**Priority**: Medium

### User Story
**As a** quality assurance engineer
**I want** comprehensive testing for cold start and performance scenarios
**So that** I can ensure reliable multi-year simulation behavior

### Problem Statement
The current testing framework lacks comprehensive coverage for cold start scenarios and performance edge cases. There's no automated testing for multi-year simulation reliability, no validation of workforce continuity across years, and limited testing of performance regression scenarios.

### Root Cause
Testing was designed for single-year scenarios without considering the complexity of multi-year simulations, cold start initialization, and performance optimization validation.

---

## Acceptance Criteria

### Primary Acceptance Criteria
1. **Cold Start Testing**: Comprehensive test scenarios for cold start initialization
2. **Workforce Continuity**: Validation of workforce state across multiple years
3. **Performance Benchmarking**: Automated performance benchmarking and regression testing
4. **Recovery Testing**: Test simulation recovery from various failure states
5. **Data Consistency**: Validation of data consistency between fresh and continuing runs

### Secondary Acceptance Criteria
1. **Stress Testing**: Performance under load and large datasets
2. **Edge Case Coverage**: Testing of unusual data scenarios and edge cases
3. **Monitoring Validation**: Testing of performance monitoring and alerting
4. **Documentation**: Comprehensive testing documentation and runbooks

---

## Technical Specifications

### Testing Framework Architecture

#### 1. Cold Start Testing Suite
```python
# tests/integration/test_cold_start_scenarios.py
import pytest
import pandas as pd
from unittest.mock import Mock
from dagster import build_asset_context
from orchestrator.resources import DuckDBResource
from orchestrator.assets.workforce_preparation import int_baseline_workforce_enhanced
from orchestrator.utils.initialization_validator import InitializationValidator, SystemState
from tests.fixtures import fresh_database, populated_database, census_data_fixture

class TestColdStartScenarios:
    """Comprehensive testing for cold start scenarios"""

    @pytest.fixture
    def fresh_db_with_census(self, fresh_database):
        """Fresh database with census data only"""
        with fresh_database.get_connection() as conn:
            # Insert test census data
            conn.execute("""
                INSERT INTO stg_census_data (
                    employee_id, hire_date, termination_date, annual_salary,
                    job_level, department, employee_type
                ) VALUES
                    ('EMP001', '2020-01-15', NULL, 75000, 'L2', 'Engineering', 'FTE'),
                    ('EMP002', '2021-06-01', NULL, 65000, 'L1', 'Marketing', 'FTE'),
                    ('EMP003', '2019-03-10', NULL, 85000, 'L3', 'Sales', 'FTE'),
                    ('EMP004', '2022-01-01', '2023-12-31', 70000, 'L2', 'HR', 'FTE'),
                    ('EMP005', '2023-05-15', NULL, 60000, 'L1', 'Finance', 'FTE')
            """)
        return fresh_database

    def test_cold_start_detection_empty_database(self, fresh_database):
        """Test cold start detection with completely empty database"""
        context = build_asset_context(
            run_config={"simulation_year": 1}
        )

        validator = InitializationValidator(context, fresh_database)
        detection = validator.detect_system_state(1)

        assert detection.system_state == SystemState.COLD_START
        assert detection.can_proceed == False  # No census data
        assert detection.active_census_records == 0
        assert "No census data" in detection.recommendation

    def test_cold_start_detection_with_census(self, fresh_db_with_census):
        """Test cold start detection with census data available"""
        context = build_asset_context(
            run_config={"simulation_year": 1}
        )

        validator = InitializationValidator(context, fresh_db_with_census)
        detection = validator.detect_system_state(1)

        assert detection.system_state == SystemState.COLD_START
        assert detection.can_proceed == True
        assert detection.active_census_records == 4  # 4 active employees
        assert detection.workforce_snapshots == 0
        assert detection.total_events == 0

    def test_cold_start_workforce_initialization(self, fresh_db_with_census):
        """Test successful workforce initialization from census data"""
        context = build_asset_context(
            run_config={"simulation_year": 1}
        )

        # Mock DbtResource
        dbt_mock = Mock()
        dbt_mock.run.return_value = {"status": "success"}

        # Execute workforce initialization
        result = int_baseline_workforce_enhanced(context, fresh_db_with_census, dbt_mock)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 4  # 4 active employees
        assert all(result['employee_status'] == 'ACTIVE')
        assert all(result['simulation_year'] == 0)

    def test_cold_start_multi_year_progression(self, fresh_db_with_census):
        """Test multi-year simulation progression from cold start"""
        # Year 1: Cold start
        context_y1 = build_asset_context(run_config={"simulation_year": 1})
        dbt_mock = Mock()

        baseline_y1 = int_baseline_workforce_enhanced(context_y1, fresh_db_with_census, dbt_mock)

        # Simulate year 1 completion by inserting workforce snapshot
        with fresh_db_with_census.get_connection() as conn:
            conn.execute("""
                INSERT INTO fct_workforce_snapshot
                SELECT
                    employee_id, hire_date, termination_date, annual_salary,
                    job_level, department, employee_status, 1 as simulation_year,
                    effective_date
                FROM int_baseline_workforce
            """)

        # Year 2: Continuing simulation
        context_y2 = build_asset_context(run_config={"simulation_year": 2})
        validator = InitializationValidator(context_y2, fresh_db_with_census)
        detection_y2 = validator.detect_system_state(2)

        assert detection_y2.system_state == SystemState.CONTINUING
        assert detection_y2.can_proceed == True
        assert detection_y2.last_simulation_year == 1

    def test_cold_start_error_handling(self, fresh_database):
        """Test error handling during cold start failures"""
        context = build_asset_context(
            run_config={"simulation_year": 1}
        )
        dbt_mock = Mock()

        # Should fail due to no census data
        with pytest.raises(Exception) as exc_info:
            int_baseline_workforce_enhanced(context, fresh_database, dbt_mock)

        assert "Cannot proceed with initialization" in str(exc_info.value)
        assert "No census data" in str(exc_info.value)

    def test_cold_start_fallback_mechanisms(self, fresh_db_with_census):
        """Test fallback mechanisms during cold start issues"""
        context = build_asset_context(
            run_config={"simulation_year": 1}
        )

        validator = InitializationValidator(context, fresh_db_with_census)
        detection = validator.detect_system_state(1)

        # Test fallback query generation
        fallback_query = validator.get_fallback_data_source()
        assert fallback_query is not None
        assert "stg_census_data" in fallback_query
        assert "termination_date IS NULL" in fallback_query

        # Test fallback execution
        fallback_data = validator.execute_fallback_initialization()
        assert len(fallback_data) == 4
        assert all(fallback_data['employee_status'] == 'ACTIVE')
```

#### 2. Performance Testing Suite
```python
# tests/performance/test_multi_year_performance.py
import pytest
import time
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from dagster import build_asset_context
from orchestrator.resources import DuckDBResource
from orchestrator.assets.scd_processing import scd_workforce_state_monitored
from orchestrator.utils.multi_year_performance_monitor import MultiYearPerformanceMonitor
from tests.fixtures import large_workforce_dataset, performance_baseline_data

class TestMultiYearPerformance:
    """Performance testing for multi-year simulations"""

    @pytest.fixture
    def large_dataset(self, duckdb_resource):
        """Create large dataset for performance testing"""
        with duckdb_resource.get_connection() as conn:
            # Generate 100K employees
            conn.execute("""
                INSERT INTO stg_census_data
                SELECT
                    'EMP' || LPAD(generate_series::text, 6, '0') as employee_id,
                    DATE '2020-01-01' + (generate_series % 1000) * INTERVAL '1 day' as hire_date,
                    NULL as termination_date,
                    50000 + (generate_series % 50000) as annual_salary,
                    'L' || ((generate_series % 5) + 1) as job_level,
                    'DEPT' || ((generate_series % 10) + 1) as department,
                    'FTE' as employee_type
                FROM generate_series(1, 100000)
            """)
        return duckdb_resource

    @pytest.mark.performance
    def test_scd_processing_performance_target(self, large_dataset):
        """Test SCD processing meets 2-minute performance target"""
        context = build_asset_context(
            run_config={"simulation_year": 2}
        )

        # Create performance monitor
        monitor = MultiYearPerformanceMonitor(context, large_dataset)
        monitor.initialize_monitoring()

        # Test SCD processing
        start_time = time.time()
        result = scd_workforce_state_monitored(context, large_dataset)
        execution_time = time.time() - start_time

        # Assert performance requirements
        assert execution_time < 120, f"SCD processing took {execution_time:.2f}s, expected <120s"
        assert len(result) > 0, "SCD processing produced no results"
        assert isinstance(result, pd.DataFrame), "SCD processing should return DataFrame"

        # Check performance metrics
        summary = monitor.generate_performance_summary()
        assert summary['sla_breaches'] == 0, "SCD processing should not breach SLA"

    @pytest.mark.performance
    def test_cold_start_initialization_performance(self, large_dataset):
        """Test cold start initialization performance"""
        context = build_asset_context(
            run_config={"simulation_year": 1}
        )

        start_time = time.time()

        # Test cold start initialization
        from orchestrator.assets.workforce_preparation import int_baseline_workforce_enhanced
        from unittest.mock import Mock

        dbt_mock = Mock()
        result = int_baseline_workforce_enhanced(context, large_dataset, dbt_mock)

        execution_time = time.time() - start_time

        # Assert performance requirements
        assert execution_time < 30, f"Cold start took {execution_time:.2f}s, expected <30s"
        assert len(result) > 90000, "Should initialize majority of workforce"

    @pytest.mark.performance
    def test_multi_year_simulation_scalability(self, large_dataset):
        """Test scalability across multiple simulation years"""
        execution_times = []

        for year in range(1, 6):  # Test 5 years
            context = build_asset_context(
                run_config={"simulation_year": year}
            )

            start_time = time.time()

            # Simulate year processing
            if year == 1:
                # Cold start
                from orchestrator.assets.workforce_preparation import int_baseline_workforce_enhanced
                from unittest.mock import Mock
                dbt_mock = Mock()
                result = int_baseline_workforce_enhanced(context, large_dataset, dbt_mock)
            else:
                # Continuing simulation
                result = scd_workforce_state_monitored(context, large_dataset)

            execution_time = time.time() - start_time
            execution_times.append(execution_time)

        # Assert scalability requirements
        assert all(t < 300 for t in execution_times), "All years should complete within 5 minutes"

        # Check for performance degradation
        avg_early_years = sum(execution_times[:2]) / 2
        avg_later_years = sum(execution_times[3:]) / 2
        degradation_pct = ((avg_later_years - avg_early_years) / avg_early_years) * 100

        assert degradation_pct < 50, f"Performance degradation {degradation_pct:.1f}% exceeds 50% threshold"

    @pytest.mark.performance
    def test_memory_usage_stability(self, large_dataset):
        """Test memory usage stability across multi-year simulation"""
        import psutil
        process = psutil.Process()

        memory_snapshots = []

        for year in range(1, 4):
            context = build_asset_context(
                run_config={"simulation_year": year}
            )

            memory_before = process.memory_info().rss / 1024 / 1024  # MB

            # Execute processing
            result = scd_workforce_state_monitored(context, large_dataset)

            memory_after = process.memory_info().rss / 1024 / 1024  # MB
            memory_snapshots.append(memory_after - memory_before)

        # Assert memory stability
        max_memory_usage = max(memory_snapshots)
        assert max_memory_usage < 4096, f"Memory usage {max_memory_usage:.2f}MB exceeds 4GB limit"

        # Check for memory leaks
        memory_growth = memory_snapshots[-1] - memory_snapshots[0]
        assert memory_growth < 1024, f"Memory growth {memory_growth:.2f}MB suggests potential leak"

    @pytest.mark.performance
    def test_concurrent_simulation_performance(self, large_dataset):
        """Test performance under concurrent simulation scenarios"""
        def run_simulation(scenario_id):
            context = build_asset_context(
                run_config={"simulation_year": 2, "scenario_id": scenario_id}
            )

            start_time = time.time()
            result = scd_workforce_state_monitored(context, large_dataset)
            execution_time = time.time() - start_time

            return execution_time, len(result)

        # Run 3 concurrent simulations
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(run_simulation, i) for i in range(3)]
            results = [f.result() for f in futures]

        # Assert concurrent performance
        execution_times = [r[0] for r in results]
        record_counts = [r[1] for r in results]

        assert all(t < 180 for t in execution_times), "Concurrent runs should complete within 3 minutes"
        assert all(c > 0 for c in record_counts), "All concurrent runs should produce results"

        # Check performance degradation under concurrency
        avg_concurrent_time = sum(execution_times) / len(execution_times)
        # Compare with single-threaded baseline (assuming 120s)
        baseline_time = 120
        degradation_pct = ((avg_concurrent_time - baseline_time) / baseline_time) * 100

        assert degradation_pct < 30, f"Concurrent performance degradation {degradation_pct:.1f}% exceeds 30%"
```

#### 3. Data Consistency Testing Suite
```python
# tests/integration/test_data_consistency.py
import pytest
import pandas as pd
from dagster import build_asset_context
from orchestrator.resources import DuckDBResource
from tests.fixtures import multi_year_simulation_data

class TestDataConsistency:
    """Test data consistency across multi-year simulations"""

    def test_workforce_continuity_across_years(self, duckdb_resource):
        """Test workforce state continuity between simulation years"""
        # Setup multi-year simulation data
        with duckdb_resource.get_connection() as conn:
            # Insert workforce snapshots for years 1-3
            conn.execute("""
                INSERT INTO fct_workforce_snapshot VALUES
                    ('EMP001', '2020-01-01', NULL, 75000, 'L2', 'Engineering', 'ACTIVE', 1, '2024-01-01'),
                    ('EMP002', '2020-01-01', NULL, 65000, 'L1', 'Marketing', 'ACTIVE', 1, '2024-01-01'),
                    ('EMP001', '2020-01-01', NULL, 78000, 'L2', 'Engineering', 'ACTIVE', 2, '2025-01-01'),
                    ('EMP002', '2020-01-01', '2024-12-31', 65000, 'L1', 'Marketing', 'TERMINATED', 2, '2025-01-01'),
                    ('EMP003', '2025-01-01', NULL, 70000, 'L1', 'Sales', 'ACTIVE', 2, '2025-01-01')
            """)

            # Insert corresponding events
            conn.execute("""
                INSERT INTO fct_yearly_events VALUES
                    ('EMP001', 1, 'HIRE', '2024-01-01', 75000, 'L2', 'Engineering'),
                    ('EMP002', 1, 'HIRE', '2024-01-01', 65000, 'L1', 'Marketing'),
                    ('EMP001', 2, 'RAISE', '2025-01-01', 78000, 'L2', 'Engineering'),
                    ('EMP002', 2, 'TERMINATION', '2024-12-31', 65000, 'L1', 'Marketing'),
                    ('EMP003', 2, 'HIRE', '2025-01-01', 70000, 'L1', 'Sales')
            """)

        # Test workforce continuity
        with duckdb_resource.get_connection() as conn:
            # Check that terminated employees don't appear as active in next year
            terminated_still_active = conn.execute("""
                SELECT COUNT(*) as count
                FROM fct_workforce_snapshot w1
                JOIN fct_workforce_snapshot w2 ON w1.employee_id = w2.employee_id
                WHERE w1.simulation_year = 2 AND w1.employee_status = 'TERMINATED'
                AND w2.simulation_year = 3 AND w2.employee_status = 'ACTIVE'
            """).fetchone()[0]

            assert terminated_still_active == 0, "Terminated employees should not appear as active in subsequent years"

            # Check that active employees continue to next year (unless terminated)
            active_continuation = conn.execute("""
                SELECT
                    COUNT(*) as total_active_y1,
                    COUNT(CASE WHEN w2.employee_id IS NOT NULL THEN 1 END) as continued_to_y2
                FROM fct_workforce_snapshot w1
                LEFT JOIN fct_workforce_snapshot w2 ON w1.employee_id = w2.employee_id AND w2.simulation_year = 2
                WHERE w1.simulation_year = 1 AND w1.employee_status = 'ACTIVE'
            """).fetchone()

            # Should have some continuation (accounting for terminations)
            assert active_continuation[1] > 0, "Some active employees should continue to next year"

    def test_event_workforce_snapshot_consistency(self, duckdb_resource):
        """Test consistency between events and workforce snapshots"""
        # Setup test data
        with duckdb_resource.get_connection() as conn:
            conn.execute("""
                INSERT INTO fct_yearly_events VALUES
                    ('EMP001', 1, 'HIRE', '2024-01-01', 75000, 'L2', 'Engineering'),
                    ('EMP001', 2, 'RAISE', '2025-01-01', 80000, 'L2', 'Engineering'),
                    ('EMP001', 3, 'PROMOTION', '2026-01-01', 85000, 'L3', 'Engineering')
            """)

            conn.execute("""
                INSERT INTO fct_workforce_snapshot VALUES
                    ('EMP001', '2020-01-01', NULL, 75000, 'L2', 'Engineering', 'ACTIVE', 1, '2024-01-01'),
                    ('EMP001', '2020-01-01', NULL, 80000, 'L2', 'Engineering', 'ACTIVE', 2, '2025-01-01'),
                    ('EMP001', '2020-01-01', NULL, 85000, 'L3', 'Engineering', 'ACTIVE', 3, '2026-01-01')
            """)

        # Test consistency
        with duckdb_resource.get_connection() as conn:
            # Check that salary changes in events match workforce snapshots
            salary_mismatches = conn.execute("""
                SELECT COUNT(*) as count
                FROM fct_yearly_events e
                JOIN fct_workforce_snapshot w ON e.employee_id = w.employee_id AND e.simulation_year = w.simulation_year
                WHERE e.annual_salary != w.annual_salary
            """).fetchone()[0]

            assert salary_mismatches == 0, "Salary in events should match workforce snapshots"

            # Check that job level changes are consistent
            level_mismatches = conn.execute("""
                SELECT COUNT(*) as count
                FROM fct_yearly_events e
                JOIN fct_workforce_snapshot w ON e.employee_id = w.employee_id AND e.simulation_year = w.simulation_year
                WHERE e.job_level != w.job_level
            """).fetchone()[0]

            assert level_mismatches == 0, "Job level in events should match workforce snapshots"

    def test_scd_type2_consistency(self, duckdb_resource):
        """Test SCD Type 2 consistency in workforce state"""
        # Setup SCD test data
        with duckdb_resource.get_connection() as conn:
            conn.execute("""
                INSERT INTO scd_workforce_state VALUES
                    ('EMP001', 1, 75000, 'L2', 'Engineering', 'ACTIVE', '2024-01-01', '2024-12-31', 'SALARY_CHANGE', false),
                    ('EMP001', 2, 80000, 'L2', 'Engineering', 'ACTIVE', '2025-01-01', '2025-12-31', 'SALARY_CHANGE', false),
                    ('EMP001', 3, 85000, 'L3', 'Engineering', 'ACTIVE', '2026-01-01', NULL, 'PROMOTION', true)
            """)

        # Test SCD Type 2 properties
        with duckdb_resource.get_connection() as conn:
            # Check that each employee has exactly one current record
            multiple_current = conn.execute("""
                SELECT employee_id, COUNT(*) as current_count
                FROM scd_workforce_state
                WHERE is_current_record = true
                GROUP BY employee_id
                HAVING COUNT(*) > 1
            """).fetchall()

            assert len(multiple_current) == 0, "Each employee should have exactly one current record"

            # Check that date ranges don't overlap
            overlapping_ranges = conn.execute("""
                SELECT s1.employee_id
                FROM scd_workforce_state s1
                JOIN scd_workforce_state s2 ON s1.employee_id = s2.employee_id
                WHERE s1.effective_date < s2.effective_date
                AND s1.end_date >= s2.effective_date
            """).fetchall()

            assert len(overlapping_ranges) == 0, "SCD date ranges should not overlap"

    def test_data_integrity_after_cold_start(self, duckdb_resource):
        """Test data integrity after cold start vs continuing simulation"""
        # Simulate cold start
        context = build_asset_context(run_config={"simulation_year": 1})

        # Insert census data
        with duckdb_resource.get_connection() as conn:
            conn.execute("""
                INSERT INTO stg_census_data VALUES
                    ('EMP001', '2020-01-01', NULL, 75000, 'L2', 'Engineering', 'FTE'),
                    ('EMP002', '2020-01-01', NULL, 65000, 'L1', 'Marketing', 'FTE')
            """)

        # Execute cold start initialization
        from orchestrator.assets.workforce_preparation import int_baseline_workforce_enhanced
        from unittest.mock import Mock
        dbt_mock = Mock()

        cold_start_result = int_baseline_workforce_enhanced(context, duckdb_resource, dbt_mock)

        # Test data integrity
        assert len(cold_start_result) == 2, "Should initialize 2 employees"
        assert all(cold_start_result['employee_status'] == 'ACTIVE'), "All should be active"
        assert cold_start_result['annual_salary'].sum() == 140000, "Total salary should match census"

        # Test that subsequent processing maintains integrity
        with duckdb_resource.get_connection() as conn:
            # Insert workforce snapshot from cold start
            conn.execute("""
                INSERT INTO fct_workforce_snapshot
                SELECT *, 1 as simulation_year FROM int_baseline_workforce
            """)

            # Test continuing simulation
            context_y2 = build_asset_context(run_config={"simulation_year": 2})
            from orchestrator.utils.initialization_validator import InitializationValidator

            validator = InitializationValidator(context_y2, duckdb_resource)
            detection = validator.detect_system_state(2)

            assert detection.can_proceed == True, "Should be able to proceed with year 2"
            assert detection.last_simulation_year == 1, "Should detect year 1 as completed"
```

#### 4. Recovery Testing Suite
```python
# tests/integration/test_recovery_scenarios.py
import pytest
import pandas as pd
from dagster import build_asset_context
from orchestrator.resources import DuckDBResource
from orchestrator.utils.initialization_validator import InitializationValidator, SystemState

class TestRecoveryScenarios:
    """Test recovery from various failure scenarios"""

    def test_interrupted_simulation_recovery(self, duckdb_resource):
        """Test recovery from interrupted simulation"""
        # Setup interrupted simulation (missing year 3)
        with duckdb_resource.get_connection() as conn:
            conn.execute("""
                INSERT INTO fct_workforce_snapshot VALUES
                    ('EMP001', '2020-01-01', NULL, 75000, 'L2', 'Engineering', 'ACTIVE', 1, '2024-01-01'),
                    ('EMP002', '2020-01-01', NULL, 65000, 'L1', 'Marketing', 'ACTIVE', 1, '2024-01-01'),
                    ('EMP001', '2020-01-01', NULL, 78000, 'L2', 'Engineering', 'ACTIVE', 2, '2025-01-01'),
                    ('EMP002', '2020-01-01', NULL, 67000, 'L1', 'Marketing', 'ACTIVE', 2, '2025-01-01'),
                    ('EMP001', '2020-01-01', NULL, 82000, 'L2', 'Engineering', 'ACTIVE', 4, '2027-01-01')
                    -- Missing year 3
            """)

        # Test interruption detection
        context = build_asset_context(run_config={"simulation_year": 4})
        validator = InitializationValidator(context, duckdb_resource)
        detection = validator.detect_system_state(4)

        assert detection.system_state == SystemState.INTERRUPTED
        assert detection.can_proceed == False
        assert detection.last_simulation_year == 2

        # Test that we can detect the gap
        assert "Missing simulation years" in detection.recommendation

    def test_partial_data_recovery(self, duckdb_resource):
        """Test recovery from partial data scenarios"""
        # Setup partial data (workforce snapshots without events)
        with duckdb_resource.get_connection() as conn:
            conn.execute("""
                INSERT INTO fct_workforce_snapshot VALUES
                    ('EMP001', '2020-01-01', NULL, 75000, 'L2', 'Engineering', 'ACTIVE', 1, '2024-01-01'),
                    ('EMP002', '2020-01-01', NULL, 65000, 'L1', 'Marketing', 'ACTIVE', 1, '2024-01-01')
                -- No corresponding events
            """)

        # Test partial data detection
        context = build_asset_context(run_config={"simulation_year": 2})
        validator = InitializationValidator(context, duckdb_resource)
        detection = validator.detect_system_state(2)

        # Should detect data inconsistency
        can_proceed, errors = validator.validate_initialization_prerequisites()
        assert not can_proceed
        assert any("data consistency" in error.lower() for error in errors)

    def test_corrupted_data_recovery(self, duckdb_resource):
        """Test recovery from corrupted data scenarios"""
        # Setup corrupted data (negative salaries, invalid dates)
        with duckdb_resource.get_connection() as conn:
            conn.execute("""
                INSERT INTO fct_workforce_snapshot VALUES
                    ('EMP001', '2020-01-01', NULL, -75000, 'L2', 'Engineering', 'ACTIVE', 1, '2024-01-01'),
                    ('EMP002', '2020-01-01', NULL, 65000, 'L1', 'Marketing', 'ACTIVE', 1, '1900-01-01')
            """)

        # Test data validation
        with duckdb_resource.get_connection() as conn:
            # Check for negative salaries
            negative_salaries = conn.execute("""
                SELECT COUNT(*) FROM fct_workforce_snapshot WHERE annual_salary < 0
            """).fetchone()[0]

            assert negative_salaries > 0, "Should detect negative salary corruption"

            # Check for invalid dates
            invalid_dates = conn.execute("""
                SELECT COUNT(*) FROM fct_workforce_snapshot WHERE effective_date < '2020-01-01'
            """).fetchone()[0]

            assert invalid_dates > 0, "Should detect invalid date corruption"

    def test_emergency_fallback_scenarios(self, duckdb_resource):
        """Test emergency fallback mechanisms"""
        # Setup scenario where normal fallback fails
        with duckdb_resource.get_connection() as conn:
            # Insert census data for emergency fallback
            conn.execute("""
                INSERT INTO stg_census_data VALUES
                    ('EMP001', '2020-01-01', NULL, 75000, 'L2', 'Engineering', 'FTE'),
                    ('EMP002', '2020-01-01', NULL, 65000, 'L1', 'Marketing', 'FTE')
            """)

            # Insert corrupted workforce data
            conn.execute("""
                INSERT INTO fct_workforce_snapshot VALUES
                    ('EMP999', '2020-01-01', NULL, 0, '', '', 'UNKNOWN', 1, '2024-01-01')
            """)

        # Test emergency fallback
        context = build_asset_context(run_config={"simulation_year": 1})
        validator = InitializationValidator(context, duckdb_resource)

        # Should fall back to census data
        fallback_data = validator.execute_fallback_initialization()

        assert len(fallback_data) == 2, "Emergency fallback should use census data"
        assert all(fallback_data['employee_status'] == 'ACTIVE'), "All should be active"
        assert fallback_data['annual_salary'].min() > 0, "Should have valid salaries"
```

#### 5. Test Fixtures and Utilities
```python
# tests/fixtures/simulation_fixtures.py
import pytest
import pandas as pd
from orchestrator.resources import DuckDBResource
from dagster import build_asset_context
import tempfile
import os

@pytest.fixture
def fresh_database():
    """Create a fresh DuckDB instance for testing"""
    with tempfile.NamedTemporaryFile(suffix='.duckdb', delete=False) as tmp:
        tmp_path = tmp.name

    # Create DuckDB resource
    duckdb_resource = DuckDBResource(database=tmp_path)

    # Initialize schema
    with duckdb_resource.get_connection() as conn:
        conn.execute("""
            CREATE TABLE stg_census_data (
                employee_id VARCHAR PRIMARY KEY,
                hire_date DATE,
                termination_date DATE,
                annual_salary DECIMAL(10,2),
                job_level VARCHAR(10),
                department VARCHAR(50),
                employee_type VARCHAR(20)
            )
        """)

        conn.execute("""
            CREATE TABLE fct_workforce_snapshot (
                employee_id VARCHAR,
                hire_date DATE,
                termination_date DATE,
                annual_salary DECIMAL(10,2),
                job_level VARCHAR(10),
                department VARCHAR(50),
                employee_status VARCHAR(20),
                simulation_year INTEGER,
                effective_date DATE
            )
        """)

        conn.execute("""
            CREATE TABLE fct_yearly_events (
                employee_id VARCHAR,
                simulation_year INTEGER,
                event_type VARCHAR(20),
                effective_date DATE,
                annual_salary DECIMAL(10,2),
                job_level VARCHAR(10),
                department VARCHAR(50)
            )
        """)

        conn.execute("""
            CREATE TABLE scd_workforce_state (
                employee_id VARCHAR,
                simulation_year INTEGER,
                annual_salary DECIMAL(10,2),
                job_level VARCHAR(10),
                department VARCHAR(50),
                employee_status VARCHAR(20),
                effective_date DATE,
                end_date DATE,
                change_type VARCHAR(20),
                is_current_record BOOLEAN
            )
        """)

    yield duckdb_resource

    # Cleanup
    os.unlink(tmp_path)

@pytest.fixture
def large_workforce_dataset(fresh_database):
    """Create large workforce dataset for performance testing"""
    with fresh_database.get_connection() as conn:
        conn.execute("""
            INSERT INTO stg_census_data
            SELECT
                'EMP' || LPAD(generate_series::text, 6, '0') as employee_id,
                DATE '2020-01-01' + (generate_series % 1000) * INTERVAL '1 day' as hire_date,
                CASE
                    WHEN generate_series % 20 = 0 THEN DATE '2023-12-31'
                    ELSE NULL
                END as termination_date,
                50000 + (generate_series % 50000) as annual_salary,
                'L' || ((generate_series % 5) + 1) as job_level,
                'DEPT' || ((generate_series % 10) + 1) as department,
                'FTE' as employee_type
            FROM generate_series(1, 100000)
        """)

    return fresh_database

@pytest.fixture
def multi_year_simulation_data(fresh_database):
    """Create multi-year simulation data for testing"""
    with fresh_database.get_connection() as conn:
        # Insert 3 years of workforce snapshots
        for year in range(1, 4):
            conn.execute(f"""
                INSERT INTO fct_workforce_snapshot
                SELECT
                    'EMP' || LPAD(generate_series::text, 4, '0') as employee_id,
                    DATE '2020-01-01' + (generate_series % 100) * INTERVAL '1 day' as hire_date,
                    CASE
                        WHEN generate_series % 50 = 0 THEN DATE '2023-12-31'
                        ELSE NULL
                    END as termination_date,
                    50000 + (generate_series % 30000) + ({year} * 1000) as annual_salary,
                    'L' || ((generate_series % 3) + 1) as job_level,
                    'DEPT' || ((generate_series % 5) + 1) as department,
                    CASE
                        WHEN generate_series % 50 = 0 THEN 'TERMINATED'
                        ELSE 'ACTIVE'
                    END as employee_status,
                    {year} as simulation_year,
                    DATE '2024-01-01' + ({year} - 1) * INTERVAL '1 year' as effective_date
                FROM generate_series(1, 1000)
            """)

    return fresh_database
```

---

## Implementation Plan

### Phase 1: Core Testing Framework (2 days)
1. Implement cold start testing suite
2. Create test fixtures for various scenarios
3. Add basic performance testing
4. Test integration with existing assets

### Phase 2: Advanced Testing (1 day)
1. Implement recovery testing scenarios
2. Add data consistency validation
3. Create performance benchmarking
4. Add monitoring validation tests

---

## Performance Requirements

| Test Category | Target | Measurement |
|---------------|--------|-------------|
| Cold Start Tests | <10 seconds | Test execution time |
| Performance Tests | <5 minutes | Full performance suite |
| Recovery Tests | <30 seconds | Recovery scenario validation |
| Data Consistency | <2 seconds | Consistency check execution |

---

## Definition of Done

### Functional Requirements
- [ ] Cold start testing suite implemented and passing
- [ ] Performance benchmarking automated
- [ ] Recovery scenario testing comprehensive
- [ ] Data consistency validation thorough
- [ ] Workforce continuity testing across years

### Technical Requirements
- [ ] Test fixtures for all scenarios created
- [ ] Performance testing framework operational
- [ ] Recovery testing scenarios implemented
- [ ] Data consistency validation automated
- [ ] Integration with CI/CD pipeline

### Quality Requirements
- [ ] Test coverage >90% for new functionality
- [ ] Performance benchmarks established
- [ ] Recovery procedures documented
- [ ] Test execution time optimized
- [ ] Clear test failure diagnostics implemented
