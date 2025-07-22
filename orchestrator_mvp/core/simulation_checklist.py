"""
SimulationChecklist: Step sequencing enforcement for multi-year workforce simulations.

This module provides systematic validation of the 7-step workflow required for each
simulation year, preventing users from executing steps out of order and ensuring
data consistency throughout the multi-year simulation process.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class SimulationStep(Enum):
    """Enumeration of required simulation steps in dependency order."""
    PRE_SIMULATION = "pre_simulation"
    YEAR_TRANSITION = "year_transition"
    WORKFORCE_BASELINE = "workforce_baseline"
    WORKFORCE_REQUIREMENTS = "workforce_requirements"
    EVENT_GENERATION = "event_generation"
    WORKFORCE_SNAPSHOT = "workforce_snapshot"
    VALIDATION_METRICS = "validation_metrics"


class StepSequenceError(Exception):
    """Raised when simulation steps are attempted out of proper sequence."""

    def __init__(self, step: str, year: int, missing_prerequisites: List[str]):
        self.step = step
        self.year = year
        self.missing_prerequisites = missing_prerequisites

        prereq_list = ", ".join(missing_prerequisites)
        message = (
            f"Cannot execute step '{step}' for year {year}. "
            f"Missing prerequisites: {prereq_list}. "
            f"Please complete these steps first before proceeding."
        )
        super().__init__(message)


@dataclass
class StepStatus:
    """Tracks completion status and metadata for a simulation step."""
    completed: bool = False
    timestamp: Optional[str] = None
    error_message: Optional[str] = None


class SimulationChecklist:
    """
    Enforces proper step sequencing for multi-year workforce simulations.

    The checklist tracks completion state for each step in each simulation year,
    validates prerequisites before allowing step execution, and provides resume
    capability for interrupted simulations.
    """

    # Step dependency mapping - which steps must be completed before others can begin
    STEP_DEPENDENCIES = {
        SimulationStep.PRE_SIMULATION: [],
        SimulationStep.YEAR_TRANSITION: [SimulationStep.PRE_SIMULATION],
        SimulationStep.WORKFORCE_BASELINE: [SimulationStep.YEAR_TRANSITION],
        SimulationStep.WORKFORCE_REQUIREMENTS: [SimulationStep.WORKFORCE_BASELINE],
        SimulationStep.EVENT_GENERATION: [SimulationStep.WORKFORCE_REQUIREMENTS],
        SimulationStep.WORKFORCE_SNAPSHOT: [SimulationStep.EVENT_GENERATION],
        SimulationStep.VALIDATION_METRICS: [SimulationStep.WORKFORCE_SNAPSHOT],
    }

    def __init__(self, start_year: int, end_year: int):
        """
        Initialize checklist for multi-year simulation.

        Args:
            start_year: First year of simulation (e.g., 2025)
            end_year: Last year of simulation (e.g., 2029)
        """
        self.start_year = start_year
        self.end_year = end_year
        self.years = list(range(start_year, end_year + 1))

        # State tracking: {year}.{step_name} -> StepStatus
        self._state: Dict[str, StepStatus] = {}

        # Initialize state for all years and steps
        self._initialize_state()

        logger.info(
            f"Initialized simulation checklist for years {start_year}-{end_year}"
        )

    def _initialize_state(self) -> None:
        """Initialize completion state for all years and steps."""
        # Pre-simulation is year-independent
        self._state["pre_simulation"] = StepStatus()

        # Initialize state for each year
        for year in self.years:
            for step in SimulationStep:
                if step != SimulationStep.PRE_SIMULATION:
                    key = f"{year}.{step.value}"
                    self._state[key] = StepStatus()

    def _get_state_key(self, step: str, year: Optional[int] = None) -> str:
        """Generate state key for step tracking."""
        if step == "pre_simulation":
            return step
        if year is None:
            raise ValueError(f"Year required for step {step}")
        return f"{year}.{step}"

    def begin_year(self, year: int) -> None:
        """
        Initialize checklist state for a new simulation year.

        Args:
            year: Simulation year to begin

        Raises:
            ValueError: If year is outside simulation range
        """
        if year not in self.years:
            raise ValueError(
                f"Year {year} is outside simulation range {self.start_year}-{self.end_year}"
            )

        # For years after the first, ensure previous year was completed
        if year > self.start_year:
            prev_year = year - 1
            if not self._is_year_complete(prev_year):
                raise StepSequenceError(
                    f"year_{year}_start",
                    year,
                    [f"Complete all steps for year {prev_year}"]
                )

        logger.info(f"Beginning simulation year {year}")

    def mark_step_complete(self, step_name: str, year: Optional[int] = None) -> None:
        """
        Mark a simulation step as completed.

        Args:
            step_name: Name of the completed step
            year: Simulation year (required for year-specific steps)
        """
        key = self._get_state_key(step_name, year)

        if key not in self._state:
            raise ValueError(f"Unknown step: {step_name} for year {year}")

        self._state[key].completed = True
        self._state[key].timestamp = self._get_timestamp()
        self._state[key].error_message = None

        year_str = f" for year {year}" if year else ""
        logger.info(f"Marked step '{step_name}'{year_str} as complete")

    def assert_step_ready(self, step_name: str, year: Optional[int] = None) -> None:
        """
        Validate that all prerequisites for a step are met.

        Args:
            step_name: Name of step to validate
            year: Simulation year (required for year-specific steps)

        Raises:
            StepSequenceError: If prerequisites are not met
        """
        # Convert string to enum for dependency lookup
        try:
            step_enum = SimulationStep(step_name)
        except ValueError:
            raise ValueError(f"Unknown step: {step_name}")

        missing_prerequisites = []

        # Check direct step dependencies
        for prereq_step in self.STEP_DEPENDENCIES[step_enum]:
            if prereq_step == SimulationStep.PRE_SIMULATION:
                if not self._state["pre_simulation"].completed:
                    missing_prerequisites.append("pre_simulation")
            else:
                prereq_key = self._get_state_key(prereq_step.value, year)
                if not self._state.get(prereq_key, StepStatus()).completed:
                    missing_prerequisites.append(f"{prereq_step.value} (year {year})")

        # Special validation for year transition
        if step_name == "year_transition" and year and year > self.start_year:
            prev_year = year - 1
            if not self._is_year_complete(prev_year):
                missing_prerequisites.append(f"Complete all steps for year {prev_year}")

        if missing_prerequisites:
            raise StepSequenceError(step_name, year or 0, missing_prerequisites)

        year_str = f" for year {year}" if year else ""
        logger.debug(f"Step '{step_name}'{year_str} is ready to execute")

    def get_completion_status(self, year: Optional[int] = None) -> Dict[str, bool]:
        """
        Get current completion status for a year or all years.

        Args:
            year: Specific year to check, or None for all years

        Returns:
            Dictionary mapping step names to completion status
        """
        if year is None:
            # Return status for all years
            status = {"pre_simulation": self._state["pre_simulation"].completed}
            for yr in self.years:
                for step in SimulationStep:
                    if step != SimulationStep.PRE_SIMULATION:
                        key = f"{yr}.{step.value}"
                        status[key] = self._state.get(key, StepStatus()).completed
            return status
        else:
            # Return status for specific year
            status = {"pre_simulation": self._state["pre_simulation"].completed}
            for step in SimulationStep:
                if step != SimulationStep.PRE_SIMULATION:
                    key = f"{year}.{step.value}"
                    status[step.value] = self._state.get(key, StepStatus()).completed
            return status

    def can_resume_from(self, year: int, step: str) -> bool:
        """
        Check if simulation can resume from a specific point.

        Args:
            year: Year to resume from
            step: Step to resume from

        Returns:
            True if resume is possible, False otherwise
        """
        try:
            self.assert_step_ready(step, year)
            return True
        except StepSequenceError:
            return False

    def reset_year(self, year: int) -> None:
        """
        Clear completion state for a specific year.

        Args:
            year: Year to reset
        """
        if year not in self.years:
            raise ValueError(f"Year {year} is outside simulation range")

        for step in SimulationStep:
            if step != SimulationStep.PRE_SIMULATION:
                key = f"{year}.{step.value}"
                if key in self._state:
                    self._state[key] = StepStatus()

        logger.info(f"Reset completion state for year {year}")

    def get_next_step(self, year: int) -> Optional[str]:
        """
        Get the next step that needs to be completed for a year.

        Args:
            year: Year to check

        Returns:
            Name of next step, or None if year is complete
        """
        # Check pre_simulation first
        if not self._state["pre_simulation"].completed:
            return "pre_simulation"

        # Check year-specific steps in order
        for step in SimulationStep:
            if step == SimulationStep.PRE_SIMULATION:
                continue

            key = f"{year}.{step.value}"
            if not self._state.get(key, StepStatus()).completed:
                return step.value

        return None  # Year is complete

    def _is_year_complete(self, year: int) -> bool:
        """Check if all steps for a year are completed."""
        for step in SimulationStep:
            if step == SimulationStep.PRE_SIMULATION:
                if not self._state["pre_simulation"].completed:
                    return False
            else:
                key = f"{year}.{step.value}"
                if not self._state.get(key, StepStatus()).completed:
                    return False
        return True

    def _get_timestamp(self) -> str:
        """Get current timestamp for step completion tracking."""
        from datetime import datetime
        return datetime.now().isoformat()

    def get_progress_summary(self) -> str:
        """
        Get a human-readable progress summary.

        Returns:
            Formatted string showing completion status
        """
        lines = ["Simulation Progress Summary:"]
        lines.append("=" * 40)

        # Pre-simulation status
        pre_status = "✓" if self._state["pre_simulation"].completed else "○"
        lines.append(f"{pre_status} Pre-simulation setup")

        # Year-by-year status
        for year in self.years:
            year_complete = self._is_year_complete(year)
            year_status = "✓" if year_complete else "○"
            lines.append(f"{year_status} Year {year}")

            # Show individual step status if year is not complete
            if not year_complete:
                for step in SimulationStep:
                    if step == SimulationStep.PRE_SIMULATION:
                        continue

                    key = f"{year}.{step.value}"
                    step_complete = self._state.get(key, StepStatus()).completed
                    step_status = "  ✓" if step_complete else "  ○"
                    step_name = step.value.replace("_", " ").title()
                    lines.append(f"{step_status} {step_name}")

        return "\n".join(lines)
