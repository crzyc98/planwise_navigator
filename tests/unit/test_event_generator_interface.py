"""
Contract tests for EventGenerator interface.

Verifies that the EventGenerator abstract base class enforces
the required interface contract.
"""

import pytest
from abc import ABC
from planalign_orchestrator.generators.base import (
    EventGenerator,
    EventContext,
    ValidationResult,
    GeneratorMetrics,
)
from planalign_orchestrator.generators.registry import EventRegistry


@pytest.fixture(autouse=True)
def clean_registry():
    """Clear registry before and after each test."""
    EventRegistry.clear()
    yield
    EventRegistry.clear()


class TestEventGeneratorInterface:
    """Tests for EventGenerator ABC contract."""

    def test_cannot_instantiate_abstract_class(self):
        """Cannot instantiate EventGenerator directly."""
        with pytest.raises(TypeError, match="abstract"):
            EventGenerator()

    def test_must_define_event_type(self):
        """Subclass must define event_type class attribute."""
        with pytest.raises(TypeError, match="event_type"):

            class NoEventType(EventGenerator):
                # Missing event_type
                execution_order = 100

                def generate_events(self, context):
                    return []

                def validate_event(self, event):
                    return ValidationResult(is_valid=True)

    def test_must_define_execution_order(self):
        """Subclass must define execution_order class attribute."""
        with pytest.raises(TypeError, match="execution_order"):

            class NoExecutionOrder(EventGenerator):
                event_type = "test"
                # Missing execution_order

                def generate_events(self, context):
                    return []

                def validate_event(self, event):
                    return ValidationResult(is_valid=True)

    def test_must_implement_generate_events(self):
        """Subclass must implement generate_events method."""
        with pytest.raises(TypeError, match="abstract"):

            class NoGenerateEvents(EventGenerator):
                event_type = "test"
                execution_order = 100

                # Missing generate_events

                def validate_event(self, event):
                    return ValidationResult(is_valid=True)

            NoGenerateEvents()

    def test_must_implement_validate_event(self):
        """Subclass must implement validate_event method."""
        with pytest.raises(TypeError, match="abstract"):

            class NoValidateEvent(EventGenerator):
                event_type = "test"
                execution_order = 100

                def generate_events(self, context):
                    return []

                # Missing validate_event

            NoValidateEvent()

    def test_valid_generator_implementation(self):
        """Valid generator implementation can be instantiated."""

        class ValidGenerator(EventGenerator):
            event_type = "valid_test"
            execution_order = 50

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        generator = ValidGenerator()
        assert generator.event_type == "valid_test"
        assert generator.execution_order == 50

    def test_default_attributes(self):
        """Check default values for optional attributes."""

        class DefaultsGenerator(EventGenerator):
            event_type = "defaults_test"
            execution_order = 100

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        generator = DefaultsGenerator()
        assert generator.requires_hazard is False
        assert generator.supports_sql is True

    def test_override_optional_attributes(self):
        """Can override optional attributes."""

        class CustomGenerator(EventGenerator):
            event_type = "custom_test"
            execution_order = 100
            requires_hazard = True
            supports_sql = False

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        generator = CustomGenerator()
        assert generator.requires_hazard is True
        assert generator.supports_sql is False


class TestEventGeneratorCalculateHazard:
    """Tests for calculate_hazard method."""

    def test_calculate_hazard_raises_if_required(self):
        """calculate_hazard raises NotImplementedError if requires_hazard=True."""

        class HazardRequiredGenerator(EventGenerator):
            event_type = "hazard_required"
            execution_order = 100
            requires_hazard = True

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        generator = HazardRequiredGenerator()
        with pytest.raises(NotImplementedError, match="requires_hazard=True"):
            generator.calculate_hazard("EMP_001", 2025, None)

    def test_calculate_hazard_returns_zero_if_not_required(self):
        """calculate_hazard returns 0.0 if requires_hazard=False."""

        class NoHazardGenerator(EventGenerator):
            event_type = "no_hazard"
            execution_order = 100
            requires_hazard = False

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        generator = NoHazardGenerator()
        assert generator.calculate_hazard("EMP_001", 2025, None) == 0.0


class TestGeneratorMetrics:
    """Tests for GeneratorMetrics dataclass."""

    def test_metrics_creation(self):
        """Can create GeneratorMetrics with all fields."""
        metrics = GeneratorMetrics(
            event_type="test_event",
            event_count=42,
            execution_time_ms=123.45,
            mode="sql",
            year=2025,
            scenario_id="test_scenario",
        )
        assert metrics.event_type == "test_event"
        assert metrics.event_count == 42
        assert metrics.execution_time_ms == 123.45
        assert metrics.mode == "sql"
        assert metrics.year == 2025
        assert metrics.scenario_id == "test_scenario"

    def test_to_log_dict(self):
        """to_log_dict() returns serializable dictionary."""
        metrics = GeneratorMetrics(
            event_type="test_event",
            event_count=100,
            execution_time_ms=50.123456,
            mode="polars",
            year=2025,
            scenario_id="test",
        )
        log_dict = metrics.to_log_dict()
        assert log_dict["event_type"] == "test_event"
        assert log_dict["event_count"] == 100
        assert log_dict["execution_time_ms"] == 50.12  # Rounded
        assert log_dict["mode"] == "polars"


class TestEventContext:
    """Tests for EventContext dataclass."""

    def test_context_creation(self):
        """Can create EventContext with required fields."""
        from unittest.mock import MagicMock

        context = EventContext(
            simulation_year=2025,
            scenario_id="test",
            plan_design_id="default",
            random_seed=42,
            dbt_runner=MagicMock(),
            db_manager=MagicMock(),
            config=MagicMock(),
        )
        assert context.simulation_year == 2025
        assert context.scenario_id == "test"
        assert context.random_seed == 42
        assert context.dbt_vars == {}

    def test_context_with_dbt_vars(self):
        """Can create EventContext with dbt_vars."""
        from unittest.mock import MagicMock

        context = EventContext(
            simulation_year=2025,
            scenario_id="test",
            plan_design_id="default",
            random_seed=42,
            dbt_runner=MagicMock(),
            db_manager=MagicMock(),
            config=MagicMock(),
            dbt_vars={"custom_var": "value"},
        )
        assert context.dbt_vars == {"custom_var": "value"}


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_valid_result(self):
        """Can create valid ValidationResult."""
        result = ValidationResult(is_valid=True)
        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_invalid_result_with_errors(self):
        """Can create invalid ValidationResult with errors."""
        result = ValidationResult(
            is_valid=False,
            errors=["Missing employee_id", "Invalid date"],
        )
        assert result.is_valid is False
        assert len(result.errors) == 2
        assert "Missing employee_id" in result.errors

    def test_valid_result_with_warnings(self):
        """Can create valid ValidationResult with warnings."""
        result = ValidationResult(
            is_valid=True,
            warnings=["Compensation seems high"],
        )
        assert result.is_valid is True
        assert len(result.warnings) == 1
