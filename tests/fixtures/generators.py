"""
Test fixtures for event generators.

Provides mock generators and test utilities for testing the event
type abstraction layer.
"""

from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Dict, Any, Optional
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from planalign_orchestrator.generators.base import EventContext, ValidationResult


@dataclass
class MockEventContext:
    """Mock EventContext for testing without database dependencies."""

    simulation_year: int = 2025
    scenario_id: str = "test_scenario"
    plan_design_id: str = "default"
    random_seed: int = 42
    dbt_runner: Any = None
    db_manager: Any = None
    config: Any = None
    dbt_vars: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.dbt_runner is None:
            self.dbt_runner = MagicMock()
        if self.db_manager is None:
            self.db_manager = MagicMock()
        if self.config is None:
            self.config = MagicMock()


@dataclass
class MockSimulationEvent:
    """Mock SimulationEvent for testing without Pydantic dependencies."""

    event_id: str = "test-uuid-1234"
    employee_id: str = "EMP_001"
    scenario_id: str = "test_scenario"
    plan_design_id: str = "default"
    effective_date: str = "2025-01-15"
    event_type: str = "test_event"
    source_system: str = "test"
    payload: Dict[str, Any] = field(default_factory=dict)


@pytest.fixture
def mock_event_context():
    """Fixture providing a mock EventContext."""
    return MockEventContext()


@pytest.fixture
def mock_simulation_event():
    """Fixture providing a mock SimulationEvent."""
    return MockSimulationEvent()


@pytest.fixture
def mock_workforce_data():
    """Fixture providing sample workforce data for testing."""
    return [
        {
            "employee_id": "EMP_001",
            "employee_ssn": "123-45-6789",
            "current_age": 35.5,
            "current_tenure": 5.2,
            "level_id": 3,
            "age_band": "35-44",
            "tenure_band": "5-10",
            "annual_compensation": 85000.00,
            "employment_status": "active",
        },
        {
            "employee_id": "EMP_002",
            "employee_ssn": "987-65-4321",
            "current_age": 28.3,
            "current_tenure": 2.1,
            "level_id": 2,
            "age_band": "25-34",
            "tenure_band": "2-5",
            "annual_compensation": 65000.00,
            "employment_status": "active",
        },
        {
            "employee_id": "EMP_003",
            "employee_ssn": "456-78-9012",
            "current_age": 52.8,
            "current_tenure": 15.6,
            "level_id": 5,
            "age_band": "45-54",
            "tenure_band": "10-20",
            "annual_compensation": 125000.00,
            "employment_status": "active",
        },
    ]


@pytest.fixture
def clean_registry():
    """Fixture that clears the EventRegistry before and after each test."""
    from planalign_orchestrator.generators import EventRegistry

    EventRegistry.clear()
    yield EventRegistry
    EventRegistry.clear()


class MockEventGenerator:
    """
    Mock event generator for testing registry behavior.

    Not a real EventGenerator subclass - use for testing registration
    and lookup without ABC requirements.
    """

    event_type: str = "mock_event"
    execution_order: int = 100
    requires_hazard: bool = False
    supports_sql: bool = True
    supports_polars: bool = False

    def __init__(self, event_type: str = "mock_event"):
        self.event_type = event_type

    def generate_events(self, context) -> List[MockSimulationEvent]:
        """Generate mock events."""
        return [MockSimulationEvent(event_type=self.event_type)]

    def validate_event(self, event) -> "ValidationResult":
        """Validate mock event."""
        from planalign_orchestrator.generators.base import ValidationResult

        return ValidationResult(is_valid=True)


def create_mock_generator(
    event_type: str,
    execution_order: int = 100,
    requires_hazard: bool = False,
    supports_sql: bool = True,
    supports_polars: bool = False,
):
    """
    Factory function to create mock generator classes for testing.

    Args:
        event_type: Unique event type identifier
        execution_order: Processing order (lower = earlier)
        requires_hazard: Whether generator uses hazard tables
        supports_sql: Whether SQL mode is supported
        supports_polars: Whether Polars mode is supported

    Returns:
        A mock generator class (not instance)
    """

    class DynamicMockGenerator(MockEventGenerator):
        pass

    DynamicMockGenerator.event_type = event_type
    DynamicMockGenerator.execution_order = execution_order
    DynamicMockGenerator.requires_hazard = requires_hazard
    DynamicMockGenerator.supports_sql = supports_sql
    DynamicMockGenerator.supports_polars = supports_polars

    return DynamicMockGenerator
