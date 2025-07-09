# Story S013-07: Validation and Testing Implementation

**Epic**: E013 - Dagster Simulation Pipeline Modularization
**Priority**: High
**Estimate**: 5 story points
**Status**: ✅ COMPLETED (2025-07-09)

## User Story

**As a** PlanWise Navigator developer
**I want** comprehensive validation and testing for the refactored pipeline
**So that** I can be confident the modularization preserves identical behavior while improving maintainability

## Background

The refactoring of the simulation pipeline involves significant structural changes across multiple operations. To ensure zero behavioral changes while achieving the modularity benefits, we need:

- Comprehensive unit tests for all new modular components
- Integration tests comparing before/after pipeline behavior
- Performance benchmarking to validate no regressions
- Mathematical validation of simulation results accuracy
- Character-level comparison of logging output

This story encompasses the testing strategy that validates the entire Epic E013 effort.

## Acceptance Criteria

### Functional Requirements
1. **Unit Test Coverage**
   - [ ] >95% code coverage on all new modular operations
   - [ ] Unit tests for execute_dbt_command utility with all parameter combinations
   - [ ] Unit tests for clean_duckdb_data with various data scenarios
   - [ ] Unit tests for run_dbt_event_models_for_year with hiring calculation validation
   - [ ] Unit tests for run_dbt_snapshot_for_year with different snapshot types

2. **Integration Test Suite**
   - [ ] End-to-end simulation comparison (before/after refactoring)
   - [ ] Multi-year simulation validation with identical inputs
   - [ ] Single-year simulation validation across different years
   - [ ] Error scenario testing with partial failures and recovery

3. **Behavior Validation**
   - [ ] Identical YearResult objects for same simulation parameters
   - [ ] Character-by-character logging output comparison
   - [ ] Mathematical validation of hiring calculations and growth rates
   - [ ] Database state validation after simulation completion

4. **Performance Validation**
   - [ ] Execution time benchmarking with no significant regression (>5%)
   - [ ] Memory usage profiling during large simulations
   - [ ] Database operation efficiency measurement
   - [ ] Scalability testing with extended year ranges

### Technical Requirements
1. **Test Infrastructure**
   - [ ] Test fixtures for baseline simulation data
   - [ ] Mock configurations for different scenarios
   - [ ] Database state capture/restore utilities
   - [ ] Logging output capture and comparison tools

2. **Comparison Framework**
   - [ ] YearResult comparison utilities with field-by-field validation
   - [ ] Simulation result diff reporting
   - [ ] Performance metric collection and analysis
   - [ ] Mathematical precision validation helpers

3. **Automated Test Execution**
   - [ ] Integration with existing test framework
   - [ ] CI/CD pipeline integration for regression detection
   - [ ] Test result reporting and artifact collection
   - [ ] Performance trend tracking

## Implementation Details

### Test Structure Organization
```
tests/
├── unit/
│   ├── test_execute_dbt_command.py
│   ├── test_clean_duckdb_data.py
│   ├── test_event_models_operation.py
│   ├── test_snapshot_operation.py
│   └── test_refactored_single_year.py
├── integration/
│   ├── test_simulation_behavior_comparison.py
│   ├── test_multi_year_pipeline.py
│   ├── test_error_scenarios.py
│   └── test_performance_benchmarks.py
├── fixtures/
│   ├── baseline_census_data.py
│   ├── simulation_configurations.py
│   └── expected_results.py
└── utilities/
    ├── result_comparison.py
    ├── logging_comparison.py
    ├── performance_measurement.py
    └── database_utilities.py
```

### Unit Test Implementation Examples

#### 1. dbt Command Utility Tests
```python
# tests/unit/test_execute_dbt_command.py
import pytest
from unittest.mock import Mock, patch
from orchestrator.simulator_pipeline import execute_dbt_command

class TestExecuteDbtCommand:
    def test_basic_command_execution(self, mock_context):
        """Test basic dbt command with no variables."""
        mock_dbt = Mock()
        mock_invocation = Mock()
        mock_invocation.process.returncode = 0
        mock_dbt.cli.return_value.wait.return_value = mock_invocation
        mock_context.resources.dbt = mock_dbt

        execute_dbt_command(mock_context, ["run"], {}, False, "test command")

        mock_dbt.cli.assert_called_once_with(
            ["run"], context=mock_context
        )

    def test_command_with_variables(self, mock_context):
        """Test dbt command with variables dictionary."""
        mock_dbt = Mock()
        mock_invocation = Mock()
        mock_invocation.process.returncode = 0
        mock_dbt.cli.return_value.wait.return_value = mock_invocation
        mock_context.resources.dbt = mock_dbt

        vars_dict = {"simulation_year": 2025, "random_seed": 42}

        execute_dbt_command(mock_context, ["run", "--select", "model"], vars_dict, False, "test")

        expected_call = ["run", "--select", "model", "--vars", "{simulation_year: 2025, random_seed: 42}"]
        mock_dbt.cli.assert_called_once_with(expected_call, context=mock_context)

    def test_full_refresh_flag(self, mock_context):
        """Test full_refresh flag addition."""
        mock_dbt = Mock()
        mock_invocation = Mock()
        mock_invocation.process.returncode = 0
        mock_dbt.cli.return_value.wait.return_value = mock_invocation
        mock_context.resources.dbt = mock_dbt

        execute_dbt_command(mock_context, ["run"], {}, True, "test")

        expected_call = ["run", "--full-refresh"]
        mock_dbt.cli.assert_called_once_with(expected_call, context=mock_context)

    def test_command_failure_handling(self, mock_context):
        """Test error handling when dbt command fails."""
        mock_dbt = Mock()
        mock_invocation = Mock()
        mock_invocation.process.returncode = 1
        mock_invocation.get_stdout.return_value = "stdout content"
        mock_invocation.get_stderr.return_value = "stderr content"
        mock_dbt.cli.return_value.wait.return_value = mock_invocation
        mock_context.resources.dbt = mock_dbt

        with pytest.raises(Exception) as exc_info:
            execute_dbt_command(mock_context, ["run"], {}, False, "test command")

        assert "Failed to run run for test command" in str(exc_info.value)
        assert "stdout content" in str(exc_info.value)
        assert "stderr content" in str(exc_info.value)
```

#### 2. Event Models Operation Tests
```python
# tests/unit/test_event_models_operation.py
import pytest
from unittest.mock import Mock, patch
from orchestrator.simulator_pipeline import run_dbt_event_models_for_year, _log_hiring_calculation_debug

class TestEventModelsOperation:
    def test_event_model_sequence(self, mock_context):
        """Test that all event models execute in correct sequence."""
        config = {
            "random_seed": 42,
            "target_growth_rate": 0.03,
            "new_hire_termination_rate": 0.25,
            "total_termination_rate": 0.12,
            "full_refresh": False
        }

        with patch('orchestrator.simulator_pipeline.execute_dbt_command') as mock_execute:
            with patch('orchestrator.simulator_pipeline._log_hiring_calculation_debug') as mock_debug:
                mock_debug.return_value = {"workforce_count": 1000}

                result = run_dbt_event_models_for_year(mock_context, 2025, config)

                # Verify all 5 models were called in correct order
                assert mock_execute.call_count == 5
                expected_models = [
                    "int_termination_events",
                    "int_promotion_events",
                    "int_merit_events",
                    "int_hiring_events",
                    "int_new_hire_termination_events"
                ]

                for i, model in enumerate(expected_models):
                    call_args = mock_execute.call_args_list[i]
                    assert call_args[0][1][2] == model  # Third argument is model name

                # Verify hiring debug was called for hiring events
                mock_debug.assert_called_once_with(mock_context, 2025, config)

    def test_hiring_calculation_debug(self, mock_context):
        """Test hiring calculation debug logic and logging."""
        config = {
            "target_growth_rate": 0.03,
            "total_termination_rate": 0.12,
            "new_hire_termination_rate": 0.25
        }

        with patch('duckdb.connect') as mock_connect:
            mock_conn = Mock()
            mock_connect.return_value = mock_conn
            mock_conn.execute.return_value.fetchone.return_value = [1000]  # workforce count

            result = _log_hiring_calculation_debug(mock_context, 2025, config)

            # Verify calculations
            assert result["workforce_count"] == 1000
            assert result["experienced_terms"] == 120  # ceil(1000 * 0.12)
            assert result["growth_amount"] == 30.0    # 1000 * 0.03
            assert result["total_hires_needed"] == 200 # ceil((120 + 30) / (1 - 0.25))
            assert result["expected_new_hire_terms"] == 50  # round(200 * 0.25)

            # Verify logging calls
            log_calls = mock_context.log.info.call_args_list
            assert any("🔍 HIRING CALCULATION DEBUG:" in str(call) for call in log_calls)
            assert any("🎯 TOTAL HIRES CALLING FOR: 200" in str(call) for call in log_calls)
```

### Integration Test Implementation

#### Simulation Behavior Comparison
```python
# tests/integration/test_simulation_behavior_comparison.py
import pytest
from typing import Dict, List
from orchestrator.simulator_pipeline import run_multi_year_simulation, YearResult

class TestSimulationBehaviorComparison:
    def test_identical_simulation_results(self, baseline_config, census_data):
        """Test that refactored pipeline produces identical results."""
        # Run simulation with original implementation (mocked or preserved)
        original_results = self._run_original_simulation(baseline_config)

        # Run simulation with refactored implementation
        refactored_results = run_multi_year_simulation(baseline_config)

        # Compare results year by year
        assert len(original_results) == len(refactored_results)

        for orig, refact in zip(original_results, refactored_results):
            self._compare_year_results(orig, refact)

    def _compare_year_results(self, original: YearResult, refactored: YearResult):
        """Compare two YearResult objects field by field."""
        assert original.year == refactored.year
        assert original.success == refactored.success
        assert original.active_employees == refactored.active_employees
        assert original.total_terminations == refactored.total_terminations
        assert original.experienced_terminations == refactored.experienced_terminations
        assert original.new_hire_terminations == refactored.new_hire_terminations
        assert original.total_hires == refactored.total_hires
        assert abs(original.growth_rate - refactored.growth_rate) < 0.0001  # Float precision
        assert original.validation_passed == refactored.validation_passed

    def test_logging_output_comparison(self, baseline_config, caplog):
        """Test that logging output is character-identical."""
        # Capture logging from both implementations
        with caplog.at_level(logging.INFO):
            original_logs = self._capture_original_logs(baseline_config)

        with caplog.at_level(logging.INFO):
            refactored_logs = self._capture_refactored_logs(baseline_config)

        # Compare hiring debug logs character by character
        hiring_debug_original = [log for log in original_logs if "🔍 HIRING CALCULATION DEBUG" in log]
        hiring_debug_refactored = [log for log in refactored_logs if "🔍 HIRING CALCULATION DEBUG" in log]

        assert hiring_debug_original == hiring_debug_refactored
```

### Performance Benchmarking

#### Performance Test Implementation
```python
# tests/integration/test_performance_benchmarks.py
import time
import psutil
import pytest
from orchestrator.simulator_pipeline import run_multi_year_simulation

class TestPerformanceBenchmarks:
    def test_execution_time_regression(self, large_simulation_config):
        """Test that refactored pipeline has no significant time regression."""
        # Baseline measurement (could be from stored metrics)
        baseline_time = self._get_baseline_execution_time(large_simulation_config)

        # Measure refactored execution time
        start_time = time.time()
        run_multi_year_simulation(large_simulation_config)
        refactored_time = time.time() - start_time

        # Allow 5% regression tolerance
        regression_threshold = baseline_time * 1.05
        assert refactored_time <= regression_threshold, (
            f"Performance regression detected: {refactored_time:.2f}s vs baseline {baseline_time:.2f}s"
        )

    def test_memory_usage_profiling(self, large_simulation_config):
        """Test memory usage during simulation execution."""
        process = psutil.Process()
        initial_memory = process.memory_info().rss

        run_multi_year_simulation(large_simulation_config)

        peak_memory = process.memory_info().rss
        memory_increase = peak_memory - initial_memory

        # Set reasonable memory usage threshold (e.g., 500MB)
        memory_threshold = 500 * 1024 * 1024  # 500MB in bytes
        assert memory_increase <= memory_threshold, (
            f"Memory usage exceeded threshold: {memory_increase / 1024 / 1024:.1f}MB"
        )
```

## Testing Strategy

### Phase 1: Unit Test Development (Week 1)
- [ ] Implement unit tests for all new modular operations
- [ ] Achieve >95% code coverage target
- [ ] Test edge cases and error scenarios
- [ ] Validate mathematical calculations

### Phase 2: Integration Test Development (Week 1-2)
- [ ] Implement simulation behavior comparison tests
- [ ] Create logging output validation tests
- [ ] Build performance benchmarking framework
- [ ] Test error scenarios and recovery

### Phase 3: Validation Execution (Week 2)
- [ ] Run comprehensive test suite against refactored code
- [ ] Compare results with baseline implementation
- [ ] Performance regression analysis
- [ ] Generate validation report

### Phase 4: Continuous Integration (Week 2)
- [ ] Integrate tests into CI/CD pipeline
- [ ] Set up automated regression detection
- [ ] Configure performance trend monitoring
- [ ] Document test maintenance procedures

## Definition of Done

- [ ] Unit test suite implemented with >95% coverage
- [ ] Integration tests validate identical behavior
- [ ] Performance benchmarks show no significant regression
- [ ] Logging output comparison passes character-level validation
- [ ] Mathematical calculation accuracy verified
- [ ] Error scenario testing completed
- [ ] CI/CD integration functional
- [ ] Test documentation completed
- [ ] Validation report generated and approved

## Dependencies

- **Upstream**: All other stories in Epic E013 (S013-01 through S013-06)
- **Downstream**: S013-08 (Documentation & Cleanup)

## Risk Mitigation

1. **Test Complexity**:
   - Start with simple test cases and build complexity gradually
   - Use test fixtures to manage data setup/teardown
   - Implement helper utilities for common validation patterns

2. **Performance Measurement**:
   - Establish baseline metrics before refactoring begins
   - Use multiple measurement runs for statistical significance
   - Account for system variability in performance thresholds

3. **Behavior Validation**:
   - Implement multiple validation approaches (mathematical, logging, database state)
   - Use property-based testing for edge case discovery
   - Create detailed failure reporting for debugging

---

**Implementation Notes**: This story is critical for Epic success validation. Comprehensive testing ensures confidence in the refactoring while providing ongoing regression protection. Start early and run continuously throughout the Epic implementation.
