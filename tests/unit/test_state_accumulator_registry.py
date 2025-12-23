"""
Unit tests for StateAccumulatorRegistry.

Tests registry operations, singleton behavior, and error handling.
These tests should run fast (<1s) and don't require database access.
"""

from __future__ import annotations

import pytest

from planalign_orchestrator.state_accumulator.contract import StateAccumulatorContract
from planalign_orchestrator.state_accumulator.registry import StateAccumulatorRegistry


@pytest.fixture
def clean_registry():
    """Provide a clean registry state for testing."""
    StateAccumulatorRegistry.clear()
    yield StateAccumulatorRegistry
    StateAccumulatorRegistry.clear()


@pytest.fixture
def sample_contract():
    """Create a sample contract for testing."""
    return StateAccumulatorContract(
        model_name="int_test_accumulator",
        table_name="int_test_accumulator",
        start_year_source="int_baseline_workforce",
        description="Test accumulator for unit tests",
    )


@pytest.fixture
def another_contract():
    """Create another sample contract for testing."""
    return StateAccumulatorContract(
        model_name="int_another_accumulator",
        table_name="int_another_accumulator",
        start_year_source="int_baseline_workforce",
        description="Another test accumulator",
    )


class TestStateAccumulatorRegistryBasicOperations:
    """Tests for basic registry operations."""

    def test_register_contract(self, clean_registry, sample_contract):
        """Test registering a contract."""
        clean_registry.register(sample_contract)

        assert clean_registry.is_registered("int_test_accumulator")
        assert clean_registry.count() == 1

    def test_register_multiple_contracts(self, clean_registry, sample_contract, another_contract):
        """Test registering multiple contracts."""
        clean_registry.register(sample_contract)
        clean_registry.register(another_contract)

        assert clean_registry.count() == 2
        assert clean_registry.is_registered("int_test_accumulator")
        assert clean_registry.is_registered("int_another_accumulator")

    def test_get_registered_contract(self, clean_registry, sample_contract):
        """Test retrieving a registered contract."""
        clean_registry.register(sample_contract)

        retrieved = clean_registry.get("int_test_accumulator")

        assert retrieved == sample_contract
        assert retrieved.table_name == "int_test_accumulator"

    def test_list_all_returns_sorted_names(self, clean_registry, sample_contract, another_contract):
        """Test that list_all returns sorted model names."""
        # Register in reverse alphabetical order
        clean_registry.register(sample_contract)  # int_test_accumulator
        clean_registry.register(another_contract)  # int_another_accumulator

        names = clean_registry.list_all()

        assert names == ["int_another_accumulator", "int_test_accumulator"]

    def test_get_registered_tables(self, clean_registry, sample_contract, another_contract):
        """Test getting all registered table names."""
        clean_registry.register(sample_contract)
        clean_registry.register(another_contract)

        tables = clean_registry.get_registered_tables()

        assert len(tables) == 2
        assert "int_test_accumulator" in tables
        assert "int_another_accumulator" in tables

    def test_get_all_contracts(self, clean_registry, sample_contract, another_contract):
        """Test getting all registered contracts."""
        clean_registry.register(sample_contract)
        clean_registry.register(another_contract)

        contracts = clean_registry.get_all_contracts()

        assert len(contracts) == 2
        assert sample_contract in contracts
        assert another_contract in contracts

    def test_clear_registry(self, clean_registry, sample_contract):
        """Test clearing the registry."""
        clean_registry.register(sample_contract)
        assert clean_registry.count() == 1

        clean_registry.clear()

        assert clean_registry.count() == 0
        assert clean_registry.list_all() == []


class TestStateAccumulatorRegistryErrorHandling:
    """Tests for registry error handling."""

    def test_duplicate_registration_raises_error(self, clean_registry, sample_contract):
        """Test that registering the same model twice raises ValueError."""
        clean_registry.register(sample_contract)

        with pytest.raises(ValueError) as exc_info:
            clean_registry.register(sample_contract)

        error_message = str(exc_info.value)
        assert "already registered" in error_message
        assert "int_test_accumulator" in error_message

    def test_get_unregistered_model_raises_error(self, clean_registry):
        """Test that getting an unregistered model raises KeyError."""
        with pytest.raises(KeyError) as exc_info:
            clean_registry.get("int_nonexistent")

        error_message = str(exc_info.value)
        assert "not registered" in error_message
        assert "int_nonexistent" in error_message

    def test_get_unregistered_shows_available_models(self, clean_registry, sample_contract):
        """Test that KeyError message includes available models."""
        clean_registry.register(sample_contract)

        with pytest.raises(KeyError) as exc_info:
            clean_registry.get("int_nonexistent")

        error_message = str(exc_info.value)
        assert "int_test_accumulator" in error_message
        assert "Available models" in error_message


class TestStateAccumulatorRegistryHelperMethods:
    """Tests for registry helper methods."""

    def test_is_registered_true(self, clean_registry, sample_contract):
        """Test is_registered returns True for registered model."""
        clean_registry.register(sample_contract)

        assert clean_registry.is_registered("int_test_accumulator") is True

    def test_is_registered_false(self, clean_registry):
        """Test is_registered returns False for unregistered model."""
        assert clean_registry.is_registered("int_nonexistent") is False

    def test_count_empty_registry(self, clean_registry):
        """Test count returns 0 for empty registry."""
        assert clean_registry.count() == 0

    def test_count_with_contracts(self, clean_registry, sample_contract, another_contract):
        """Test count returns correct number."""
        clean_registry.register(sample_contract)
        assert clean_registry.count() == 1

        clean_registry.register(another_contract)
        assert clean_registry.count() == 2

    def test_summary_empty_registry(self, clean_registry):
        """Test summary for empty registry."""
        summary = clean_registry.summary()
        assert "No accumulators registered" in summary

    def test_summary_with_contracts(self, clean_registry, sample_contract, another_contract):
        """Test summary with registered contracts."""
        clean_registry.register(sample_contract)
        clean_registry.register(another_contract)

        summary = clean_registry.summary()

        assert "2 accumulators" in summary
        assert "int_test_accumulator" in summary
        assert "int_another_accumulator" in summary


class TestStateAccumulatorRegistrySingletonBehavior:
    """Tests for singleton-like behavior of the registry."""

    def test_class_level_storage(self, clean_registry, sample_contract):
        """Test that contracts are stored at class level."""
        clean_registry.register(sample_contract)

        # Access directly through class
        assert StateAccumulatorRegistry.is_registered("int_test_accumulator")

    def test_persistence_across_operations(self, clean_registry, sample_contract):
        """Test that contracts persist across multiple operations."""
        clean_registry.register(sample_contract)

        # Multiple operations should see the same state
        assert StateAccumulatorRegistry.count() == 1
        assert StateAccumulatorRegistry.list_all() == ["int_test_accumulator"]
        assert StateAccumulatorRegistry.get("int_test_accumulator") == sample_contract


class TestStateAccumulatorRegistryEdgeCases:
    """Tests for edge cases."""

    def test_list_all_empty_registry(self, clean_registry):
        """Test list_all on empty registry returns empty list."""
        assert clean_registry.list_all() == []

    def test_get_registered_tables_empty(self, clean_registry):
        """Test get_registered_tables on empty registry returns empty list."""
        assert clean_registry.get_registered_tables() == []

    def test_get_all_contracts_empty(self, clean_registry):
        """Test get_all_contracts on empty registry returns empty list."""
        assert clean_registry.get_all_contracts() == []
