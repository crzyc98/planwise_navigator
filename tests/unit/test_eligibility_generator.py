"""
Eligibility Event Generator Tests (Feature 086)

Tests for EligibilityEventGenerator class attributes, interface compliance,
and registry integration.
"""

import pytest
from unittest.mock import MagicMock

from planalign_orchestrator.generators.base import (
    EventContext,
    ValidationResult,
)
from planalign_orchestrator.generators.registry import EventRegistry
from config.constants import EVENT_ELIGIBILITY


@pytest.fixture(autouse=True)
def clean_registry():
    """Isolate registry state between tests."""
    EventRegistry.clear()
    yield
    EventRegistry.clear()


@pytest.fixture
def generator():
    """Fresh EligibilityEventGenerator instance with clean registry."""
    from planalign_orchestrator.generators.eligibility import EligibilityEventGenerator

    EventRegistry.register(EVENT_ELIGIBILITY)(EligibilityEventGenerator)
    return EligibilityEventGenerator()


@pytest.fixture
def mock_context():
    return EventContext(
        simulation_year=2025,
        scenario_id="test",
        plan_design_id="default",
        random_seed=42,
        dbt_runner=MagicMock(),
        db_manager=MagicMock(),
        config=MagicMock(),
    )


@pytest.fixture
def valid_event():
    payload = MagicMock()
    payload.event_type = EVENT_ELIGIBILITY
    payload.eligibility_date = "2025-03-15"
    event = MagicMock()
    event.payload = payload
    return event


@pytest.fixture
def wrong_type_event():
    payload = MagicMock()
    payload.event_type = "enrollment"
    payload.eligibility_date = "2025-03-15"
    event = MagicMock()
    event.payload = payload
    return event


@pytest.fixture
def missing_date_event():
    payload = MagicMock(spec=[])
    payload.event_type = EVENT_ELIGIBILITY
    event = MagicMock()
    event.payload = payload
    return event


@pytest.mark.fast
class TestEligibilityGeneratorAttributes:
    def test_event_type(self, generator):
        assert generator.event_type == "eligibility"

    def test_execution_order(self, generator):
        assert generator.execution_order == 25

    def test_execution_order_between_hire_and_promotion(self, generator):
        assert generator.execution_order > 20  # after hire
        assert generator.execution_order < 30  # before promotion
        assert generator.execution_order < 50  # before enrollment

    def test_supports_sql(self, generator):
        assert generator.supports_sql is True

    def test_requires_hazard_false(self, generator):
        assert generator.requires_hazard is False

    def test_dbt_models_listed(self, generator):
        assert "int_eligibility_events" in generator.dbt_models
        assert "int_plan_eligibility_determination" in generator.dbt_models


@pytest.mark.fast
class TestGenerateEvents:
    def test_returns_empty_list(self, generator, mock_context):
        result = generator.generate_events(mock_context)
        assert result == []

    def test_returns_list_type(self, generator, mock_context):
        result = generator.generate_events(mock_context)
        assert isinstance(result, list)


@pytest.mark.fast
class TestValidateEvent:
    def test_valid_event_passes(self, generator, valid_event):
        result = generator.validate_event(valid_event)
        assert result.is_valid is True
        assert result.errors == []

    def test_wrong_event_type_fails(self, generator, wrong_type_event):
        result = generator.validate_event(wrong_type_event)
        assert result.is_valid is False
        assert any("eligibility" in e for e in result.errors)

    def test_missing_eligibility_date_fails(self, generator, missing_date_event):
        result = generator.validate_event(missing_date_event)
        assert result.is_valid is False
        assert any("eligibility_date" in e for e in result.errors)


@pytest.mark.fast
class TestRegistryIntegration:
    def test_generator_registered(self, generator):
        registered = EventRegistry.list_all()
        assert EVENT_ELIGIBILITY in registered

    def test_registry_lookup_returns_generator(self, generator):
        from planalign_orchestrator.generators.eligibility import (
            EligibilityEventGenerator,
        )

        gen = EventRegistry.get(EVENT_ELIGIBILITY)
        assert isinstance(gen, EligibilityEventGenerator)
