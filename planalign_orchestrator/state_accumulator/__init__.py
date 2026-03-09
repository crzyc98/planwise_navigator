"""
State Accumulator Contract Module

Provides runtime validation for temporal state accumulator models where
Year N depends on Year N-1 data. Prevents silent data corruption by
failing fast with clear error messages when year dependencies are violated.

Public API:
    - StateAccumulatorContract: Pydantic model defining accumulator contract
    - StateAccumulatorRegistry: Singleton registry for tracking accumulators
    - YearDependencyValidator: Runtime validation of year dependencies

Usage:
    from planalign_orchestrator.state_accumulator import (
        StateAccumulatorContract,
        StateAccumulatorRegistry,
        YearDependencyValidator,
    )

    # Register an accumulator
    StateAccumulatorRegistry.register(
        StateAccumulatorContract(
            model_name="int_my_accumulator",
            table_name="int_my_accumulator",
            start_year_source="int_baseline_workforce",
        )
    )

    # Validate year dependencies
    validator = YearDependencyValidator(db_manager, start_year=2025)
    validator.validate_year_dependencies(year=2026)  # Raises if 2025 missing
"""

from __future__ import annotations

from .contract import StateAccumulatorContract
from .registry import StateAccumulatorRegistry
from .validator import YearDependencyValidator
from config.constants import (
    COL_SIMULATION_YEAR,
    MODEL_INT_BASELINE_WORKFORCE,
    MODEL_INT_EMPLOYEE_COMPENSATION,
    MODEL_INT_ENROLLMENT_STATE_ACCUMULATOR,
)

__all__ = [
    "StateAccumulatorContract",
    "StateAccumulatorRegistry",
    "YearDependencyValidator",
]


def _register_default_accumulators() -> None:
    """Register the default state accumulator models.

    Called at module import to register the two primary accumulators:
    - int_enrollment_state_accumulator: Tracks enrollment state
    - int_deferral_rate_state_accumulator: Tracks deferral rate state

    This function is idempotent - calling it multiple times will not
    cause duplicate registration errors due to the registry's
    duplicate check.
    """
    # Register enrollment state accumulator
    if not StateAccumulatorRegistry.is_registered(MODEL_INT_ENROLLMENT_STATE_ACCUMULATOR):
        StateAccumulatorRegistry.register(
            StateAccumulatorContract(
                model_name=MODEL_INT_ENROLLMENT_STATE_ACCUMULATOR,
                table_name=MODEL_INT_ENROLLMENT_STATE_ACCUMULATOR,
                prior_year_column=COL_SIMULATION_YEAR,
                start_year_source=MODEL_INT_BASELINE_WORKFORCE,
                description="Tracks employee enrollment state across simulation years. "
                           "Consolidates latest enrollment event per employee.",
            )
        )

    # Register deferral rate state accumulator (v2)
    # Note: The pipeline uses int_deferral_rate_state_accumulator_v2, not the original
    if not StateAccumulatorRegistry.is_registered("int_deferral_rate_state_accumulator_v2"):
        StateAccumulatorRegistry.register(
            StateAccumulatorContract(
                model_name="int_deferral_rate_state_accumulator_v2",
                table_name="int_deferral_rate_state_accumulator_v2",
                prior_year_column=COL_SIMULATION_YEAR,
                start_year_source=MODEL_INT_EMPLOYEE_COMPENSATION,
                description="Tracks employee deferral rate state across simulation years. "
                           "Reads previous year deferral rates for continuity.",
            )
        )


# Register default accumulators at module import
_register_default_accumulators()
