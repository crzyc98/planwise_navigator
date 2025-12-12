"""
Unit tests for EventRegistry.

Tests the centralized event type registration and lookup functionality.
"""

import pytest
from planalign_orchestrator.generators.registry import EventRegistry
from planalign_orchestrator.generators.base import EventGenerator, EventContext, ValidationResult


@pytest.fixture(autouse=True)
def clean_registry():
    """Clear registry before and after each test."""
    EventRegistry.clear()
    yield
    EventRegistry.clear()


class TestEventRegistryRegistration:
    """Tests for EventRegistry.register()"""

    def test_register_valid_event_type(self):
        """Can register a generator with valid event_type."""

        @EventRegistry.register("test_event")
        class TestGenerator(EventGenerator):
            event_type = "test_event"
            execution_order = 100

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        assert "test_event" in EventRegistry.list_all()

    def test_register_duplicate_raises_error(self):
        """Cannot register same event_type twice."""

        @EventRegistry.register("duplicate")
        class FirstGenerator(EventGenerator):
            event_type = "duplicate"
            execution_order = 100

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        with pytest.raises(ValueError, match="already registered"):

            @EventRegistry.register("duplicate")
            class SecondGenerator(EventGenerator):
                event_type = "duplicate"
                execution_order = 200

                def generate_events(self, context):
                    return []

                def validate_event(self, event):
                    return ValidationResult(is_valid=True)

    def test_register_empty_event_type_raises_error(self):
        """Cannot register empty event_type."""
        with pytest.raises(ValueError, match="cannot be empty"):

            @EventRegistry.register("")
            class EmptyGenerator(EventGenerator):
                event_type = ""
                execution_order = 100

                def generate_events(self, context):
                    return []

                def validate_event(self, event):
                    return ValidationResult(is_valid=True)

    def test_register_uppercase_event_type_raises_error(self):
        """Cannot register event_type starting with uppercase."""
        with pytest.raises(ValueError, match="must start with lowercase"):

            @EventRegistry.register("InvalidEvent")
            class UppercaseGenerator(EventGenerator):
                event_type = "InvalidEvent"
                execution_order = 100

                def generate_events(self, context):
                    return []

                def validate_event(self, event):
                    return ValidationResult(is_valid=True)


class TestEventRegistryLookup:
    """Tests for EventRegistry.get() and related lookup methods."""

    def test_get_registered_generator(self):
        """Can retrieve registered generator by event_type."""

        @EventRegistry.register("lookup_test")
        class LookupGenerator(EventGenerator):
            event_type = "lookup_test"
            execution_order = 50

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        generator = EventRegistry.get("lookup_test")
        assert generator.event_type == "lookup_test"
        assert generator.execution_order == 50

    def test_get_unregistered_raises_key_error(self):
        """Getting unregistered event_type raises KeyError with helpful message."""
        with pytest.raises(KeyError, match="not registered"):
            EventRegistry.get("nonexistent")

    def test_get_returns_cached_instance(self):
        """Multiple get() calls return same instance."""

        @EventRegistry.register("cached")
        class CachedGenerator(EventGenerator):
            event_type = "cached"
            execution_order = 100

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        instance1 = EventRegistry.get("cached")
        instance2 = EventRegistry.get("cached")
        assert instance1 is instance2

    def test_list_all_returns_sorted(self):
        """list_all() returns sorted list of event types."""

        @EventRegistry.register("zebra")
        class ZebraGenerator(EventGenerator):
            event_type = "zebra"
            execution_order = 100

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        @EventRegistry.register("alpha")
        class AlphaGenerator(EventGenerator):
            event_type = "alpha"
            execution_order = 200

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        assert EventRegistry.list_all() == ["alpha", "zebra"]


class TestEventRegistryScenarioDisable:
    """Tests for scenario-specific enable/disable."""

    def test_disable_event_type_for_scenario(self):
        """Can disable event_type for specific scenario."""

        @EventRegistry.register("disableable")
        class DisableableGenerator(EventGenerator):
            event_type = "disableable"
            execution_order = 100

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        # Initially enabled
        assert "disableable" in EventRegistry.list_enabled("test_scenario")

        # Disable for scenario
        EventRegistry.disable("disableable", "test_scenario")
        assert "disableable" not in EventRegistry.list_enabled("test_scenario")

        # Still enabled for other scenarios
        assert "disableable" in EventRegistry.list_enabled("other_scenario")

    def test_enable_after_disable(self):
        """Can re-enable event_type after disabling."""

        @EventRegistry.register("reenableable")
        class ReenableableGenerator(EventGenerator):
            event_type = "reenableable"
            execution_order = 100

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        EventRegistry.disable("reenableable", "test_scenario")
        assert "reenableable" not in EventRegistry.list_enabled("test_scenario")

        EventRegistry.enable("reenableable", "test_scenario")
        assert "reenableable" in EventRegistry.list_enabled("test_scenario")

    def test_is_enabled(self):
        """is_enabled() returns correct status."""

        @EventRegistry.register("check_enabled")
        class CheckEnabledGenerator(EventGenerator):
            event_type = "check_enabled"
            execution_order = 100

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        assert EventRegistry.is_enabled("check_enabled", "test_scenario")
        assert not EventRegistry.is_enabled("nonexistent", "test_scenario")

        EventRegistry.disable("check_enabled", "test_scenario")
        assert not EventRegistry.is_enabled("check_enabled", "test_scenario")


class TestEventRegistryOrdering:
    """Tests for execution_order based ordering."""

    def test_list_ordered_returns_by_execution_order(self):
        """list_ordered() returns generators sorted by execution_order."""

        @EventRegistry.register("order_last")
        class LastGenerator(EventGenerator):
            event_type = "order_last"
            execution_order = 100

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        @EventRegistry.register("order_first")
        class FirstGenerator(EventGenerator):
            event_type = "order_first"
            execution_order = 10

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        @EventRegistry.register("order_middle")
        class MiddleGenerator(EventGenerator):
            event_type = "order_middle"
            execution_order = 50

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        ordered = EventRegistry.list_ordered("test_scenario")
        assert len(ordered) == 3
        assert ordered[0].event_type == "order_first"
        assert ordered[1].event_type == "order_middle"
        assert ordered[2].event_type == "order_last"

    def test_list_ordered_excludes_disabled(self):
        """list_ordered() excludes disabled event types."""

        @EventRegistry.register("ordered_enabled")
        class EnabledGenerator(EventGenerator):
            event_type = "ordered_enabled"
            execution_order = 10

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        @EventRegistry.register("ordered_disabled")
        class DisabledGenerator(EventGenerator):
            event_type = "ordered_disabled"
            execution_order = 20

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        EventRegistry.disable("ordered_disabled", "test_scenario")

        ordered = EventRegistry.list_ordered("test_scenario")
        assert len(ordered) == 1
        assert ordered[0].event_type == "ordered_enabled"


class TestEventRegistryUtilities:
    """Tests for utility methods."""

    def test_count(self):
        """count() returns correct count."""
        assert EventRegistry.count() == 0

        @EventRegistry.register("counted")
        class CountedGenerator(EventGenerator):
            event_type = "counted"
            execution_order = 100

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        assert EventRegistry.count() == 1

    def test_clear(self):
        """clear() removes all registrations."""

        @EventRegistry.register("clearable")
        class ClearableGenerator(EventGenerator):
            event_type = "clearable"
            execution_order = 100

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        EventRegistry.disable("clearable", "test")
        assert EventRegistry.count() == 1

        EventRegistry.clear()

        assert EventRegistry.count() == 0
        assert EventRegistry.list_all() == []

    def test_summary(self):
        """summary() returns human-readable string."""

        @EventRegistry.register("summarized")
        class SummarizedGenerator(EventGenerator):
            event_type = "summarized"
            execution_order = 42

            def generate_events(self, context):
                return []

            def validate_event(self, event):
                return ValidationResult(is_valid=True)

        summary = EventRegistry.summary()
        assert "EventRegistry:" in summary
        assert "summarized" in summary
        assert "order=42" in summary
