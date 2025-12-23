"""
StateAccumulatorRegistry - Singleton registry for temporal state accumulator contracts.

Tracks all registered accumulator models and provides lookup methods for
validation. Follows the same singleton pattern as EventRegistry.

Example:
    from planalign_orchestrator.state_accumulator import (
        StateAccumulatorContract,
        StateAccumulatorRegistry,
    )

    # Register an accumulator
    StateAccumulatorRegistry.register(
        StateAccumulatorContract(
            model_name="int_my_accumulator",
            table_name="int_my_accumulator",
            start_year_source="int_baseline_workforce",
        )
    )

    # Query registered accumulators
    names = StateAccumulatorRegistry.list_all()
    tables = StateAccumulatorRegistry.get_registered_tables()
"""

from __future__ import annotations

import logging
from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from planalign_orchestrator.state_accumulator.contract import StateAccumulatorContract

logger = logging.getLogger(__name__)


class StateAccumulatorRegistry:
    """Centralized registry for temporal state accumulator contracts.

    Singleton pattern ensures consistent state across the application.
    All state accumulator models must be registered here to enable
    year dependency validation.

    Class Attributes:
        _contracts: Map of model_name to StateAccumulatorContract

    Thread Safety:
        Not thread-safe. Designed for single-threaded orchestration.
        Registration should happen at import time, before execution.

    Example:
        >>> StateAccumulatorRegistry.register(contract)
        >>> names = StateAccumulatorRegistry.list_all()
        >>> ['int_deferral_rate_state_accumulator', 'int_enrollment_state_accumulator']
    """

    _contracts: Dict[str, "StateAccumulatorContract"] = {}

    @classmethod
    def register(cls, contract: "StateAccumulatorContract") -> None:
        """Register a new state accumulator contract.

        Args:
            contract: The contract to register. Must have a unique model_name.

        Raises:
            ValueError: If a contract with the same model_name is already registered.

        Example:
            >>> from planalign_orchestrator.state_accumulator import (
            ...     StateAccumulatorContract, StateAccumulatorRegistry
            ... )
            >>> contract = StateAccumulatorContract(
            ...     model_name="int_my_accumulator",
            ...     table_name="int_my_accumulator",
            ...     start_year_source="int_baseline_workforce",
            ... )
            >>> StateAccumulatorRegistry.register(contract)
        """
        if contract.model_name in cls._contracts:
            existing = cls._contracts[contract.model_name]
            raise ValueError(
                f"Model '{contract.model_name}' is already registered. "
                f"Existing registration: {existing}. "
                f"Each state accumulator model can only be registered once."
            )
        cls._contracts[contract.model_name] = contract
        logger.debug(f"Registered state accumulator: {contract.model_name}")

    @classmethod
    def get(cls, model_name: str) -> "StateAccumulatorContract":
        """Get a contract by model name.

        Args:
            model_name: The model name to look up.

        Returns:
            The registered StateAccumulatorContract.

        Raises:
            KeyError: If model_name is not registered. Error message includes
                     list of available model names for debugging.

        Example:
            >>> contract = StateAccumulatorRegistry.get("int_enrollment_state_accumulator")
            >>> contract.table_name
            'int_enrollment_state_accumulator'
        """
        if model_name not in cls._contracts:
            available = ", ".join(sorted(cls._contracts.keys())) or "(none)"
            raise KeyError(
                f"Model '{model_name}' is not registered as a state accumulator. "
                f"Available models: [{available}]. "
                f"Did you forget to register the model in state_accumulator/__init__.py?"
            )
        return cls._contracts[model_name]

    @classmethod
    def list_all(cls) -> List[str]:
        """List all registered model names.

        Returns:
            Sorted list of registered model names.

        Example:
            >>> names = StateAccumulatorRegistry.list_all()
            >>> ['int_deferral_rate_state_accumulator', 'int_enrollment_state_accumulator']
        """
        return sorted(cls._contracts.keys())

    @classmethod
    def get_registered_tables(cls) -> List[str]:
        """Get all registered table names.

        Returns:
            List of table names from all registered contracts.
            Order matches iteration order of internal dict.

        Example:
            >>> tables = StateAccumulatorRegistry.get_registered_tables()
            >>> ['int_enrollment_state_accumulator', 'int_deferral_rate_state_accumulator']
        """
        return [contract.table_name for contract in cls._contracts.values()]

    @classmethod
    def get_all_contracts(cls) -> List["StateAccumulatorContract"]:
        """Get all registered contracts.

        Returns:
            List of all registered StateAccumulatorContract objects.

        Example:
            >>> contracts = StateAccumulatorRegistry.get_all_contracts()
            >>> len(contracts)
            2
        """
        return list(cls._contracts.values())

    @classmethod
    def clear(cls) -> None:
        """Clear all registered contracts.

        Note:
            This should only be used in testing to reset registry state
            between tests. Should NOT be called in production code.

        Example:
            >>> StateAccumulatorRegistry.clear()
            >>> StateAccumulatorRegistry.list_all()
            []
        """
        cls._contracts.clear()
        logger.debug("StateAccumulatorRegistry cleared")

    @classmethod
    def count(cls) -> int:
        """Return the number of registered contracts.

        Returns:
            Number of registered state accumulator contracts.

        Example:
            >>> StateAccumulatorRegistry.count()
            2
        """
        return len(cls._contracts)

    @classmethod
    def is_registered(cls, model_name: str) -> bool:
        """Check if a model is registered.

        Args:
            model_name: The model name to check.

        Returns:
            True if the model is registered, False otherwise.

        Example:
            >>> StateAccumulatorRegistry.is_registered("int_enrollment_state_accumulator")
            True
        """
        return model_name in cls._contracts

    @classmethod
    def summary(cls) -> str:
        """Return a summary string of registered accumulators.

        Useful for debugging and logging.

        Returns:
            Human-readable summary of registered accumulators.

        Example:
            >>> print(StateAccumulatorRegistry.summary())
            StateAccumulatorRegistry (2 accumulators):
              - int_deferral_rate_state_accumulator -> int_deferral_rate_state_accumulator
              - int_enrollment_state_accumulator -> int_enrollment_state_accumulator
        """
        if not cls._contracts:
            return "StateAccumulatorRegistry: No accumulators registered"

        lines = [f"StateAccumulatorRegistry ({len(cls._contracts)} accumulators):"]
        for model_name in sorted(cls._contracts.keys()):
            contract = cls._contracts[model_name]
            lines.append(f"  - {model_name} -> {contract.table_name}")

        return "\n".join(lines)
