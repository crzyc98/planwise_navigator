"""
Event Generator Tests (T050)

Tests for mode support flags and generator attributes.
Updated for SQL-only mode (E024 - Polars removal).
"""

import pytest
from unittest.mock import MagicMock

from planalign_orchestrator.generators.base import (
    EventContext,
    EventGenerator,
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


class TestModeSupport:
    """Tests for supports_sql attribute (SQL-only mode after E024)."""

    def test_default_mode_support(self, mock_context):
        """Default generator supports SQL."""

        @EventRegistry.register("default_mode")
        class DefaultModeGenerator(EventGenerator):
            event_type = "default_mode"
            execution_order = 50

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        gen = EventRegistry.get("default_mode")
        assert gen.supports_sql is True

    def test_sql_generator(self, mock_context):
        """Generator with explicit SQL support."""

        @EventRegistry.register("sql_gen")
        class SQLGenerator(EventGenerator):
            event_type = "sql_gen"
            execution_order = 50
            supports_sql = True

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        gen = EventRegistry.get("sql_gen")
        assert gen.supports_sql is True


class TestRegistryModeFiltering:
    """Tests for filtering generators by mode support."""

    def test_list_sql_supported(self, mock_context):
        """Can list generators that support SQL mode."""

        @EventRegistry.register("sql_gen")
        class SQLGen(EventGenerator):
            event_type = "sql_gen"
            execution_order = 10
            supports_sql = True

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        @EventRegistry.register("another_sql_gen")
        class AnotherSQLGen(EventGenerator):
            event_type = "another_sql_gen"
            execution_order = 20
            supports_sql = True

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        # Filter SQL-supported generators
        sql_generators = [
            EventRegistry.get(et)
            for et in EventRegistry.list_all()
            if EventRegistry.get(et).supports_sql
        ]
        sql_types = [g.event_type for g in sql_generators]

        assert "sql_gen" in sql_types
        assert "another_sql_gen" in sql_types

    def test_list_by_mode_sql(self, mock_context):
        """list_by_mode returns SQL generators."""

        @EventRegistry.register("sql_gen_1")
        class SQLGen1(EventGenerator):
            event_type = "sql_gen_1"
            execution_order = 10
            supports_sql = True

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        @EventRegistry.register("sql_gen_2")
        class SQLGen2(EventGenerator):
            event_type = "sql_gen_2"
            execution_order = 20
            supports_sql = True

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        sql_generators = EventRegistry.list_by_mode("sql", "test_scenario")
        sql_types = [g.event_type for g in sql_generators]

        assert "sql_gen_1" in sql_types
        assert "sql_gen_2" in sql_types


class TestGeneratorAttributes:
    """Tests for generator attribute inheritance."""

    def test_requires_hazard_attribute(self, mock_context):
        """requires_hazard attribute controls hazard calculation."""

        @EventRegistry.register("hazard_required")
        class HazardRequired(EventGenerator):
            event_type = "hazard_required"
            execution_order = 50
            requires_hazard = True

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        @EventRegistry.register("hazard_not_required")
        class HazardNotRequired(EventGenerator):
            event_type = "hazard_not_required"
            execution_order = 50
            requires_hazard = False

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        gen_with = EventRegistry.get("hazard_required")
        gen_without = EventRegistry.get("hazard_not_required")

        assert gen_with.requires_hazard is True
        assert gen_without.requires_hazard is False

    def test_execution_order_determines_sequence(self, mock_context):
        """execution_order determines generator sequence."""

        @EventRegistry.register("late_gen")
        class LateGen(EventGenerator):
            event_type = "late_gen"
            execution_order = 100

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        @EventRegistry.register("early_gen")
        class EarlyGen(EventGenerator):
            event_type = "early_gen"
            execution_order = 10

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        @EventRegistry.register("middle_gen")
        class MiddleGen(EventGenerator):
            event_type = "middle_gen"
            execution_order = 50

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        ordered = EventRegistry.list_ordered("test")
        types = [g.event_type for g in ordered]

        assert types == ["early_gen", "middle_gen", "late_gen"]
