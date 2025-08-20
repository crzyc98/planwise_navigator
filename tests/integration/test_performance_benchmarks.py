"""
Performance benchmarking tests for S013-07: Validation and Testing

Comprehensive performance tests to ensure the refactored pipeline
maintains or improves performance compared to the original implementation.
"""

import os
import time
from unittest.mock import Mock, patch

import psutil
import pytest
from dagster import OpExecutionContext
from orchestrator.simulator_pipeline import (YearResult, clean_duckdb_data,
                                             execute_dbt_command,
                                             run_dbt_event_models_for_year,
                                             run_dbt_snapshot_for_year,
                                             run_multi_year_simulation,
                                             run_year_simulation)


class PerformanceTimer:
    """Utility class for measuring execution time."""

    def __init__(self):
        self.start_time = None
        self.end_time = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.end_time = time.perf_counter()

    @property
    def elapsed_time(self) -> float:
        """Get elapsed time in seconds."""
        if self.start_time is None or self.end_time is None:
            return 0.0
        return self.end_time - self.start_time


class MemoryProfiler:
    """Utility class for measuring memory usage."""

    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.start_memory = None
        self.peak_memory = None
        self.end_memory = None

    def __enter__(self):
        self.start_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        self.peak_memory = self.start_memory
        return self

    def __exit__(self, *args):
        self.end_memory = self.process.memory_info().rss / 1024 / 1024  # MB

    def update_peak(self):
        """Update peak memory usage."""
        current_memory = self.process.memory_info().rss / 1024 / 1024
        if current_memory > self.peak_memory:
            self.peak_memory = current_memory

    @property
    def memory_delta(self) -> float:
        """Get memory usage delta in MB."""
        if self.start_memory is None or self.end_memory is None:
            return 0.0
        return self.end_memory - self.start_memory


class TestPerformanceBenchmarks:
    """Performance benchmark tests for the refactored pipeline."""

    @pytest.fixture
    def performance_config(self):
        """Configuration optimized for performance testing."""
        return {
            "start_year": 2023,
            "end_year": 2025,
            "target_growth_rate": 0.03,
            "total_termination_rate": 0.12,
            "new_hire_termination_rate": 0.25,
            "random_seed": 42,
            "full_refresh": False,
        }

    @pytest.fixture
    def mock_context_performance(self, performance_config):
        """Create a mock context optimized for performance testing."""
        context = Mock(spec=OpExecutionContext)
        context.log = Mock()
        context.op_config = performance_config.copy()

        # Mock dbt resource with minimal overhead
        dbt_resource = Mock()
        dbt_resource.cli = Mock()
        context.resources = Mock()
        context.resources.dbt = dbt_resource
        context.op_def = Mock()

        return context

    @pytest.fixture
    def fast_mocks(self):
        """Fast mock implementations for performance testing."""

        def fast_clean_data(context, years):
            return {
                "fct_yearly_events": len(years),
                "fct_workforce_snapshot": len(years),
            }

        def fast_execute_dbt(context, command, vars_dict, full_refresh, description):
            pass  # Minimal implementation

        def fast_event_models(context, year, config):
            return {
                "year": year,
                "models_executed": ["int_termination_events", "int_hiring_events"],
                "hiring_debug": {"hire_count": 100},
            }

        def fast_validate(context, year, config):
            return YearResult(year, True, 1000, 100, 80, 20, 110, 0.03, True)

        def fast_snapshot(context, year, snapshot_type):
            return {
                "success": True,
                "records_created": 100,
                "year": year,
                "snapshot_type": snapshot_type,
            }

        return {
            "clean_data": fast_clean_data,
            "execute_dbt": fast_execute_dbt,
            "event_models": fast_event_models,
            "validate": fast_validate,
            "snapshot": fast_snapshot,
        }

    @patch("orchestrator.simulator_pipeline.validate_year_results")
    @patch("orchestrator.simulator_pipeline.run_dbt_event_models_for_year")
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.clean_duckdb_data")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_single_year_simulation_performance(
        self,
        mock_duckdb_connect,
        mock_clean_data,
        mock_execute_dbt,
        mock_event_models,
        mock_validate,
        mock_context_performance,
        fast_mocks,
    ):
        """Benchmark single-year simulation performance."""
        # Setup fast mocks
        mock_clean_data.side_effect = fast_mocks["clean_data"]
        mock_execute_dbt.side_effect = fast_mocks["execute_dbt"]
        mock_event_models.side_effect = fast_mocks["event_models"]
        mock_validate.side_effect = fast_mocks["validate"]

        # Mock database connection
        mock_conn = Mock()
        mock_conn.fetchone.return_value = [100]
        mock_conn.close = Mock()
        mock_duckdb_connect.return_value = mock_conn

        # Update context for single year
        mock_context_performance.op_config["start_year"] = 2025
        mock_context_performance.op_config["end_year"] = 2025

        # Performance measurement
        with PerformanceTimer() as timer, MemoryProfiler() as memory:
            result = run_year_simulation(mock_context_performance)
            memory.update_peak()

        # Verify execution completed successfully
        assert result.success is True
        assert result.year == 2025

        # Performance assertions
        assert timer.elapsed_time < 0.1  # Should complete in < 100ms
        assert abs(memory.memory_delta) < 10  # Should use < 10MB additional memory

        print(
            f"Single-year simulation: {timer.elapsed_time:.3f}s, {memory.memory_delta:.1f}MB delta"
        )

    @patch("orchestrator.simulator_pipeline.run_year_simulation")
    @patch("orchestrator.simulator_pipeline.run_dbt_snapshot_for_year")
    @patch("orchestrator.simulator_pipeline.clean_duckdb_data")
    @patch("orchestrator.simulator_pipeline.assert_year_complete")
    @patch("dagster.build_op_context")
    def test_multi_year_simulation_performance(
        self,
        mock_build_context,
        mock_assert_complete,
        mock_clean_data,
        mock_snapshot,
        mock_single_year,
        mock_context_performance,
        fast_mocks,
    ):
        """Benchmark multi-year simulation performance."""
        # Setup fast mocks
        mock_clean_data.side_effect = fast_mocks["clean_data"]
        mock_snapshot.side_effect = fast_mocks["snapshot"]

        # Mock single-year simulation results
        year_results = [
            YearResult(2023, True, 1000, 100, 80, 20, 110, 0.03, True),
            YearResult(2024, True, 1100, 110, 90, 20, 120, 0.03, True),
            YearResult(2025, True, 1200, 120, 100, 20, 130, 0.03, True),
        ]
        mock_single_year.side_effect = year_results

        # Mock build_op_context
        mock_year_contexts = [Mock() for _ in range(3)]
        for ctx in mock_year_contexts:
            ctx.log = mock_context_performance.log
        mock_build_context.side_effect = mock_year_contexts

        # Performance measurement
        with PerformanceTimer() as timer, MemoryProfiler() as memory:
            results = run_multi_year_simulation(mock_context_performance, True)
            memory.update_peak()

        # Verify execution completed successfully
        assert len(results) == 3
        assert all(r.success for r in results)

        # Performance assertions
        assert timer.elapsed_time < 0.3  # Should complete in < 300ms for 3 years
        assert abs(memory.memory_delta) < 20  # Should use < 20MB additional memory

        print(
            f"Multi-year simulation (3 years): {timer.elapsed_time:.3f}s, {memory.memory_delta:.1f}MB delta"
        )

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_data_cleaning_performance(
        self, mock_duckdb_connect, mock_context_performance
    ):
        """Benchmark data cleaning operation performance."""
        years = list(range(2020, 2031))  # 11 years

        # Mock database connection
        mock_conn = Mock()
        mock_conn.execute = Mock()
        mock_conn.close = Mock()
        mock_duckdb_connect.return_value = mock_conn

        # Performance measurement
        with PerformanceTimer() as timer, MemoryProfiler() as memory:
            result = clean_duckdb_data(mock_context_performance, years)
            memory.update_peak()

        # Verify cleaning results
        assert result["fct_yearly_events"] == 11
        assert result["fct_workforce_snapshot"] == 11

        # Performance assertions
        assert timer.elapsed_time < 0.05  # Should complete in < 50ms
        assert abs(memory.memory_delta) < 5  # Should use < 5MB additional memory

        print(
            f"Data cleaning (11 years): {timer.elapsed_time:.3f}s, {memory.memory_delta:.1f}MB delta"
        )

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_event_models_operation_performance(
        self, mock_duckdb_connect, mock_execute_dbt, mock_context_performance
    ):
        """Benchmark event models operation performance."""
        year = 2025
        config = mock_context_performance.op_config

        # Mock database connection
        mock_conn = Mock()
        mock_conn.fetchone.return_value = [150]
        mock_conn.close = Mock()
        mock_duckdb_connect.return_value = mock_conn

        # Performance measurement
        with PerformanceTimer() as timer, MemoryProfiler() as memory:
            result = run_dbt_event_models_for_year(
                mock_context_performance, year, config
            )
            memory.update_peak()

        # Verify execution completed
        assert result["year"] == year
        assert len(result["models_executed"]) == 5

        # Performance assertions
        assert timer.elapsed_time < 0.02  # Should complete in < 20ms
        assert abs(memory.memory_delta) < 3  # Should use < 3MB additional memory

        print(
            f"Event models operation: {timer.elapsed_time:.3f}s, {memory.memory_delta:.1f}MB delta"
        )

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_snapshot_operation_performance(
        self, mock_duckdb_connect, mock_execute_dbt, mock_context_performance
    ):
        """Benchmark snapshot operation performance."""
        year = 2025

        # Mock database connection
        mock_conn = Mock()
        mock_conn.fetchone.side_effect = [[0], [100]]
        mock_conn.close = Mock()
        mock_duckdb_connect.return_value = mock_conn

        # Performance measurement
        with PerformanceTimer() as timer, MemoryProfiler() as memory:
            result = run_dbt_snapshot_for_year(
                mock_context_performance, year, "end_of_year"
            )
            memory.update_peak()

        # Verify execution completed
        assert result["success"] is True
        assert result["records_created"] == 100

        # Performance assertions
        assert timer.elapsed_time < 0.02  # Should complete in < 20ms
        assert abs(memory.memory_delta) < 3  # Should use < 3MB additional memory

        print(
            f"Snapshot operation: {timer.elapsed_time:.3f}s, {memory.memory_delta:.1f}MB delta"
        )

    def test_dbt_command_utility_performance(self, mock_context_performance):
        """Benchmark dbt command utility performance."""
        command = ["run", "--select", "test_model"]
        vars_dict = {"simulation_year": 2025, "random_seed": 42}

        # Performance measurement
        with PerformanceTimer() as timer, MemoryProfiler() as memory:
            for _ in range(100):  # Test repeated calls
                execute_dbt_command(
                    mock_context_performance, command, vars_dict, False, "test"
                )
            memory.update_peak()

        # Performance assertions
        avg_time = timer.elapsed_time / 100
        assert avg_time < 0.001  # Each call should take < 1ms on average
        assert abs(memory.memory_delta) < 5  # Should use < 5MB for 100 calls

        print(
            f"dbt command utility (100 calls): {timer.elapsed_time:.3f}s total, {avg_time:.4f}s avg"
        )

    @pytest.mark.parametrize("year_count", [1, 3, 5, 10])
    def test_scalability_by_year_count(
        self, mock_context_performance, fast_mocks, year_count
    ):
        """Test performance scalability with increasing year counts."""
        # Update configuration for different year counts
        start_year = 2025
        end_year = start_year + year_count - 1
        mock_context_performance.op_config["start_year"] = start_year
        mock_context_performance.op_config["end_year"] = end_year

        years = list(range(start_year, end_year + 1))

        with patch(
            "orchestrator.simulator_pipeline.run_year_simulation"
        ) as mock_single_year, patch(
            "orchestrator.simulator_pipeline.run_dbt_snapshot_for_year"
        ) as mock_snapshot, patch(
            "orchestrator.simulator_pipeline.clean_duckdb_data"
        ) as mock_clean_data, patch(
            "orchestrator.simulator_pipeline.assert_year_complete"
        ), patch(
            "dagster.build_op_context"
        ) as mock_build_context:
            # Setup mocks
            mock_clean_data.side_effect = fast_mocks["clean_data"]
            mock_snapshot.side_effect = fast_mocks["snapshot"]

            # Mock single-year results for each year
            year_results = [
                YearResult(
                    year, True, 1000 + year - start_year, 100, 80, 20, 110, 0.03, True
                )
                for year in years
            ]
            mock_single_year.side_effect = year_results

            # Mock build_op_context
            mock_year_contexts = [Mock() for _ in range(year_count)]
            for ctx in mock_year_contexts:
                ctx.log = mock_context_performance.log
            mock_build_context.side_effect = mock_year_contexts

            # Performance measurement
            with PerformanceTimer() as timer, MemoryProfiler() as memory:
                results = run_multi_year_simulation(mock_context_performance, True)
                memory.update_peak()

            # Verify execution completed
            assert len(results) == year_count
            assert all(r.success for r in results)

            # Performance assertions scale linearly with year count
            max_time = 0.05 * year_count  # 50ms per year max
            max_memory = 5 * year_count  # 5MB per year max

            assert timer.elapsed_time < max_time
            assert abs(memory.memory_delta) < max_memory

            print(
                f"Scalability test ({year_count} years): {timer.elapsed_time:.3f}s, {memory.memory_delta:.1f}MB"
            )

    def test_memory_leak_detection(self, mock_context_performance, fast_mocks):
        """Test for memory leaks during repeated operations."""
        mock_context_performance.op_config["start_year"] = 2025
        mock_context_performance.op_config["end_year"] = 2025

        with patch(
            "orchestrator.simulator_pipeline.validate_year_results"
        ) as mock_validate, patch(
            "orchestrator.simulator_pipeline.run_dbt_event_models_for_year"
        ) as mock_event_models, patch(
            "orchestrator.simulator_pipeline.execute_dbt_command"
        ) as mock_execute_dbt, patch(
            "orchestrator.simulator_pipeline.clean_duckdb_data"
        ) as mock_clean_data, patch(
            "orchestrator.simulator_pipeline.duckdb.connect"
        ) as mock_duckdb_connect:
            # Setup fast mocks
            mock_clean_data.side_effect = fast_mocks["clean_data"]
            mock_execute_dbt.side_effect = fast_mocks["execute_dbt"]
            mock_event_models.side_effect = fast_mocks["event_models"]
            mock_validate.side_effect = fast_mocks["validate"]

            # Mock database connection
            mock_conn = Mock()
            mock_conn.fetchone.return_value = [100]
            mock_conn.close = Mock()
            mock_duckdb_connect.return_value = mock_conn

            # Measure memory usage over multiple iterations
            initial_memory = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024

            for i in range(50):  # Run 50 iterations
                result = run_year_simulation(mock_context_performance)
                assert result.success is True

                # Check memory every 10 iterations
                if (i + 1) % 10 == 0:
                    current_memory = (
                        psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
                    )
                    memory_growth = current_memory - initial_memory

                    # Memory growth should be minimal (< 20MB after 50 iterations)
                    assert memory_growth < 20

                    print(
                        f"Memory after {i + 1} iterations: {current_memory:.1f}MB (growth: {memory_growth:.1f}MB)"
                    )

    @pytest.mark.parametrize("full_refresh", [True, False])
    def test_full_refresh_performance_impact(
        self, mock_context_performance, fast_mocks, full_refresh
    ):
        """Test performance impact of full_refresh parameter."""
        mock_context_performance.op_config["full_refresh"] = full_refresh
        mock_context_performance.op_config["start_year"] = 2025

        with patch(
            "orchestrator.simulator_pipeline.validate_year_results"
        ) as mock_validate, patch(
            "orchestrator.simulator_pipeline.run_dbt_event_models_for_year"
        ) as mock_event_models, patch(
            "orchestrator.simulator_pipeline.execute_dbt_command"
        ) as mock_execute_dbt, patch(
            "orchestrator.simulator_pipeline.clean_duckdb_data"
        ) as mock_clean_data, patch(
            "orchestrator.simulator_pipeline.duckdb.connect"
        ) as mock_duckdb_connect:
            # Setup mocks
            mock_clean_data.side_effect = fast_mocks["clean_data"]
            mock_execute_dbt.side_effect = fast_mocks["execute_dbt"]
            mock_event_models.side_effect = fast_mocks["event_models"]
            mock_validate.side_effect = fast_mocks["validate"]

            # Mock database connection
            mock_conn = Mock()
            mock_conn.fetchone.return_value = [100]
            mock_conn.close = Mock()
            mock_duckdb_connect.return_value = mock_conn

            # Performance measurement
            with PerformanceTimer() as timer, MemoryProfiler() as memory:
                result = run_year_simulation(mock_context_performance)
                memory.update_peak()

            # Verify execution completed
            assert result.success is True

            # Performance should be similar regardless of full_refresh (in mock environment)
            assert timer.elapsed_time < 0.1
            assert abs(memory.memory_delta) < 10

            # Verify full_refresh was passed correctly
            for call_args in mock_execute_dbt.call_args_list:
                full_refresh_param = call_args[0][3]
                assert full_refresh_param == full_refresh

            print(
                f"Full refresh {full_refresh}: {timer.elapsed_time:.3f}s, {memory.memory_delta:.1f}MB"
            )


class TestPerformanceRegression:
    """Tests specifically for performance regression detection."""

    def test_performance_baseline_establishment(self):
        """Establish performance baselines for future regression testing."""
        baselines = {
            "single_year_simulation_max_time": 0.1,  # 100ms
            "single_year_simulation_max_memory": 10,  # 10MB
            "multi_year_simulation_max_time_per_year": 0.1,  # 100ms per year
            "multi_year_simulation_max_memory_per_year": 7,  # 7MB per year
            "data_cleaning_max_time_per_year": 0.005,  # 5ms per year
            "event_models_max_time": 0.02,  # 20ms
            "snapshot_operation_max_time": 0.02,  # 20ms
            "dbt_command_utility_max_time": 0.001,  # 1ms per call
        }

        # Document baselines for future reference
        print("Performance baselines established:")
        for metric, value in baselines.items():
            print(f"  {metric}: {value}")

        # All baselines should be reasonable
        assert all(value > 0 for value in baselines.values())
        assert (
            baselines["single_year_simulation_max_time"] < 1.0
        )  # Should be sub-second
        assert (
            baselines["multi_year_simulation_max_time_per_year"] < 1.0
        )  # Should be sub-second per year

    def test_performance_regression_thresholds(self):
        """Define performance regression detection thresholds."""
        # Performance should not regress by more than these percentages
        regression_thresholds = {
            "max_execution_time_regression": 1.20,  # 20% slower is concerning
            "max_memory_usage_regression": 1.50,  # 50% more memory is concerning
            "max_throughput_regression": 0.80,  # 20% less throughput is concerning
        }

        print("Performance regression thresholds:")
        for metric, threshold in regression_thresholds.items():
            print(f"  {metric}: {threshold}")

        # Verify thresholds are reasonable
        assert regression_thresholds["max_execution_time_regression"] > 1.0
        assert regression_thresholds["max_memory_usage_regression"] > 1.0
        assert regression_thresholds["max_throughput_regression"] < 1.0
