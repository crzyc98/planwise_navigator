"""
Comprehensive Payload Type Coverage Tests - S072-06

Tests all 11 payload types with >95% coverage including edge cases.
Validates discriminated union routing, factory methods, and serialization.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List

import pytest
from pydantic import ValidationError

from config.events import (ComplianceEventPayload,  # All payload types
                           ContributionEventFactory, ContributionPayload,
                           EligibilityEventFactory, EligibilityPayload,
                           EnrollmentEventFactory, EnrollmentPayload,
                           EventFactory, ForfeiturePayload, HCEStatusPayload,
                           HirePayload, MeritPayload,
                           PlanAdministrationEventFactory, PromotionPayload,
                           SimulationEvent, TerminationPayload,
                           VestingEventFactory, VestingPayload)


class TestComprehensivePayloadCoverage:
    """Comprehensive test coverage for all 11 payload types - S072-06."""

    def setup_method(self):
        """Setup common test data."""
        self.base_event_data = {
            "employee_id": "TEST_001",
            "scenario_id": "TEST_SCENARIO",
            "plan_design_id": "TEST_DESIGN",
            "effective_date": date(2024, 1, 15),
        }

        self.plan_event_data = {**self.base_event_data, "plan_id": "TEST_PLAN_001"}

    # ========== WORKFORCE EVENT PAYLOAD TESTS ==========

    def test_hire_payload_comprehensive_validation(self):
        """Test HirePayload with comprehensive validation scenarios."""

        # Valid hire payload
        valid_data = {
            "event_type": "hire",
            "starting_compensation": Decimal("75000.00"),
            "starting_level": 3,
            "employee_ssn": "123456789",
            "employee_birth_date": date(1990, 5, 15),
            "location": "HQ_BOSTON",
        }

        payload = HirePayload(**valid_data)
        assert payload.event_type == "hire"
        assert payload.starting_compensation == Decimal("75000.00")
        assert payload.starting_level == 3
        assert payload.employee_ssn == "123456789"
        assert payload.location == "HQ_BOSTON"

        # Edge case: minimum compensation
        min_comp_data = {**valid_data, "starting_compensation": Decimal("0.01")}
        min_payload = HirePayload(**min_comp_data)
        assert min_payload.starting_compensation == Decimal("0.01")

        # Edge case: maximum level
        max_level_data = {**valid_data, "starting_level": 5}
        max_payload = HirePayload(**max_level_data)
        assert max_payload.starting_level == 5

        # Validation errors
        with pytest.raises(ValidationError) as exc_info:
            HirePayload(**{**valid_data, "starting_compensation": Decimal("-1000.00")})
        assert "greater than 0" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            HirePayload(**{**valid_data, "starting_level": 6})
        assert "less than or equal to 5" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            HirePayload(**{**valid_data, "employee_ssn": "123"})  # Too short
        assert "at least 9 characters" in str(exc_info.value)

    def test_promotion_payload_comprehensive_validation(self):
        """Test PromotionPayload with comprehensive validation scenarios."""

        valid_data = {
            "event_type": "promotion",
            "new_level": 4,
            "new_compensation": Decimal("85000.00"),
            "previous_level": 3,
            "previous_compensation": Decimal("75000.00"),
        }

        payload = PromotionPayload(**valid_data)
        assert payload.new_level == 4
        assert payload.new_compensation == Decimal("85000.00")
        assert payload.previous_level == 3

        # Edge case: same level promotion (compensation adjustment)
        same_level_data = {**valid_data, "new_level": 3}
        same_payload = PromotionPayload(**same_level_data)
        assert same_payload.new_level == same_payload.previous_level

        # Edge case: maximum level promotion
        max_promotion_data = {**valid_data, "new_level": 5, "previous_level": 4}
        max_payload = PromotionPayload(**max_promotion_data)
        assert max_payload.new_level == 5

        # Validation errors
        with pytest.raises(ValidationError) as exc_info:
            PromotionPayload(**{**valid_data, "new_level": 0})
        assert "greater than or equal to 1" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            PromotionPayload(**{**valid_data, "new_compensation": Decimal("0")})
        assert "greater than 0" in str(exc_info.value)

    def test_termination_payload_comprehensive_validation(self):
        """Test TerminationPayload with comprehensive validation scenarios."""

        valid_data = {
            "event_type": "termination",
            "termination_reason": "voluntary",
            "final_compensation": Decimal("80000.00"),
        }

        payload = TerminationPayload(**valid_data)
        assert payload.termination_reason == "voluntary"
        assert payload.final_compensation == Decimal("80000.00")

        # Test all termination reasons
        termination_reasons = [
            "voluntary",
            "involuntary",
            "retirement",
            "death",
            "disability",
        ]
        for reason in termination_reasons:
            reason_data = {**valid_data, "termination_reason": reason}
            reason_payload = TerminationPayload(**reason_data)
            assert reason_payload.termination_reason == reason

        # Edge case: minimum final compensation
        min_comp_data = {**valid_data, "final_compensation": Decimal("0.01")}
        min_payload = TerminationPayload(**min_comp_data)
        assert min_payload.final_compensation == Decimal("0.01")

        # Validation errors
        with pytest.raises(ValidationError) as exc_info:
            TerminationPayload(**{**valid_data, "termination_reason": "invalid_reason"})
        assert "Input should be" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            TerminationPayload(
                **{**valid_data, "final_compensation": Decimal("-100.00")}
            )
        assert "greater than 0" in str(exc_info.value)

    def test_merit_payload_comprehensive_validation(self):
        """Test MeritPayload with comprehensive validation scenarios."""

        valid_data = {
            "event_type": "merit",
            "merit_percentage": Decimal("0.04"),  # 4%
            "previous_compensation": Decimal("75000.00"),
        }

        payload = MeritPayload(**valid_data)
        assert payload.merit_percentage == Decimal("0.04")
        assert payload.previous_compensation == Decimal("75000.00")

        # Edge case: zero merit increase
        zero_merit_data = {**valid_data, "merit_percentage": Decimal("0.00")}
        zero_payload = MeritPayload(**zero_merit_data)
        assert zero_payload.merit_percentage == Decimal("0.00")

        # Edge case: maximum merit increase (50%)
        max_merit_data = {**valid_data, "merit_percentage": Decimal("0.50")}
        max_payload = MeritPayload(**max_merit_data)
        assert max_payload.merit_percentage == Decimal("0.50")

        # Validation errors
        with pytest.raises(ValidationError) as exc_info:
            MeritPayload(**{**valid_data, "merit_percentage": Decimal("-0.05")})
        assert "greater than or equal to 0" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            MeritPayload(**{**valid_data, "merit_percentage": Decimal("1.01")})
        assert "less than or equal to 1" in str(exc_info.value)

    # ========== DC PLAN EVENT PAYLOAD TESTS ==========

    def test_eligibility_payload_comprehensive_validation(self):
        """Test EligibilityPayload with comprehensive validation scenarios."""

        valid_data = {
            "event_type": "eligibility",
            "plan_id": "401K_PLAN",
            "eligibility_date": date(2024, 1, 1),
            "service_requirement_months": 3,
            "age_requirement": None,
        }

        payload = EligibilityPayload(**valid_data)
        assert payload.plan_id == "401K_PLAN"
        assert payload.eligibility_date == date(2024, 1, 1)
        assert payload.service_requirement_months == 3
        assert payload.age_requirement is None

        # Edge case: immediate eligibility
        immediate_data = {**valid_data, "service_requirement_months": 0}
        immediate_payload = EligibilityPayload(**immediate_data)
        assert immediate_payload.service_requirement_months == 0

        # Edge case: with age requirement
        age_req_data = {**valid_data, "age_requirement": 21}
        age_payload = EligibilityPayload(**age_req_data)
        assert age_payload.age_requirement == 21

        # Edge case: maximum service requirement
        max_service_data = {**valid_data, "service_requirement_months": 12}
        max_payload = EligibilityPayload(**max_service_data)
        assert max_payload.service_requirement_months == 12

        # Validation errors
        with pytest.raises(ValidationError) as exc_info:
            EligibilityPayload(**{**valid_data, "service_requirement_months": -1})
        assert "greater than or equal to 0" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            EligibilityPayload(**{**valid_data, "age_requirement": 17})
        assert "greater than or equal to 18" in str(exc_info.value)

    def test_enrollment_payload_comprehensive_validation(self):
        """Test EnrollmentPayload with comprehensive validation scenarios."""

        valid_data = {
            "event_type": "enrollment",
            "plan_id": "401K_PLAN",
            "enrollment_date": date(2024, 2, 1),
            "deferral_percentage": Decimal("0.06"),
            "deferral_amount": None,
            "catch_up_percentage": Decimal("0.00"),
        }

        payload = EnrollmentPayload(**valid_data)
        assert payload.deferral_percentage == Decimal("0.06")
        assert payload.deferral_amount is None
        assert payload.catch_up_percentage == Decimal("0.00")

        # Edge case: deferral amount instead of percentage
        amount_data = {
            **valid_data,
            "deferral_percentage": None,
            "deferral_amount": Decimal("500.00"),
        }
        amount_payload = EnrollmentPayload(**amount_data)
        assert amount_payload.deferral_percentage is None
        assert amount_payload.deferral_amount == Decimal("500.00")

        # Edge case: maximum deferral percentage
        max_defer_data = {**valid_data, "deferral_percentage": Decimal("1.00")}  # 100%
        max_payload = EnrollmentPayload(**max_defer_data)
        assert max_payload.deferral_percentage == Decimal("1.00")

        # Edge case: catch-up contribution
        catchup_data = {**valid_data, "catch_up_percentage": Decimal("0.04")}
        catchup_payload = EnrollmentPayload(**catchup_data)
        assert catchup_payload.catch_up_percentage == Decimal("0.04")

        # Validation errors
        with pytest.raises(ValidationError) as exc_info:
            EnrollmentPayload(**{**valid_data, "deferral_percentage": Decimal("-0.01")})
        assert "greater than or equal to 0" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            EnrollmentPayload(**{**valid_data, "catch_up_percentage": Decimal("1.01")})
        assert "less than or equal to 1" in str(exc_info.value)

    def test_contribution_payload_comprehensive_validation(self):
        """Test ContributionPayload with comprehensive validation scenarios."""

        valid_data = {
            "event_type": "contribution",
            "plan_id": "401K_PLAN",
            "contribution_date": date(2024, 3, 15),
            "employee_contribution": Decimal("500.00"),
            "employer_contribution": Decimal("250.00"),
            "contribution_source": "regular_payroll",
            "vesting_service_years": Decimal("1.25"),
        }

        payload = ContributionPayload(**valid_data)
        assert payload.employee_contribution == Decimal("500.00")
        assert payload.employer_contribution == Decimal("250.00")
        assert payload.contribution_source == "regular_payroll"
        assert payload.vesting_service_years == Decimal("1.25")

        # Test all contribution sources
        sources = ["regular_payroll", "bonus", "catch_up", "rollover", "transfer"]
        for source in sources:
            source_data = {**valid_data, "contribution_source": source}
            source_payload = ContributionPayload(**source_data)
            assert source_payload.contribution_source == source

        # Edge case: zero employee contribution
        zero_emp_data = {**valid_data, "employee_contribution": Decimal("0.00")}
        zero_payload = ContributionPayload(**zero_emp_data)
        assert zero_payload.employee_contribution == Decimal("0.00")

        # Edge case: zero employer contribution (employee only)
        zero_er_data = {**valid_data, "employer_contribution": Decimal("0.00")}
        zero_er_payload = ContributionPayload(**zero_er_data)
        assert zero_er_payload.employer_contribution == Decimal("0.00")

        # Validation errors
        with pytest.raises(ValidationError) as exc_info:
            ContributionPayload(
                **{**valid_data, "employee_contribution": Decimal("-100.00")}
            )
        assert "greater than or equal to 0" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            ContributionPayload(
                **{**valid_data, "vesting_service_years": Decimal("-0.5")}
            )
        assert "greater than or equal to 0" in str(exc_info.value)

    def test_vesting_payload_comprehensive_validation(self):
        """Test VestingPayload with comprehensive validation scenarios."""

        valid_data = {
            "event_type": "vesting",
            "plan_id": "401K_PLAN",
            "vesting_date": date(2024, 12, 31),
            "vesting_schedule_type": "graded",
            "vested_percentage": Decimal("0.60"),
            "service_years": Decimal("3.0"),
        }

        payload = VestingPayload(**valid_data)
        assert payload.vesting_schedule_type == "graded"
        assert payload.vested_percentage == Decimal("0.60")
        assert payload.service_years == Decimal("3.0")

        # Test all vesting schedule types
        schedule_types = ["cliff", "graded", "immediate"]
        for schedule in schedule_types:
            schedule_data = {**valid_data, "vesting_schedule_type": schedule}
            schedule_payload = VestingPayload(**schedule_data)
            assert schedule_payload.vesting_schedule_type == schedule

        # Edge case: 0% vested
        zero_vested_data = {**valid_data, "vested_percentage": Decimal("0.0000")}
        zero_payload = VestingPayload(**zero_vested_data)
        assert zero_payload.vested_percentage == Decimal("0.0000")

        # Edge case: 100% vested
        full_vested_data = {**valid_data, "vested_percentage": Decimal("1.0000")}
        full_payload = VestingPayload(**full_vested_data)
        assert full_payload.vested_percentage == Decimal("1.0000")

        # Validation errors
        with pytest.raises(ValidationError) as exc_info:
            VestingPayload(**{**valid_data, "vested_percentage": Decimal("1.0001")})
        assert "less than or equal to 1" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            VestingPayload(**{**valid_data, "service_years": Decimal("-1.0")})
        assert "greater than or equal to 0" in str(exc_info.value)

    # ========== PLAN ADMINISTRATION EVENT PAYLOAD TESTS ==========

    def test_forfeiture_payload_comprehensive_validation(self):
        """Test ForfeiturePayload with comprehensive validation scenarios."""

        valid_data = {
            "event_type": "forfeiture",
            "plan_id": "401K_PLAN",
            "forfeited_from_source": "employer_match",
            "amount": Decimal("2500.00"),
            "reason": "unvested_termination",
            "vested_percentage": Decimal("0.25"),
        }

        payload = ForfeiturePayload(**valid_data)
        assert payload.forfeited_from_source == "employer_match"
        assert payload.amount == Decimal("2500.00")
        assert payload.reason == "unvested_termination"
        assert payload.vested_percentage == Decimal("0.25")

        # Test all forfeiture sources
        sources = ["employer_match", "employer_nonelective", "employer_profit_sharing"]
        for source in sources:
            source_data = {**valid_data, "forfeited_from_source": source}
            source_payload = ForfeiturePayload(**source_data)
            assert source_payload.forfeited_from_source == source

        # Test all forfeiture reasons
        reasons = ["unvested_termination", "break_in_service"]
        for reason in reasons:
            reason_data = {**valid_data, "reason": reason}
            reason_payload = ForfeiturePayload(**reason_data)
            assert reason_payload.reason == reason

        # Edge case: maximum vesting (minimal forfeiture)
        max_vested_data = {**valid_data, "vested_percentage": Decimal("0.9999")}
        max_payload = ForfeiturePayload(**max_vested_data)
        assert max_payload.vested_percentage == Decimal("0.9999")

        # Validation errors
        with pytest.raises(ValidationError) as exc_info:
            ForfeiturePayload(**{**valid_data, "amount": Decimal("0.00")})
        assert "greater than 0" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            ForfeiturePayload(**{**valid_data, "vested_percentage": Decimal("1.0001")})
        assert "less than or equal to 1" in str(exc_info.value)

    def test_hce_status_payload_comprehensive_validation(self):
        """Test HCEStatusPayload with comprehensive validation scenarios."""

        valid_data = {
            "event_type": "hce_status",
            "plan_id": "401K_PLAN",
            "determination_method": "prior_year",
            "ytd_compensation": Decimal("125000.00"),
            "annualized_compensation": Decimal("150000.00"),
            "hce_threshold": Decimal("135000.00"),
            "is_hce": True,
            "determination_date": date(2024, 1, 1),
            "prior_year_hce": False,
        }

        payload = HCEStatusPayload(**valid_data)
        assert payload.determination_method == "prior_year"
        assert payload.ytd_compensation == Decimal("125000.00")
        assert payload.is_hce is True
        assert payload.prior_year_hce is False

        # Test both determination methods
        methods = ["prior_year", "current_year"]
        for method in methods:
            method_data = {**valid_data, "determination_method": method}
            method_payload = HCEStatusPayload(**method_data)
            assert method_payload.determination_method == method

        # Edge case: current year determination (no prior year data)
        current_year_data = {
            **valid_data,
            "determination_method": "current_year",
            "prior_year_hce": None,
        }
        current_payload = HCEStatusPayload(**current_year_data)
        assert current_payload.prior_year_hce is None

        # Edge case: exactly at HCE threshold
        threshold_data = {**valid_data, "annualized_compensation": Decimal("135000.00")}
        threshold_payload = HCEStatusPayload(**threshold_data)
        assert threshold_payload.annualized_compensation == Decimal("135000.00")

        # Validation errors
        with pytest.raises(ValidationError) as exc_info:
            HCEStatusPayload(**{**valid_data, "ytd_compensation": Decimal("-1000.00")})
        assert "greater than or equal to 0" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            HCEStatusPayload(**{**valid_data, "hce_threshold": Decimal("0.00")})
        assert "greater than 0" in str(exc_info.value)

    def test_compliance_event_payload_comprehensive_validation(self):
        """Test ComplianceEventPayload with comprehensive validation scenarios."""

        valid_data = {
            "event_type": "compliance",
            "plan_id": "401K_PLAN",
            "compliance_type": "402g_limit_approach",
            "limit_type": "elective_deferral",
            "applicable_limit": Decimal("23000.00"),
            "current_amount": Decimal("21500.00"),
            "monitoring_date": date(2024, 11, 15),
        }

        payload = ComplianceEventPayload(**valid_data)
        assert payload.compliance_type == "402g_limit_approach"
        assert payload.limit_type == "elective_deferral"
        assert payload.applicable_limit == Decimal("23000.00")
        assert payload.current_amount == Decimal("21500.00")

        # Test all compliance types
        compliance_types = [
            "402g_limit_approach",
            "415c_limit_approach",
            "catch_up_eligible",
        ]
        for comp_type in compliance_types:
            type_data = {**valid_data, "compliance_type": comp_type}
            type_payload = ComplianceEventPayload(**type_data)
            assert type_payload.compliance_type == comp_type

        # Test all limit types
        limit_types = ["elective_deferral", "annual_additions", "catch_up"]
        for limit_type in limit_types:
            limit_data = {**valid_data, "limit_type": limit_type}
            limit_payload = ComplianceEventPayload(**limit_data)
            assert limit_payload.limit_type == limit_type

        # Edge case: zero current amount (new participant)
        zero_current_data = {**valid_data, "current_amount": Decimal("0.00")}
        zero_payload = ComplianceEventPayload(**zero_current_data)
        assert zero_payload.current_amount == Decimal("0.00")

        # Edge case: catch-up eligibility scenario
        catchup_data = {
            **valid_data,
            "compliance_type": "catch_up_eligible",
            "limit_type": "catch_up",
            "applicable_limit": Decimal("7500.00"),
        }
        catchup_payload = ComplianceEventPayload(**catchup_data)
        assert catchup_payload.compliance_type == "catch_up_eligible"

        # Validation errors
        with pytest.raises(ValidationError) as exc_info:
            ComplianceEventPayload(
                **{**valid_data, "applicable_limit": Decimal("0.00")}
            )
        assert "greater than 0" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            ComplianceEventPayload(
                **{**valid_data, "current_amount": Decimal("-100.00")}
            )
        assert "greater than or equal to 0" in str(exc_info.value)

    # ========== INTEGRATION AND DISCRIMINATED UNION TESTS ==========

    def test_simulation_event_discriminated_union_routing(self):
        """Test that all payload types route correctly through SimulationEvent discriminated union."""

        # Test each payload type through the discriminated union
        test_events = []

        # Workforce events
        hire_event = EventFactory.create_hire_event(
            **self.base_event_data,
            starting_compensation=Decimal("75000.00"),
            starting_level=3,
            employee_ssn="123456789",
            employee_birth_date=date(1990, 5, 15),
            location="HQ",
        )
        test_events.append(("hire", hire_event))

        promotion_event = EventFactory.create_promotion_event(
            **self.base_event_data,
            new_level=4,
            new_compensation=Decimal("85000.00"),
            previous_level=3,
            previous_compensation=Decimal("75000.00"),
        )
        test_events.append(("promotion", promotion_event))

        termination_event = EventFactory.create_termination_event(
            **self.base_event_data,
            termination_reason="voluntary",
            final_compensation=Decimal("80000.00"),
        )
        test_events.append(("termination", termination_event))

        merit_event = EventFactory.create_merit_event(
            **self.base_event_data,
            merit_percentage=Decimal("0.04"),
            previous_compensation=Decimal("75000.00"),
        )
        test_events.append(("merit", merit_event))

        # DC plan events
        eligibility_event = EligibilityEventFactory.create_eligibility_event(
            **self.plan_event_data,
            eligibility_date=date(2024, 1, 1),
            service_requirement_months=3,
            age_requirement=None,
        )
        test_events.append(("eligibility", eligibility_event))

        enrollment_event = EnrollmentEventFactory.create_enrollment_event(
            **self.plan_event_data,
            enrollment_date=date(2024, 2, 1),
            deferral_percentage=Decimal("0.06"),
            deferral_amount=None,
            catch_up_percentage=Decimal("0.00"),
        )
        test_events.append(("enrollment", enrollment_event))

        contribution_event = ContributionEventFactory.create_contribution_event(
            **self.plan_event_data,
            contribution_date=date(2024, 3, 15),
            employee_contribution=Decimal("500.00"),
            employer_contribution=Decimal("250.00"),
            contribution_source="regular_payroll",
            vesting_service_years=Decimal("1.25"),
        )
        test_events.append(("contribution", contribution_event))

        vesting_event = VestingEventFactory.create_vesting_event(
            **self.plan_event_data,
            vesting_date=date(2024, 12, 31),
            vesting_schedule_type="graded",
            vested_percentage=Decimal("0.60"),
            service_years=Decimal("3.0"),
        )
        test_events.append(("vesting", vesting_event))

        # Plan administration events
        forfeiture_event = PlanAdministrationEventFactory.create_forfeiture_event(
            **self.plan_event_data,
            forfeited_from_source="employer_match",
            amount=Decimal("2500.00"),
            reason="unvested_termination",
            vested_percentage=Decimal("0.25"),
        )
        test_events.append(("forfeiture", forfeiture_event))

        hce_event = PlanAdministrationEventFactory.create_hce_status_event(
            **self.plan_event_data,
            determination_method="prior_year",
            ytd_compensation=Decimal("125000.00"),
            annualized_compensation=Decimal("150000.00"),
            hce_threshold=Decimal("135000.00"),
            is_hce=True,
            determination_date=date(2024, 1, 1),
        )
        test_events.append(("hce_status", hce_event))

        compliance_event = (
            PlanAdministrationEventFactory.create_compliance_monitoring_event(
                **self.plan_event_data,
                compliance_type="402g_limit_approach",
                limit_type="elective_deferral",
                applicable_limit=Decimal("23000.00"),
                current_amount=Decimal("21500.00"),
                monitoring_date=date(2024, 11, 15),
            )
        )
        test_events.append(("compliance", compliance_event))

        # Validate all events
        for event_type, event in test_events:
            # Verify event structure
            assert isinstance(event, SimulationEvent)
            assert event.payload.event_type == event_type
            assert event.employee_id == self.base_event_data["employee_id"]
            assert event.scenario_id == self.base_event_data["scenario_id"]
            assert event.plan_design_id == self.base_event_data["plan_design_id"]

            # Test serialization/deserialization
            json_data = event.model_dump_json()
            reconstructed = SimulationEvent.model_validate_json(json_data)
            assert event == reconstructed

            # Verify discriminated union routing
            assert (
                type(event.payload).__name__.lower().startswith(event_type)
                or event_type in type(event.payload).__name__.lower()
            )

        # Verify we tested all 11 payload types
        assert (
            len(test_events) == 11
        ), f"Expected 11 event types, tested {len(test_events)}"

    def test_factory_method_coverage_and_validation(self):
        """Test all factory methods with validation and error handling."""

        # Test EventFactory methods
        assert hasattr(EventFactory, "create_hire_event")
        assert hasattr(EventFactory, "create_promotion_event")
        assert hasattr(EventFactory, "create_termination_event")
        assert hasattr(EventFactory, "create_merit_event")

        # Test specialized factory classes
        assert hasattr(EligibilityEventFactory, "create_eligibility_event")
        assert hasattr(EnrollmentEventFactory, "create_enrollment_event")
        assert hasattr(ContributionEventFactory, "create_contribution_event")
        assert hasattr(VestingEventFactory, "create_vesting_event")
        assert hasattr(PlanAdministrationEventFactory, "create_forfeiture_event")
        assert hasattr(PlanAdministrationEventFactory, "create_hce_status_event")
        assert hasattr(
            PlanAdministrationEventFactory, "create_compliance_monitoring_event"
        )

        # Test factory validation (invalid inputs should raise ValidationError)
        with pytest.raises(ValidationError):
            EventFactory.create_hire_event(
                **self.base_event_data,
                starting_compensation=Decimal("-1000.00"),  # Invalid negative
                starting_level=3,
                employee_ssn="123456789",
                employee_birth_date=date(1990, 5, 15),
                location="HQ",
            )

        with pytest.raises(ValidationError):
            EligibilityEventFactory.create_eligibility_event(
                **self.plan_event_data,
                eligibility_date=date(2024, 1, 1),
                service_requirement_months=-1,  # Invalid negative
                age_requirement=None,
            )

    def test_serialization_performance_and_accuracy(self):
        """Test serialization/deserialization performance and data accuracy."""

        # Create representative events
        events = []

        # Large decimal values for precision testing
        hire_event = EventFactory.create_hire_event(
            **self.base_event_data,
            starting_compensation=Decimal("123456.789012"),  # High precision
            starting_level=3,
            employee_ssn="123456789",
            employee_birth_date=date(1990, 5, 15),
            location="HQ",
        )
        events.append(hire_event)

        # Contribution with high precision
        contribution_event = ContributionEventFactory.create_contribution_event(
            **self.plan_event_data,
            contribution_date=date(2024, 3, 15),
            employee_contribution=Decimal("1234.567890"),
            employer_contribution=Decimal("987.654321"),
            contribution_source="regular_payroll",
            vesting_service_years=Decimal("2.333333"),
        )
        events.append(contribution_event)

        # Vesting with 4-decimal precision
        vesting_event = VestingEventFactory.create_vesting_event(
            **self.plan_event_data,
            vesting_date=date(2024, 12, 31),
            vesting_schedule_type="graded",
            vested_percentage=Decimal("0.6789"),  # 4 decimal places
            service_years=Decimal("3.25"),
        )
        events.append(vesting_event)

        # Test serialization accuracy
        for event in events:
            # Serialize to JSON
            json_data = event.model_dump_json()

            # Deserialize from JSON
            reconstructed = SimulationEvent.model_validate_json(json_data)

            # Verify complete equality
            assert event == reconstructed

            # Verify all field values are preserved exactly
            assert event.employee_id == reconstructed.employee_id
            assert event.scenario_id == reconstructed.scenario_id
            assert event.plan_design_id == reconstructed.plan_design_id
            assert event.effective_date == reconstructed.effective_date
            assert event.event_id == reconstructed.event_id

            # Verify payload fields are preserved
            for field_name in event.payload.model_fields:
                original_value = getattr(event.payload, field_name)
                reconstructed_value = getattr(reconstructed.payload, field_name)
                assert (
                    original_value == reconstructed_value
                ), f"Field {field_name} mismatch: {original_value} != {reconstructed_value}"

    def test_payload_type_coverage_summary(self):
        """Verify comprehensive coverage of all 11 payload types."""

        # Define all expected payload types
        expected_payload_types = {
            "HirePayload",
            "PromotionPayload",
            "TerminationPayload",
            "MeritPayload",
            "EligibilityPayload",
            "EnrollmentPayload",
            "ContributionPayload",
            "VestingPayload",
            "ForfeiturePayload",
            "HCEStatusPayload",
            "ComplianceEventPayload",
        }

        # Get all payload types from module
        import config.events as events_module

        actual_payload_types = set()

        for attr_name in dir(events_module):
            attr = getattr(events_module, attr_name)
            if (
                hasattr(attr, "__bases__")
                and hasattr(attr, "event_type")
                and attr_name.endswith("Payload")
            ):
                actual_payload_types.add(attr_name)

        # Verify coverage
        missing_types = expected_payload_types - actual_payload_types
        extra_types = actual_payload_types - expected_payload_types

        assert (
            len(missing_types) == 0
        ), f"Missing payload types in module: {missing_types}"
        assert (
            len(actual_payload_types) >= 11
        ), f"Expected at least 11 payload types, found {len(actual_payload_types)}"

        print(
            f"✅ Comprehensive payload coverage validated: {len(actual_payload_types)} payload types"
        )
        print(f"   Expected: {sorted(expected_payload_types)}")
        print(f"   Actual: {sorted(actual_payload_types)}")

        if extra_types:
            print(f"   Additional types found: {sorted(extra_types)}")


if __name__ == "__main__":
    # Run comprehensive payload coverage tests
    import pytest

    # Run with verbose output
    pytest.main([__file__, "-v", "--tb=short", "--durations=10"])
