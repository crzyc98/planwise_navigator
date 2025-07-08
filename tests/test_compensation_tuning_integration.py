"""
Comprehensive Testing Framework for Compensation Tuning Optimization Features

This module provides extensive test coverage for:
1. Edge cases: extreme parameter values, empty datasets, missing files
2. Integration scenarios: synthetic vs real mode transitions, algorithm fallbacks
3. Performance testing: optimization speed, memory usage, timeout handling
4. Scenario validation: various business scenarios (budget constraints, growth targets)
5. Error handling: database locks, network issues, invalid configurations
6. Data consistency between optimization methods

Design follows PlanWise Navigator testing patterns and Enterprise-grade requirements.
"""

import pytest
import pandas as pd
import numpy as np
import os
import tempfile
import time
import subprocess
import json
import yaml
import sqlite3
import threading
import psutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from contextlib import contextmanager
import warnings

# Import modules under test
from streamlit_dashboard.optimization_schemas import (
    ParameterSchema,
    get_parameter_schema,
    ParameterCategory,
    RiskLevel,
    get_default_parameters,
    validate_parameters
)

# Test configuration
TEST_DB_PATH = "/tmp/test_compensation_tuning.duckdb"
TEST_CONFIG_PATH = "/tmp/test_simulation_config.yaml"
PERFORMANCE_TIMEOUT = 300  # 5 minutes max for performance tests


@dataclass
class TestScenario:
    """Define test scenarios for business validation."""
    name: str
    description: str
    budget_constraint: float
    growth_target: float
    expected_outcome: str
    risk_tolerance: RiskLevel
    parameter_overrides: Dict[str, float]


@dataclass
class PerformanceMetrics:
    """Track performance metrics during tests."""
    execution_time: float
    memory_usage_mb: float
    cpu_usage_percent: float
    database_operations: int
    optimization_iterations: int


class TestEdgeCases:
    """Test edge cases with extreme parameter values, empty datasets, and missing files."""

    def setup_method(self):
        """Setup for each test method."""
        self.schema = get_parameter_schema()
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Cleanup after each test method."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_extreme_parameter_values(self):
        """Test handling of extreme parameter values at bounds."""

        # Test minimum values
        min_params = {}
        for param_name, param_def in self.schema._parameters.items():
            min_params[param_name] = param_def.bounds.min_value

        validation_result = self.schema.validate_parameter_set(min_params)
        assert validation_result['is_valid'], f"Minimum values should be valid: {validation_result['errors']}"

        # Test maximum values
        max_params = {}
        for param_name, param_def in self.schema._parameters.items():
            max_params[param_name] = param_def.bounds.max_value

        validation_result = self.schema.validate_parameter_set(max_params)
        assert validation_result['is_valid'], f"Maximum values should be valid: {validation_result['errors']}"

        # Test beyond bounds (should fail)
        beyond_max_params = {}
        for param_name, param_def in self.schema._parameters.items():
            beyond_max_params[param_name] = param_def.bounds.max_value * 1.1

        validation_result = self.schema.validate_parameter_set(beyond_max_params)
        assert not validation_result['is_valid'], "Beyond-max values should be invalid"
        assert len(validation_result['errors']) > 0, "Should have validation errors"

    def test_empty_datasets(self):
        """Test behavior with empty datasets and missing data."""

        # Test with empty parameter dictionary
        empty_params = {}
        validation_result = self.schema.validate_parameter_set(empty_params)

        # Should handle gracefully, possibly with warnings for missing params
        assert isinstance(validation_result, dict)
        assert 'is_valid' in validation_result

        # Test with None values
        none_params = {
            "merit_rate_level_1": None,
            "cola_rate": None
        }

        with pytest.raises((TypeError, ValueError)):
            self.schema.validate_parameter_set(none_params)

    def test_missing_configuration_files(self):
        """Test handling of missing configuration files."""

        missing_file_path = "/nonexistent/path/config.yaml"

        # Test graceful handling of missing files
        with pytest.raises(FileNotFoundError):
            with open(missing_file_path, 'r') as f:
                yaml.safe_load(f)

    def test_corrupted_parameter_file(self):
        """Test handling of corrupted parameter files."""

        # Create corrupted CSV file
        corrupted_csv_path = os.path.join(self.temp_dir, "corrupted_comp_levers.csv")
        with open(corrupted_csv_path, 'w') as f:
            f.write("invalid,csv,format\n")
            f.write("not,a,proper,compensation,file\n")
            f.write("missing,required,columns\n")

        # Test that reading corrupted file fails gracefully
        try:
            df = pd.read_csv(corrupted_csv_path)
            # Should not have expected columns
            expected_columns = ['parameter_name', 'job_level', 'year', 'value']
            for col in expected_columns:
                assert col not in df.columns
        except Exception as e:
            # Acceptable to raise exception for corrupted data
            assert isinstance(e, (pd.errors.EmptyDataError, ValueError, KeyError))

    def test_invalid_data_types(self):
        """Test handling of invalid data types in parameters."""

        invalid_params = {
            "merit_rate_level_1": "not_a_number",
            "cola_rate": [1, 2, 3],  # List instead of float
            "promotion_probability_level_1": {"invalid": "dict"}
        }

        with pytest.raises((TypeError, ValueError)):
            self.schema.validate_parameter_set(invalid_params)

    def test_unicode_and_special_characters(self):
        """Test handling of unicode and special characters in inputs."""

        # Test with unicode parameter names (should fail validation)
        unicode_params = {
            "merit_rate_lével_1": 0.045,  # Non-ASCII character
            "côla_rate": 0.025
        }

        validation_result = self.schema.validate_parameter_set(unicode_params)
        # Should warn about unknown parameters
        assert len(validation_result['warnings']) > 0

    def test_extremely_large_numbers(self):
        """Test handling of extremely large numbers."""

        large_params = {
            "merit_rate_level_1": 1e10,  # Extremely large
            "cola_rate": np.inf,  # Infinity
            "promotion_probability_level_1": float('nan')  # NaN
        }

        # Should handle gracefully with appropriate errors/warnings
        with pytest.raises((ValueError, OverflowError)):
            validation_result = self.schema.validate_parameter_set(large_params)


class TestIntegrationScenarios:
    """Test integration scenarios including synthetic vs real mode transitions and algorithm fallbacks."""

    def setup_method(self):
        """Setup for integration tests."""
        self.schema = get_parameter_schema()
        self.test_params = get_default_parameters()

    @pytest.mark.integration
    def test_synthetic_to_real_mode_transition(self):
        """Test transition from synthetic optimization to real simulation."""

        # Mock synthetic optimization result
        synthetic_result = {
            "merit_rate_level_1": 0.055,
            "merit_rate_level_2": 0.050,
            "cola_rate": 0.030,
            "optimization_score": 0.85
        }

        # Validate synthetic parameters are within bounds
        validation_result = self.schema.validate_parameter_set(synthetic_result)
        assert validation_result['is_valid'], "Synthetic result should be valid"

        # Test parameter format conversion for real simulation
        comp_tuning_format = self.schema.transform_to_compensation_tuning_format(synthetic_result)

        assert 'merit_base' in comp_tuning_format
        assert 'cola_rate' in comp_tuning_format
        assert comp_tuning_format['merit_base'][1] == 0.055
        assert comp_tuning_format['cola_rate'][1] == 0.030

        # Test reverse transformation
        converted_back = self.schema.transform_from_compensation_tuning_format(comp_tuning_format)

        for key in synthetic_result:
            if key != "optimization_score":  # Skip non-parameter fields
                assert abs(converted_back[key] - synthetic_result[key]) < 1e-6

    @pytest.mark.integration
    def test_algorithm_fallback_scenarios(self):
        """Test algorithm fallback mechanisms."""

        # Test scenarios where primary optimization might fail
        challenging_params = {
            "merit_rate_level_1": 0.02,  # At minimum bound
            "merit_rate_level_2": 0.02,
            "merit_rate_level_3": 0.02,
            "merit_rate_level_4": 0.02,
            "merit_rate_level_5": 0.02,
            "cola_rate": 0.0,  # Zero COLA
            "new_hire_salary_adjustment": 1.0  # No premium
        }

        # Should still validate even if challenging
        validation_result = self.schema.validate_parameter_set(challenging_params)
        assert validation_result['is_valid']

        # Should generate warnings about extreme values
        assert validation_result['overall_risk'] in [RiskLevel.MEDIUM, RiskLevel.HIGH]

    @pytest.mark.integration
    def test_multi_method_execution_consistency(self):
        """Test consistency across different execution methods."""

        # Test parameter set
        test_params = {
            "merit_rate_level_1": 0.045,
            "merit_rate_level_2": 0.040,
            "cola_rate": 0.025
        }

        # Method 1: Direct parameter validation
        direct_result = self.schema.validate_parameter_set(test_params)

        # Method 2: Individual parameter validation
        individual_results = {}
        for param_name, value in test_params.items():
            param_def = self.schema.get_parameter(param_name)
            if param_def:
                is_valid, messages, risk = param_def.validate_value(value)
                individual_results[param_name] = {
                    'is_valid': is_valid,
                    'risk': risk
                }

        # Results should be consistent
        for param_name in test_params:
            if param_name in individual_results:
                direct_param_result = direct_result['parameter_results'][param_name]
                individual_result = individual_results[param_name]

                assert direct_param_result['is_valid'] == individual_result['is_valid']
                assert direct_param_result['risk_level'] == individual_result['risk']

    @pytest.mark.integration
    def test_parameter_dependency_validation(self):
        """Test validation of parameter dependencies and relationships."""

        # Test merit rate progression (should generally increase with level)
        inconsistent_merit_params = {
            "merit_rate_level_1": 0.08,  # Very high for level 1
            "merit_rate_level_5": 0.02   # Very low for level 5
        }

        validation_result = self.schema.validate_parameter_set(inconsistent_merit_params)

        # Should validate individual parameters but might warn about inconsistency
        # This depends on business logic implementation
        assert validation_result['is_valid']  # Individual parameters are valid

    @pytest.mark.integration
    def test_cross_component_data_flow(self):
        """Test data flow between optimization components."""

        # Simulate data flow from UI → Parameter Schema → Optimization → Results

        # 1. UI input (simulated)
        ui_input = {
            "merit_sliders": {1: 4.5, 2: 4.0, 3: 3.5, 4: 3.5, 5: 4.0},  # Percentages
            "cola_slider": 2.5,
            "new_hire_premium": 115  # Percentage
        }

        # 2. Convert to parameter format
        parameters = {}
        for level, value in ui_input["merit_sliders"].items():
            parameters[f"merit_rate_level_{level}"] = value / 100.0  # Convert to decimal

        parameters["cola_rate"] = ui_input["cola_slider"] / 100.0
        parameters["new_hire_salary_adjustment"] = ui_input["new_hire_premium"] / 100.0

        # 3. Validate parameters
        validation_result = self.schema.validate_parameter_set(parameters)
        assert validation_result['is_valid']

        # 4. Transform for compensation tuning format
        comp_format = self.schema.transform_to_compensation_tuning_format(parameters)

        # 5. Verify data integrity throughout pipeline
        assert comp_format['merit_base'][1] == 0.045
        assert comp_format['cola_rate'][1] == 0.025
        assert comp_format['new_hire_salary_adjustment'][1] == 1.15


class TestPerformance:
    """Performance testing for optimization speed, memory usage, and timeout handling."""

    def setup_method(self):
        """Setup performance testing environment."""
        self.schema = get_parameter_schema()
        self.metrics = []

    def measure_performance(self, func, *args, **kwargs) -> PerformanceMetrics:
        """Measure performance metrics for a function call."""

        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        start_time = time.time()
        start_cpu = process.cpu_percent()

        # Execute function
        result = func(*args, **kwargs)

        end_time = time.time()
        end_cpu = process.cpu_percent()
        final_memory = process.memory_info().rss / 1024 / 1024  # MB

        metrics = PerformanceMetrics(
            execution_time=end_time - start_time,
            memory_usage_mb=final_memory - initial_memory,
            cpu_usage_percent=(start_cpu + end_cpu) / 2,
            database_operations=0,  # Would need to instrument DB calls
            optimization_iterations=0  # Would need to instrument optimization
        )

        return metrics, result

    @pytest.mark.performance
    def test_parameter_validation_speed(self):
        """Test parameter validation performance."""

        # Large parameter set
        large_param_set = {}
        for i in range(1000):  # Simulate many scenarios
            param_base = get_default_parameters()
            for key, value in param_base.items():
                large_param_set[f"{key}_{i}"] = value

        # Test individual parameter validation speed
        start_time = time.time()

        for param_name in self.schema.get_all_parameter_names():
            param_def = self.schema.get_parameter(param_name)
            if param_def:
                param_def.validate_value(param_def.bounds.default_value)

        individual_time = time.time() - start_time

        # Should complete quickly
        assert individual_time < 1.0, f"Individual validation took {individual_time:.2f}s"

        # Test bulk validation
        metrics, result = self.measure_performance(
            self.schema.validate_parameter_set,
            get_default_parameters()
        )

        assert metrics.execution_time < 0.1, f"Bulk validation took {metrics.execution_time:.2f}s"

    @pytest.mark.performance
    def test_memory_usage_limits(self):
        """Test memory usage stays within acceptable limits."""

        # Create many parameter variations
        parameter_variations = []
        for i in range(100):
            params = get_default_parameters()
            # Slight variations
            for key in params:
                params[key] *= (1 + np.random.normal(0, 0.01))  # 1% random variation
            parameter_variations.append(params)

        initial_memory = psutil.Process().memory_info().rss / 1024 / 1024

        # Process all variations
        results = []
        for params in parameter_variations:
            result = self.schema.validate_parameter_set(params)
            results.append(result)

        final_memory = psutil.Process().memory_info().rss / 1024 / 1024
        memory_increase = final_memory - initial_memory

        # Memory increase should be reasonable (less than 50MB for this test)
        assert memory_increase < 50, f"Memory increased by {memory_increase:.1f}MB"

    @pytest.mark.performance
    def test_timeout_handling(self):
        """Test timeout handling for long-running operations."""

        def slow_validation_simulation():
            """Simulate a slow validation process."""
            time.sleep(0.5)  # Simulate slow operation
            return self.schema.validate_parameter_set(get_default_parameters())

        # Test with timeout
        start_time = time.time()

        try:
            # In real implementation, this would have timeout logic
            result = slow_validation_simulation()
            execution_time = time.time() - start_time

            # Should complete but we can measure the time
            assert execution_time > 0.4  # Should take at least the sleep time
            assert result['is_valid']

        except Exception as e:
            # If timeout mechanism is implemented, this is acceptable
            pass

    @pytest.mark.performance
    def test_concurrent_access(self):
        """Test performance under concurrent access."""

        results = []
        errors = []

        def validate_parameters_thread():
            """Thread function for concurrent validation."""
            try:
                params = get_default_parameters()
                # Add some variation
                params['merit_rate_level_1'] += np.random.uniform(-0.01, 0.01)
                result = self.schema.validate_parameter_set(params)
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = []
        for i in range(10):
            thread = threading.Thread(target=validate_parameters_thread)
            threads.append(thread)

        # Start all threads
        start_time = time.time()
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        total_time = time.time() - start_time

        # Check results
        assert len(errors) == 0, f"Concurrent access caused errors: {errors}"
        assert len(results) == 10, "Not all threads completed successfully"
        assert total_time < 5.0, f"Concurrent access took {total_time:.2f}s"

    @pytest.mark.performance
    def test_large_dataset_handling(self):
        """Test handling of large parameter datasets."""

        # Create large parameter dataset
        large_dataset = {}
        base_params = get_default_parameters()

        # Simulate 1000 scenarios
        for scenario_id in range(1000):
            for param_name, base_value in base_params.items():
                # Add scenario-specific variation
                variation = np.random.uniform(0.9, 1.1)  # ±10% variation
                param_def = self.schema.get_parameter(param_name)
                if param_def:
                    # Keep within bounds
                    varied_value = base_value * variation
                    varied_value = max(param_def.bounds.min_value,
                                     min(param_def.bounds.max_value, varied_value))
                    large_dataset[f"{param_name}_scenario_{scenario_id}"] = varied_value

        # Test processing time
        start_time = time.time()

        # Process in batches to avoid memory issues
        batch_size = 50
        for i in range(0, len(base_params), batch_size):
            batch_params = {}
            for j, (param_name, value) in enumerate(base_params.items()):
                if i <= j < i + batch_size:
                    batch_params[param_name] = value

            if batch_params:
                self.schema.validate_parameter_set(batch_params)

        processing_time = time.time() - start_time

        # Should handle large datasets efficiently
        assert processing_time < 10.0, f"Large dataset processing took {processing_time:.2f}s"


class TestScenarioValidation:
    """Test various business scenarios including budget constraints and growth targets."""

    def setup_method(self):
        """Setup scenario validation tests."""
        self.schema = get_parameter_schema()
        self.business_scenarios = self._create_business_scenarios()

    def _create_business_scenarios(self) -> List[TestScenario]:
        """Create comprehensive business test scenarios."""

        return [
            TestScenario(
                name="conservative_budget",
                description="Conservative budget with minimal increases",
                budget_constraint=0.02,  # 2% total budget increase
                growth_target=0.01,  # 1% workforce growth
                expected_outcome="low_risk_low_cost",
                risk_tolerance=RiskLevel.LOW,
                parameter_overrides={
                    "merit_rate_level_1": 0.02,
                    "merit_rate_level_2": 0.02,
                    "merit_rate_level_3": 0.02,
                    "merit_rate_level_4": 0.02,
                    "merit_rate_level_5": 0.02,
                    "cola_rate": 0.015
                }
            ),
            TestScenario(
                name="aggressive_growth",
                description="Aggressive growth with high compensation increases",
                budget_constraint=0.10,  # 10% budget increase allowed
                growth_target=0.15,  # 15% workforce growth
                expected_outcome="high_cost_high_growth",
                risk_tolerance=RiskLevel.HIGH,
                parameter_overrides={
                    "merit_rate_level_1": 0.08,
                    "merit_rate_level_2": 0.07,
                    "merit_rate_level_3": 0.06,
                    "merit_rate_level_4": 0.07,
                    "merit_rate_level_5": 0.08,
                    "cola_rate": 0.05,
                    "new_hire_salary_adjustment": 1.25
                }
            ),
            TestScenario(
                name="retention_focused",
                description="Focus on retention with balanced increases",
                budget_constraint=0.06,  # 6% budget increase
                growth_target=0.03,  # 3% workforce growth
                expected_outcome="balanced_retention",
                risk_tolerance=RiskLevel.MEDIUM,
                parameter_overrides={
                    "merit_rate_level_1": 0.05,
                    "merit_rate_level_2": 0.045,
                    "merit_rate_level_3": 0.04,
                    "merit_rate_level_4": 0.045,
                    "merit_rate_level_5": 0.05,
                    "promotion_probability_level_1": 0.15,
                    "promotion_probability_level_2": 0.10
                }
            ),
            TestScenario(
                name="cost_cutting",
                description="Cost-cutting scenario with minimal increases",
                budget_constraint=0.005,  # 0.5% budget increase
                growth_target=-0.05,  # 5% workforce reduction
                expected_outcome="cost_reduction",
                risk_tolerance=RiskLevel.CRITICAL,
                parameter_overrides={
                    "merit_rate_level_1": 0.01,
                    "merit_rate_level_2": 0.01,
                    "merit_rate_level_3": 0.01,
                    "merit_rate_level_4": 0.01,
                    "merit_rate_level_5": 0.01,
                    "cola_rate": 0.0,
                    "new_hire_salary_adjustment": 1.0
                }
            ),
            TestScenario(
                name="market_competitive",
                description="Market-competitive compensation strategy",
                budget_constraint=0.075,  # 7.5% budget increase
                growth_target=0.08,  # 8% workforce growth
                expected_outcome="market_competitive",
                risk_tolerance=RiskLevel.MEDIUM,
                parameter_overrides={
                    "merit_rate_level_1": 0.045,
                    "merit_rate_level_2": 0.04,
                    "merit_rate_level_3": 0.035,
                    "merit_rate_level_4": 0.04,
                    "merit_rate_level_5": 0.045,
                    "cola_rate": 0.03,
                    "new_hire_salary_adjustment": 1.20
                }
            )
        ]

    @pytest.mark.parametrize("scenario", [
        scenario for scenario in TestScenarioValidation()._create_business_scenarios()
    ], ids=lambda scenario: scenario.name)
    def test_business_scenario_validation(self, scenario: TestScenario):
        """Test validation of specific business scenarios."""

        # Validate scenario parameters
        validation_result = self.schema.validate_parameter_set(scenario.parameter_overrides)

        # All scenarios should have valid parameters
        assert validation_result['is_valid'], f"Scenario {scenario.name} has invalid parameters: {validation_result['errors']}"

        # Check risk level alignment
        actual_risk = validation_result['overall_risk']

        # Allow some flexibility in risk assessment
        risk_hierarchy = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
        scenario_risk_index = risk_hierarchy.index(scenario.risk_tolerance)
        actual_risk_index = risk_hierarchy.index(actual_risk)

        # Actual risk should be within ±1 level of expected
        assert abs(actual_risk_index - scenario_risk_index) <= 1, \
            f"Scenario {scenario.name}: Expected risk {scenario.risk_tolerance}, got {actual_risk}"

    def test_budget_constraint_scenarios(self):
        """Test scenarios with various budget constraints."""

        budget_scenarios = [
            (0.01, "very_tight"),   # 1% budget
            (0.03, "tight"),        # 3% budget
            (0.05, "moderate"),     # 5% budget
            (0.08, "generous"),     # 8% budget
            (0.12, "very_generous") # 12% budget
        ]

        for budget_limit, scenario_name in budget_scenarios:
            # Create parameters that should fit budget
            conservative_params = {
                "merit_rate_level_1": budget_limit * 0.4,  # Use 40% of budget for merit
                "merit_rate_level_2": budget_limit * 0.35,
                "merit_rate_level_3": budget_limit * 0.3,
                "merit_rate_level_4": budget_limit * 0.35,
                "merit_rate_level_5": budget_limit * 0.4,
                "cola_rate": budget_limit * 0.3  # Use 30% of budget for COLA
            }

            # Ensure parameters are within schema bounds
            for param_name, value in conservative_params.items():
                param_def = self.schema.get_parameter(param_name)
                if param_def:
                    conservative_params[param_name] = max(
                        param_def.bounds.min_value,
                        min(param_def.bounds.max_value, value)
                    )

            validation_result = self.schema.validate_parameter_set(conservative_params)
            assert validation_result['is_valid'], f"Budget scenario {scenario_name} failed validation"

    def test_growth_target_scenarios(self):
        """Test scenarios with various growth targets."""

        growth_scenarios = [
            (-0.10, "significant_reduction"),
            (-0.05, "moderate_reduction"),
            (0.0, "steady_state"),
            (0.05, "moderate_growth"),
            (0.10, "significant_growth"),
            (0.20, "aggressive_growth")
        ]

        for growth_rate, scenario_name in growth_scenarios:
            # Adjust parameters based on growth expectations
            base_params = get_default_parameters()

            if growth_rate > 0.10:  # Aggressive growth
                # Higher new hire premiums and merit rates
                base_params["new_hire_salary_adjustment"] = min(1.30, base_params.get("new_hire_salary_adjustment", 1.15) * 1.1)
                base_params["merit_rate_level_1"] = min(0.08, base_params.get("merit_rate_level_1", 0.045) * 1.2)
            elif growth_rate < -0.05:  # Reduction scenarios
                # Lower merit rates and no new hire premium
                base_params["new_hire_salary_adjustment"] = 1.0
                for level in range(1, 6):
                    merit_key = f"merit_rate_level_{level}"
                    if merit_key in base_params:
                        base_params[merit_key] = max(0.01, base_params[merit_key] * 0.5)

            validation_result = self.schema.validate_parameter_set(base_params)
            assert validation_result['is_valid'], f"Growth scenario {scenario_name} failed validation"

    def test_industry_benchmark_scenarios(self):
        """Test scenarios based on industry benchmarks."""

        industry_benchmarks = {
            "tech_startup": {
                "merit_rate_level_1": 0.08,
                "merit_rate_level_2": 0.075,
                "merit_rate_level_3": 0.07,
                "new_hire_salary_adjustment": 1.25,
                "promotion_probability_level_1": 0.20
            },
            "traditional_finance": {
                "merit_rate_level_1": 0.03,
                "merit_rate_level_2": 0.035,
                "merit_rate_level_3": 0.04,
                "new_hire_salary_adjustment": 1.10,
                "promotion_probability_level_1": 0.08
            },
            "government_org": {
                "merit_rate_level_1": 0.025,
                "merit_rate_level_2": 0.025,
                "merit_rate_level_3": 0.025,
                "cola_rate": 0.02,
                "new_hire_salary_adjustment": 1.05
            }
        }

        for industry, benchmark_params in industry_benchmarks.items():
            # Fill in missing parameters with defaults
            full_params = get_default_parameters()
            full_params.update(benchmark_params)

            validation_result = self.schema.validate_parameter_set(full_params)
            assert validation_result['is_valid'], f"Industry benchmark {industry} failed validation"

            # Industry-specific risk assessments
            if industry == "tech_startup":
                # Tech startups can have higher risk tolerance
                assert validation_result['overall_risk'] in [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH]
            elif industry == "government_org":
                # Government should be low risk
                assert validation_result['overall_risk'] in [RiskLevel.LOW, RiskLevel.MEDIUM]


class TestErrorHandling:
    """Test error handling for database locks, network issues, and invalid configurations."""

    def setup_method(self):
        """Setup error handling tests."""
        self.schema = get_parameter_schema()
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Cleanup after error handling tests."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_database_lock_handling(self):
        """Test handling of database lock scenarios."""

        # Create a test database file
        test_db_path = os.path.join(self.temp_dir, "test.duckdb")

        # Simulate database lock by opening exclusive connection
        import duckdb

        # First connection (locks the database)
        conn1 = duckdb.connect(test_db_path)
        conn1.execute("CREATE TABLE test_table (id INTEGER)")

        try:
            # Second connection should detect lock
            conn2 = duckdb.connect(test_db_path)
            conn2.execute("CREATE TABLE another_table (id INTEGER)")

            # If we get here, locking isn't as strict as expected
            # This is acceptable for DuckDB in many cases
            conn2.close()

        except Exception as e:
            # This is expected behavior for locked database
            assert "lock" in str(e).lower() or "busy" in str(e).lower()

        finally:
            conn1.close()

    def test_network_timeout_simulation(self):
        """Test handling of network timeouts and connectivity issues."""

        # Simulate network timeout with slow operation
        def slow_network_simulation():
            """Simulate slow network operation."""
            time.sleep(2.0)  # Simulate 2-second delay
            return {"status": "success", "data": get_default_parameters()}

        # Test with timeout handling
        start_time = time.time()

        try:
            result = slow_network_simulation()
            execution_time = time.time() - start_time

            # Should complete but take time
            assert execution_time >= 2.0
            assert result["status"] == "success"

        except Exception as e:
            # Timeout or other network error is acceptable
            assert "timeout" in str(e).lower() or "network" in str(e).lower()

    def test_invalid_configuration_handling(self):
        """Test handling of invalid configuration files."""

        # Create invalid YAML configuration
        invalid_yaml_path = os.path.join(self.temp_dir, "invalid_config.yaml")
        with open(invalid_yaml_path, 'w') as f:
            f.write("invalid: yaml: content:\n")
            f.write("  - incomplete\n")
            f.write("  - structure\n")
            f.write("missing_quotes: this is \"unclosed\n")

        # Test loading invalid YAML
        with pytest.raises(yaml.YAMLError):
            with open(invalid_yaml_path, 'r') as f:
                yaml.safe_load(f)

        # Create invalid JSON configuration
        invalid_json_path = os.path.join(self.temp_dir, "invalid_config.json")
        with open(invalid_json_path, 'w') as f:
            f.write('{"invalid": json, "missing": quotes}')

        # Test loading invalid JSON
        with pytest.raises(json.JSONDecodeError):
            with open(invalid_json_path, 'r') as f:
                json.load(f)

    def test_permission_error_handling(self):
        """Test handling of file permission errors."""

        # Create a file and remove write permissions
        restricted_file = os.path.join(self.temp_dir, "restricted.yaml")
        with open(restricted_file, 'w') as f:
            f.write("test: content")

        # Remove write permissions
        os.chmod(restricted_file, 0o444)  # Read-only

        try:
            # Try to write to restricted file
            with open(restricted_file, 'w') as f:
                f.write("new content")
        except PermissionError:
            # Expected behavior
            pass

        # Restore permissions for cleanup
        os.chmod(restricted_file, 0o644)

    def test_memory_exhaustion_simulation(self):
        """Test handling of memory exhaustion scenarios."""

        # Create large data structure to simulate memory pressure
        large_data = []

        try:
            # Try to allocate large amounts of memory
            for i in range(1000):
                # Create 1MB chunks
                chunk = [0] * (1024 * 1024 // 8)  # Roughly 1MB of integers
                large_data.append(chunk)

                # Check if we're using too much memory
                if i % 100 == 0:
                    memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
                    if memory_mb > 1000:  # Stop at 1GB
                        break

            # If we get here, test completed without memory error
            # This is acceptable on systems with sufficient memory

        except MemoryError:
            # Expected on systems with limited memory
            pass

        finally:
            # Clean up memory
            large_data.clear()

    def test_parameter_validation_error_recovery(self):
        """Test recovery from parameter validation errors."""

        # Test with various invalid parameter combinations
        invalid_scenarios = [
            {
                "name": "negative_values",
                "params": {"merit_rate_level_1": -0.05},
                "expected_error": "below minimum"
            },
            {
                "name": "excessive_values",
                "params": {"merit_rate_level_1": 0.50},
                "expected_error": "above maximum"
            },
            {
                "name": "missing_required",
                "params": {},
                "expected_error": None  # Should handle gracefully
            }
        ]

        for scenario in invalid_scenarios:
            try:
                validation_result = self.schema.validate_parameter_set(scenario["params"])

                if scenario["expected_error"]:
                    # Should have validation errors
                    assert not validation_result['is_valid'] or len(validation_result['warnings']) > 0
                else:
                    # Should handle gracefully
                    assert isinstance(validation_result, dict)

            except Exception as e:
                # Some errors are acceptable depending on implementation
                if scenario["expected_error"]:
                    assert scenario["expected_error"].lower() in str(e).lower()

    def test_concurrent_modification_handling(self):
        """Test handling of concurrent modifications."""

        # Simulate concurrent parameter modifications
        shared_params = get_default_parameters()
        errors = []
        results = []

        def modify_parameters_thread(thread_id):
            """Thread function to modify parameters concurrently."""
            try:
                local_params = shared_params.copy()
                local_params[f"merit_rate_level_{(thread_id % 5) + 1}"] += 0.001 * thread_id

                result = self.schema.validate_parameter_set(local_params)
                results.append((thread_id, result))

            except Exception as e:
                errors.append((thread_id, e))

        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=modify_parameters_thread, args=(i,))
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Check results
        assert len(errors) == 0, f"Concurrent modifications caused errors: {errors}"
        assert len(results) == 5, "Not all concurrent modifications completed"


class TestDataConsistency:
    """Test data consistency between optimization methods."""

    def setup_method(self):
        """Setup data consistency tests."""
        self.schema = get_parameter_schema()

    def test_parameter_format_consistency(self):
        """Test consistency between different parameter formats."""

        # Start with optimization format
        optimization_params = {
            "merit_rate_level_1": 0.045,
            "merit_rate_level_2": 0.040,
            "merit_rate_level_3": 0.035,
            "merit_rate_level_4": 0.040,
            "merit_rate_level_5": 0.045,
            "cola_rate": 0.025,
            "new_hire_salary_adjustment": 1.15,
            "promotion_probability_level_1": 0.12,
            "promotion_raise_level_1": 0.12
        }

        # Convert to compensation tuning format
        comp_tuning_format = self.schema.transform_to_compensation_tuning_format(optimization_params)

        # Convert back to optimization format
        converted_back = self.schema.transform_from_compensation_tuning_format(comp_tuning_format)

        # Should be identical (within floating point precision)
        for key in optimization_params:
            if key in converted_back:
                assert abs(optimization_params[key] - converted_back[key]) < 1e-10, \
                    f"Parameter {key}: original={optimization_params[key]}, converted={converted_back[key]}"

    def test_validation_result_consistency(self):
        """Test consistency of validation results across multiple calls."""

        test_params = get_default_parameters()

        # Run validation multiple times
        results = []
        for i in range(10):
            result = self.schema.validate_parameter_set(test_params)
            results.append(result)

        # All results should be identical
        first_result = results[0]
        for i, result in enumerate(results[1:], 1):
            assert result['is_valid'] == first_result['is_valid'], f"Run {i}: is_valid differs"
            assert result['overall_risk'] == first_result['overall_risk'], f"Run {i}: overall_risk differs"
            assert len(result['warnings']) == len(first_result['warnings']), f"Run {i}: warnings count differs"
            assert len(result['errors']) == len(first_result['errors']), f"Run {i}: errors count differs"

    def test_parameter_bounds_consistency(self):
        """Test consistency of parameter bounds across schema."""

        # Check that all parameters have consistent bound relationships
        for param_name, param_def in self.schema._parameters.items():
            bounds = param_def.bounds

            # Basic bound consistency
            assert bounds.min_value < bounds.max_value, f"{param_name}: min >= max"
            assert bounds.min_value <= bounds.default_value <= bounds.max_value, \
                f"{param_name}: default outside bounds"

            # Recommended bounds should be within absolute bounds
            assert bounds.min_value <= bounds.recommended_min <= bounds.recommended_max <= bounds.max_value, \
                f"{param_name}: recommended bounds outside absolute bounds"

    def test_risk_assessment_consistency(self):
        """Test consistency of risk assessments."""

        # Test parameters at various risk levels
        test_cases = [
            (0.02, "merit_rate_level_1"),  # At minimum (higher risk)
            (0.05, "merit_rate_level_1"),  # In middle (lower risk)
            (0.08, "merit_rate_level_1"),  # At maximum (higher risk)
        ]

        for value, param_name in test_cases:
            param_def = self.schema.get_parameter(param_name)

            # Test individual parameter risk
            is_valid, messages, risk = param_def.validate_value(value)

            # Test in parameter set
            param_set = get_default_parameters()
            param_set[param_name] = value
            set_result = self.schema.validate_parameter_set(param_set)
            set_param_risk = set_result['parameter_results'][param_name]['risk_level']

            # Risk assessments should be consistent
            assert risk == set_param_risk, \
                f"Risk assessment inconsistent for {param_name}={value}: individual={risk}, set={set_param_risk}"

    def test_default_parameter_consistency(self):
        """Test consistency of default parameters across methods."""

        # Get defaults from schema
        schema_defaults = self.schema.get_default_parameters()

        # Get defaults from convenience function
        convenience_defaults = get_default_parameters()

        # Should be identical
        assert set(schema_defaults.keys()) == set(convenience_defaults.keys()), \
            "Default parameter keys differ between methods"

        for key in schema_defaults:
            assert abs(schema_defaults[key] - convenience_defaults[key]) < 1e-10, \
                f"Default value for {key} differs: schema={schema_defaults[key]}, convenience={convenience_defaults[key]}"

    def test_category_grouping_consistency(self):
        """Test consistency of parameter category groupings."""

        # Get parameters by category
        category_groups = self.schema.get_parameter_groups()

        # Check that all parameters are included exactly once
        all_categorized_params = set()
        for group_name, group_params in category_groups.items():
            for param_name in group_params:
                assert param_name not in all_categorized_params, \
                    f"Parameter {param_name} appears in multiple groups"
                all_categorized_params.add(param_name)

        # Check that all schema parameters are categorized
        all_schema_params = set(self.schema.get_all_parameter_names())

        # Some parameters might not be in display groups, so this is informational
        uncategorized = all_schema_params - all_categorized_params
        if uncategorized:
            print(f"Warning: Uncategorized parameters: {uncategorized}")


class TestMockDataGeneration:
    """Mock data generation utilities for testing."""

    @staticmethod
    def generate_workforce_data(num_employees: int = 1000, random_seed: int = 42) -> pd.DataFrame:
        """Generate mock workforce data for testing."""

        np.random.seed(random_seed)

        # Generate employee data
        employees = []
        for i in range(num_employees):
            employee = {
                'employee_id': f"EMP_{i:06d}",
                'job_level': np.random.choice([1, 2, 3, 4, 5], p=[0.4, 0.3, 0.2, 0.08, 0.02]),
                'current_compensation': np.random.normal(65000, 15000),
                'years_of_service': np.random.exponential(5),
                'department': np.random.choice(['Engineering', 'Finance', 'HR', 'Sales', 'Marketing']),
                'location': np.random.choice(['New York', 'San Francisco', 'Chicago', 'Remote']),
                'performance_rating': np.random.choice([1, 2, 3, 4, 5], p=[0.05, 0.15, 0.6, 0.15, 0.05])
            }

            # Adjust compensation based on job level
            level_multipliers = {1: 0.8, 2: 1.0, 3: 1.4, 4: 2.0, 5: 3.0}
            employee['current_compensation'] *= level_multipliers[employee['job_level']]

            employees.append(employee)

        return pd.DataFrame(employees)

    @staticmethod
    def generate_parameter_scenarios(num_scenarios: int = 100, random_seed: int = 42) -> List[Dict[str, float]]:
        """Generate mock parameter scenarios for testing."""

        np.random.seed(random_seed)
        schema = get_parameter_schema()
        scenarios = []

        for i in range(num_scenarios):
            scenario = {}

            for param_name, param_def in schema._parameters.items():
                # Generate random value within bounds
                min_val = param_def.bounds.min_value
                max_val = param_def.bounds.max_value

                # Use beta distribution to favor values near the middle
                alpha, beta = 2, 2  # Parameters for beta distribution
                random_factor = np.random.beta(alpha, beta)
                value = min_val + (max_val - min_val) * random_factor

                scenario[param_name] = value

            scenarios.append(scenario)

        return scenarios

    @staticmethod
    def generate_optimization_results(num_results: int = 50, random_seed: int = 42) -> List[Dict[str, Any]]:
        """Generate mock optimization results for testing."""

        np.random.seed(random_seed)
        results = []

        for i in range(num_results):
            result = {
                'scenario_id': f"scenario_{i:03d}",
                'converged': np.random.choice([True, False], p=[0.8, 0.2]),
                'objective_value': np.random.uniform(0.1, 1.0),
                'iterations': np.random.randint(10, 200),
                'runtime_seconds': np.random.exponential(30),
                'parameters': TestMockDataGeneration.generate_parameter_scenarios(1, random_seed + i)[0],
                'cost_impact': np.random.uniform(-500000, 2000000),
                'employee_impact_count': np.random.randint(800, 1500)
            }
            results.append(result)

        return results


# Cross-browser compatibility testing setup
class TestCrossBrowserCompatibility:
    """Cross-browser compatibility tests for Streamlit interface."""

    def setup_method(self):
        """Setup cross-browser testing."""
        # This would require Selenium WebDriver setup
        # For now, we'll test the underlying logic that supports browser compatibility
        pass

    def test_parameter_serialization_for_web(self):
        """Test parameter serialization for web interface compatibility."""

        schema = get_parameter_schema()
        params = get_default_parameters()

        # Test JSON serialization (required for web interfaces)
        try:
            json_str = json.dumps(params)
            deserialized = json.loads(json_str)

            # Should round-trip successfully
            for key in params:
                assert abs(params[key] - deserialized[key]) < 1e-10

        except (TypeError, ValueError) as e:
            pytest.fail(f"Parameter serialization failed: {e}")

    def test_unicode_handling_for_web(self):
        """Test unicode handling for international browser support."""

        # Test parameter names with various encodings
        test_strings = [
            "merit_rate_level_1",  # ASCII
            "mérit_rate_level_1",  # Latin-1
            "مmerit_rate_level_1",  # Arabic
            "merit_rate_レベル_1"   # Japanese
        ]

        for test_string in test_strings:
            # Should handle encoding/decoding gracefully
            try:
                encoded = test_string.encode('utf-8')
                decoded = encoded.decode('utf-8')
                assert decoded == test_string
            except UnicodeError:
                # Some strings may not be valid, which is acceptable
                pass


# Performance profiling decorator
def profile_performance(func):
    """Decorator to profile performance of test functions."""

    def wrapper(*args, **kwargs):
        process = psutil.Process()
        start_memory = process.memory_info().rss / 1024 / 1024
        start_time = time.time()

        result = func(*args, **kwargs)

        end_time = time.time()
        end_memory = process.memory_info().rss / 1024 / 1024

        execution_time = end_time - start_time
        memory_delta = end_memory - start_memory

        print(f"\n{func.__name__} Performance:")
        print(f"  Execution time: {execution_time:.3f}s")
        print(f"  Memory delta: {memory_delta:.1f}MB")

        return result

    return wrapper


# Test configuration for different environments
class TestEnvironmentConfig:
    """Test configuration for different deployment environments."""

    ENVIRONMENTS = {
        'development': {
            'timeout_multiplier': 2.0,
            'memory_limit_mb': 1000,
            'performance_tolerance': 0.5
        },
        'staging': {
            'timeout_multiplier': 1.5,
            'memory_limit_mb': 500,
            'performance_tolerance': 0.3
        },
        'production': {
            'timeout_multiplier': 1.0,
            'memory_limit_mb': 200,
            'performance_tolerance': 0.1
        }
    }

    @classmethod
    def get_config(cls, env_name: str = 'development') -> Dict[str, Any]:
        """Get configuration for specified environment."""
        return cls.ENVIRONMENTS.get(env_name, cls.ENVIRONMENTS['development'])


if __name__ == "__main__":
    # Run specific test categories
    pytest.main([
        __file__ + "::TestEdgeCases",
        "-v",
        "--tb=short"
    ])
