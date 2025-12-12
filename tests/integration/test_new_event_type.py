"""
Integration test for new event type registration.

Tests that a new event type can be created, registered, and
generates events correctly through the abstraction layer.
"""

import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

from planalign_orchestrator.generators.base import (
    EventGenerator,
    EventContext,
    ValidationResult,
)
from planalign_orchestrator.generators.registry import EventRegistry


@pytest.fixture(autouse=True)
def clean_registry():
    """Clear registry before and after each test."""
    EventRegistry.clear()
    yield
    EventRegistry.clear()


@pytest.fixture
def mock_context():
    """Create mock EventContext for testing."""
    return EventContext(
        simulation_year=2025,
        scenario_id="test_scenario",
        plan_design_id="default",
        random_seed=42,
        dbt_runner=MagicMock(),
        db_manager=MagicMock(),
        config=MagicMock(),
    )


class MockSimulationEvent:
    """Mock SimulationEvent for testing without full Pydantic model."""

    def __init__(
        self,
        event_id: str = None,
        employee_id: str = "EMP_001",
        scenario_id: str = "test_scenario",
        plan_design_id: str = "default",
        effective_date: date = None,
        event_type: str = "test_event",
    ):
        self.event_id = event_id or str(uuid4())
        self.employee_id = employee_id
        self.scenario_id = scenario_id
        self.plan_design_id = plan_design_id
        self.effective_date = effective_date or date(2025, 6, 1)
        self.event_type = event_type


class TestNewEventTypeRegistration:
    """Tests for registering and using a new event type."""

    def test_register_and_instantiate_new_event_type(self, mock_context):
        """Can register a new event type and get its generator."""

        @EventRegistry.register("sabbatical")
        class SabbaticalEventGenerator(EventGenerator):
            event_type = "sabbatical"
            execution_order = 45

            def generate_events(self, context: EventContext):
                # Simple implementation that generates one event
                return [
                    MockSimulationEvent(
                        employee_id="EMP_001",
                        scenario_id=context.scenario_id,
                        event_type="sabbatical",
                    )
                ]

            def validate_event(self, event) -> ValidationResult:
                if not event.employee_id:
                    return ValidationResult(
                        is_valid=False, errors=["Missing employee_id"]
                    )
                return ValidationResult(is_valid=True)

        # Verify registration
        assert "sabbatical" in EventRegistry.list_all()

        # Get generator and verify it works
        generator = EventRegistry.get("sabbatical")
        assert generator.event_type == "sabbatical"
        assert generator.execution_order == 45

        # Generate events
        events = generator.generate_events(mock_context)
        assert len(events) == 1
        assert events[0].event_type == "sabbatical"

    def test_new_event_type_appears_in_ordered_list(self, mock_context):
        """New event type appears in correct position in ordered list."""

        @EventRegistry.register("early_event")
        class EarlyEventGenerator(EventGenerator):
            event_type = "early_event"
            execution_order = 10

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        @EventRegistry.register("late_event")
        class LateEventGenerator(EventGenerator):
            event_type = "late_event"
            execution_order = 90

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        @EventRegistry.register("middle_event")
        class MiddleEventGenerator(EventGenerator):
            event_type = "middle_event"
            execution_order = 50

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        ordered = EventRegistry.list_ordered("test_scenario")
        event_types = [g.event_type for g in ordered]

        assert event_types == ["early_event", "middle_event", "late_event"]

    def test_generate_events_with_metrics(self, mock_context):
        """generate_with_metrics returns events and structured metrics."""

        @EventRegistry.register("metrics_test")
        class MetricsTestGenerator(EventGenerator):
            event_type = "metrics_test"
            execution_order = 50

            def generate_events(self, context):
                return [
                    MockSimulationEvent(event_type="metrics_test"),
                    MockSimulationEvent(event_type="metrics_test"),
                    MockSimulationEvent(event_type="metrics_test"),
                ]

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        generator = EventRegistry.get("metrics_test")
        events, metrics = generator.generate_with_metrics(mock_context, mode="sql")

        assert len(events) == 3
        assert metrics.event_type == "metrics_test"
        assert metrics.event_count == 3
        assert metrics.mode == "sql"
        assert metrics.year == 2025
        assert metrics.scenario_id == "test_scenario"
        assert metrics.execution_time_ms >= 0

    def test_validation_of_generated_events(self, mock_context):
        """Generated events can be validated by the generator."""

        @EventRegistry.register("validated_event")
        class ValidatedEventGenerator(EventGenerator):
            event_type = "validated_event"
            execution_order = 50

            def generate_events(self, context):
                return [
                    MockSimulationEvent(
                        employee_id="EMP_001",
                        event_type="validated_event",
                    ),
                    MockSimulationEvent(
                        employee_id="",  # Invalid - empty
                        event_type="validated_event",
                    ),
                ]

            def validate_event(self, event) -> ValidationResult:
                if not event.employee_id:
                    return ValidationResult(
                        is_valid=False,
                        errors=["employee_id cannot be empty"],
                    )
                return ValidationResult(is_valid=True)

        generator = EventRegistry.get("validated_event")
        events = generator.generate_events(mock_context)

        # First event should be valid
        result1 = generator.validate_event(events[0])
        assert result1.is_valid is True

        # Second event should be invalid
        result2 = generator.validate_event(events[1])
        assert result2.is_valid is False
        assert "employee_id cannot be empty" in result2.errors


class TestNewEventTypeWithDisable:
    """Tests for disabling new event types per scenario."""

    def test_disabled_event_type_excluded_from_generation(self, mock_context):
        """Disabled event types don't appear in list_ordered."""

        @EventRegistry.register("disabled_test")
        class DisabledTestGenerator(EventGenerator):
            event_type = "disabled_test"
            execution_order = 50

            def generate_events(self, context):
                return [MockSimulationEvent(event_type="disabled_test")]

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        # Initially included
        ordered = EventRegistry.list_ordered("test_scenario")
        assert any(g.event_type == "disabled_test" for g in ordered)

        # After disable
        EventRegistry.disable("disabled_test", "test_scenario")
        ordered = EventRegistry.list_ordered("test_scenario")
        assert not any(g.event_type == "disabled_test" for g in ordered)

        # Still available in other scenarios
        ordered_other = EventRegistry.list_ordered("other_scenario")
        assert any(g.event_type == "disabled_test" for g in ordered_other)


class TestNewEventTypeErrorHandling:
    """Tests for error handling when creating new event types."""

    def test_missing_event_type_clear_error(self):
        """Clear error message when event_type is missing."""
        with pytest.raises(TypeError) as excinfo:

            class MissingEventType(EventGenerator):
                # Missing event_type
                execution_order = 50

                def generate_events(self, context):
                    return []

                def validate_event(self, event):
                    return ValidationResult(is_valid=True)

        assert "event_type" in str(excinfo.value)

    def test_missing_execution_order_clear_error(self):
        """Clear error message when execution_order is missing."""
        with pytest.raises(TypeError) as excinfo:

            class MissingOrder(EventGenerator):
                event_type = "missing_order"
                # Missing execution_order

                def generate_events(self, context):
                    return []

                def validate_event(self, event):
                    return ValidationResult(is_valid=True)

        assert "execution_order" in str(excinfo.value)

    def test_unregistered_event_type_clear_error(self):
        """Clear error message when getting unregistered event type."""
        with pytest.raises(KeyError) as excinfo:
            EventRegistry.get("nonexistent_event")

        error_msg = str(excinfo.value)
        assert "not registered" in error_msg
        assert "nonexistent_event" in error_msg
