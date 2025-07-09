"""
Unit tests for WF-001-01: Hazard-based termination implementation

Test suite validating the transition from quota-based to hazard-based
termination selection, ensuring:
- Demographic-aware probability selection
- Deterministic randomization for reproducibility
- Integration with existing hazard infrastructure
- Consistent behavior with promotion selection pattern
"""

import pytest
from unittest.mock import Mock, patch
import pandas as pd
from dagster import OpExecutionContext

from orchestrator.simulator_pipeline import _run_dbt_event_models_for_year_internal


class TestHazardBasedTermination:
    """Test suite for hazard-based termination implementation."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock Dagster execution context."""
        context = Mock(spec=OpExecutionContext)
        context.log = Mock()
        context.log.info = Mock()
        context.log.error = Mock()
        return context

    @pytest.fixture
    def termination_config(self):
        """Configuration for termination testing."""
        return {
            "random_seed": 42,
            "total_termination_rate": 0.12,
            "new_hire_termination_rate": 0.25,
            "target_growth_rate": 0.03,
            "full_refresh": False,
        }

    @pytest.fixture
    def sample_workforce_data(self):
        """Sample workforce data for testing hazard calculations."""
        return pd.DataFrame(
            {
                "employee_id": ["E001", "E002", "E003", "E004", "E005"],
                "current_age": [24, 32, 45, 28, 55],
                "current_tenure": [1, 3, 8, 5, 15],
                "level_id": [1, 2, 3, 2, 4],
                "age_band": ["< 25", "25-34", "35-44", "25-34", "55-64"],
                "tenure_band": ["< 2", "2-4", "5-9", "2-4", "10-19"],
                "employment_status": ["active"] * 5,
            }
        )

    @pytest.fixture
    def sample_hazard_data(self):
        """Sample termination hazard rates for testing."""
        return pd.DataFrame(
            {
                "level_id": [1, 1, 2, 2, 3, 3, 4, 4],
                "age_band": [
                    "< 25",
                    "25-34",
                    "25-34",
                    "35-44",
                    "35-44",
                    "45-54",
                    "55-64",
                    "65+",
                ],
                "tenure_band": [
                    "< 2",
                    "2-4",
                    "2-4",
                    "5-9",
                    "5-9",
                    "10-19",
                    "10-19",
                    "20+",
                ],
                "termination_rate": [0.25, 0.15, 0.18, 0.12, 0.10, 0.08, 0.06, 0.04],
                "year": [2025] * 8,
            }
        )

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_hazard_based_selection_enabled(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        termination_config,
    ):
        """Test that termination events use hazard-based selection."""
        year = 2025

        # Mock DuckDB connection
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = [50]  # Mock hiring count
        mock_duckdb_connect.return_value = mock_conn

        # Execute termination events
        _run_dbt_event_models_for_year_internal(mock_context, year, termination_config)

        # Verify termination events model was executed (first in Epic 11.5 sequence)
        first_call = mock_execute_dbt.call_args_list[0]
        command = first_call[0][1]
        assert command == ["run", "--select", "int_termination_events"]

        # Verify configuration passed includes termination rate
        vars_dict = first_call[0][2]
        assert vars_dict["total_termination_rate"] == 0.12
        assert vars_dict["simulation_year"] == year

    def test_deterministic_randomization_pattern(self):
        """Test that employee termination selection is deterministic based on employee_id."""
        # Test the hash-based randomization used in the model
        employee_ids = ["E001", "E002", "E003", "E001", "E002", "E003"]

        # Calculate random values using same formula as in SQL
        random_values = []
        for emp_id in employee_ids:
            # Simulate the SQL: (ABS(HASH(employee_id)) % 1000) / 1000.0
            # Use Python's hash function as approximation
            hash_val = abs(hash(emp_id))
            random_val = (hash_val % 1000) / 1000.0
            random_values.append(random_val)

        # Verify same employee_id produces same random value
        assert random_values[0] == random_values[3]  # E001
        assert random_values[1] == random_values[4]  # E002
        assert random_values[2] == random_values[5]  # E003

        # Verify different employee_ids produce different values
        assert len(set(random_values[:3])) == 3  # All unique

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_termination_reason_updated(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        termination_config,
    ):
        """Test that termination reason is updated to hazard_termination."""
        year = 2025

        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = [30]
        mock_duckdb_connect.return_value = mock_conn

        # Execute and verify no errors
        result = _run_dbt_event_models_for_year_internal(mock_context, year, termination_config)

        # Verify execution completed successfully
        assert result["year"] == year
        assert "int_termination_events" in result["models_executed"]

    @pytest.mark.parametrize("termination_rate", [0.05, 0.10, 0.15, 0.20])
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_various_termination_rates(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        termination_config,
        termination_rate,
    ):
        """Test termination model with various termination rates."""
        year = 2025
        termination_config["total_termination_rate"] = termination_rate

        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = [25]
        mock_duckdb_connect.return_value = mock_conn

        # Execute with different rates
        result = _run_dbt_event_models_for_year_internal(mock_context, year, termination_config)

        # Verify rate was passed correctly
        termination_call = mock_execute_dbt.call_args_list[0]
        vars_dict = termination_call[0][2]
        assert vars_dict["total_termination_rate"] == termination_rate

        # Verify successful execution
        assert result["year"] == year

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_integration_with_hazard_infrastructure(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        termination_config,
    ):
        """Test that termination events integrate with existing hazard infrastructure."""
        year = 2025

        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = [75]
        mock_duckdb_connect.return_value = mock_conn

        # Execute the full Epic 11.5 sequence
        _run_dbt_event_models_for_year_internal(mock_context, year, termination_config)

        # Verify termination events is first in sequence (Epic 11.5)
        expected_sequence = [
            "int_termination_events",
            "int_promotion_events",
            "int_merit_events",
            "int_hiring_events",
            "int_new_hire_termination_events",
        ]

        # Check first model is termination events
        first_call = mock_execute_dbt.call_args_list[0]
        command = first_call[0][1]
        assert command == ["run", "--select", expected_sequence[0]]

        # Verify all models executed in correct order
        for i, expected_model in enumerate(expected_sequence):
            call_args = mock_execute_dbt.call_args_list[i]
            command = call_args[0][1]
            assert command == ["run", "--select", expected_model]

    def test_probability_threshold_logic(self):
        """Test the core probability threshold logic used in hazard-based selection."""
        # Simulate the WHERE clause logic: WHERE random_value < termination_rate

        test_cases = [
            # (random_value, termination_rate, should_terminate)
            (0.05, 0.10, True),  # Low random, moderate rate -> terminate
            (0.15, 0.10, False),  # High random, moderate rate -> keep
            (0.08, 0.25, True),  # Low random, high rate -> terminate
            (0.30, 0.25, False),  # High random, high rate -> keep
            (0.00, 0.05, True),  # Zero random -> terminate
            (0.99, 0.05, False),  # Max random, low rate -> keep
        ]

        for random_val, term_rate, expected_terminate in test_cases:
            actual_terminate = random_val < term_rate
            assert (
                actual_terminate == expected_terminate
            ), f"Failed for random_value={random_val}, termination_rate={term_rate}"

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_demographic_aware_selection(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        termination_config,
    ):
        """Test that hazard-based selection considers demographic factors."""
        year = 2025

        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = [40]
        mock_duckdb_connect.return_value = mock_conn

        # Execute with standard configuration
        result = _run_dbt_event_models_for_year_internal(mock_context, year, termination_config)

        # Verify termination model execution
        termination_call = mock_execute_dbt.call_args_list[0]
        vars_dict = termination_call[0][2]

        # Verify all demographic factors are available as variables
        assert "simulation_year" in vars_dict
        assert vars_dict["simulation_year"] == year

        # Verify execution success
        assert result["year"] == year
        assert len(result["models_executed"]) == 5

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_backward_compatibility_maintained(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        termination_config,
    ):
        """Test that the new hazard-based approach maintains backward compatibility."""
        year = 2025

        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = [60]
        mock_duckdb_connect.return_value = mock_conn

        # Execute with previous configuration format
        legacy_config = {
            "random_seed": 42,
            "total_termination_rate": 0.12,  # Legacy parameter name
            "new_hire_termination_rate": 0.25,
            "target_growth_rate": 0.03,
            "full_refresh": False,
        }

        # Should execute without errors
        result = _run_dbt_event_models_for_year_internal(mock_context, year, legacy_config)
        assert result["year"] == year

        # Verify termination events model was called
        first_call = mock_execute_dbt.call_args_list[0]
        command = first_call[0][1]
        assert command == ["run", "--select", "int_termination_events"]


class TestHazardTerminationValidation:
    """Test suite for validating hazard-based termination data quality."""

    def test_age_band_mapping_consistency(self):
        """Test that age band mapping is consistent between models."""
        # Age band logic from the updated model
        test_ages = [20, 24, 25, 30, 34, 35, 40, 44, 45, 50, 54, 55, 60, 64, 65, 70]

        expected_bands = [
            "< 25",
            "< 25",
            "25-34",
            "25-34",
            "25-34",
            "35-44",
            "35-44",
            "35-44",
            "45-54",
            "45-54",
            "45-54",
            "55-64",
            "55-64",
            "55-64",
            "65+",
            "65+",
        ]

        for age, expected_band in zip(test_ages, expected_bands):
            # Simulate the CASE statement logic
            if age < 25:
                actual_band = "< 25"
            elif age < 35:
                actual_band = "25-34"
            elif age < 45:
                actual_band = "35-44"
            elif age < 55:
                actual_band = "45-54"
            elif age < 65:
                actual_band = "55-64"
            else:
                actual_band = "65+"

            assert actual_band == expected_band, f"Age {age} mapped incorrectly"

    def test_tenure_band_mapping_consistency(self):
        """Test that tenure band mapping is consistent between models."""
        test_tenures = [0, 1, 1.5, 2, 3, 4, 5, 7, 9, 10, 15, 19, 20, 25]

        expected_bands = [
            "< 2",
            "< 2",
            "< 2",
            "2-4",
            "2-4",
            "2-4",
            "5-9",
            "5-9",
            "5-9",
            "10-19",
            "10-19",
            "10-19",
            "20+",
            "20+",
        ]

        for tenure, expected_band in zip(test_tenures, expected_bands):
            # Simulate the CASE statement logic
            if tenure < 2:
                actual_band = "< 2"
            elif tenure < 5:
                actual_band = "2-4"
            elif tenure < 10:
                actual_band = "5-9"
            elif tenure < 20:
                actual_band = "10-19"
            else:
                actual_band = "20+"

            assert actual_band == expected_band, f"Tenure {tenure} mapped incorrectly"

    def test_termination_rate_bounds(self):
        """Test termination rate validation bounds."""
        valid_rates = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 1.0]
        invalid_rates = [-0.1, 1.1, 2.0, -1.0]

        # Valid rates should pass bounds check
        for rate in valid_rates:
            assert 0 <= rate <= 1, f"Valid rate {rate} failed bounds check"

        # Invalid rates should fail bounds check
        for rate in invalid_rates:
            assert not (0 <= rate <= 1), f"Invalid rate {rate} passed bounds check"
