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
    if not StateAccumulatorRegistry.is_registered("int_enrollment_state_accumulator"):
        StateAccumulatorRegistry.register(
            StateAccumulatorContract(
                model_name="int_enrollment_state_accumulator",
                table_name="int_enrollment_state_accumulator",
                prior_year_column="simulation_year",
                start_year_source="int_baseline_workforce",
                description="Tracks employee enrollment state across simulation years. "
                           "Consolidates latest enrollment event per employee.",
            )
        )

    # Register deferral rate state accumulator
    if not StateAccumulatorRegistry.is_registered("int_deferral_rate_state_accumulator"):
        StateAccumulatorRegistry.register(
            StateAccumulatorContract(
                model_name="int_deferral_rate_state_accumulator",
                table_name="int_deferral_rate_state_accumulator",
                prior_year_column="simulation_year",
                start_year_source="int_employee_compensation_by_year",
                description="Tracks employee deferral rate state across simulation years. "
                           "Reads previous year deferral rates for continuity.",
            )
        )


# Register default accumulators at module import
_register_default_accumulators()
