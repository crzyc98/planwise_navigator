"""Test data factories for creating test objects."""

from datetime import date, datetime
from typing import Dict, Any, Optional
import uuid

from config.events import (
    SimulationEvent,
    HirePayload,
    TerminationPayload,
    PromotionPayload,
    MeritPayload,
)


class EventFactory:
    """Factory for creating test simulation events."""

    @staticmethod
    def create_hire(
        employee_id: Optional[str] = None,
        effective_date: Optional[date] = None,
        **kwargs
    ) -> SimulationEvent:
        """Create a hire event for testing."""
        return SimulationEvent(
            event_id=str(uuid.uuid4()),
            event_type="hire",
            employee_id=employee_id or f"EMP_{uuid.uuid4().hex[:6].upper()}",
            effective_date=effective_date or date.today(),
            scenario_id=kwargs.get("scenario_id", "test_scenario"),
            plan_design_id=kwargs.get("plan_design_id", "test_plan"),
            payload=HirePayload(
                job_level=kwargs.get("job_level", 2),
                starting_salary=kwargs.get("starting_salary", 65000.0),
                department=kwargs.get("department", "Engineering"),
            )
        )

    @staticmethod
    def create_termination(
        employee_id: str,
        effective_date: Optional[date] = None,
        **kwargs
    ) -> SimulationEvent:
        """Create a termination event for testing."""
        return SimulationEvent(
            event_id=str(uuid.uuid4()),
            event_type="termination",
            employee_id=employee_id,
            effective_date=effective_date or date.today(),
            scenario_id=kwargs.get("scenario_id", "test_scenario"),
            plan_design_id=kwargs.get("plan_design_id", "test_plan"),
            payload=TerminationPayload(
                reason=kwargs.get("reason", "voluntary"),
                termination_type=kwargs.get("termination_type", "resignation"),
            )
        )


class WorkforceFactory:
    """Factory for creating test workforce data."""

    @staticmethod
    def create_employee(employee_id: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Create a test employee record."""
        return {
            "employee_id": employee_id or f"EMP_{uuid.uuid4().hex[:6].upper()}",
            "job_level": kwargs.get("job_level", 2),
            "current_compensation": kwargs.get("current_compensation", 65000.0),
            "years_of_service": kwargs.get("years_of_service", 3.0),
            "department": kwargs.get("department", "Engineering"),
            "performance_rating": kwargs.get("performance_rating", 3),
        }


class ConfigFactory:
    """Factory for creating test configuration objects."""

    @staticmethod
    def create_simulation_config(**kwargs) -> Dict[str, Any]:
        """Create a test simulation configuration."""
        return {
            "simulation": {
                "start_year": kwargs.get("start_year", 2025),
                "end_year": kwargs.get("end_year", 2025),
                "scenario_id": kwargs.get("scenario_id", "test_scenario"),
                "plan_design_id": kwargs.get("plan_design_id", "test_plan"),
                "random_seed": kwargs.get("random_seed", 42),
            },
            "database": {
                "path": kwargs.get("database_path", "dbt/simulation.duckdb"),
            },
        }
