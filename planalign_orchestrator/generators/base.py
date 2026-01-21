"""
Event Generator Base Classes

This module defines the abstract interfaces for the event type abstraction layer:
- EventContext: Runtime context passed to generators
- ValidationResult: Result of event validation
- GeneratorMetrics: Structured logging output (FR-011)
- EventGenerator: Abstract base class for all event generators
- HazardBasedEventGeneratorMixin: Mixin for hazard-based event generation

All event generators must inherit from EventGenerator and implement the
required abstract methods: generate_events() and validate_event().
"""

from __future__ import annotations

import hashlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from config.events import SimulationEvent
    from planalign_orchestrator.config import SimulationConfig
    from planalign_orchestrator.dbt_runner import DbtRunner
    from planalign_orchestrator.utils import DatabaseConnectionManager

logger = logging.getLogger(__name__)


# =============================================================================
# Context and Result Types (T004, T005, T006)
# =============================================================================


@dataclass
class EventContext:
    """
    Runtime context passed to event generators.

    Contains all dependencies and configuration needed to generate events
    for a specific simulation year and scenario.

    Attributes:
        simulation_year: Current simulation year being processed
        scenario_id: Active scenario identifier
        plan_design_id: Plan design configuration identifier
        random_seed: Global random seed for reproducibility
        dbt_runner: DbtRunner instance for SQL mode execution
        db_manager: DatabaseConnectionManager for direct queries
        config: Full SimulationConfig instance
        dbt_vars: Additional dbt variables for model execution
    """

    simulation_year: int
    scenario_id: str
    plan_design_id: str
    random_seed: int
    dbt_runner: "DbtRunner"
    db_manager: "DatabaseConnectionManager"
    config: "SimulationConfig"
    dbt_vars: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """
    Result of event validation.

    Returned by EventGenerator.validate_event() to indicate whether
    an event is valid and any errors or warnings encountered.

    Attributes:
        is_valid: Whether the event passed validation
        errors: List of validation error messages (blocking)
        warnings: List of validation warning messages (non-blocking)
    """

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class GeneratorMetrics:
    """
    Structured logging output for observability (FR-011).

    Emitted after each generator completes event generation to provide
    metrics for monitoring and debugging.

    Attributes:
        event_type: Generator event type identifier
        event_count: Number of events generated
        execution_time_ms: Generation time in milliseconds
        mode: Execution mode (always "sql")
        year: Simulation year
        scenario_id: Scenario identifier
    """

    event_type: str
    event_count: int
    execution_time_ms: float
    mode: str  # always "sql"
    year: int
    scenario_id: str

    def to_log_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for structured logging."""
        return {
            "event_type": self.event_type,
            "event_count": self.event_count,
            "execution_time_ms": round(self.execution_time_ms, 2),
            "mode": self.mode,
            "year": self.year,
            "scenario_id": self.scenario_id,
        }


# =============================================================================
# Base Event Generator Interface (T007)
# =============================================================================


class EventGenerator(ABC):
    """
    Abstract base class for all event generators.

    All event generators MUST implement:
    - generate_events(): Produce events for a simulation year
    - validate_event(): Validate a single event

    Subclasses MUST define class attributes:
    - event_type: Unique identifier string (e.g., "hire", "termination")
    - execution_order: Processing sequence (lower = earlier)

    Optional attributes:
    - requires_hazard: Whether generator uses hazard probability tables
    - supports_sql: Whether SQL/dbt mode is supported (default: True)

    Example:
        from planalign_orchestrator.generators import EventGenerator, EventRegistry

        @EventRegistry.register("sabbatical")
        class SabbaticalEventGenerator(EventGenerator):
            event_type = "sabbatical"
            execution_order = 35
            requires_hazard = False
            supports_sql = True

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

    # Optional attributes with defaults
    requires_hazard: bool = False
    supports_sql: bool = True

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

    def calculate_hazard(
        self, employee_id: str, year: int, context: EventContext
    ) -> float:
        """
        Calculate hazard probability for an employee.

        Only required if requires_hazard=True. Default implementation raises
        NotImplementedError if called when requires_hazard is True.

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
                "but does not implement calculate_hazard(). "
                "Either set requires_hazard=False or implement calculate_hazard()."
            )
        return 0.0

    def generate_with_metrics(
        self, context: EventContext, mode: str = "sql"
    ) -> tuple[List["SimulationEvent"], GeneratorMetrics]:
        """
        Generate events and return metrics for structured logging (FR-011).

        Wraps generate_events() with timing and count tracking.

        Args:
            context: Runtime context
            mode: Execution mode (always "sql")

        Returns:
            Tuple of (events, metrics)
        """
        start_time = time.perf_counter()
        events = self.generate_events(context)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        metrics = GeneratorMetrics(
            event_type=self.event_type,
            event_count=len(events),
            execution_time_ms=elapsed_ms,
            mode=mode,
            year=context.simulation_year,
            scenario_id=context.scenario_id,
        )

        # Emit structured log (FR-011)
        logger.info(
            f"Event generation complete: {self.event_type}",
            extra={"generator_metrics": metrics.to_log_dict()},
        )

        return events, metrics

    def __init_subclass__(cls, **kwargs):
        """
        Validate subclass defines required attributes (FR-007).

        Called when a class inherits from EventGenerator. Raises
        TypeError with clear message if required attributes are missing.
        """
        super().__init_subclass__(**kwargs)

        # Skip validation for abstract classes
        if ABC in cls.__bases__:
            return

        # Check required attributes
        missing = []
        if not hasattr(cls, "event_type") or cls.event_type is None:
            missing.append("event_type")
        if not hasattr(cls, "execution_order") or cls.execution_order is None:
            missing.append("execution_order")

        if missing:
            raise TypeError(
                f"Class {cls.__name__} must define class attributes: {', '.join(missing)}. "
                f"Example:\n"
                f"  class {cls.__name__}(EventGenerator):\n"
                f"      event_type = 'my_event'\n"
                f"      execution_order = 50\n"
                f"      ..."
            )


# =============================================================================
# Hazard-Based Event Generator Mixin (T041-T046, implemented later)
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
            execution_order = 30
            requires_hazard = True
            hazard_table_name = "config_promotion_hazard"

            def generate_events(self, context):
                workforce = self._get_active_workforce(context)
                selected = self.select_by_hazard(workforce, context)
                return self._create_events(selected, context)
    """

    # Subclasses should override these
    hazard_table_name: str = ""
    rng_salt: str = ""

    # Cache for band definitions
    _age_bands: Optional[List[Dict[str, Any]]] = None
    _tenure_bands: Optional[List[Dict[str, Any]]] = None

    def get_random_value(self, employee_id: str, year: int, seed: int) -> float:
        """
        Generate deterministic random value matching dbt hash_rng macro.

        Uses MD5 hash for consistency with existing dbt macro implementation.
        Hash key format: {seed}|{employee_id}|{year}|{event_type}[|{salt}]

        Args:
            employee_id: Employee identifier
            year: Simulation year
            seed: Random seed

        Returns:
            Float between 0.0 and 1.0 (deterministic for same inputs)
        """
        # Build hash key exactly matching dbt macro
        hash_key = f"{seed}|{employee_id}|{year}|{self.event_type}"
        if self.rng_salt:
            hash_key += f"|{self.rng_salt}"

        # Use MD5 hash like dbt macro, then normalize to [0, 1)
        hash_value = hashlib.md5(hash_key.encode()).hexdigest()
        hash_int = int(hash_value[:8], 16)
        return (hash_int % 2147483647) / 2147483647.0

    def assign_age_band(self, age: float, context: EventContext) -> str:
        """
        Assign age band using centralized config_age_bands seed.

        Uses [min, max) interval convention where age >= min_value
        and age < max_value.

        Args:
            age: Employee age in years
            context: Runtime context for database access

        Returns:
            Age band label string (e.g., "25-34", "35-44")
        """
        if self._age_bands is None:
            self._load_age_bands(context)

        for band in self._age_bands:
            if band["min_value"] <= age < band["max_value"]:
                return band["band_label"]

        # Default to last band if age exceeds all ranges
        return self._age_bands[-1]["band_label"] if self._age_bands else "unknown"

    def assign_tenure_band(self, tenure: float, context: EventContext) -> str:
        """
        Assign tenure band using centralized config_tenure_bands seed.

        Uses [min, max) interval convention.

        Args:
            tenure: Employee tenure in years
            context: Runtime context for database access

        Returns:
            Tenure band label string (e.g., "0-2", "2-5")
        """
        if self._tenure_bands is None:
            self._load_tenure_bands(context)

        for band in self._tenure_bands:
            if band["min_value"] <= tenure < band["max_value"]:
                return band["band_label"]

        # Default to last band if tenure exceeds all ranges
        return self._tenure_bands[-1]["band_label"] if self._tenure_bands else "unknown"

    def _load_age_bands(self, context: EventContext) -> None:
        """Load age band definitions from database."""

        def _query(conn):
            return conn.execute(
                """
                SELECT band_label, min_value, max_value
                FROM stg_config_age_bands
                ORDER BY min_value
                """
            ).fetchall()

        rows = context.db_manager.execute_with_retry(_query)
        self._age_bands = [
            {"band_label": r[0], "min_value": float(r[1]), "max_value": float(r[2])}
            for r in rows
        ]

    def _load_tenure_bands(self, context: EventContext) -> None:
        """Load tenure band definitions from database."""

        def _query(conn):
            return conn.execute(
                """
                SELECT band_label, min_value, max_value
                FROM stg_config_tenure_bands
                ORDER BY min_value
                """
            ).fetchall()

        rows = context.db_manager.execute_with_retry(_query)
        self._tenure_bands = [
            {"band_label": r[0], "min_value": float(r[1]), "max_value": float(r[2])}
            for r in rows
        ]

    def get_hazard_rate(
        self,
        age_band: str,
        tenure_band: str,
        level: int,
        context: EventContext,
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
        if not self.hazard_table_name:
            raise ValueError(
                f"{self.__class__.__name__} must define hazard_table_name "
                "to use get_hazard_rate()"
            )

        def _query(conn):
            return conn.execute(
                f"""
                SELECT hazard_rate
                FROM {self.hazard_table_name}
                WHERE age_band = ?
                  AND tenure_band = ?
                  AND level_id = ?
                """,
                [age_band, tenure_band, level],
            ).fetchone()

        result = context.db_manager.execute_with_retry(_query)
        if result:
            return float(result[0])

        # Log warning and return 0 if no matching rate found
        logger.warning(
            f"No hazard rate found for age_band={age_band}, "
            f"tenure_band={tenure_band}, level={level} in {self.hazard_table_name}"
        )
        return 0.0

    def select_by_hazard(
        self, workforce: List[Dict[str, Any]], context: EventContext
    ) -> List[Dict[str, Any]]:
        """
        Filter workforce by hazard probability.

        For each employee, compare random value to hazard rate.
        Employees with random_value < hazard_rate are selected.

        Args:
            workforce: List of employee dictionaries with keys:
                       employee_id, age_band, tenure_band, level_id
            context: Runtime context

        Returns:
            Filtered list of selected employees
        """
        selected = []
        for emp in workforce:
            random_val = self.get_random_value(
                emp["employee_id"],
                context.simulation_year,
                context.random_seed,
            )
            hazard_rate = self.get_hazard_rate(
                emp.get("age_band", "unknown"),
                emp.get("tenure_band", "unknown"),
                emp.get("level_id", 1),
                context,
            )
            if random_val < hazard_rate:
                selected.append(emp)

        logger.debug(
            f"{self.event_type}: Selected {len(selected)}/{len(workforce)} "
            f"employees by hazard probability"
        )
        return selected
