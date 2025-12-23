"""
State Accumulator Contract API Specification

This file defines the Python interfaces (contracts) for the state accumulator
system. These are not runnable code - they define the expected interfaces.

Feature: 007-state-accumulator-contract
Date: 2025-12-14
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Protocol, runtime_checkable


# =============================================================================
# StateAccumulatorContract Interface
# =============================================================================

@runtime_checkable
class StateAccumulatorContractProtocol(Protocol):
    """Protocol defining the required attributes of a state accumulator contract."""

    model_name: str
    """dbt model name (e.g., 'int_enrollment_state_accumulator')"""

    table_name: str
    """Database table name for querying state"""

    prior_year_column: str
    """Column used for year-based filtering (typically 'simulation_year')"""

    start_year_source: str
    """Model providing initial state for start year"""

    description: str
    """Human-readable description of the accumulator's purpose"""


# =============================================================================
# StateAccumulatorRegistry Interface
# =============================================================================

class StateAccumulatorRegistryInterface(ABC):
    """Abstract interface for the state accumulator registry."""

    @classmethod
    @abstractmethod
    def register(cls, contract: StateAccumulatorContractProtocol) -> None:
        """Register a new state accumulator contract.

        Args:
            contract: The contract to register

        Raises:
            ValueError: If contract.model_name is already registered
        """
        ...

    @classmethod
    @abstractmethod
    def get(cls, model_name: str) -> StateAccumulatorContractProtocol:
        """Get a contract by model name.

        Args:
            model_name: The model name to look up

        Returns:
            The registered contract

        Raises:
            KeyError: If model_name is not registered
        """
        ...

    @classmethod
    @abstractmethod
    def list_all(cls) -> List[str]:
        """List all registered model names.

        Returns:
            Sorted list of registered model names
        """
        ...

    @classmethod
    @abstractmethod
    def get_registered_tables(cls) -> List[str]:
        """Get all registered table names.

        Returns:
            List of table names from all registered contracts
        """
        ...

    @classmethod
    @abstractmethod
    def clear(cls) -> None:
        """Clear all registered contracts.

        Note: This should only be used in testing.
        """
        ...


# =============================================================================
# YearDependencyValidator Interface
# =============================================================================

class YearDependencyValidatorInterface(ABC):
    """Abstract interface for year dependency validation."""

    @abstractmethod
    def __init__(self, db_manager, start_year: int) -> None:
        """Initialize the validator.

        Args:
            db_manager: DatabaseConnectionManager for database queries
            start_year: The configured simulation start year
        """
        ...

    @abstractmethod
    def validate_year_dependencies(self, year: int) -> None:
        """Validate that prior year data exists for all registered accumulators.

        This method should be called before STATE_ACCUMULATION stage execution.
        If year == start_year, validation is skipped (no prior dependency).

        Args:
            year: The simulation year about to execute

        Raises:
            YearDependencyError: If prior year data is missing for any accumulator
        """
        ...

    @abstractmethod
    def get_missing_years(self, year: int) -> Dict[str, int]:
        """Get mapping of accumulators with missing prior year data.

        Args:
            year: The simulation year to check

        Returns:
            Dict mapping table_name to row count (0 indicates missing data)
            Empty dict if all dependencies are satisfied
        """
        ...

    @abstractmethod
    def validate_checkpoint_dependencies(self, checkpoint_year: int) -> None:
        """Validate dependency chain from start_year to checkpoint_year.

        Used when resuming from a checkpoint to ensure all prior years have data.

        Args:
            checkpoint_year: The year of the checkpoint being resumed

        Raises:
            YearDependencyError: If any year in the chain is missing data
        """
        ...


# =============================================================================
# YearDependencyError Interface
# =============================================================================

class YearDependencyErrorInterface(Exception):
    """Interface for year dependency validation errors."""

    year: int
    """The year that failed validation"""

    missing_tables: Dict[str, int]
    """Mapping of table names to row counts (0 = missing)"""

    start_year: int
    """The configured start year"""

    message: str
    """Human-readable error message"""

    resolution_hint: str
    """Suggested fix for the error"""


# =============================================================================
# Integration Points
# =============================================================================

class YearExecutorValidationHook(Protocol):
    """Protocol for the validation hook in YearExecutor.

    This describes the expected signature for integrating validation
    into the YearExecutor.execute_workflow_stage() method.
    """

    def validate_before_state_accumulation(
        self,
        year: int,
        validator: YearDependencyValidatorInterface
    ) -> None:
        """Called before STATE_ACCUMULATION stage execution.

        Args:
            year: The simulation year
            validator: The dependency validator instance

        Raises:
            YearDependencyError: If validation fails
        """
        ...


class CheckpointRecoveryValidationHook(Protocol):
    """Protocol for checkpoint recovery validation.

    This describes the expected signature for integrating validation
    into the checkpoint recovery flow in StateManager.
    """

    def validate_before_checkpoint_resume(
        self,
        checkpoint_year: int,
        validator: YearDependencyValidatorInterface
    ) -> None:
        """Called before resuming from a checkpoint.

        Args:
            checkpoint_year: The year of the checkpoint
            validator: The dependency validator instance

        Raises:
            YearDependencyError: If dependency chain is broken
        """
        ...
