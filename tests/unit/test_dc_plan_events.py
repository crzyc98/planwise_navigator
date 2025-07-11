# filename: tests/unit/test_dc_plan_events.py
"""Unit tests for DC Plan Event payloads and factory methods."""

import pytest
from datetime import date
from decimal import Decimal
from typing import Dict
from pydantic import ValidationError

from config.events import (
    SimulationEvent, DCPlanEventFactory,
    EligibilityPayload, EnrollmentPayload, ContributionPayload,
    VestingPayload
)


class TestEligibilityPayload:
    """Test cases for EligibilityPayload"""

    def test_eligibility_payload_creation(self):
        """Test creating valid eligibility payload"""
        payload = EligibilityPayload(
            plan_id="PLAN_DC_401K",
            eligible=True,
            eligibility_date=date(2025, 1, 1),
            reason="age_and_service"
        )

        assert payload.event_type == "eligibility"
        assert payload.plan_id == "PLAN_DC_401K"
        assert payload.eligible is True
        assert payload.eligibility_date == date(2025, 1, 1)
        assert payload.reason == "age_and_service"

    def test_eligibility_reason_enum_validation(self):
        """Test validation of eligibility reason enum values"""
        valid_reasons = ["age_and_service", "immediate", "hours_requirement", "rehire"]

        for reason in valid_reasons:
            payload = EligibilityPayload(
                plan_id="PLAN_DC_401K",
                eligible=True,
                eligibility_date=date(2025, 1, 1),
                reason=reason
            )
            assert payload.reason == reason

    def test_eligibility_invalid_reason(self):
        """Test validation error for invalid eligibility reason"""
        with pytest.raises(ValidationError):
            EligibilityPayload(
                plan_id="PLAN_DC_401K",
                eligible=True,
                eligibility_date=date(2025, 1, 1),
                reason="invalid_reason"
            )

    def test_eligibility_empty_plan_id(self):
        """Test validation error for empty plan_id"""
        with pytest.raises(ValidationError, match="String should have at least 1 character"):
            EligibilityPayload(
                plan_id="",
                eligible=True,
                eligibility_date=date(2025, 1, 1),
                reason="immediate"
            )


class TestEnrollmentPayload:
    """Test cases for EnrollmentPayload"""

    def test_enrollment_payload_creation(self):
        """Test creating valid enrollment payload"""
        payload = EnrollmentPayload(
            plan_id="PLAN_DC_401K",
            enrollment_date=date(2025, 1, 1),
            pre_tax_contribution_rate=Decimal('0.06'),
            roth_contribution_rate=Decimal('0.04'),
            after_tax_contribution_rate=Decimal('0.02'),
            auto_enrollment=True,
            opt_out_window_expires=date(2025, 2, 1)
        )

        assert payload.event_type == "enrollment"
        assert payload.plan_id == "PLAN_DC_401K"
        assert payload.enrollment_date == date(2025, 1, 1)
        assert payload.pre_tax_contribution_rate == Decimal('0.0600')
        assert payload.roth_contribution_rate == Decimal('0.0400')
        assert payload.after_tax_contribution_rate == Decimal('0.0200')
        assert payload.auto_enrollment is True
        assert payload.opt_out_window_expires == date(2025, 2, 1)

    def test_enrollment_default_values(self):
        """Test default values for optional fields"""
        payload = EnrollmentPayload(
            plan_id="PLAN_DC_401K",
            enrollment_date=date(2025, 1, 1),
            pre_tax_contribution_rate=Decimal('0.06'),
            roth_contribution_rate=Decimal('0.04')
        )

        assert payload.after_tax_contribution_rate == Decimal('0')
        assert payload.auto_enrollment is False
        assert payload.opt_out_window_expires is None

    def test_enrollment_rate_precision_validation(self):
        """Test contribution rate precision validation"""
        # Test that rates with more than 4 decimal places are rejected
        with pytest.raises(ValidationError, match="Decimal input should have no more than 4 decimal places"):
            EnrollmentPayload(
                plan_id="PLAN_DC_401K",
                enrollment_date=date(2025, 1, 1),
                pre_tax_contribution_rate=Decimal('0.123456789'),
                roth_contribution_rate=Decimal('0.04')
            )

    def test_enrollment_rate_precision_acceptance(self):
        """Test that rates with valid precision are accepted and properly quantized"""
        payload = EnrollmentPayload(
            plan_id="PLAN_DC_401K",
            enrollment_date=date(2025, 1, 1),
            pre_tax_contribution_rate=Decimal('0.1235'),
            roth_contribution_rate=Decimal('0.0988')
        )

        # Should be quantized to 4 decimal places
        assert payload.pre_tax_contribution_rate == Decimal('0.1235')
        assert payload.roth_contribution_rate == Decimal('0.0988')

    def test_enrollment_rate_bounds_validation(self):
        """Test contribution rate bounds validation"""
        # Test upper bound
        with pytest.raises(ValidationError):
            EnrollmentPayload(
                plan_id="PLAN_DC_401K",
                enrollment_date=date(2025, 1, 1),
                pre_tax_contribution_rate=Decimal('1.1'),  # Over 100%
                roth_contribution_rate=Decimal('0.04')
            )

        # Test lower bound
        with pytest.raises(ValidationError):
            EnrollmentPayload(
                plan_id="PLAN_DC_401K",
                enrollment_date=date(2025, 1, 1),
                pre_tax_contribution_rate=Decimal('-0.01'),  # Negative
                roth_contribution_rate=Decimal('0.04')
            )


class TestContributionPayload:
    """Test cases for ContributionPayload"""

    def test_contribution_payload_creation(self):
        """Test creating valid contribution payload"""
        payload = ContributionPayload(
            plan_id="PLAN_DC_401K",
            source="employee_pre_tax",
            amount=Decimal('1250.50'),
            pay_period_end=date(2025, 1, 15),
            contribution_date=date(2025, 1, 20),
            ytd_amount=Decimal('2501.00'),
            payroll_id="PR_2025_01_15",
            irs_limit_applied=True,
            inferred_value=False
        )

        assert payload.event_type == "contribution"
        assert payload.plan_id == "PLAN_DC_401K"
        assert payload.source == "employee_pre_tax"
        assert payload.amount == Decimal('1250.500000')
        assert payload.pay_period_end == date(2025, 1, 15)
        assert payload.contribution_date == date(2025, 1, 20)
        assert payload.ytd_amount == Decimal('2501.000000')
        assert payload.payroll_id == "PR_2025_01_15"
        assert payload.irs_limit_applied is True
        assert payload.inferred_value is False

    def test_contribution_source_enum_validation(self):
        """Test validation of contribution source enum values"""
        valid_sources = [
            "employee_pre_tax", "employee_roth", "employee_after_tax", "employee_catch_up",
            "employer_match", "employer_match_true_up", "employer_nonelective",
            "employer_profit_sharing", "forfeiture_allocation"
        ]

        for source in valid_sources:
            payload = ContributionPayload(
                plan_id="PLAN_DC_401K",
                source=source,
                amount=Decimal('1000.00'),
                pay_period_end=date(2025, 1, 15),
                contribution_date=date(2025, 1, 20),
                ytd_amount=Decimal('1000.00'),
                payroll_id="PR_001"
            )
            assert payload.source == source

    def test_contribution_amount_precision_rejection(self):
        """Test that amounts with more than 6 decimal places are rejected"""
        with pytest.raises(ValidationError, match="Decimal input should have no more than 6 decimal places"):
            ContributionPayload(
                plan_id="PLAN_DC_401K",
                source="employee_pre_tax",
                amount=Decimal('1250.123456789'),
                pay_period_end=date(2025, 1, 15),
                contribution_date=date(2025, 1, 20),
                ytd_amount=Decimal('2501.00'),
                payroll_id="PR_001"
            )

    def test_contribution_amount_precision_acceptance(self):
        """Test that amounts with valid precision are accepted and properly quantized"""
        payload = ContributionPayload(
            plan_id="PLAN_DC_401K",
            source="employee_pre_tax",
            amount=Decimal('1250.123457'),
            pay_period_end=date(2025, 1, 15),
            contribution_date=date(2025, 1, 20),
            ytd_amount=Decimal('2501.987654'),
            payroll_id="PR_001"
        )

        # Should be quantized to 6 decimal places
        assert payload.amount == Decimal('1250.123457')
        assert payload.ytd_amount == Decimal('2501.987654')

    def test_contribution_amount_validation(self):
        """Test contribution amount validation"""
        # Test zero amount should fail
        with pytest.raises(ValidationError):
            ContributionPayload(
                plan_id="PLAN_DC_401K",
                source="employee_pre_tax",
                amount=Decimal('0'),
                pay_period_end=date(2025, 1, 15),
                contribution_date=date(2025, 1, 20),
                ytd_amount=Decimal('1000.00'),
                payroll_id="PR_001"
            )

        # Test negative amount should fail
        with pytest.raises(ValidationError):
            ContributionPayload(
                plan_id="PLAN_DC_401K",
                source="employee_pre_tax",
                amount=Decimal('-100.00'),
                pay_period_end=date(2025, 1, 15),
                contribution_date=date(2025, 1, 20),
                ytd_amount=Decimal('1000.00'),
                payroll_id="PR_001"
            )



class TestVestingPayload:
    """Test cases for VestingPayload"""

    def test_vesting_payload_creation(self):
        """Test creating valid vesting payload"""
        source_balances = {
            "employer_match": Decimal('10000.00'),
            "employer_nonelective": Decimal('5000.00'),
            "employer_profit_sharing": Decimal('3000.00')
        }

        payload = VestingPayload(
            plan_id="PLAN_DC_401K",
            vested_percentage=Decimal('0.60'),
            source_balances_vested=source_balances,
            vesting_schedule_type="graded",
            service_computation_date=date(2025, 12, 31),
            service_credited_hours=2080,
            service_period_end_date=date(2025, 12, 31)
        )

        assert payload.event_type == "vesting"
        assert payload.plan_id == "PLAN_DC_401K"
        assert payload.vested_percentage == Decimal('0.6000')
        assert payload.source_balances_vested["employer_match"] == Decimal('10000.000000')
        assert payload.source_balances_vested["employer_nonelective"] == Decimal('5000.000000')
        assert payload.source_balances_vested["employer_profit_sharing"] == Decimal('3000.000000')
        assert payload.vesting_schedule_type == "graded"
        assert payload.service_computation_date == date(2025, 12, 31)
        assert payload.service_credited_hours == 2080
        assert payload.service_period_end_date == date(2025, 12, 31)

    def test_vesting_schedule_type_validation(self):
        """Test vesting schedule type enum validation"""
        valid_types = ["graded", "cliff", "immediate"]

        for schedule_type in valid_types:
            payload = VestingPayload(
                plan_id="PLAN_DC_401K",
                vested_percentage=Decimal('1.0'),
                source_balances_vested={"employer_match": Decimal('1000.00')},
                vesting_schedule_type=schedule_type,
                service_computation_date=date(2025, 12, 31),
                service_credited_hours=2080,
                service_period_end_date=date(2025, 12, 31)
            )
            assert payload.vesting_schedule_type == schedule_type

    def test_vested_percentage_bounds(self):
        """Test vested percentage bounds validation"""
        # Test upper bound
        with pytest.raises(ValidationError):
            VestingPayload(
                plan_id="PLAN_DC_401K",
                vested_percentage=Decimal('1.1'),  # Over 100%
                source_balances_vested={"employer_match": Decimal('1000.00')},
                vesting_schedule_type="immediate",
                service_computation_date=date(2025, 12, 31),
                service_credited_hours=2080,
                service_period_end_date=date(2025, 12, 31)
            )

        # Test lower bound
        with pytest.raises(ValidationError):
            VestingPayload(
                plan_id="PLAN_DC_401K",
                vested_percentage=Decimal('-0.01'),  # Negative
                source_balances_vested={"employer_match": Decimal('1000.00')},
                vesting_schedule_type="immediate",
                service_computation_date=date(2025, 12, 31),
                service_credited_hours=2080,
                service_period_end_date=date(2025, 12, 31)
            )

    def test_service_hours_validation(self):
        """Test service hours validation"""
        # Test negative hours should fail
        with pytest.raises(ValidationError):
            VestingPayload(
                plan_id="PLAN_DC_401K",
                vested_percentage=Decimal('1.0'),
                source_balances_vested={"employer_match": Decimal('1000.00')},
                vesting_schedule_type="immediate",
                service_computation_date=date(2025, 12, 31),
                service_credited_hours=-100,
                service_period_end_date=date(2025, 12, 31)
            )


class TestDCPlanEventFactory:
    """Test cases for DCPlanEventFactory"""

    def test_create_eligibility_event(self):
        """Test creating eligibility event via factory"""
        event = DCPlanEventFactory.create_eligibility_event(
            employee_id="EMP001",
            plan_id="PLAN_DC_401K",
            scenario_id="SCENARIO_001",
            plan_design_id="DESIGN_001",
            eligible=True,
            eligibility_date=date(2025, 1, 1),
            reason="age_and_service"
        )

        assert isinstance(event, SimulationEvent)
        assert event.employee_id == "EMP001"
        assert event.scenario_id == "SCENARIO_001"
        assert event.plan_design_id == "DESIGN_001"
        assert event.effective_date == date(2025, 1, 1)
        assert event.source_system == "dc_plan_administration"
        assert isinstance(event.payload, EligibilityPayload)
        assert event.payload.plan_id == "PLAN_DC_401K"
        assert event.payload.eligible is True

    def test_create_enrollment_event(self):
        """Test creating enrollment event via factory"""
        event = DCPlanEventFactory.create_enrollment_event(
            employee_id="EMP001",
            plan_id="PLAN_DC_401K",
            scenario_id="SCENARIO_001",
            plan_design_id="DESIGN_001",
            enrollment_date=date(2025, 1, 15),
            pre_tax_contribution_rate=Decimal('0.06'),
            roth_contribution_rate=Decimal('0.04'),
            auto_enrollment=True
        )

        assert isinstance(event, SimulationEvent)
        assert event.employee_id == "EMP001"
        assert event.effective_date == date(2025, 1, 15)
        assert event.source_system == "dc_plan_administration"
        assert isinstance(event.payload, EnrollmentPayload)
        assert event.payload.auto_enrollment is True

    def test_create_contribution_event(self):
        """Test creating contribution event via factory"""
        event = DCPlanEventFactory.create_contribution_event(
            employee_id="EMP001",
            plan_id="PLAN_DC_401K",
            scenario_id="SCENARIO_001",
            plan_design_id="DESIGN_001",
            source="employee_pre_tax",
            amount=Decimal('1250.50'),
            pay_period_end=date(2025, 1, 15),
            contribution_date=date(2025, 1, 20),
            ytd_amount=Decimal('2501.00'),
            payroll_id="PR_2025_01_15"
        )

        assert isinstance(event, SimulationEvent)
        assert event.employee_id == "EMP001"
        assert event.effective_date == date(2025, 1, 20)
        assert event.source_system == "dc_plan_administration"
        assert isinstance(event.payload, ContributionPayload)
        assert event.payload.source == "employee_pre_tax"


    def test_create_vesting_event(self):
        """Test creating vesting event via factory"""
        source_balances = {
            "employer_match": Decimal('10000.00'),
            "employer_nonelective": Decimal('5000.00'),
            "employer_profit_sharing": Decimal('3000.00')
        }

        event = DCPlanEventFactory.create_vesting_event(
            employee_id="EMP001",
            plan_id="PLAN_DC_401K",
            scenario_id="SCENARIO_001",
            plan_design_id="DESIGN_001",
            vested_percentage=Decimal('0.60'),
            source_balances_vested=source_balances,
            vesting_schedule_type="graded",
            service_computation_date=date(2025, 12, 31),
            service_credited_hours=2080,
            service_period_end_date=date(2025, 12, 31)
        )

        assert isinstance(event, SimulationEvent)
        assert event.employee_id == "EMP001"
        assert event.effective_date == date(2025, 12, 31)
        assert event.source_system == "dc_plan_administration"
        assert isinstance(event.payload, VestingPayload)
        assert event.payload.vesting_schedule_type == "graded"


class TestDiscriminatedUnionIntegration:
    """Test integration with SimulationEvent discriminated union"""

    def test_all_dc_plan_payloads_in_union(self):
        """Test that all 4 core DC plan payloads work with SimulationEvent discriminated union"""

        # Test eligibility event
        eligibility_event = SimulationEvent(
            employee_id="EMP001",
            scenario_id="SCENARIO_001",
            plan_design_id="DESIGN_001",
            effective_date=date(2025, 1, 1),
            source_system="dc_plan_administration",
            payload={
                "event_type": "eligibility",
                "plan_id": "PLAN_DC_401K",
                "eligible": True,
                "eligibility_date": date(2025, 1, 1),
                "reason": "immediate"
            }
        )
        assert isinstance(eligibility_event.payload, EligibilityPayload)

        # Test enrollment event
        enrollment_event = SimulationEvent(
            employee_id="EMP001",
            scenario_id="SCENARIO_001",
            plan_design_id="DESIGN_001",
            effective_date=date(2025, 1, 15),
            source_system="dc_plan_administration",
            payload={
                "event_type": "enrollment",
                "plan_id": "PLAN_DC_401K",
                "enrollment_date": date(2025, 1, 15),
                "pre_tax_contribution_rate": Decimal('0.06'),
                "roth_contribution_rate": Decimal('0.04')
            }
        )
        assert isinstance(enrollment_event.payload, EnrollmentPayload)

        # Test contribution event
        contribution_event = SimulationEvent(
            employee_id="EMP001",
            scenario_id="SCENARIO_001",
            plan_design_id="DESIGN_001",
            effective_date=date(2025, 1, 20),
            source_system="dc_plan_administration",
            payload={
                "event_type": "contribution",
                "plan_id": "PLAN_DC_401K",
                "source": "employee_pre_tax",
                "amount": Decimal('1250.50'),
                "pay_period_end": date(2025, 1, 15),
                "contribution_date": date(2025, 1, 20),
                "ytd_amount": Decimal('2501.00'),
                "payroll_id": "PR_001"
            }
        )
        assert isinstance(contribution_event.payload, ContributionPayload)

        # Test vesting event
        vesting_event = SimulationEvent(
            employee_id="EMP001",
            scenario_id="SCENARIO_001",
            plan_design_id="DESIGN_001",
            effective_date=date(2025, 12, 31),
            source_system="dc_plan_administration",
            payload={
                "event_type": "vesting",
                "plan_id": "PLAN_DC_401K",
                "vested_percentage": Decimal('0.60'),
                "source_balances_vested": {
                    "employer_match": Decimal('10000.00'),
                    "employer_nonelective": Decimal('5000.00'),
                    "employer_profit_sharing": Decimal('3000.00')
                },
                "vesting_schedule_type": "graded",
                "service_computation_date": date(2025, 12, 31),
                "service_credited_hours": 2080,
                "service_period_end_date": date(2025, 12, 31)
            }
        )
        assert isinstance(vesting_event.payload, VestingPayload)

    def test_serialization_deserialization(self):
        """Test serialization and deserialization of DC plan events"""
        # Create an event via factory
        original_event = DCPlanEventFactory.create_contribution_event(
            employee_id="EMP001",
            plan_id="PLAN_DC_401K",
            scenario_id="SCENARIO_001",
            plan_design_id="DESIGN_001",
            source="employee_pre_tax",
            amount=Decimal('1250.50'),
            pay_period_end=date(2025, 1, 15),
            contribution_date=date(2025, 1, 20),
            ytd_amount=Decimal('2501.00'),
            payroll_id="PR_2025_01_15"
        )

        # Serialize to dict
        event_dict = original_event.model_dump()

        # Deserialize back to event
        reconstructed_event = SimulationEvent.model_validate(event_dict)

        # Verify reconstruction
        assert reconstructed_event.employee_id == original_event.employee_id
        assert reconstructed_event.effective_date == original_event.effective_date
        assert isinstance(reconstructed_event.payload, ContributionPayload)
        assert reconstructed_event.payload.source == "employee_pre_tax"
        assert reconstructed_event.payload.amount == Decimal('1250.500000')


class TestPerformance:
    """Performance tests for DC plan events"""

    def test_dc_plan_event_creation_performance(self):
        """Test performance of creating DC plan events"""
        import time

        start_time = time.time()

        events = []
        for i in range(1000):
            event = DCPlanEventFactory.create_contribution_event(
                employee_id=f"EMP{i:06d}",
                plan_id="PLAN_DC_401K",
                scenario_id="SCENARIO_001",
                plan_design_id="DESIGN_001",
                source="employee_pre_tax",
                amount=Decimal('1250.50'),
                pay_period_end=date(2025, 1, 15),
                contribution_date=date(2025, 1, 20),
                ytd_amount=Decimal('2501.00'),
                payroll_id=f"PR_{i:06d}"
            )
            events.append(event)

        end_time = time.time()
        creation_time = end_time - start_time

        # Should create 1000 events in less than 1 second
        assert creation_time < 1.0
        assert len(events) == 1000

        # Verify all events are properly created
        for event in events[:10]:  # Check first 10
            assert isinstance(event.payload, ContributionPayload)
            assert event.source_system == "dc_plan_administration"
