"""Unit tests for workforce event integration with unified event model."""

import pytest
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from config.events import (
    SimulationEvent,
    WorkforceEventFactory,
    HirePayload,
    PromotionPayload,
    TerminationPayload,
    MeritPayload,
)


class TestWorkforceEventPayloads:
    """Test workforce event payload classes."""

    def test_hire_payload_creation(self):
        """Test creating a hire payload with all fields."""
        payload = HirePayload(
            hire_date=date(2025, 1, 15),
            department="Engineering",
            job_level=3,
            annual_compensation=Decimal("120000.50"),
            plan_id="401k-standard"
        )

        assert payload.event_type == "hire"
        assert payload.hire_date == date(2025, 1, 15)
        assert payload.department == "Engineering"
        assert payload.job_level == 3
        assert payload.annual_compensation == Decimal("120000.500000")  # 6 decimal places
        assert payload.plan_id == "401k-standard"

    def test_hire_payload_without_plan_id(self):
        """Test hire payload with optional plan_id field."""
        payload = HirePayload(
            hire_date=date(2025, 1, 15),
            department="Sales",
            job_level=2,
            annual_compensation=Decimal("85000")
        )

        assert payload.plan_id is None

    def test_promotion_payload_creation(self):
        """Test creating a promotion payload."""
        payload = PromotionPayload(
            new_job_level=4,
            new_annual_compensation=Decimal("140000.75"),
            effective_date=date(2025, 4, 1),
            plan_id="401k-enhanced"
        )

        assert payload.event_type == "promotion"
        assert payload.new_job_level == 4
        assert payload.new_annual_compensation == Decimal("140000.750000")
        assert payload.effective_date == date(2025, 4, 1)

    def test_termination_payload_creation(self):
        """Test creating a termination payload with all reason types."""
        reasons = ["voluntary", "involuntary", "retirement", "death", "disability"]

        for reason in reasons:
            payload = TerminationPayload(
                termination_reason=reason,
                final_pay_date=date(2025, 6, 30)
            )

            assert payload.event_type == "termination"
            assert payload.termination_reason == reason
            assert payload.final_pay_date == date(2025, 6, 30)

    def test_merit_payload_creation(self):
        """Test creating a merit payload with percentage validation."""
        payload = MeritPayload(
            new_compensation=Decimal("125000"),
            merit_percentage=Decimal("0.0425")  # 4.25%
        )

        assert payload.event_type == "merit"
        assert payload.new_compensation == Decimal("125000.000000")
        assert payload.merit_percentage == Decimal("0.0425")

    def test_payload_validation_errors(self):
        """Test validation errors for invalid payloads."""
        # Invalid job level
        with pytest.raises(ValueError):
            HirePayload(
                hire_date=date(2025, 1, 1),
                department="IT",
                job_level=11,  # Max is 10
                annual_compensation=Decimal("100000")
            )

        # Negative compensation
        with pytest.raises(ValueError):
            MeritPayload(
                new_compensation=Decimal("-50000"),
                merit_percentage=Decimal("0.03")
            )

        # Merit percentage > 100%
        with pytest.raises(ValueError):
            MeritPayload(
                new_compensation=Decimal("100000"),
                merit_percentage=Decimal("1.5")  # 150%
            )


class TestWorkforceEventFactory:
    """Test WorkforceEventFactory methods."""

    def test_create_hire_event(self):
        """Test creating a complete hire event."""
        event = WorkforceEventFactory.create_hire_event(
            employee_id="EMP-12345",
            scenario_id="baseline-2025",
            plan_design_id="standard-401k",
            hire_date=date(2025, 2, 1),
            department="Finance",
            job_level=3,
            annual_compensation=Decimal("95000"),
            plan_id="401k-standard"
        )

        # Verify core event fields
        assert isinstance(event.event_id, UUID)
        assert event.employee_id == "EMP-12345"
        assert event.scenario_id == "baseline-2025"
        assert event.plan_design_id == "standard-401k"
        assert event.effective_date == date(2025, 2, 1)
        assert event.source_system == "workforce_simulation"

        # Verify payload
        assert isinstance(event.payload, HirePayload)
        assert event.payload.event_type == "hire"
        assert event.payload.department == "Finance"
        assert event.payload.job_level == 3
        assert event.payload.annual_compensation == Decimal("95000.000000")
        assert event.payload.plan_id == "401k-standard"

    def test_create_promotion_event(self):
        """Test creating a promotion event."""
        event = WorkforceEventFactory.create_promotion_event(
            employee_id="EMP-54321",
            scenario_id="growth-scenario",
            plan_design_id="enhanced-401k",
            effective_date=date(2025, 7, 1),
            new_job_level=5,
            new_annual_compensation=Decimal("175000.50")
        )

        assert event.employee_id == "EMP-54321"
        assert isinstance(event.payload, PromotionPayload)
        assert event.payload.new_job_level == 5
        assert event.payload.new_annual_compensation == Decimal("175000.500000")

    def test_create_termination_event(self):
        """Test creating a termination event."""
        event = WorkforceEventFactory.create_termination_event(
            employee_id="EMP-99999",
            scenario_id="downsizing",
            plan_design_id="standard-401k",
            effective_date=date(2025, 9, 30),
            termination_reason="involuntary",
            final_pay_date=date(2025, 10, 15)
        )

        assert isinstance(event.payload, TerminationPayload)
        assert event.payload.termination_reason == "involuntary"
        assert event.payload.final_pay_date == date(2025, 10, 15)

    def test_create_merit_event(self):
        """Test creating a merit event."""
        event = WorkforceEventFactory.create_merit_event(
            employee_id="EMP-11111",
            scenario_id="merit-cycle-2025",
            plan_design_id="standard-401k",
            effective_date=date(2025, 3, 1),
            new_compensation=Decimal("105000"),
            merit_percentage=Decimal("0.05")  # 5%
        )

        assert isinstance(event.payload, MeritPayload)
        assert event.payload.new_compensation == Decimal("105000.000000")
        assert event.payload.merit_percentage == Decimal("0.0500")

    def test_event_serialization(self):
        """Test that events can be serialized and deserialized."""
        event = WorkforceEventFactory.create_hire_event(
            employee_id="EMP-SER-001",
            scenario_id="test-scenario",
            plan_design_id="test-plan",
            hire_date=date(2025, 1, 1),
            department="QA",
            job_level=2,
            annual_compensation=Decimal("80000")
        )

        # Serialize to dict
        event_dict = event.model_dump(mode='json')

        # Verify structure
        assert 'event_id' in event_dict
        assert 'payload' in event_dict
        assert event_dict['payload']['event_type'] == 'hire'

        # Deserialize back
        restored_event = SimulationEvent.model_validate(event_dict)

        assert restored_event.employee_id == event.employee_id
        assert isinstance(restored_event.payload, HirePayload)
        assert restored_event.payload.department == "QA"


class TestDiscriminatedUnion:
    """Test discriminated union behavior."""

    def test_discriminator_routing(self):
        """Test that discriminator correctly routes to payload types."""
        # Create different event types
        hire_event = WorkforceEventFactory.create_hire_event(
            employee_id="EMP-001",
            scenario_id="test",
            plan_design_id="test",
            hire_date=date(2025, 1, 1),
            department="Test",
            job_level=1,
            annual_compensation=Decimal("50000")
        )

        promotion_event = WorkforceEventFactory.create_promotion_event(
            employee_id="EMP-001",
            scenario_id="test",
            plan_design_id="test",
            effective_date=date(2025, 6, 1),
            new_job_level=2,
            new_annual_compensation=Decimal("60000")
        )

        # Verify correct payload types
        assert isinstance(hire_event.payload, HirePayload)
        assert isinstance(promotion_event.payload, PromotionPayload)

        # Verify discriminator field
        assert hire_event.payload.event_type == "hire"
        assert promotion_event.payload.event_type == "promotion"

    def test_invalid_discriminator(self):
        """Test that invalid discriminator values are rejected."""
        with pytest.raises(ValueError):
            SimulationEvent.model_validate({
                "employee_id": "EMP-001",
                "effective_date": "2025-01-01",
                "scenario_id": "test",
                "plan_design_id": "test",
                "source_system": "test",
                "payload": {
                    "event_type": "invalid_type",  # Not a valid discriminator
                    "some_field": "value"
                }
            })


class TestBackwardCompatibility:
    """Test backward compatibility with existing workforce simulation."""

    def test_event_factory_create_event(self):
        """Test that EventFactory.create_event works with workforce payloads."""
        from config.events import EventFactory

        event_data = {
            "employee_id": "EMP-LEGACY-001",
            "effective_date": date(2025, 1, 1),
            "scenario_id": "legacy-test",
            "plan_design_id": "legacy-plan",
            "source_system": "legacy-system",
            "payload": {
                "event_type": "hire",
                "hire_date": date(2025, 1, 1),
                "department": "Legacy Dept",
                "job_level": 3,
                "annual_compensation": Decimal("100000")
            }
        }

        event = EventFactory.create_event(event_data)

        assert event.employee_id == "EMP-LEGACY-001"
        assert isinstance(event.payload, HirePayload)
        assert event.payload.department == "Legacy Dept"

    def test_legacy_alias(self):
        """Test that LegacySimulationEvent alias works."""
        from config.events import LegacySimulationEvent

        # Should be the same class
        assert LegacySimulationEvent is SimulationEvent

    def test_field_name_consistency(self):
        """Test that field names match legacy expectations."""
        # Legacy uses these exact event types
        legacy_event_types = ["hire", "promotion", "termination", "merit"]

        # Test each can be created
        for event_type in legacy_event_types:
            if event_type == "hire":
                payload = HirePayload(
                    hire_date=date(2025, 1, 1),
                    department="Test",
                    job_level=1,
                    annual_compensation=Decimal("50000")
                )
            elif event_type == "promotion":
                payload = PromotionPayload(
                    new_job_level=2,
                    new_annual_compensation=Decimal("60000"),
                    effective_date=date(2025, 1, 1)
                )
            elif event_type == "termination":
                payload = TerminationPayload(
                    termination_reason="voluntary",
                    final_pay_date=date(2025, 1, 1)
                )
            else:  # merit
                payload = MeritPayload(
                    new_compensation=Decimal("55000"),
                    merit_percentage=Decimal("0.05")
                )

            assert payload.event_type == event_type
