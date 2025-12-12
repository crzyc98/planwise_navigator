"""
Event Generator Tests (T050)

Tests for mode support flags and generator attributes.
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
    """Tests for supports_sql and supports_polars attributes (T050)."""

    def test_default_mode_support(self, mock_context):
        """Default generator supports SQL but not Polars."""

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
        assert gen.supports_polars is False

    def test_sql_only_generator(self, mock_context):
        """Generator can be SQL-only."""

        @EventRegistry.register("sql_only")
        class SQLOnlyGenerator(EventGenerator):
            event_type = "sql_only"
            execution_order = 50
            supports_sql = True
            supports_polars = False

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        gen = EventRegistry.get("sql_only")
        assert gen.supports_sql is True
        assert gen.supports_polars is False

    def test_polars_only_generator(self, mock_context):
        """Generator can be Polars-only."""

        @EventRegistry.register("polars_only")
        class PolarsOnlyGenerator(EventGenerator):
            event_type = "polars_only"
            execution_order = 50
            supports_sql = False
            supports_polars = True

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        gen = EventRegistry.get("polars_only")
        assert gen.supports_sql is False
        assert gen.supports_polars is True

    def test_dual_mode_generator(self, mock_context):
        """Generator can support both modes."""

        @EventRegistry.register("dual_mode")
        class DualModeGenerator(EventGenerator):
            event_type = "dual_mode"
            execution_order = 50
            supports_sql = True
            supports_polars = True

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        gen = EventRegistry.get("dual_mode")
        assert gen.supports_sql is True
        assert gen.supports_polars is True


class TestRegistryModeFiltering:
    """Tests for filtering generators by mode support."""

    def test_list_sql_supported(self, mock_context):
        """Can list generators that support SQL mode."""

        @EventRegistry.register("sql_gen")
        class SQLGen(EventGenerator):
            event_type = "sql_gen"
            execution_order = 10
            supports_sql = True
            supports_polars = False

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        @EventRegistry.register("polars_gen")
        class PolarsGen(EventGenerator):
            event_type = "polars_gen"
            execution_order = 20
            supports_sql = False
            supports_polars = True

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        @EventRegistry.register("both_gen")
        class BothGen(EventGenerator):
            event_type = "both_gen"
            execution_order = 30
            supports_sql = True
            supports_polars = True

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
        assert "both_gen" in sql_types
        assert "polars_gen" not in sql_types

    def test_list_polars_supported(self, mock_context):
        """Can list generators that support Polars mode."""

        @EventRegistry.register("sql_only_p")
        class SQLOnlyP(EventGenerator):
            event_type = "sql_only_p"
            execution_order = 10
            supports_sql = True
            supports_polars = False

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        @EventRegistry.register("polars_only_p")
        class PolarsOnlyP(EventGenerator):
            event_type = "polars_only_p"
            execution_order = 20
            supports_sql = False
            supports_polars = True

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        @EventRegistry.register("both_p")
        class BothP(EventGenerator):
            event_type = "both_p"
            execution_order = 30
            supports_sql = True
            supports_polars = True

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        # Filter Polars-supported generators
        polars_generators = [
            EventRegistry.get(et)
            for et in EventRegistry.list_all()
            if EventRegistry.get(et).supports_polars
        ]
        polars_types = [g.event_type for g in polars_generators]

        assert "polars_only_p" in polars_types
        assert "both_p" in polars_types
        assert "sql_only_p" not in polars_types


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
