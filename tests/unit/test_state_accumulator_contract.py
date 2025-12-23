"""
Unit tests for StateAccumulatorContract.

Tests contract validation, field requirements, and Pydantic behavior.
These tests should run fast (<1s) and don't require database access.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from planalign_orchestrator.state_accumulator.contract import StateAccumulatorContract


class TestStateAccumulatorContractCreation:
    """Tests for StateAccumulatorContract instantiation."""

    def test_valid_contract_creation(self):
        """Test creating a valid contract with all required fields."""
        contract = StateAccumulatorContract(
            model_name="int_test_accumulator",
            table_name="int_test_accumulator",
            start_year_source="int_baseline_workforce",
        )

        assert contract.model_name == "int_test_accumulator"
        assert contract.table_name == "int_test_accumulator"
        assert contract.prior_year_column == "simulation_year"  # default
        assert contract.start_year_source == "int_baseline_workforce"
        assert contract.description == ""  # default

    def test_contract_with_all_fields(self):
        """Test creating a contract with all fields specified."""
        contract = StateAccumulatorContract(
            model_name="int_custom_accumulator",
            table_name="custom_table",
            prior_year_column="fiscal_year",
            start_year_source="int_custom_baseline",
            description="Custom accumulator for testing",
        )

        assert contract.model_name == "int_custom_accumulator"
        assert contract.table_name == "custom_table"
        assert contract.prior_year_column == "fiscal_year"
        assert contract.start_year_source == "int_custom_baseline"
        assert contract.description == "Custom accumulator for testing"

    def test_contract_repr(self):
        """Test string representation of contract."""
        contract = StateAccumulatorContract(
            model_name="int_test_accumulator",
            table_name="int_test_accumulator",
            start_year_source="int_baseline_workforce",
        )

        repr_str = repr(contract)
        assert "int_test_accumulator" in repr_str
        assert "StateAccumulatorContract" in repr_str

    def test_contract_str(self):
        """Test human-readable string representation."""
        contract = StateAccumulatorContract(
            model_name="int_test_accumulator",
            table_name="custom_table",
            start_year_source="int_baseline_workforce",
        )

        str_repr = str(contract)
        assert "int_test_accumulator" in str_repr
        assert "custom_table" in str_repr


class TestStateAccumulatorContractValidation:
    """Tests for StateAccumulatorContract field validation."""

    def test_model_name_must_start_with_int_prefix(self):
        """Test that model_name must start with 'int_' prefix."""
        with pytest.raises(ValidationError) as exc_info:
            StateAccumulatorContract(
                model_name="enrollment_state_accumulator",  # missing int_ prefix
                table_name="enrollment_state_accumulator",
                start_year_source="int_baseline_workforce",
            )

        error = exc_info.value
        assert "int_" in str(error)
        assert "model_name" in str(error)

    def test_model_name_cannot_be_empty(self):
        """Test that model_name cannot be empty."""
        with pytest.raises(ValidationError) as exc_info:
            StateAccumulatorContract(
                model_name="",
                table_name="int_test",
                start_year_source="int_baseline_workforce",
            )

        error = exc_info.value
        assert "empty" in str(error).lower()

    def test_table_name_cannot_be_empty(self):
        """Test that table_name cannot be empty."""
        with pytest.raises(ValidationError) as exc_info:
            StateAccumulatorContract(
                model_name="int_test",
                table_name="",
                start_year_source="int_baseline_workforce",
            )

        error = exc_info.value
        assert "empty" in str(error).lower()

    def test_start_year_source_cannot_be_empty(self):
        """Test that start_year_source cannot be empty."""
        with pytest.raises(ValidationError) as exc_info:
            StateAccumulatorContract(
                model_name="int_test",
                table_name="int_test",
                start_year_source="",
            )

        error = exc_info.value
        assert "empty" in str(error).lower()

    def test_model_name_is_required(self):
        """Test that model_name is a required field."""
        with pytest.raises(ValidationError):
            StateAccumulatorContract(
                table_name="int_test",
                start_year_source="int_baseline_workforce",
            )

    def test_table_name_is_required(self):
        """Test that table_name is a required field."""
        with pytest.raises(ValidationError):
            StateAccumulatorContract(
                model_name="int_test",
                start_year_source="int_baseline_workforce",
            )

    def test_start_year_source_is_required(self):
        """Test that start_year_source is a required field."""
        with pytest.raises(ValidationError):
            StateAccumulatorContract(
                model_name="int_test",
                table_name="int_test",
            )


class TestStateAccumulatorContractEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_model_name_exactly_int_prefix(self):
        """Test model_name that is exactly 'int_' (minimal valid prefix)."""
        # This is a valid model_name, just the prefix + empty name
        contract = StateAccumulatorContract(
            model_name="int_x",  # Minimal valid name
            table_name="int_x",
            start_year_source="int_baseline",
        )
        assert contract.model_name == "int_x"

    def test_model_name_with_multiple_underscores(self):
        """Test model_name with multiple underscores."""
        contract = StateAccumulatorContract(
            model_name="int_very_long_accumulator_name",
            table_name="int_very_long_accumulator_name",
            start_year_source="int_baseline_workforce",
        )
        assert contract.model_name == "int_very_long_accumulator_name"

    def test_prior_year_column_default(self):
        """Test that prior_year_column defaults to 'simulation_year'."""
        contract = StateAccumulatorContract(
            model_name="int_test",
            table_name="int_test",
            start_year_source="int_baseline",
        )
        assert contract.prior_year_column == "simulation_year"

    def test_description_default(self):
        """Test that description defaults to empty string."""
        contract = StateAccumulatorContract(
            model_name="int_test",
            table_name="int_test",
            start_year_source="int_baseline",
        )
        assert contract.description == ""

    def test_contract_equality(self):
        """Test that contracts with same values are equal."""
        contract1 = StateAccumulatorContract(
            model_name="int_test",
            table_name="int_test",
            start_year_source="int_baseline",
        )
        contract2 = StateAccumulatorContract(
            model_name="int_test",
            table_name="int_test",
            start_year_source="int_baseline",
        )
        assert contract1 == contract2

    def test_contract_inequality(self):
        """Test that contracts with different values are not equal."""
        contract1 = StateAccumulatorContract(
            model_name="int_test1",
            table_name="int_test1",
            start_year_source="int_baseline",
        )
        contract2 = StateAccumulatorContract(
            model_name="int_test2",
            table_name="int_test2",
            start_year_source="int_baseline",
        )
        assert contract1 != contract2
