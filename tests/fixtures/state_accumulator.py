"""
Test fixtures for state accumulator contract testing.

Provides fixtures for:
- StateAccumulatorContract instances
- StateAccumulatorRegistry setup/teardown
- YearDependencyValidator mock database scenarios
"""

from __future__ import annotations

import pytest
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from planalign_orchestrator.state_accumulator import (
        StateAccumulatorContract,
        StateAccumulatorRegistry,
    )


@pytest.fixture
def sample_enrollment_contract():
    """Create a sample enrollment state accumulator contract."""
    from planalign_orchestrator.state_accumulator import StateAccumulatorContract

    return StateAccumulatorContract(
        model_name="int_enrollment_state_accumulator",
        table_name="int_enrollment_state_accumulator",
        prior_year_column="simulation_year",
        start_year_source="int_baseline_workforce",
        description="Tracks employee enrollment state across simulation years",
    )


@pytest.fixture
def sample_deferral_contract():
    """Create a sample deferral rate state accumulator contract."""
    from planalign_orchestrator.state_accumulator import StateAccumulatorContract

    return StateAccumulatorContract(
        model_name="int_deferral_rate_state_accumulator",
        table_name="int_deferral_rate_state_accumulator",
        prior_year_column="simulation_year",
        start_year_source="int_employee_compensation_by_year",
        description="Tracks employee deferral rate state across simulation years",
    )


@pytest.fixture
def clean_registry():
    """Provide a clean registry state for testing.

    Clears the registry before and after each test to ensure isolation.
    """
    from planalign_orchestrator.state_accumulator import StateAccumulatorRegistry

    StateAccumulatorRegistry.clear()
    yield StateAccumulatorRegistry
    StateAccumulatorRegistry.clear()


@pytest.fixture
def populated_registry(clean_registry, sample_enrollment_contract, sample_deferral_contract):
    """Provide a registry pre-populated with standard accumulators."""
    clean_registry.register(sample_enrollment_contract)
    clean_registry.register(sample_deferral_contract)
    return clean_registry


@pytest.fixture
def invalid_contract_data():
    """Provide data that should fail contract validation."""
    return [
        # Missing int_ prefix
        {
            "model_name": "enrollment_state_accumulator",
            "table_name": "enrollment_state_accumulator",
            "start_year_source": "int_baseline_workforce",
        },
        # Empty model_name
        {
            "model_name": "",
            "table_name": "int_test",
            "start_year_source": "int_baseline_workforce",
        },
        # Empty table_name
        {
            "model_name": "int_test",
            "table_name": "",
            "start_year_source": "int_baseline_workforce",
        },
    ]


@pytest.fixture
def violating_contract():
    """Create a contract that intentionally violates temporal patterns.

    Used for negative testing to verify violation detection.
    """
    from planalign_orchestrator.state_accumulator import StateAccumulatorContract

    return StateAccumulatorContract(
        model_name="int_intentionally_violating_accumulator",
        table_name="int_intentionally_violating_accumulator",
        prior_year_column="simulation_year",
        start_year_source="int_baseline_workforce",
        description="Test accumulator that intentionally violates temporal patterns",
    )
