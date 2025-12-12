"""
Event Generator Interface Contracts

This file defines the abstract interfaces for the event type abstraction layer.
It serves as the contract specification - actual implementation will be in
planalign_orchestrator/generators/base.py.

NOTE: This is a design document, not production code. It demonstrates the
interface contract that implementations must fulfill.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Set, Type

if TYPE_CHECKING:
    from config.events import SimulationEvent
    from planalign_orchestrator.config import SimulationConfig
    from planalign_orchestrator.dbt_runner import DbtRunner
    from planalign_orchestrator.utils import DatabaseConnectionManager


# =============================================================================
# Context and Result Types
# =============================================================================


@dataclass
class EventContext:
    """Runtime context passed to event generators."""

    simulation_year: int
    scenario_id: str
    plan_design_id: str
    random_seed: int
    dbt_runner: "DbtRunner"
    db_manager: "DatabaseConnectionManager"
    config: "SimulationConfig"
    dbt_vars: Dict[str, any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Result of event validation."""

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class GeneratorMetrics:
    """Structured logging output for observability (FR-011)."""

    event_type: str
    event_count: int
    execution_time_ms: float
    mode: str  # "sql" or "polars"
    year: int
    scenario_id: str


# =============================================================================
# Base Event Generator Interface
# =============================================================================


class EventGenerator(ABC):
    """
    Abstract base class for all event generators.

    All event generators MUST implement:
    - generate_events(): Produce events for a simulation year
    - validate_event(): Validate a single event

    Subclasses define:
    - event_type: Unique identifier string
    - execution_order: Processing sequence (lower = earlier)
    - requires_hazard: Whether hazard tables are used
    - supports_sql: Whether SQL/dbt mode works
    - supports_polars: Whether Polars mode works

    Example:
        @EventRegistry.register("sabbatical")
        class SabbaticalEventGenerator(EventGenerator):
            event_type = "sabbatical"
            execution_order = 35
            requires_hazard = False
            supports_sql = True
            supports_polars = False

            def generate_events(self, context: EventContext) -> List[SimulationEvent]:
                # Implementation here
                pass

            def validate_event(self, event: SimulationEvent) -> ValidationResult:
                # Validation logic here
                pass
    """

    # Class attributes - must be defined by subclasses
    event_type: str
    execution_order: int
    requires_hazard: bool = False
    supports_sql: bool = True
    supports_polars: bool = False

    @abstractmethod
    def generate_events(self, context: EventContext) -> List["SimulationEvent"]:
        """
        Generate events for the given simulation context.

        Args:
            context: Runtime context with year, config, database access

        Returns:
            List of SimulationEvent instances

        Raises:
            EventGenerationError: If generation fails unrecoverably
        """
        pass

    @abstractmethod
    def validate_event(self, event: "SimulationEvent") -> ValidationResult:
        """
        Validate a single event.

        Args:
            event: The event to validate

        Returns:
            ValidationResult with is_valid flag and any errors/warnings
        """
        pass

    def calculate_hazard(self, employee_id: str, year: int, context: EventContext) -> float:
        """
        Calculate hazard probability for an employee.

        Only required if requires_hazard=True. Default implementation raises.

        Args:
            employee_id: Employee identifier
            year: Simulation year
            context: Runtime context

        Returns:
            Probability between 0.0 and 1.0

        Raises:
            NotImplementedError: If requires_hazard=True but not implemented
        """
        if self.requires_hazard:
            raise NotImplementedError(
                f"{self.__class__.__name__} has requires_hazard=True "
                "but does not implement calculate_hazard()"
            )
        return 0.0


# =============================================================================
# Hazard-Based Event Generator Mixin
# =============================================================================


class HazardBasedEventGeneratorMixin:
    """
    Mixin providing hazard calculation infrastructure.

    Use with EventGenerator for events that select employees based on
    hazard probability tables (e.g., promotions, merit raises).

    Provides:
    - Deterministic RNG matching dbt hash_rng macro
    - Age/tenure band assignment from config seeds
    - Hazard rate lookup from config tables
    - Selection algorithm for hazard-based filtering

    Example:
        class PromotionEventGenerator(HazardBasedEventGeneratorMixin, EventGenerator):
            event_type = "promotion"
            requires_hazard = True
            hazard_table_name = "config_promotion_hazard"

            def generate_events(self, context):
                workforce = self.get_active_workforce(context)
                selected = self.select_by_hazard(workforce, context)
                return self.create_events(selected, context)
    """

    hazard_table_name: str = ""
    rng_salt: str = ""

    def get_random_value(self, employee_id: str, year: int, seed: int) -> float:
        """
        Generate deterministic random value matching dbt hash_rng macro.

        Args:
            employee_id: Employee identifier
            year: Simulation year
            seed: Random seed

        Returns:
            Float between 0.0 and 1.0
        """
        import hashlib

        hash_key = f"{seed}|{employee_id}|{year}|{self.event_type}"
        if self.rng_salt:
            hash_key += f"|{self.rng_salt}"

        hash_value = hashlib.md5(hash_key.encode()).hexdigest()
        hash_int = int(hash_value[:8], 16)
        return (hash_int % 2147483647) / 2147483647.0

    def assign_age_band(self, age: float) -> str:
        """
        Assign age band using centralized config_age_bands seed.

        Args:
            age: Employee age in years

        Returns:
            Age band string (e.g., "25-34", "35-44")
        """
        # Implementation reads from config_age_bands seed
        # Bands use [min, max) interval convention
        pass

    def assign_tenure_band(self, tenure: float) -> str:
        """
        Assign tenure band using centralized config_tenure_bands seed.

        Args:
            tenure: Employee tenure in years

        Returns:
            Tenure band string (e.g., "0-2", "2-5")
        """
        # Implementation reads from config_tenure_bands seed
        pass

    def get_hazard_rate(
        self, age_band: str, tenure_band: str, level: int, context: EventContext
    ) -> float:
        """
        Look up hazard rate from configuration table.

        Args:
            age_band: Age band string
            tenure_band: Tenure band string
            level: Job level
            context: Runtime context for database access

        Returns:
            Hazard rate (probability 0.0 to 1.0)
        """
        # Implementation queries hazard_table_name seed
        pass

    def select_by_hazard(
        self, workforce: List[dict], context: EventContext
    ) -> List[dict]:
        """
        Filter workforce by hazard probability.

        For each employee, compare random value to hazard rate.
        Employees with random_value < hazard_rate are selected.

        Args:
            workforce: List of employee dictionaries
            context: Runtime context

        Returns:
            Filtered list of selected employees
        """
        selected = []
        for emp in workforce:
            random_val = self.get_random_value(
                emp["employee_id"], context.simulation_year, context.random_seed
            )
            hazard_rate = self.get_hazard_rate(
                emp["age_band"], emp["tenure_band"], emp["level_id"], context
            )
            if random_val < hazard_rate:
                selected.append(emp)
        return selected


# =============================================================================
# Event Registry
# =============================================================================


class EventRegistry:
    """
    Centralized registration and lookup for event generators.

    Singleton pattern ensures consistent state across the application.

    Usage:
        # Registration via decorator
        @EventRegistry.register("hire")
        class HireEventGenerator(EventGenerator):
            ...

        # Lookup
        generator = EventRegistry.get("hire")
        all_types = EventRegistry.list_all()

        # Scenario-specific disable
        EventRegistry.disable("sabbatical", scenario_id="baseline")
    """

    _generators: Dict[str, Type[EventGenerator]] = {}
    _instances: Dict[str, EventGenerator] = {}
    _disabled: Dict[str, Set[str]] = {}  # scenario_id -> set of disabled event_types

    @classmethod
    def register(cls, event_type: str) -> Callable[[Type[EventGenerator]], Type[EventGenerator]]:
        """
        Decorator to register an event generator class.

        Args:
            event_type: Unique event type identifier

        Returns:
            Decorator function

        Raises:
            ValueError: If event_type already registered or invalid
        """

        def decorator(generator_class: Type[EventGenerator]) -> Type[EventGenerator]:
            if event_type in cls._generators:
                raise ValueError(f"Event type '{event_type}' already registered")

            if not event_type or not event_type[0].islower():
                raise ValueError(
                    f"Event type must start with lowercase letter: '{event_type}'"
                )

            cls._generators[event_type] = generator_class
            return generator_class

        return decorator

    @classmethod
    def get(cls, event_type: str) -> EventGenerator:
        """
        Get generator instance by event type.

        Args:
            event_type: Event type identifier

        Returns:
            EventGenerator instance (cached)

        Raises:
            KeyError: If event type not registered
        """
        if event_type not in cls._generators:
            raise KeyError(
                f"Event type '{event_type}' not registered. "
                f"Available: {list(cls._generators.keys())}"
            )

        if event_type not in cls._instances:
            cls._instances[event_type] = cls._generators[event_type]()

        return cls._instances[event_type]

    @classmethod
    def list_all(cls) -> List[str]:
        """List all registered event types."""
        return sorted(cls._generators.keys())

    @classmethod
    def list_enabled(cls, scenario_id: str) -> List[str]:
        """List event types enabled for a scenario."""
        disabled = cls._disabled.get(scenario_id, set())
        return [et for et in cls.list_all() if et not in disabled]

    @classmethod
    def list_ordered(cls, scenario_id: str) -> List[EventGenerator]:
        """Get enabled generators ordered by execution_order."""
        enabled = cls.list_enabled(scenario_id)
        generators = [cls.get(et) for et in enabled]
        return sorted(generators, key=lambda g: g.execution_order)

    @classmethod
    def disable(cls, event_type: str, scenario_id: str) -> None:
        """Disable an event type for a specific scenario."""
        if scenario_id not in cls._disabled:
            cls._disabled[scenario_id] = set()
        cls._disabled[scenario_id].add(event_type)

    @classmethod
    def enable(cls, event_type: str, scenario_id: str) -> None:
        """Enable an event type for a specific scenario."""
        if scenario_id in cls._disabled:
            cls._disabled[scenario_id].discard(event_type)

    @classmethod
    def clear(cls) -> None:
        """Clear all registrations (for testing)."""
        cls._generators.clear()
        cls._instances.clear()
        cls._disabled.clear()
