# filename: tests/unit/test_plan_administration_events.py
"""Unit tests for plan administration events (S072-04)"""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from config.events import (ComplianceEventPayload, ForfeiturePayload,
                           HCEStatusPayload, PlanAdministrationEventFactory,
                           SimulationEvent)


class TestForfeiturePayload:
    """Test ForfeiturePayload validation and creation"""

    def test_valid_forfeiture_payload(self):
        """Test creating valid forfeiture payload"""
        payload = ForfeiturePayload(
            plan_id="PLAN_001",
            forfeited_from_source="employer_match",
            amount=Decimal("1000.50"),
            reason="unvested_termination",
            vested_percentage=Decimal("0.25"),
        )

        assert payload.event_type == "forfeiture"
        assert payload.plan_id == "PLAN_001"
        assert payload.forfeited_from_source == "employer_match"
        assert payload.amount == Decimal("1000.500000")  # Quantized to 6 decimal places
        assert payload.reason == "unvested_termination"
        assert payload.vested_percentage == Decimal(
            "0.2500"
        )  # Quantized to 4 decimal places

    def test_forfeiture_payload_invalid_source(self):
        """Test forfeiture payload with invalid source"""
        with pytest.raises(ValidationError) as exc_info:
            ForfeiturePayload(
                plan_id="PLAN_001",
                forfeited_from_source="employee_deferral",  # Invalid
                amount=Decimal("1000"),
                reason="unvested_termination",
                vested_percentage=Decimal("0.25"),
            )

        assert "Input should be 'employer_match'" in str(exc_info.value)

    def test_forfeiture_payload_negative_amount(self):
        """Test forfeiture payload with negative amount"""
        with pytest.raises(ValidationError) as exc_info:
            ForfeiturePayload(
                plan_id="PLAN_001",
                forfeited_from_source="employer_match",
                amount=Decimal("-100"),  # Invalid negative
                reason="unvested_termination",
                vested_percentage=Decimal("0.25"),
            )

        assert "Input should be greater than 0" in str(exc_info.value)

    def test_forfeiture_payload_invalid_vested_percentage(self):
        """Test forfeiture payload with invalid vested percentage"""
        with pytest.raises(ValidationError) as exc_info:
            ForfeiturePayload(
                plan_id="PLAN_001",
                forfeited_from_source="employer_match",
                amount=Decimal("1000"),
                reason="unvested_termination",
                vested_percentage=Decimal("1.5"),  # Invalid > 1
            )

        assert "Input should be less than or equal to 1" in str(exc_info.value)

    def test_forfeiture_payload_empty_plan_id(self):
        """Test forfeiture payload with empty plan_id"""
        with pytest.raises(ValidationError) as exc_info:
            ForfeiturePayload(
                plan_id="",  # Invalid empty
                forfeited_from_source="employer_match",
                amount=Decimal("1000"),
                reason="unvested_termination",
                vested_percentage=Decimal("0.25"),
            )

        assert "String should have at least 1 character" in str(exc_info.value)


class TestHCEStatusPayload:
    """Test HCEStatusPayload validation and creation"""

    def test_valid_hce_status_payload(self):
        """Test creating valid HCE status payload"""
        payload = HCEStatusPayload(
            plan_id="PLAN_001",
            determination_method="prior_year",
            ytd_compensation=Decimal("125000.00"),
            annualized_compensation=Decimal("150000.00"),
            hce_threshold=Decimal("135000.00"),
            is_hce=True,
            determination_date=date(2025, 1, 1),
            prior_year_hce=False,
        )

        assert payload.event_type == "hce_status"
        assert payload.plan_id == "PLAN_001"
        assert payload.determination_method == "prior_year"
        assert payload.ytd_compensation == Decimal("125000.000000")
        assert payload.annualized_compensation == Decimal("150000.000000")
        assert payload.hce_threshold == Decimal("135000.000000")
        assert payload.is_hce is True
        assert payload.determination_date == date(2025, 1, 1)
        assert payload.prior_year_hce is False

    def test_hce_status_payload_optional_prior_year_hce(self):
        """Test HCE status payload with optional prior_year_hce field"""
        payload = HCEStatusPayload(
            plan_id="PLAN_001",
            determination_method="current_year",
            ytd_compensation=Decimal("100000"),
            annualized_compensation=Decimal("120000"),
            hce_threshold=Decimal("135000"),
            is_hce=False,
            determination_date=date(2025, 1, 1)
            # prior_year_hce not provided - should be None
        )

        assert payload.prior_year_hce is None

    def test_hce_status_payload_invalid_determination_method(self):
        """Test HCE status payload with invalid determination method"""
        with pytest.raises(ValidationError) as exc_info:
            HCEStatusPayload(
                plan_id="PLAN_001",
                determination_method="future_year",  # Invalid
                ytd_compensation=Decimal("125000"),
                annualized_compensation=Decimal("150000"),
                hce_threshold=Decimal("135000"),
                is_hce=True,
                determination_date=date(2025, 1, 1),
            )

        assert "Input should be 'prior_year' or 'current_year'" in str(exc_info.value)

    def test_hce_status_payload_negative_compensation(self):
        """Test HCE status payload with negative compensation"""
        with pytest.raises(ValidationError) as exc_info:
            HCEStatusPayload(
                plan_id="PLAN_001",
                determination_method="prior_year",
                ytd_compensation=Decimal("-1000"),  # Invalid negative
                annualized_compensation=Decimal("150000"),
                hce_threshold=Decimal("135000"),
                is_hce=True,
                determination_date=date(2025, 1, 1),
            )

        assert "Input should be greater than or equal to 0" in str(exc_info.value)

    def test_hce_status_payload_zero_threshold(self):
        """Test HCE status payload with zero threshold"""
        with pytest.raises(ValidationError) as exc_info:
            HCEStatusPayload(
                plan_id="PLAN_001",
                determination_method="prior_year",
                ytd_compensation=Decimal("125000"),
                annualized_compensation=Decimal("150000"),
                hce_threshold=Decimal("0"),  # Invalid - must be > 0
                is_hce=True,
                determination_date=date(2025, 1, 1),
            )

        assert "Input should be greater than 0" in str(exc_info.value)


class TestComplianceEventPayload:
    """Test ComplianceEventPayload validation and creation"""

    def test_valid_compliance_event_payload(self):
        """Test creating valid compliance event payload"""
        payload = ComplianceEventPayload(
            plan_id="PLAN_001",
            compliance_type="402g_limit_approach",
            limit_type="elective_deferral",
            applicable_limit=Decimal("23000.00"),
            current_amount=Decimal("20000.00"),
            monitoring_date=date(2025, 11, 1),
        )

        assert payload.event_type == "compliance"
        assert payload.plan_id == "PLAN_001"
        assert payload.compliance_type == "402g_limit_approach"
        assert payload.limit_type == "elective_deferral"
        assert payload.applicable_limit == Decimal("23000.000000")
        assert payload.current_amount == Decimal("20000.000000")
        assert payload.monitoring_date == date(2025, 11, 1)

    def test_compliance_event_payload_catch_up_eligible(self):
        """Test compliance event payload for catch-up eligibility"""
        payload = ComplianceEventPayload(
            plan_id="PLAN_001",
            compliance_type="catch_up_eligible",
            limit_type="catch_up",
            applicable_limit=Decimal("7500.00"),
            current_amount=Decimal("0.00"),
            monitoring_date=date(2025, 1, 1),
        )

        assert payload.compliance_type == "catch_up_eligible"
        assert payload.limit_type == "catch_up"

    def test_compliance_event_payload_415c_limit(self):
        """Test compliance event payload for 415(c) annual additions limit"""
        payload = ComplianceEventPayload(
            plan_id="PLAN_001",
            compliance_type="415c_limit_approach",
            limit_type="annual_additions",
            applicable_limit=Decimal("69000.00"),
            current_amount=Decimal("65000.00"),
            monitoring_date=date(2025, 10, 1),
        )

        assert payload.compliance_type == "415c_limit_approach"
        assert payload.limit_type == "annual_additions"

    def test_compliance_event_payload_invalid_compliance_type(self):
        """Test compliance event payload with invalid compliance type"""
        with pytest.raises(ValidationError) as exc_info:
            ComplianceEventPayload(
                plan_id="PLAN_001",
                compliance_type="invalid_compliance_type",  # Invalid
                limit_type="elective_deferral",
                applicable_limit=Decimal("23000"),
                current_amount=Decimal("20000"),
                monitoring_date=date(2025, 11, 1),
            )

        assert "Input should be '402g_limit_approach'" in str(exc_info.value)

    def test_compliance_event_payload_invalid_limit_type(self):
        """Test compliance event payload with invalid limit type"""
        with pytest.raises(ValidationError) as exc_info:
            ComplianceEventPayload(
                plan_id="PLAN_001",
                compliance_type="402g_limit_approach",
                limit_type="invalid_limit_type",  # Invalid
                applicable_limit=Decimal("23000"),
                current_amount=Decimal("20000"),
                monitoring_date=date(2025, 11, 1),
            )

        assert "Input should be 'elective_deferral'" in str(exc_info.value)

    def test_compliance_event_payload_zero_applicable_limit(self):
        """Test compliance event payload with zero applicable limit"""
        with pytest.raises(ValidationError) as exc_info:
            ComplianceEventPayload(
                plan_id="PLAN_001",
                compliance_type="402g_limit_approach",
                limit_type="elective_deferral",
                applicable_limit=Decimal("0"),  # Invalid - must be > 0
                current_amount=Decimal("20000"),
                monitoring_date=date(2025, 11, 1),
            )

        assert "Input should be greater than 0" in str(exc_info.value)

    def test_compliance_event_payload_negative_current_amount(self):
        """Test compliance event payload with negative current amount"""
        with pytest.raises(ValidationError) as exc_info:
            ComplianceEventPayload(
                plan_id="PLAN_001",
                compliance_type="402g_limit_approach",
                limit_type="elective_deferral",
                applicable_limit=Decimal("23000"),
                current_amount=Decimal("-1000"),  # Invalid negative
                monitoring_date=date(2025, 11, 1),
            )

        assert "Input should be greater than or equal to 0" in str(exc_info.value)


class TestPlanAdministrationEventFactory:
    """Test PlanAdministrationEventFactory methods"""

    def test_create_forfeiture_event(self):
        """Test creating forfeiture event via factory"""
        event = PlanAdministrationEventFactory.create_forfeiture_event(
            employee_id="EMP_001",
            plan_id="PLAN_001",
            scenario_id="SCENARIO_001",
            plan_design_id="DESIGN_001",
            forfeited_from_source="employer_match",
            amount=Decimal("2500.00"),
            reason="unvested_termination",
            vested_percentage=Decimal("0.40"),
            effective_date=date(2025, 3, 15),
        )

        assert isinstance(event, SimulationEvent)
        assert event.employee_id == "EMP_001"
        assert event.scenario_id == "SCENARIO_001"
        assert event.plan_design_id == "DESIGN_001"
        assert event.effective_date == date(2025, 3, 15)
        assert event.source_system == "plan_administration"

        assert isinstance(event.payload, ForfeiturePayload)
        assert event.payload.event_type == "forfeiture"
        assert event.payload.plan_id == "PLAN_001"
        assert event.payload.amount == Decimal("2500.000000")

    def test_create_hce_status_event(self):
        """Test creating HCE status event via factory"""
        event = PlanAdministrationEventFactory.create_hce_status_event(
            employee_id="EMP_002",
            plan_id="PLAN_001",
            scenario_id="SCENARIO_001",
            plan_design_id="DESIGN_001",
            determination_method="prior_year",
            ytd_compensation=Decimal("130000.00"),
            annualized_compensation=Decimal("156000.00"),
            hce_threshold=Decimal("135000.00"),
            is_hce=True,
            determination_date=date(2025, 1, 1),
            prior_year_hce=False,
        )

        assert isinstance(event, SimulationEvent)
        assert event.employee_id == "EMP_002"
        assert event.effective_date == date(2025, 1, 1)
        assert event.source_system == "hce_determination"

        assert isinstance(event.payload, HCEStatusPayload)
        assert event.payload.event_type == "hce_status"
        assert event.payload.is_hce is True
        assert event.payload.prior_year_hce is False

    def test_create_compliance_monitoring_event(self):
        """Test creating compliance monitoring event via factory"""
        event = PlanAdministrationEventFactory.create_compliance_monitoring_event(
            employee_id="EMP_003",
            plan_id="PLAN_001",
            scenario_id="SCENARIO_001",
            plan_design_id="DESIGN_001",
            compliance_type="catch_up_eligible",
            limit_type="catch_up",
            applicable_limit=Decimal("7500.00"),
            current_amount=Decimal("0.00"),
            monitoring_date=date(2025, 7, 1),
        )

        assert isinstance(event, SimulationEvent)
        assert event.employee_id == "EMP_003"
        assert event.effective_date == date(2025, 7, 1)
        assert event.source_system == "compliance_monitoring"

        assert isinstance(event.payload, ComplianceEventPayload)
        assert event.payload.event_type == "compliance"
        assert event.payload.compliance_type == "catch_up_eligible"
        assert event.payload.limit_type == "catch_up"


class TestPlanAdministrationEventIntegration:
    """Test integration of plan administration events with SimulationEvent"""

    def test_simulation_event_discriminated_union_forfeiture(self):
        """Test SimulationEvent correctly routes forfeiture payload"""
        event_data = {
            "employee_id": "EMP_001",
            "scenario_id": "SCENARIO_001",
            "plan_design_id": "DESIGN_001",
            "effective_date": date(2025, 3, 15),
            "source_system": "plan_administration",
            "payload": {
                "event_type": "forfeiture",
                "plan_id": "PLAN_001",
                "forfeited_from_source": "employer_nonelective",
                "amount": Decimal("1500.00"),
                "reason": "break_in_service",
                "vested_percentage": Decimal("0.60"),
            },
        }

        event = SimulationEvent.model_validate(event_data)
        assert isinstance(event.payload, ForfeiturePayload)
        assert event.payload.forfeited_from_source == "employer_nonelective"

    def test_simulation_event_discriminated_union_hce_status(self):
        """Test SimulationEvent correctly routes HCE status payload"""
        event_data = {
            "employee_id": "EMP_002",
            "scenario_id": "SCENARIO_001",
            "plan_design_id": "DESIGN_001",
            "effective_date": date(2025, 1, 1),
            "source_system": "hce_determination",
            "payload": {
                "event_type": "hce_status",
                "plan_id": "PLAN_001",
                "determination_method": "current_year",
                "ytd_compensation": Decimal("110000.00"),
                "annualized_compensation": Decimal("132000.00"),
                "hce_threshold": Decimal("135000.00"),
                "is_hce": False,
                "determination_date": date(2025, 1, 1),
            },
        }

        event = SimulationEvent.model_validate(event_data)
        assert isinstance(event.payload, HCEStatusPayload)
        assert event.payload.is_hce is False

    def test_simulation_event_discriminated_union_compliance(self):
        """Test SimulationEvent correctly routes compliance event payload"""
        event_data = {
            "employee_id": "EMP_003",
            "scenario_id": "SCENARIO_001",
            "plan_design_id": "DESIGN_001",
            "effective_date": date(2025, 10, 1),
            "source_system": "compliance_monitoring",
            "payload": {
                "event_type": "compliance",
                "plan_id": "PLAN_001",
                "compliance_type": "415c_limit_approach",
                "limit_type": "annual_additions",
                "applicable_limit": Decimal("69000.00"),
                "current_amount": Decimal("64000.00"),
                "monitoring_date": date(2025, 10, 1),
            },
        }

        event = SimulationEvent.model_validate(event_data)
        assert isinstance(event.payload, ComplianceEventPayload)
        assert event.payload.compliance_type == "415c_limit_approach"

    def test_event_serialization_deserialization(self):
        """Test plan administration events can be serialized and deserialized"""
        original_event = PlanAdministrationEventFactory.create_forfeiture_event(
            employee_id="EMP_001",
            plan_id="PLAN_001",
            scenario_id="SCENARIO_001",
            plan_design_id="DESIGN_001",
            forfeited_from_source="employer_profit_sharing",
            amount=Decimal("3000.00"),
            reason="unvested_termination",
            vested_percentage=Decimal("0.75"),
            effective_date=date(2025, 6, 30),
        )

        # Serialize to dict
        event_dict = original_event.model_dump()

        # Deserialize from dict
        reconstructed_event = SimulationEvent.model_validate(event_dict)

        assert reconstructed_event.employee_id == original_event.employee_id
        assert reconstructed_event.payload.event_type == "forfeiture"
        assert reconstructed_event.payload.amount == original_event.payload.amount
        assert reconstructed_event.effective_date == original_event.effective_date
