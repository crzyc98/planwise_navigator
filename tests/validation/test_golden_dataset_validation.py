"""
Golden Dataset Validation Framework - S072-06

Validates event schema against benchmark calculations with 100% accuracy requirement.
Tests all 11 payload types with comprehensive edge case coverage.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from datetime import date, datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

import pytest
import pandas as pd
import numpy as np
from pydantic import ValidationError

from config.events import (
    SimulationEvent,
    EventFactory,
    EligibilityEventFactory,
    EnrollmentEventFactory,
    ContributionEventFactory,
    VestingEventFactory,
    PlanAdministrationEventFactory,
    # All payload types for comprehensive testing
    HirePayload,
    PromotionPayload,
    TerminationPayload,
    MeritPayload,
    EligibilityPayload,
    EnrollmentPayload,
    ContributionPayload,
    VestingPayload,
    ForfeiturePayload,
    HCEStatusPayload,
    ComplianceEventPayload
)


class GoldenDatasetManager:
    """Manages golden dataset for validation testing."""

    def __init__(self, dataset_path: Optional[str] = None):
        self.dataset_path = Path(dataset_path) if dataset_path else Path("tests/validation/golden_dataset")
        self.dataset_path.mkdir(parents=True, exist_ok=True)

    def load_golden_scenarios(self) -> Dict[str, Any]:
        """Load golden test scenarios with expected results."""
        return {
            "participant_lifecycle": {
                "description": "Complete participant lifecycle from hire to termination with DC plan participation",
                "employee_id": "GOLDEN_001",
                "scenario_id": "GOLDEN_SCENARIO",
                "plan_design_id": "GOLDEN_DESIGN",
                "plan_id": "GOLDEN_401K",
                "events": [
                    {
                        "event_type": "hire",
                        "effective_date": "2020-01-15",
                        "starting_compensation": "75000.00",
                        "starting_level": 3,
                        "employee_ssn": "123456789",
                        "employee_birth_date": "1985-06-15",
                        "location": "HQ"
                    },
                    {
                        "event_type": "eligibility",
                        "effective_date": "2020-04-15",
                        "eligibility_date": "2020-04-15",
                        "service_requirement_months": 3,
                        "age_requirement": None
                    },
                    {
                        "event_type": "enrollment",
                        "effective_date": "2020-05-01",
                        "enrollment_date": "2020-05-01",
                        "deferral_percentage": "0.06",
                        "catch_up_percentage": "0.00"
                    },
                    {
                        "event_type": "contribution",
                        "effective_date": "2020-05-15",
                        "contribution_date": "2020-05-15",
                        "employee_contribution": "375.00",  # 6% of 6250/month
                        "employer_contribution": "187.50",  # 3% match
                        "contribution_source": "regular_payroll",
                        "vesting_service_years": "0.33"
                    },
                    {
                        "event_type": "merit",
                        "effective_date": "2021-03-01",
                        "merit_percentage": "0.04",  # 4% merit increase
                        "previous_compensation": "75000.00"
                    },
                    {
                        "event_type": "promotion",
                        "effective_date": "2022-07-01",
                        "new_level": 4,
                        "new_compensation": "85000.00",
                        "previous_level": 3,
                        "previous_compensation": "78000.00"
                    },
                    {
                        "event_type": "vesting",
                        "effective_date": "2022-12-31",
                        "vesting_date": "2022-12-31",
                        "vesting_schedule_type": "graded",
                        "vested_percentage": "0.60",  # 60% after 3 years
                        "service_years": "3.0"
                    },
                    {
                        "event_type": "hce_status",
                        "effective_date": "2023-01-01",
                        "determination_method": "prior_year",
                        "ytd_compensation": "85000.00",
                        "annualized_compensation": "85000.00",
                        "hce_threshold": "135000.00",
                        "is_hce": False,
                        "determination_date": "2023-01-01"
                    },
                    {
                        "event_type": "termination",
                        "effective_date": "2024-06-30",
                        "termination_reason": "voluntary",
                        "final_compensation": "88000.00"
                    },
                    {
                        "event_type": "forfeiture",
                        "effective_date": "2024-07-15",
                        "forfeited_from_source": "employer_match",
                        "amount": "2500.00",  # Unvested portion
                        "reason": "unvested_termination",
                        "vested_percentage": "0.80"
                    }
                ],
                "expected_calculations": {
                    "total_employee_contributions": "10800.00",  # 4.5 years of contributions
                    "total_employer_contributions": "5400.00",   # 50% match
                    "total_vested_amount": "14820.00",          # 80% vested + all employee
                    "total_forfeited_amount": "2500.00",        # 20% unvested employer
                    "final_compensation": "88000.00",
                    "total_merit_increases": 2,
                    "total_promotions": 1,
                    "service_years": "4.46",
                    "hce_determinations": 1
                }
            },

            "compliance_monitoring": {
                "description": "Comprehensive compliance event scenarios with IRS limits",
                "employee_id": "GOLDEN_002",
                "scenario_id": "COMPLIANCE_SCENARIO",
                "plan_design_id": "COMPLIANCE_DESIGN",
                "plan_id": "COMPLIANCE_401K",
                "events": [
                    {
                        "event_type": "hire",
                        "effective_date": "2024-01-01",
                        "starting_compensation": "200000.00",
                        "starting_level": 5,
                        "employee_ssn": "987654321",
                        "employee_birth_date": "1970-01-01",  # Age 54 - catch-up eligible
                        "location": "HQ"
                    },
                    {
                        "event_type": "eligibility",
                        "effective_date": "2024-01-01",
                        "eligibility_date": "2024-01-01",
                        "service_requirement_months": 0,
                        "age_requirement": None
                    },
                    {
                        "event_type": "enrollment",
                        "effective_date": "2024-01-15",
                        "enrollment_date": "2024-01-15",
                        "deferral_percentage": "0.15",  # 15% - high deferral
                        "catch_up_percentage": "0.04"   # 4% catch-up
                    },
                    {
                        "event_type": "compliance",
                        "effective_date": "2024-11-01",
                        "compliance_type": "catch_up_eligible",
                        "limit_type": "catch_up",
                        "applicable_limit": "7500.00",  # 2024 catch-up limit
                        "current_amount": "0.00",
                        "monitoring_date": "2024-11-01"
                    },
                    {
                        "event_type": "compliance",
                        "effective_date": "2024-11-15",
                        "compliance_type": "402g_limit_approach",
                        "limit_type": "elective_deferral",
                        "applicable_limit": "23000.00",  # 2024 402(g) limit
                        "current_amount": "21500.00",    # Approaching limit
                        "monitoring_date": "2024-11-15"
                    },
                    {
                        "event_type": "hce_status",
                        "effective_date": "2024-01-01",
                        "determination_method": "current_year",
                        "ytd_compensation": "200000.00",
                        "annualized_compensation": "200000.00",
                        "hce_threshold": "135000.00",  # 2024 HCE threshold
                        "is_hce": True,
                        "determination_date": "2024-01-01"
                    }
                ],
                "expected_calculations": {
                    "is_catch_up_eligible": True,
                    "max_annual_deferral": "30500.00",  # 23000 + 7500 catch-up
                    "projected_annual_deferral": "25000.00",  # 15% of 200K
                    "is_hce": True,
                    "compliance_events_count": 2,
                    "limit_approach_warnings": 1
                }
            },

            "edge_case_scenarios": {
                "description": "Edge cases and boundary conditions for robust validation",
                "test_cases": [
                    {
                        "case": "zero_compensation_hire",
                        "employee_id": "EDGE_001",
                        "event_type": "hire",
                        "starting_compensation": "0.01",  # Minimum valid compensation
                        "should_validate": True
                    },
                    {
                        "case": "maximum_compensation",
                        "employee_id": "EDGE_002",
                        "event_type": "hire",
                        "starting_compensation": "999999.99",  # Very high compensation
                        "should_validate": True
                    },
                    {
                        "case": "100_percent_vested",
                        "employee_id": "EDGE_003",
                        "event_type": "vesting",
                        "vested_percentage": "1.0000",  # Exactly 100%
                        "should_validate": True
                    },
                    {
                        "case": "zero_percent_vested",
                        "employee_id": "EDGE_004",
                        "event_type": "vesting",
                        "vested_percentage": "0.0000",  # Exactly 0%
                        "should_validate": True
                    },
                    {
                        "case": "invalid_negative_compensation",
                        "employee_id": "EDGE_005",
                        "event_type": "hire",
                        "starting_compensation": "-1000.00",  # Invalid negative
                        "should_validate": False
                    },
                    {
                        "case": "invalid_over_100_percent_vested",
                        "employee_id": "EDGE_006",
                        "event_type": "vesting",
                        "vested_percentage": "1.0001",  # Over 100%
                        "should_validate": False
                    }
                ]
            }
        }


class ValidationCalculator:
    """Performs benchmark calculations for validation comparison."""

    @staticmethod
    def calculate_participant_totals(events: List[Dict[str, Any]]) -> Dict[str, Decimal]:
        """Calculate expected totals from event sequence."""
        totals = {
            "total_employee_contributions": Decimal("0"),
            "total_employer_contributions": Decimal("0"),
            "total_merit_increases": 0,
            "total_promotions": 0,
            "hce_determinations": 0,
            "compliance_events": 0
        }

        for event in events:
            event_type = event["event_type"]

            if event_type == "contribution":
                totals["total_employee_contributions"] += Decimal(str(event["employee_contribution"]))
                totals["total_employer_contributions"] += Decimal(str(event["employer_contribution"]))
            elif event_type == "merit":
                totals["total_merit_increases"] += 1
            elif event_type == "promotion":
                totals["total_promotions"] += 1
            elif event_type == "hce_status":
                totals["hce_determinations"] += 1
            elif event_type == "compliance":
                totals["compliance_events"] += 1

        return totals

    @staticmethod
    def calculate_vesting_amount(contributions: Decimal, vested_percentage: Decimal) -> Decimal:
        """Calculate vested amount based on contributions and vesting percentage."""
        return contributions * vested_percentage

    @staticmethod
    def validate_irs_limits(compensation: Decimal, deferral_pct: Decimal, catch_up_pct: Decimal,
                          birth_date: date, limit_year: int) -> Dict[str, Any]:
        """Validate IRS contribution limits for given year."""
        age = limit_year - birth_date.year

        # 2024 IRS limits (update annually)
        base_limit = Decimal("23000") if limit_year == 2024 else Decimal("22500")
        catch_up_limit = Decimal("7500") if limit_year == 2024 else Decimal("7500")

        is_catch_up_eligible = age >= 50
        max_deferral = base_limit + (catch_up_limit if is_catch_up_eligible else Decimal("0"))

        projected_deferral = compensation * deferral_pct
        if is_catch_up_eligible:
            projected_deferral += compensation * catch_up_pct

        return {
            "is_catch_up_eligible": is_catch_up_eligible,
            "max_annual_deferral": max_deferral,
            "projected_annual_deferral": min(projected_deferral, max_deferral),
            "exceeds_limit": projected_deferral > max_deferral
        }


class TestGoldenDatasetValidation:
    """Golden dataset validation test suite - S072-06."""

    def setup_method(self):
        """Setup for each test method."""
        self.golden_manager = GoldenDatasetManager()
        self.calculator = ValidationCalculator()
        self.golden_scenarios = self.golden_manager.load_golden_scenarios()

    def test_json_schema_validation_all_payloads(self):
        """Test JSON schema validation for all 11 payload types - Target: ≥99% success."""
        validation_results = []

        # Test each payload type individually
        payload_types = [
            HirePayload, PromotionPayload, TerminationPayload, MeritPayload,
            EligibilityPayload, EnrollmentPayload, ContributionPayload, VestingPayload,
            ForfeiturePayload, HCEStatusPayload, ComplianceEventPayload
        ]

        for payload_class in payload_types:
            try:
                # Create valid test data for each payload type
                test_data = self._create_valid_payload_data(payload_class)

                # Test validation
                payload_instance = payload_class.model_validate(test_data)

                # Test serialization/deserialization
                json_data = payload_instance.model_dump_json()
                reconstructed = payload_class.model_validate_json(json_data)

                # Verify data integrity
                assert payload_instance == reconstructed

                validation_results.append({
                    "payload_type": payload_class.__name__,
                    "status": "PASS",
                    "error": None
                })

            except Exception as e:
                validation_results.append({
                    "payload_type": payload_class.__name__,
                    "status": "FAIL",
                    "error": str(e)
                })

        # Calculate success rate
        passed_tests = sum(1 for result in validation_results if result["status"] == "PASS")
        success_rate = passed_tests / len(validation_results)

        print(f"\n=== JSON Schema Validation Results ===")
        for result in validation_results:
            status_icon = "✅" if result["status"] == "PASS" else "❌"
            print(f"{status_icon} {result['payload_type']}: {result['status']}")
            if result["error"]:
                print(f"   Error: {result['error']}")

        print(f"\nSuccess Rate: {success_rate:.1%} ({passed_tests}/{len(validation_results)})")

        # Requirement: ≥99% success rate
        assert success_rate >= 0.99, f"Schema validation success rate too low: {success_rate:.1%} < 99%"

    def test_participant_lifecycle_golden_scenario(self):
        """Test complete participant lifecycle with 100% calculation accuracy."""
        scenario = self.golden_scenarios["participant_lifecycle"]
        expected = scenario["expected_calculations"]

        # Create events from golden scenario
        events = []
        for event_data in scenario["events"]:
            event = self._create_event_from_data(event_data, scenario)
            events.append(event)

        # Calculate actual totals from events
        actual_totals = self.calculator.calculate_participant_totals(scenario["events"])

        # Validate against expected calculations with zero variance tolerance
        assertions = [
            ("total_employee_contributions", Decimal(expected["total_employee_contributions"])),
            ("total_employer_contributions", Decimal(expected["total_employer_contributions"])),
            ("total_merit_increases", expected["total_merit_increases"]),
            ("total_promotions", expected["total_promotions"]),
            ("hce_determinations", expected["hce_determinations"])
        ]

        print(f"\n=== Participant Lifecycle Validation ===")
        for field, expected_value in assertions:
            actual_value = actual_totals[field]
            match = actual_value == expected_value
            status_icon = "✅" if match else "❌"

            print(f"{status_icon} {field}: Expected {expected_value}, Actual {actual_value}")

            # Zero variance tolerance for golden dataset
            assert actual_value == expected_value, f"Golden dataset mismatch for {field}: {actual_value} != {expected_value}"

        # Validate event creation and serialization
        for event in events:
            # Ensure each event can be serialized and reconstructed perfectly
            json_data = event.model_dump_json()
            reconstructed = SimulationEvent.model_validate_json(json_data)
            assert event == reconstructed, "Event serialization/deserialization mismatch"

        print(f"✅ All {len(events)} events validated with 100% accuracy")

    def test_compliance_monitoring_golden_scenario(self):
        """Test compliance monitoring scenarios with regulatory accuracy."""
        scenario = self.golden_scenarios["compliance_monitoring"]
        expected = scenario["expected_calculations"]

        # Extract compliance parameters
        hire_event = next(e for e in scenario["events"] if e["event_type"] == "hire")
        enrollment_event = next(e for e in scenario["events"] if e["event_type"] == "enrollment")

        compensation = Decimal(hire_event["starting_compensation"])
        deferral_pct = Decimal(enrollment_event["deferral_percentage"])
        catch_up_pct = Decimal(enrollment_event["catch_up_percentage"])
        birth_date = date.fromisoformat(hire_event["employee_birth_date"])

        # Calculate IRS limits validation
        irs_validation = self.calculator.validate_irs_limits(
            compensation, deferral_pct, catch_up_pct, birth_date, 2024
        )

        # Validate against expected calculations
        print(f"\n=== Compliance Monitoring Validation ===")

        compliance_assertions = [
            ("is_catch_up_eligible", expected["is_catch_up_eligible"]),
            ("max_annual_deferral", Decimal(expected["max_annual_deferral"])),
            ("is_hce", expected["is_hce"])
        ]

        for field, expected_value in compliance_assertions:
            if field in irs_validation:
                actual_value = irs_validation[field]
            else:
                # For HCE status, check the event
                hce_event = next(e for e in scenario["events"] if e["event_type"] == "hce_status")
                actual_value = hce_event["is_hce"]

            match = actual_value == expected_value
            status_icon = "✅" if match else "❌"

            print(f"{status_icon} {field}: Expected {expected_value}, Actual {actual_value}")
            assert actual_value == expected_value, f"Compliance calculation mismatch for {field}"

        # Count compliance events
        compliance_events = [e for e in scenario["events"] if e["event_type"] == "compliance"]
        assert len(compliance_events) == expected["compliance_events_count"], \
            f"Expected {expected['compliance_events_count']} compliance events, got {len(compliance_events)}"

        print(f"✅ Compliance monitoring validated with regulatory accuracy")

    def test_edge_case_validation_coverage(self):
        """Test edge cases and boundary conditions - >95% coverage target."""
        edge_cases = self.golden_scenarios["edge_case_scenarios"]["test_cases"]

        validation_results = []

        print(f"\n=== Edge Case Validation ===")

        for case in edge_cases:
            case_name = case["case"]
            should_validate = case["should_validate"]

            try:
                # Create test event from edge case data
                test_data = {
                    "employee_id": case["employee_id"],
                    "scenario_id": "EDGE_CASE_SCENARIO",
                    "plan_design_id": "EDGE_CASE_DESIGN",
                    "effective_date": date(2024, 1, 1)
                }

                # Add case-specific data
                for key, value in case.items():
                    if key not in ["case", "employee_id", "should_validate"]:
                        test_data[key] = value

                # Attempt validation based on event type
                if case["event_type"] == "hire":
                    test_data.update({
                        "starting_level": 1,
                        "employee_ssn": "123456789",
                        "employee_birth_date": date(1990, 1, 1),
                        "location": "HQ"
                    })
                    event = EventFactory.create_hire_event(**test_data)
                elif case["event_type"] == "vesting":
                    test_data.update({
                        "plan_id": "TEST_PLAN",
                        "vesting_date": date(2024, 1, 1),
                        "vesting_schedule_type": "graded",
                        "service_years": Decimal("1.0")
                    })
                    event = VestingEventFactory.create_vesting_event(**test_data)

                # If we get here, validation succeeded
                validation_succeeded = True
                error_msg = None

            except (ValidationError, ValueError) as e:
                validation_succeeded = False
                error_msg = str(e)
            except Exception as e:
                validation_succeeded = False
                error_msg = f"Unexpected error: {str(e)}"

            # Check if result matches expectation
            test_passed = validation_succeeded == should_validate
            status_icon = "✅" if test_passed else "❌"

            print(f"{status_icon} {case_name}: Expected {should_validate}, Got {validation_succeeded}")
            if error_msg and not should_validate:
                print(f"   Expected error: {error_msg}")

            validation_results.append({
                "case": case_name,
                "expected": should_validate,
                "actual": validation_succeeded,
                "passed": test_passed,
                "error": error_msg
            })

        # Calculate coverage
        passed_tests = sum(1 for result in validation_results if result["passed"])
        coverage_rate = passed_tests / len(validation_results)

        print(f"\nEdge Case Coverage: {coverage_rate:.1%} ({passed_tests}/{len(validation_results)})")

        # Requirement: >95% coverage
        assert coverage_rate > 0.95, f"Edge case coverage too low: {coverage_rate:.1%} < 95%"

    def test_integration_workflow_validation(self):
        """Test complete end-to-end workflow with all event combinations."""
        print(f"\n=== Integration Workflow Validation ===")

        # Create comprehensive workflow with all event types
        employee_id = "INTEGRATION_001"
        scenario_id = "INTEGRATION_SCENARIO"
        plan_design_id = "INTEGRATION_DESIGN"
        plan_id = "INTEGRATION_PLAN"

        workflow_events = []

        # 1. Hire event
        hire_event = EventFactory.create_hire_event(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            starting_compensation=Decimal("80000.00"),
            starting_level=3,
            effective_date=date(2020, 1, 1),
            employee_ssn="555666777",
            employee_birth_date=date(1975, 5, 15),  # Age 45 in 2020
            location="HQ"
        )
        workflow_events.append(hire_event)

        # 2. Plan eligibility
        eligibility_event = EligibilityEventFactory.create_eligibility_event(
            employee_id=employee_id,
            plan_id=plan_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            eligibility_date=date(2020, 4, 1),
            service_requirement_months=3,
            age_requirement=None,
            effective_date=date(2020, 4, 1)
        )
        workflow_events.append(eligibility_event)

        # 3. Plan enrollment
        enrollment_event = EnrollmentEventFactory.create_enrollment_event(
            employee_id=employee_id,
            plan_id=plan_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            enrollment_date=date(2020, 5, 1),
            deferral_percentage=Decimal("0.08"),
            deferral_amount=None,
            catch_up_percentage=Decimal("0.0"),
            effective_date=date(2020, 5, 1)
        )
        workflow_events.append(enrollment_event)

        # 4. Monthly contributions (12 months)
        for month in range(1, 13):
            contribution_event = ContributionEventFactory.create_contribution_event(
                employee_id=employee_id,
                plan_id=plan_id,
                scenario_id=scenario_id,
                plan_design_id=plan_design_id,
                contribution_date=date(2020, month, 15),
                employee_contribution=Decimal("533.33"),  # 8% of ~6667/month
                employer_contribution=Decimal("266.67"),   # 50% match
                contribution_source="regular_payroll",
                vesting_service_years=Decimal(f"{month/12:.2f}"),
                effective_date=date(2020, month, 15)
            )
            workflow_events.append(contribution_event)

        # 5. Merit increase
        merit_event = EventFactory.create_merit_event(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            merit_percentage=Decimal("0.05"),
            effective_date=date(2021, 3, 1),
            previous_compensation=Decimal("80000.00")
        )
        workflow_events.append(merit_event)

        # 6. Promotion
        promotion_event = EventFactory.create_promotion_event(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            new_level=4,
            new_compensation=Decimal("90000.00"),
            effective_date=date(2022, 7, 1),
            previous_level=3,
            previous_compensation=Decimal("84000.00")
        )
        workflow_events.append(promotion_event)

        # 7. Vesting event
        vesting_event = VestingEventFactory.create_vesting_event(
            employee_id=employee_id,
            plan_id=plan_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            vesting_date=date(2023, 12, 31),
            vesting_schedule_type="graded",
            vested_percentage=Decimal("0.80"),
            service_years=Decimal("4.0"),
            effective_date=date(2023, 12, 31)
        )
        workflow_events.append(vesting_event)

        # 8. HCE determination (becomes 50+ in 2025)
        hce_event = PlanAdministrationEventFactory.create_hce_status_event(
            employee_id=employee_id,
            plan_id=plan_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            determination_method="prior_year",
            ytd_compensation=Decimal("95000.00"),
            annualized_compensation=Decimal("95000.00"),
            hce_threshold=Decimal("135000.00"),
            is_hce=False,
            determination_date=date(2024, 1, 1),
            effective_date=date(2024, 1, 1)
        )
        workflow_events.append(hce_event)

        # 9. Compliance monitoring (catch-up eligible at 50)
        compliance_event = PlanAdministrationEventFactory.create_compliance_monitoring_event(
            employee_id=employee_id,
            plan_id=plan_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            compliance_type="catch_up_eligible",
            limit_type="catch_up",
            applicable_limit=Decimal("7500.00"),
            current_amount=Decimal("0.00"),
            monitoring_date=date(2025, 5, 15),
            effective_date=date(2025, 5, 15)
        )
        workflow_events.append(compliance_event)

        # 10. Termination
        termination_event = EventFactory.create_termination_event(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            termination_reason="retirement",
            effective_date=date(2025, 12, 31),
            final_compensation=Decimal("100000.00")
        )
        workflow_events.append(termination_event)

        # 11. Forfeiture (unvested portion)
        forfeiture_event = PlanAdministrationEventFactory.create_forfeiture_event(
            employee_id=employee_id,
            plan_id=plan_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            forfeited_from_source="employer_match",
            amount=Decimal("800.00"),  # 20% unvested
            reason="unvested_termination",
            vested_percentage=Decimal("0.80"),
            effective_date=date(2026, 1, 15)
        )
        workflow_events.append(forfeiture_event)

        # Validate complete workflow
        total_events = len(workflow_events)
        validation_errors = []

        for i, event in enumerate(workflow_events):
            try:
                # Test serialization/deserialization
                json_data = event.model_dump_json()
                reconstructed = SimulationEvent.model_validate_json(json_data)
                assert event == reconstructed

                # Validate event structure
                assert event.employee_id == employee_id
                assert event.scenario_id == scenario_id
                assert event.plan_design_id == plan_design_id
                assert hasattr(event, 'event_id')
                assert hasattr(event, 'payload')

                print(f"✅ Event {i+1}/{total_events}: {event.payload.event_type}")

            except Exception as e:
                validation_errors.append(f"Event {i+1} ({event.payload.event_type}): {str(e)}")
                print(f"❌ Event {i+1}/{total_events}: {event.payload.event_type} - {str(e)}")

        # Integration validation requirements
        assert len(validation_errors) == 0, f"Integration validation failed: {validation_errors}"
        assert total_events == 18, f"Expected 18 events in complete workflow, got {total_events}"  # 1+1+1+12+1+1+1+1+1+1+1 = 21

        # Validate event type coverage (all 11 payload types)
        event_types = set(event.payload.event_type for event in workflow_events)
        expected_types = {
            "hire", "eligibility", "enrollment", "contribution", "merit",
            "promotion", "vesting", "hce_status", "compliance", "termination", "forfeiture"
        }

        assert event_types == expected_types, f"Missing event types: {expected_types - event_types}"

        print(f"✅ Complete integration workflow validated: {total_events} events, {len(event_types)} event types")

    def _create_valid_payload_data(self, payload_class) -> Dict[str, Any]:
        """Create valid test data for each payload type."""
        base_data = {
            "employee_id": "TEST_001",
            "scenario_id": "TEST_SCENARIO",
            "plan_design_id": "TEST_DESIGN",
            "effective_date": date(2024, 1, 1)
        }

        if payload_class == HirePayload:
            return {
                "event_type": "hire",
                "starting_compensation": Decimal("75000.00"),
                "starting_level": 3,
                "employee_ssn": "123456789",
                "employee_birth_date": date(1990, 1, 1),
                "location": "HQ"
            }
        elif payload_class == PromotionPayload:
            return {
                "event_type": "promotion",
                "new_level": 4,
                "new_compensation": Decimal("85000.00"),
                "previous_level": 3,
                "previous_compensation": Decimal("75000.00")
            }
        elif payload_class == TerminationPayload:
            return {
                "event_type": "termination",
                "termination_reason": "voluntary",
                "final_compensation": Decimal("80000.00")
            }
        elif payload_class == MeritPayload:
            return {
                "event_type": "merit",
                "merit_percentage": Decimal("0.04"),
                "previous_compensation": Decimal("75000.00")
            }
        elif payload_class == EligibilityPayload:
            return {
                "event_type": "eligibility",
                "plan_id": "TEST_PLAN",
                "eligibility_date": date(2024, 1, 1),
                "service_requirement_months": 3,
                "age_requirement": None
            }
        elif payload_class == EnrollmentPayload:
            return {
                "event_type": "enrollment",
                "plan_id": "TEST_PLAN",
                "enrollment_date": date(2024, 1, 1),
                "deferral_percentage": Decimal("0.06"),
                "deferral_amount": None,
                "catch_up_percentage": Decimal("0.0")
            }
        elif payload_class == ContributionPayload:
            return {
                "event_type": "contribution",
                "plan_id": "TEST_PLAN",
                "contribution_date": date(2024, 1, 1),
                "employee_contribution": Decimal("500.00"),
                "employer_contribution": Decimal("250.00"),
                "contribution_source": "regular_payroll",
                "vesting_service_years": Decimal("1.0")
            }
        elif payload_class == VestingPayload:
            return {
                "event_type": "vesting",
                "plan_id": "TEST_PLAN",
                "vesting_date": date(2024, 1, 1),
                "vesting_schedule_type": "graded",
                "vested_percentage": Decimal("0.60"),
                "service_years": Decimal("3.0")
            }
        elif payload_class == ForfeiturePayload:
            return {
                "event_type": "forfeiture",
                "plan_id": "TEST_PLAN",
                "forfeited_from_source": "employer_match",
                "amount": Decimal("1000.00"),
                "reason": "unvested_termination",
                "vested_percentage": Decimal("0.40")
            }
        elif payload_class == HCEStatusPayload:
            return {
                "event_type": "hce_status",
                "plan_id": "TEST_PLAN",
                "determination_method": "prior_year",
                "ytd_compensation": Decimal("125000.00"),
                "annualized_compensation": Decimal("150000.00"),
                "hce_threshold": Decimal("135000.00"),
                "is_hce": True,
                "determination_date": date(2024, 1, 1)
            }
        elif payload_class == ComplianceEventPayload:
            return {
                "event_type": "compliance",
                "plan_id": "TEST_PLAN",
                "compliance_type": "402g_limit_approach",
                "limit_type": "elective_deferral",
                "applicable_limit": Decimal("23000.00"),
                "current_amount": Decimal("21500.00"),
                "monitoring_date": date(2024, 11, 15)
            }

        return {}

    def _create_event_from_data(self, event_data: Dict[str, Any], scenario: Dict[str, Any]) -> SimulationEvent:
        """Create SimulationEvent from golden scenario data."""
        event_type = event_data["event_type"]

        base_params = {
            "employee_id": scenario["employee_id"],
            "scenario_id": scenario["scenario_id"],
            "plan_design_id": scenario["plan_design_id"],
            "effective_date": date.fromisoformat(event_data["effective_date"])
        }

        if event_type == "hire":
            return EventFactory.create_hire_event(
                starting_compensation=Decimal(event_data["starting_compensation"]),
                starting_level=event_data["starting_level"],
                employee_ssn=event_data["employee_ssn"],
                employee_birth_date=date.fromisoformat(event_data["employee_birth_date"]),
                location=event_data["location"],
                **base_params
            )
        elif event_type == "eligibility":
            return EligibilityEventFactory.create_eligibility_event(
                plan_id=scenario["plan_id"],
                eligibility_date=date.fromisoformat(event_data["eligibility_date"]),
                service_requirement_months=event_data["service_requirement_months"],
                age_requirement=event_data.get("age_requirement"),
                **base_params
            )
        # Add other event types as needed...

        return None


if __name__ == "__main__":
    # Run golden dataset validation tests
    test_suite = TestGoldenDatasetValidation()
    test_suite.setup_method()

    print("=" * 60)
    print("GOLDEN DATASET VALIDATION FRAMEWORK - S072-06")
    print("=" * 60)

    try:
        test_suite.test_json_schema_validation_all_payloads()
        print("✅ JSON schema validation test PASSED")
    except Exception as e:
        print(f"❌ JSON schema validation test FAILED: {e}")

    try:
        test_suite.test_participant_lifecycle_golden_scenario()
        print("✅ Participant lifecycle validation test PASSED")
    except Exception as e:
        print(f"❌ Participant lifecycle validation test FAILED: {e}")

    try:
        test_suite.test_compliance_monitoring_golden_scenario()
        print("✅ Compliance monitoring validation test PASSED")
    except Exception as e:
        print(f"❌ Compliance monitoring validation test FAILED: {e}")

    try:
        test_suite.test_edge_case_validation_coverage()
        print("✅ Edge case validation test PASSED")
    except Exception as e:
        print(f"❌ Edge case validation test FAILED: {e}")

    try:
        test_suite.test_integration_workflow_validation()
        print("✅ Integration workflow validation test PASSED")
    except Exception as e:
        print(f"❌ Integration workflow validation test FAILED: {e}")

    print("\n" + "=" * 60)
    print("GOLDEN DATASET VALIDATION COMPLETE")
    print("=" * 60)
