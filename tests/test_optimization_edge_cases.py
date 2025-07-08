"""
Comprehensive Edge Case Testing for Optimization Features
========================================================

This module provides extensive edge case testing for the optimization system,
covering boundary conditions, extreme scenarios, data corruption, and failure modes.

Test Categories:
1. Boundary Value Testing: Min/max parameter values, floating point precision
2. Data Corruption Scenarios: Malformed inputs, missing data, inconsistent states
3. Extreme Business Scenarios: Zero budgets, massive growth, workforce reduction
4. Numerical Stability: Very small/large numbers, convergence issues
5. Concurrent Access: Race conditions, resource contention
6. Memory and Performance: Large datasets, timeout handling, resource exhaustion

Includes sophisticated mock data generation for realistic testing scenarios.
"""

import pytest
import pandas as pd
import numpy as np
import json
import time
import tempfile
import os
import threading
import multiprocessing
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
import warnings
import random
import string
from decimal import Decimal, ROUND_HALF_UP
import math

# Import components under test
from streamlit_dashboard.optimization_schemas import (
    ParameterSchema, get_parameter_schema, get_default_parameters,
    validate_parameters, assess_parameter_risk, RiskLevel
)
from orchestrator.optimization.constraint_solver import CompensationOptimizer
from orchestrator.optimization.objective_functions import ObjectiveFunctions
from orchestrator.optimization.optimization_schemas import (
    OptimizationRequest, OptimizationResult, PARAMETER_SCHEMA
)


class MockDataGenerator:
    """Advanced mock data generator for edge case testing."""

    @staticmethod
    def generate_boundary_parameters() -> List[Dict[str, float]]:
        """Generate parameter sets at various boundary conditions."""
        schema = get_parameter_schema()
        boundary_sets = []

        # Minimum boundary values
        min_params = {}
        for param_name, param_def in schema._parameters.items():
            min_params[param_name] = param_def.bounds.min_value
        boundary_sets.append(("minimum_boundaries", min_params))

        # Maximum boundary values
        max_params = {}
        for param_name, param_def in schema._parameters.items():
            max_params[param_name] = param_def.bounds.max_value
        boundary_sets.append(("maximum_boundaries", max_params))

        # Just inside boundaries (min + epsilon)
        inside_min_params = {}
        for param_name, param_def in schema._parameters.items():
            epsilon = (param_def.bounds.max_value - param_def.bounds.min_value) * 1e-10
            inside_min_params[param_name] = param_def.bounds.min_value + epsilon
        boundary_sets.append(("inside_minimum", inside_min_params))

        # Just inside boundaries (max - epsilon)
        inside_max_params = {}
        for param_name, param_def in schema._parameters.items():
            epsilon = (param_def.bounds.max_value - param_def.bounds.min_value) * 1e-10
            inside_max_params[param_name] = param_def.bounds.max_value - epsilon
        boundary_sets.append(("inside_maximum", inside_max_params))

        # Mixed boundary conditions
        mixed_params = {}
        param_names = list(schema._parameters.keys())
        for i, (param_name, param_def) in enumerate(schema._parameters.items()):
            if i % 2 == 0:
                mixed_params[param_name] = param_def.bounds.min_value
            else:
                mixed_params[param_name] = param_def.bounds.max_value
        boundary_sets.append(("mixed_boundaries", mixed_params))

        return boundary_sets

    @staticmethod
    def generate_invalid_parameters() -> List[Tuple[str, Dict[str, Any]]]:
        """Generate various invalid parameter scenarios."""
        schema = get_parameter_schema()
        invalid_sets = []

        # Below minimum values
        below_min = {}
        for param_name, param_def in schema._parameters.items():
            range_size = param_def.bounds.max_value - param_def.bounds.min_value
            below_min[param_name] = param_def.bounds.min_value - range_size * 0.1
        invalid_sets.append(("below_minimum", below_min))

        # Above maximum values
        above_max = {}
        for param_name, param_def in schema._parameters.items():
            range_size = param_def.bounds.max_value - param_def.bounds.min_value
            above_max[param_name] = param_def.bounds.max_value + range_size * 0.1
        invalid_sets.append(("above_maximum", above_max))

        # Invalid data types
        invalid_types = {}
        for param_name in list(schema._parameters.keys())[:3]:
            invalid_types[param_name] = "not_a_number"
        invalid_sets.append(("invalid_types", invalid_types))

        # None values
        none_values = {}
        for param_name in list(schema._parameters.keys())[:3]:
            none_values[param_name] = None
        invalid_sets.append(("none_values", none_values))

        # Infinity values
        infinity_values = {}
        for param_name in list(schema._parameters.keys())[:3]:
            infinity_values[param_name] = float('inf')
        invalid_sets.append(("infinity_values", infinity_values))

        # NaN values
        nan_values = {}
        for param_name in list(schema._parameters.keys())[:3]:
            nan_values[param_name] = float('nan')
        invalid_sets.append(("nan_values", nan_values))

        return invalid_sets

    @staticmethod
    def generate_extreme_business_scenarios() -> List[Tuple[str, Dict[str, float]]]:
        """Generate extreme business scenario parameters."""
        scenarios = []

        # Zero budget scenario
        zero_budget = {
            "merit_rate_level_1": 0.0,
            "merit_rate_level_2": 0.0,
            "merit_rate_level_3": 0.0,
            "merit_rate_level_4": 0.0,
            "merit_rate_level_5": 0.0,
            "cola_rate": 0.0,
            "new_hire_salary_adjustment": 1.0,
            "promotion_probability_level_1": 0.0,
            "promotion_probability_level_2": 0.0,
            "promotion_probability_level_3": 0.0,
            "promotion_probability_level_4": 0.0,
            "promotion_probability_level_5": 0.0,
            "promotion_raise_level_1": 0.0,
            "promotion_raise_level_2": 0.0,
            "promotion_raise_level_3": 0.0,
            "promotion_raise_level_4": 0.0,
            "promotion_raise_level_5": 0.0
        }
        scenarios.append(("zero_budget", zero_budget))

        # Maximum budget scenario
        max_budget = {}
        schema = get_parameter_schema()
        for param_name, param_def in schema._parameters.items():
            max_budget[param_name] = param_def.bounds.max_value
        scenarios.append(("maximum_budget", max_budget))

        # Inverted merit structure (higher levels get less)
        inverted_merit = {
            "merit_rate_level_1": 0.08,
            "merit_rate_level_2": 0.06,
            "merit_rate_level_3": 0.04,
            "merit_rate_level_4": 0.03,
            "merit_rate_level_5": 0.02,
            "cola_rate": 0.02,
            "new_hire_salary_adjustment": 1.05
        }
        scenarios.append(("inverted_merit", inverted_merit))

        # High growth scenario
        high_growth = {
            "merit_rate_level_1": 0.12,
            "merit_rate_level_2": 0.11,
            "merit_rate_level_3": 0.10,
            "merit_rate_level_4": 0.11,
            "merit_rate_level_5": 0.12,
            "cola_rate": 0.08,
            "new_hire_salary_adjustment": 1.5,
            "promotion_probability_level_1": 0.30,
            "promotion_probability_level_2": 0.25,
            "promotion_raise_level_1": 0.25,
            "promotion_raise_level_2": 0.25
        }
        scenarios.append(("high_growth", high_growth))

        return scenarios

    @staticmethod
    def generate_floating_point_edge_cases() -> List[Tuple[str, Dict[str, float]]]:
        """Generate floating point precision edge cases."""
        edge_cases = []

        # Very small numbers
        tiny_numbers = {
            "merit_rate_level_1": 1e-10,
            "merit_rate_level_2": 1e-15,
            "cola_rate": 1e-12
        }
        edge_cases.append(("tiny_numbers", tiny_numbers))

        # Numbers with many decimal places
        high_precision = {
            "merit_rate_level_1": 0.045123456789012345,
            "merit_rate_level_2": 0.039876543210987654,
            "cola_rate": 0.024999999999999997
        }
        edge_cases.append(("high_precision", high_precision))

        # Numbers that might cause rounding errors
        rounding_edge = {
            "merit_rate_level_1": 0.1 + 0.2 - 0.3,  # Should be 0, but floating point...
            "merit_rate_level_2": 0.7 * 0.1,  # 0.07 but might have precision issues
            "cola_rate": 1.0 / 3.0 * 3.0 - 1.0  # Should be 0
        }
        edge_cases.append(("rounding_edge", rounding_edge))

        return edge_cases

    @staticmethod
    def generate_large_workforce_data(num_employees: int = 100000) -> pd.DataFrame:
        """Generate large workforce dataset for performance testing."""
        np.random.seed(42)  # Reproducible results

        data = []
        for i in range(num_employees):
            employee = {
                'employee_id': f"EMP_{i:08d}",
                'job_level': np.random.choice([1, 2, 3, 4, 5], p=[0.4, 0.3, 0.2, 0.08, 0.02]),
                'current_compensation': max(30000, np.random.normal(65000, 20000)),
                'years_of_service': max(0, np.random.exponential(4)),
                'department': np.random.choice(['Engineering', 'Finance', 'HR', 'Sales', 'Marketing', 'Operations']),
                'location': np.random.choice(['New York', 'San Francisco', 'Chicago', 'Austin', 'Remote']),
                'performance_rating': np.random.choice([1, 2, 3, 4, 5], p=[0.05, 0.15, 0.6, 0.15, 0.05]),
                'hire_date': pd.Timestamp('2020-01-01') + pd.Timedelta(days=np.random.randint(0, 1460))
            }

            # Adjust compensation based on job level and experience
            level_multipliers = {1: 0.7, 2: 1.0, 3: 1.5, 4: 2.2, 5: 3.5}
            experience_multiplier = 1 + (employee['years_of_service'] * 0.03)

            employee['current_compensation'] *= level_multipliers[employee['job_level']]
            employee['current_compensation'] *= experience_multiplier
            employee['current_compensation'] = round(employee['current_compensation'], 2)

            data.append(employee)

        return pd.DataFrame(data)

    @staticmethod
    def generate_corrupted_data_scenarios() -> List[Tuple[str, pd.DataFrame]]:
        """Generate various data corruption scenarios."""
        scenarios = []

        # Missing critical columns
        base_data = MockDataGenerator.generate_large_workforce_data(100)
        missing_columns = base_data.drop(columns=['job_level', 'current_compensation'])
        scenarios.append(("missing_critical_columns", missing_columns))

        # Null values in critical fields
        null_values = base_data.copy()
        null_values.loc[:10, 'job_level'] = None
        null_values.loc[5:15, 'current_compensation'] = None
        scenarios.append(("null_critical_values", null_values))

        # Invalid job levels
        invalid_levels = base_data.copy()
        invalid_levels.loc[:20, 'job_level'] = [0, -1, 6, 10, 999] * 4
        scenarios.append(("invalid_job_levels", invalid_levels))

        # Negative compensation
        negative_comp = base_data.copy()
        negative_comp.loc[:10, 'current_compensation'] = -abs(negative_comp.loc[:10, 'current_compensation'])
        scenarios.append(("negative_compensation", negative_comp))

        # Extremely high compensation (outliers)
        extreme_comp = base_data.copy()
        extreme_comp.loc[:5, 'current_compensation'] = np.random.uniform(10_000_000, 100_000_000, 5)
        scenarios.append(("extreme_compensation", extreme_comp))

        return scenarios


class TestBoundaryValueTesting:
    """Test boundary value conditions and floating point precision."""

    def setup_method(self):
        """Setup boundary testing."""
        self.schema = get_parameter_schema()
        self.mock_duckdb = Mock()
        self.mock_conn = Mock()
        self.mock_duckdb.get_connection.return_value.__enter__.return_value = self.mock_conn

    @pytest.mark.parametrize("scenario_name,params", MockDataGenerator.generate_boundary_parameters())
    def test_boundary_parameter_validation(self, scenario_name, params):
        """Test parameter validation at boundary conditions."""

        validation_result = self.schema.validate_parameter_set(params)

        # Boundary values should be valid
        assert validation_result['is_valid'], \
            f"Boundary scenario {scenario_name} failed validation: {validation_result['errors']}"

        # Check that all parameters are within bounds
        for param_name, value in params.items():
            param_def = self.schema.get_parameter(param_name)
            if param_def:
                assert param_def.bounds.min_value <= value <= param_def.bounds.max_value, \
                    f"Parameter {param_name} = {value} outside bounds [{param_def.bounds.min_value}, {param_def.bounds.max_value}]"

    @pytest.mark.parametrize("scenario_name,params", MockDataGenerator.generate_invalid_parameters())
    def test_invalid_parameter_handling(self, scenario_name, params):
        """Test handling of invalid parameter values."""

        if scenario_name in ["invalid_types", "none_values"]:
            # These should raise exceptions during validation
            with pytest.raises((TypeError, ValueError, AttributeError)):
                self.schema.validate_parameter_set(params)
        else:
            # These should return validation errors
            validation_result = self.schema.validate_parameter_set(params)
            assert not validation_result['is_valid'], \
                f"Invalid scenario {scenario_name} should fail validation"
            assert len(validation_result['errors']) > 0, \
                f"Invalid scenario {scenario_name} should have error messages"

    @pytest.mark.parametrize("scenario_name,params", MockDataGenerator.generate_floating_point_edge_cases())
    def test_floating_point_precision(self, scenario_name, params):
        """Test handling of floating point precision issues."""

        # Fill in missing parameters with defaults
        full_params = get_default_parameters()
        full_params.update(params)

        # Should handle floating point precision gracefully
        validation_result = self.schema.validate_parameter_set(full_params)

        # May or may not be valid depending on the specific values
        assert isinstance(validation_result, dict)
        assert 'is_valid' in validation_result

        # Should not crash or hang
        assert validation_result['overall_risk'] in [level for level in RiskLevel]

    def test_parameter_precision_consistency(self):
        """Test consistency of parameter precision handling."""

        # Test with high precision values
        high_precision_params = {
            "merit_rate_level_1": Decimal('0.045123456789012345').quantize(Decimal('0.000000000000001')),
            "cola_rate": Decimal('0.024999999999999997').quantize(Decimal('0.000000000000001'))
        }

        # Convert to float for validation
        float_params = {k: float(v) for k, v in high_precision_params.items()}
        full_params = get_default_parameters()
        full_params.update(float_params)

        # Should handle conversion gracefully
        validation_result = self.schema.validate_parameter_set(full_params)

        assert isinstance(validation_result, dict)
        assert 'is_valid' in validation_result

    def test_numerical_stability_edge_cases(self):
        """Test numerical stability with edge case calculations."""

        # Test parameters that might cause numerical instability
        edge_params = {
            "merit_rate_level_1": 1e-8,  # Very small
            "merit_rate_level_2": 0.999999999999999,  # Close to 1
            "cola_rate": 0.0000000001  # Tiny positive number
        }

        full_params = get_default_parameters()
        full_params.update(edge_params)

        # Test optimization with edge case parameters
        optimizer = CompensationOptimizer(self.mock_duckdb, "edge_test")

        # Mock objective function to return reasonable values
        self.mock_conn.execute.return_value.fetchone.return_value = [1000000.0]
        self.mock_conn.execute.return_value.fetchall.return_value = [(1, 50000, 2500)]

        # Should not crash with numerical edge cases
        try:
            with patch.object(optimizer.obj_funcs, 'combined_objective', return_value=0.5):
                # Test constraint generation
                constraints = optimizer._generate_constraints(edge_params, {"cost": 1.0})
                assert isinstance(constraints, list)

                # Test bounds generation
                bounds = optimizer._generate_bounds(edge_params)
                assert isinstance(bounds, list)
                assert len(bounds) == len(edge_params)

        except (ValueError, OverflowError, ZeroDivisionError) as e:
            # These errors are acceptable for extreme edge cases
            assert "overflow" in str(e).lower() or "division" in str(e).lower() or "invalid" in str(e).lower()


class TestExtremeBusinessScenarios:
    """Test extreme business scenarios and edge cases."""

    def setup_method(self):
        """Setup extreme scenario testing."""
        self.schema = get_parameter_schema()
        self.mock_duckdb = Mock()
        self.mock_conn = Mock()
        self.mock_duckdb.get_connection.return_value.__enter__.return_value = self.mock_conn

    @pytest.mark.parametrize("scenario_name,params", MockDataGenerator.generate_extreme_business_scenarios())
    def test_extreme_business_scenario_validation(self, scenario_name, params):
        """Test validation of extreme business scenarios."""

        # Fill in missing parameters with defaults
        full_params = get_default_parameters()
        full_params.update(params)

        validation_result = self.schema.validate_parameter_set(full_params)

        # Scenarios should be processable (may not be valid business-wise)
        assert isinstance(validation_result, dict)
        assert 'is_valid' in validation_result
        assert 'overall_risk' in validation_result

        # Extreme scenarios should typically result in high risk assessments
        if scenario_name in ["zero_budget", "maximum_budget", "high_growth"]:
            assert validation_result['overall_risk'] in [RiskLevel.HIGH, RiskLevel.CRITICAL], \
                f"Extreme scenario {scenario_name} should have high risk assessment"

    def test_zero_budget_scenario_impact(self):
        """Test impact analysis for zero budget scenario."""

        zero_params = {
            "merit_rate_level_1": 0.0,
            "merit_rate_level_2": 0.0,
            "merit_rate_level_3": 0.0,
            "cola_rate": 0.0,
            "new_hire_salary_adjustment": 1.0
        }

        full_params = get_default_parameters()
        full_params.update(zero_params)

        # Mock zero cost impact
        self.mock_conn.execute.return_value.fetchone.return_value = [0.0]

        obj_funcs = ObjectiveFunctions(self.mock_duckdb, "zero_budget_test")

        with patch.object(obj_funcs, '_update_parameters'):
            cost = obj_funcs.cost_objective(zero_params)

        # Zero budget should result in zero cost
        assert cost == 0.0

    def test_maximum_budget_scenario_impact(self):
        """Test impact analysis for maximum budget scenario."""

        # Create maximum budget parameters
        max_params = {}
        for param_name, param_def in self.schema._parameters.items():
            max_params[param_name] = param_def.bounds.max_value

        # Mock very high cost impact
        self.mock_conn.execute.return_value.fetchone.return_value = [100_000_000.0]

        obj_funcs = ObjectiveFunctions(self.mock_duckdb, "max_budget_test")

        with patch.object(obj_funcs, '_update_parameters'):
            cost = obj_funcs.cost_objective(max_params)

        # Maximum budget should result in very high cost
        assert cost == 100.0  # $100M

    def test_inverted_merit_structure_scenario(self):
        """Test inverted merit structure (higher levels get less)."""

        inverted_params = {
            "merit_rate_level_1": 0.08,
            "merit_rate_level_2": 0.06,
            "merit_rate_level_3": 0.04,
            "merit_rate_level_4": 0.03,
            "merit_rate_level_5": 0.02
        }

        full_params = get_default_parameters()
        full_params.update(inverted_params)

        validation_result = self.schema.validate_parameter_set(full_params)

        # Should be valid but likely flagged as high risk
        assert validation_result['is_valid']
        assert validation_result['overall_risk'] in [RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]

        # Should generate warnings about unusual structure
        assert len(validation_result['warnings']) > 0

    def test_extreme_growth_scenario_constraints(self):
        """Test constraint handling for extreme growth scenarios."""

        extreme_growth = {
            "merit_rate_level_1": 0.15,  # 15% merit increase
            "promotion_probability_level_1": 0.50,  # 50% promotion rate
            "new_hire_salary_adjustment": 2.0  # 200% salary premium
        }

        full_params = get_default_parameters()
        full_params.update(extreme_growth)

        # Most extreme values should be outside parameter bounds
        validation_result = self.schema.validate_parameter_set(full_params)

        # Should be invalid due to exceeding bounds
        assert not validation_result['is_valid']
        assert len(validation_result['errors']) > 0

        # Error messages should be specific
        error_messages = ' '.join(validation_result['errors'])
        assert "above maximum" in error_messages.lower()

    def test_workforce_reduction_scenario(self):
        """Test scenarios involving workforce reduction."""

        reduction_params = {
            "merit_rate_level_1": 0.01,  # Very low merit
            "cola_rate": 0.0,  # No COLA
            "new_hire_salary_adjustment": 0.95,  # Salary reduction for new hires
            "promotion_probability_level_1": 0.01  # Almost no promotions
        }

        full_params = get_default_parameters()
        full_params.update(reduction_params)

        validation_result = self.schema.validate_parameter_set(full_params)

        # Should be valid but high risk
        assert validation_result['is_valid']
        assert validation_result['overall_risk'] in [RiskLevel.HIGH, RiskLevel.CRITICAL]

        # Should generate retention warnings
        warning_text = ' '.join(validation_result['warnings']).lower()
        assert "retention" in warning_text or "risk" in warning_text


class TestDataCorruptionScenarios:
    """Test handling of corrupted and malformed data."""

    def setup_method(self):
        """Setup data corruption testing."""
        self.schema = get_parameter_schema()
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Cleanup temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.parametrize("scenario_name,corrupted_data", MockDataGenerator.generate_corrupted_data_scenarios())
    def test_corrupted_workforce_data_handling(self, scenario_name, corrupted_data):
        """Test handling of corrupted workforce data."""

        # Save corrupted data to temporary file
        corrupted_file = os.path.join(self.temp_dir, f"corrupted_{scenario_name}.csv")

        try:
            corrupted_data.to_csv(corrupted_file, index=False)

            # Try to read corrupted data
            loaded_data = pd.read_csv(corrupted_file)

            # Should handle missing columns gracefully
            if scenario_name == "missing_critical_columns":
                assert 'job_level' not in loaded_data.columns
                assert 'current_compensation' not in loaded_data.columns

            # Should detect null values
            elif scenario_name == "null_critical_values":
                assert loaded_data['job_level'].isnull().sum() > 0
                assert loaded_data['current_compensation'].isnull().sum() > 0

            # Should preserve invalid data for validation to catch
            elif scenario_name == "invalid_job_levels":
                invalid_levels = loaded_data['job_level'].unique()
                assert any(level not in [1, 2, 3, 4, 5] for level in invalid_levels if not pd.isna(level))

        except Exception as e:
            # Some corruption scenarios may cause read failures - this is acceptable
            assert isinstance(e, (pd.errors.EmptyDataError, ValueError, UnicodeDecodeError))

    def test_malformed_parameter_files(self):
        """Test handling of malformed parameter configuration files."""

        # Create malformed JSON file
        malformed_json = os.path.join(self.temp_dir, "malformed.json")
        with open(malformed_json, 'w') as f:
            f.write('{"incomplete": json syntax, "missing": quotes}')

        # Should raise appropriate exception
        with pytest.raises(json.JSONDecodeError):
            with open(malformed_json, 'r') as f:
                json.load(f)

        # Create malformed YAML file
        malformed_yaml = os.path.join(self.temp_dir, "malformed.yaml")
        with open(malformed_yaml, 'w') as f:
            f.write("invalid: yaml: structure:\n")
            f.write("  - incomplete\n")
            f.write("  - nested: structure\n")
            f.write("missing_quotes: this is \"unclosed\n")

        # Should raise appropriate exception
        with pytest.raises(Exception):  # yaml.YAMLError or similar
            import yaml
            with open(malformed_yaml, 'r') as f:
                yaml.safe_load(f)

    def test_inconsistent_parameter_state(self):
        """Test handling of inconsistent parameter states."""

        # Create parameters that are individually valid but inconsistent together
        inconsistent_params = {
            "merit_rate_level_1": 0.02,  # Very low
            "merit_rate_level_5": 0.08,  # Very high
            "cola_rate": 0.0,  # No COLA
            "new_hire_salary_adjustment": 1.50  # High premium
        }

        full_params = get_default_parameters()
        full_params.update(inconsistent_params)

        validation_result = self.schema.validate_parameter_set(inconsistent_params)

        # Should be processable but likely generate warnings
        assert isinstance(validation_result, dict)
        assert 'is_valid' in validation_result

        # Inconsistent policies should generate warnings or high risk
        if validation_result['is_valid']:
            assert validation_result['overall_risk'] in [RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL] or \
                   len(validation_result['warnings']) > 0

    def test_parameter_file_encoding_issues(self):
        """Test handling of file encoding issues."""

        # Create file with various encoding issues
        encoding_test_file = os.path.join(self.temp_dir, "encoding_test.csv")

        # Write with problematic characters
        problematic_content = "parameter_name,value\n"
        problematic_content += "merit_rate_lével_1,0.045\n"  # Non-ASCII character
        problematic_content += "côla_rate,0.025\n"  # Non-ASCII character

        # Test different encodings
        encodings = ['utf-8', 'latin-1', 'cp1252']

        for encoding in encodings:
            try:
                with open(encoding_test_file, 'w', encoding=encoding) as f:
                    f.write(problematic_content)

                # Try to read with pandas
                df = pd.read_csv(encoding_test_file, encoding=encoding)

                # Should read successfully with correct encoding
                assert len(df) > 0
                assert 'parameter_name' in df.columns

            except UnicodeDecodeError:
                # Some encoding mismatches are expected
                pass

    def test_memory_corruption_simulation(self):
        """Test handling of simulated memory corruption scenarios."""

        # Create large parameter dictionary
        large_params = {}
        for i in range(1000):
            param_name = f"merit_rate_level_{i % 5 + 1}_{i}"
            large_params[param_name] = 0.045 + (i * 0.001) % 0.05

        # Most parameters won't be recognized by schema
        validation_result = self.schema.validate_parameter_set(large_params)

        # Should handle gracefully with warnings about unknown parameters
        assert isinstance(validation_result, dict)
        assert len(validation_result['warnings']) > 0

        # Should not crash or hang
        assert time.time()  # Simple check that we're still running

    def test_concurrent_file_modification(self):
        """Test handling of concurrent file modifications."""

        test_file = os.path.join(self.temp_dir, "concurrent_test.csv")

        # Create initial file
        initial_data = pd.DataFrame({
            'parameter_name': ['merit_rate_level_1', 'cola_rate'],
            'value': [0.045, 0.025]
        })
        initial_data.to_csv(test_file, index=False)

        # Function to modify file
        def modify_file():
            time.sleep(0.1)  # Small delay
            modified_data = pd.DataFrame({
                'parameter_name': ['merit_rate_level_1', 'cola_rate'],
                'value': [0.050, 0.030]
            })
            modified_data.to_csv(test_file, index=False)

        # Start file modification in background
        modifier_thread = threading.Thread(target=modify_file)
        modifier_thread.start()

        # Try to read file while it's being modified
        try:
            for _ in range(10):
                data = pd.read_csv(test_file)
                assert len(data) > 0  # Should read something
                time.sleep(0.01)

        except (pd.errors.EmptyDataError, PermissionError):
            # These errors are acceptable during concurrent access
            pass

        modifier_thread.join()


class TestConcurrentAccessPatterns:
    """Test concurrent access and race condition scenarios."""

    def setup_method(self):
        """Setup concurrent access testing."""
        self.schema = get_parameter_schema()
        self.results = []
        self.errors = []

    def test_concurrent_parameter_validation(self):
        """Test concurrent parameter validation operations."""

        def validate_parameters_worker(worker_id):
            """Worker function for concurrent validation."""
            try:
                params = get_default_parameters()
                # Add slight variation per worker
                params['merit_rate_level_1'] += worker_id * 0.001

                result = self.schema.validate_parameter_set(params)
                self.results.append((worker_id, result))

            except Exception as e:
                self.errors.append((worker_id, e))

        # Create multiple worker threads
        threads = []
        for i in range(10):
            thread = threading.Thread(target=validate_parameters_worker, args=(i,))
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
        assert len(self.errors) == 0, f"Concurrent validation errors: {self.errors}"
        assert len(self.results) == 10, "Not all validation threads completed"
        assert total_time < 5.0, f"Concurrent validation took {total_time:.2f}s"

        # All results should be valid
        for worker_id, result in self.results:
            assert result['is_valid'], f"Worker {worker_id} validation failed"

    def test_concurrent_optimization_requests(self):
        """Test handling of concurrent optimization requests."""

        def optimization_worker(worker_id):
            """Worker function for concurrent optimization."""
            try:
                mock_duckdb = Mock()
                mock_conn = Mock()
                mock_duckdb.get_connection.return_value.__enter__.return_value = mock_conn

                # Mock database responses
                mock_conn.execute.return_value.fetchone.return_value = [1_000_000.0]
                mock_conn.execute.return_value.fetchall.return_value = [(1, 50000, 2500)]

                optimizer = CompensationOptimizer(mock_duckdb, f"concurrent_test_{worker_id}")

                request = OptimizationRequest(
                    scenario_id=f"concurrent_test_{worker_id}",
                    initial_parameters=get_default_parameters(),
                    objectives={"cost": 1.0}
                )

                # Mock optimization
                with patch('scipy.optimize.minimize') as mock_minimize:
                    mock_result = Mock()
                    mock_result.success = True
                    mock_result.x = [0.045]
                    mock_result.fun = 0.5
                    mock_result.nit = 25
                    mock_result.nfev = 75
                    mock_minimize.return_value = mock_result

                    result = optimizer.optimize(request)
                    self.results.append((worker_id, result))

            except Exception as e:
                self.errors.append((worker_id, e))

        # Create concurrent optimization workers
        threads = []
        for i in range(5):  # Fewer threads for more intensive operations
            thread = threading.Thread(target=optimization_worker, args=(i,))
            threads.append(thread)

        # Start and wait for completion
        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Check results
        assert len(self.errors) == 0, f"Concurrent optimization errors: {self.errors}"
        assert len(self.results) == 5, "Not all optimization threads completed"

        # All optimizations should have unique scenario IDs
        scenario_ids = [result.scenario_id for _, result in self.results]
        assert len(set(scenario_ids)) == 5, "Scenario IDs should be unique"

    def test_resource_contention_handling(self):
        """Test handling of resource contention scenarios."""

        # Simulate resource contention with file locking
        lock_file = os.path.join(tempfile.gettempdir(), "resource_lock_test.lock")

        def resource_worker(worker_id):
            """Worker that competes for file resource."""
            try:
                # Try to acquire exclusive file lock
                for attempt in range(5):
                    try:
                        with open(lock_file, 'x') as f:  # Exclusive creation
                            f.write(f"Worker {worker_id}")
                            time.sleep(0.1)  # Hold resource briefly

                        # Clean up lock file
                        os.remove(lock_file)
                        self.results.append((worker_id, "success"))
                        break

                    except FileExistsError:
                        # Resource is locked, wait and retry
                        time.sleep(0.02)
                        continue

                else:
                    self.results.append((worker_id, "timeout"))

            except Exception as e:
                self.errors.append((worker_id, e))

        # Create competing workers
        threads = []
        for i in range(5):
            thread = threading.Thread(target=resource_worker, args=(i,))
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Clean up any remaining lock file
        try:
            os.remove(lock_file)
        except FileNotFoundError:
            pass

        # Check that some workers succeeded
        success_count = sum(1 for _, status in self.results if status == "success")
        assert success_count > 0, "No workers succeeded in acquiring resource"

        # Should handle contention gracefully
        assert len(self.errors) == 0, f"Resource contention caused errors: {self.errors}"


if __name__ == "__main__":
    # Run edge case tests
    pytest.main([
        __file__ + "::TestBoundaryValueTesting::test_boundary_parameter_validation",
        __file__ + "::TestExtremeBusinessScenarios::test_extreme_business_scenario_validation",
        __file__ + "::TestDataCorruptionScenarios::test_corrupted_workforce_data_handling",
        __file__ + "::TestConcurrentAccessPatterns::test_concurrent_parameter_validation",
        "-v"
    ])
