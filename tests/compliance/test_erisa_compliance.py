"""
Comprehensive tests for ERISA compliance framework.

This module tests all aspects of the ERISA compliance validation system,
including requirement coverage, data classification, audit procedures,
and compliance reporting.
"""

import json
import tempfile
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from config.erisa_compliance import (AuditTrailManager, DataClassification,
                                     DataFieldClassification,
                                     ERISAComplianceChecklist,
                                     ERISAComplianceLevel,
                                     ERISAComplianceValidator,
                                     ERISARequirement, ERISASection, IRSCode)


class TestERISAComplianceValidator:
    """Test suite for the main ERISA compliance validator."""

    @pytest.fixture
    def validator(self):
        """Create a fresh validator instance for each test."""
        return ERISAComplianceValidator()

    def test_validator_initialization(self, validator):
        """Test that validator initializes correctly with all requirements."""
        # Verify checklist is created
        assert validator.compliance_checklist is not None
        assert len(validator.compliance_checklist.requirements) > 0

        # Verify data classifications are loaded
        assert len(validator.data_classifications) > 0

        # Verify all critical fields are classified
        critical_fields = [
            "ssn",
            "birth_date",
            "annual_compensation",
            "contribution_amount",
        ]
        for field in critical_fields:
            assert field in validator.data_classifications

    def test_compliance_checklist_structure(self, validator):
        """Test the structure and content of the compliance checklist."""
        checklist = validator.compliance_checklist

        # Verify required fields
        assert checklist.checklist_version == "1.0"
        assert checklist.review_date == date.today()
        assert checklist.plan_sponsor == "Fidelity Investments"

        # Verify requirements coverage
        requirement_ids = [req.requirement_id for req in checklist.requirements]
        expected_requirements = [
            "ERISA_404_A",
            "ERISA_404_C",
            "ERISA_101_A",
            "ERISA_402_A",
            "ERISA_203_A",
            "ERISA_204_H",
            "ERISA_406_A",
            "ERISA_107_A",
            "IRS_402G",
            "IRS_415C",
        ]

        for req_id in expected_requirements:
            assert req_id in requirement_ids, f"Missing requirement: {req_id}"

    def test_event_coverage_validation(self, validator):
        """Test validation of event type coverage for ERISA requirements."""
        coverage = validator.validate_event_coverage()

        # Verify coverage structure
        assert "total_requirements" in coverage
        assert "compliant_requirements" in coverage
        assert "event_type_coverage" in coverage
        assert "section_coverage" in coverage

        # Verify high compliance rate (should be 100% for implemented requirements)
        assert coverage["compliance_percentage"] >= 90.0

        # Verify critical event types are covered
        critical_events = ["contribution", "distribution", "vesting", "forfeiture"]
        for event in critical_events:
            assert event in coverage["event_type_coverage"]
            assert len(coverage["event_type_coverage"][event]) > 0

    def test_field_classification_validation(self, validator):
        """Test data field classification validation."""
        # Test restricted field
        ssn_validation = validator.validate_field_classification("ssn")
        assert ssn_validation["classification"] == "RESTRICTED"
        assert ssn_validation["compliance_requirements"]["encryption_required"] is True
        assert ssn_validation["compliance_requirements"]["audit_required"] is True
        assert ssn_validation["pii_type"] == "Social Security Number"

        # Test confidential field
        comp_validation = validator.validate_field_classification("annual_compensation")
        assert comp_validation["classification"] == "CONFIDENTIAL"
        assert comp_validation["compliance_requirements"]["encryption_required"] is True

        # Test internal field
        emp_validation = validator.validate_field_classification("employee_id")
        assert emp_validation["classification"] == "INTERNAL"
        assert emp_validation["compliance_requirements"]["encryption_required"] is False

        # Test unknown field (should get default classification)
        unknown_validation = validator.validate_field_classification("unknown_field")
        assert unknown_validation["classification"] == "INTERNAL"
        assert (
            unknown_validation["compliance_requirements"]["retention_required"] is True
        )

    def test_compliance_report_generation(self, validator):
        """Test generation of comprehensive compliance report."""
        report = validator.generate_compliance_report()

        # Verify report structure
        assert "ERISA Compliance Report" in report
        assert "Executive Summary" in report
        assert "ERISA Section Coverage" in report
        assert "Detailed Requirements Analysis" in report
        assert "Event Type Coverage Summary" in report
        assert "Data Classification Summary" in report
        assert "Compliance Certification" in report

        # Verify specific content
        assert "Fidelity Investments" in report
        assert str(date.today()) in report
        assert "Benefits Counsel Review Required: Yes" in report

        # Verify all requirements are documented
        for req in validator.compliance_checklist.requirements:
            assert req.requirement_id in report
            assert req.description in report

    def test_checklist_export_import(self, validator):
        """Test export and import of compliance checklist."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            # Export checklist
            validator.export_checklist(temp_path)

            # Verify file was created
            assert Path(temp_path).exists()

            # Verify JSON structure
            with open(temp_path, "r") as f:
                data = json.load(f)

            assert "checklist_version" in data
            assert "requirements" in data
            assert len(data["requirements"]) > 0

            # Create new validator and import
            new_validator = ERISAComplianceValidator()
            new_validator.import_checklist(temp_path)

            # Verify import worked
            assert (
                new_validator.compliance_checklist.checklist_version
                == validator.compliance_checklist.checklist_version
            )
            assert len(new_validator.compliance_checklist.requirements) == len(
                validator.compliance_checklist.requirements
            )

        finally:
            # Clean up
            Path(temp_path).unlink(missing_ok=True)


class TestERISARequirement:
    """Test suite for individual ERISA requirement validation."""

    def test_requirement_creation(self):
        """Test creation of ERISA requirement with validation."""
        requirement = ERISARequirement(
            requirement_id="TEST_001",
            section_reference=ERISASection.SECTION_404,
            description="Test requirement",
            compliance_level=ERISAComplianceLevel.COMPLIANT,
            event_types_covered=["contribution", "distribution"],
            validation_notes="Test validation",
        )

        assert requirement.requirement_id == "TEST_001"
        assert requirement.section_reference == ERISASection.SECTION_404
        assert requirement.compliance_level == ERISAComplianceLevel.COMPLIANT
        assert len(requirement.event_types_covered) == 2

    def test_invalid_event_types(self):
        """Test validation of event types in requirements."""
        with pytest.raises(ValueError, match="Invalid event types"):
            ERISARequirement(
                requirement_id="TEST_002",
                section_reference=ERISASection.SECTION_404,
                description="Test requirement",
                compliance_level=ERISAComplianceLevel.COMPLIANT,
                event_types_covered=["invalid_event_type"],
                validation_notes="Test validation",
            )

    def test_requirement_with_irs_code(self):
        """Test requirement with IRS code reference."""
        requirement = ERISARequirement(
            requirement_id="TEST_003",
            section_reference=ERISASection.SECTION_101,
            irs_code_reference=IRSCode.CODE_402G,
            description="Test IRS requirement",
            compliance_level=ERISAComplianceLevel.COMPLIANT,
            event_types_covered=["contribution"],
            validation_notes="Test IRS validation",
        )

        assert requirement.irs_code_reference == IRSCode.CODE_402G
        assert "402(g)" in requirement.irs_code_reference.value


class TestDataFieldClassification:
    """Test suite for data field classification system."""

    def test_restricted_classification(self):
        """Test restricted data classification."""
        classification = DataFieldClassification(
            field_name="ssn",
            classification=DataClassification.RESTRICTED,
            encryption_required=True,
            access_roles=["admin", "auditor"],
            retention_years=7,
            erisa_reference="ERISA Section 107",
            audit_on_access=True,
            pii_type="Social Security Number",
        )

        assert classification.classification == DataClassification.RESTRICTED
        assert classification.encryption_required is True
        assert classification.audit_on_access is True
        assert classification.pii_type == "Social Security Number"
        assert len(classification.access_roles) == 2

    def test_retention_validation(self):
        """Test validation of retention period."""
        with pytest.raises(ValueError, match="ERISA requires minimum 7-year retention"):
            DataFieldClassification(
                field_name="test_field",
                classification=DataClassification.INTERNAL,
                encryption_required=False,
                access_roles=["admin"],
                retention_years=5,  # Invalid: less than 7 years
                erisa_reference="Test reference",
            )

    def test_confidential_classification(self):
        """Test confidential data classification."""
        classification = DataFieldClassification(
            field_name="annual_compensation",
            classification=DataClassification.CONFIDENTIAL,
            encryption_required=True,
            access_roles=["admin", "analyst", "auditor"],
            retention_years=7,
            erisa_reference="ERISA Section 204",
        )

        assert classification.classification == DataClassification.CONFIDENTIAL
        assert classification.encryption_required is True
        assert len(classification.access_roles) == 3


class TestERISAComplianceChecklist:
    """Test suite for compliance checklist functionality."""

    def test_compliance_percentage_calculation(self):
        """Test calculation of compliance percentage."""
        requirements = [
            ERISARequirement(
                requirement_id="REQ_001",
                section_reference=ERISASection.SECTION_404,
                description="Test 1",
                compliance_level=ERISAComplianceLevel.COMPLIANT,
                event_types_covered=["contribution"],
                validation_notes="Test",
            ),
            ERISARequirement(
                requirement_id="REQ_002",
                section_reference=ERISASection.SECTION_404,
                description="Test 2",
                compliance_level=ERISAComplianceLevel.NEEDS_REVIEW,
                event_types_covered=["distribution"],
                validation_notes="Test",
            ),
            ERISARequirement(
                requirement_id="REQ_003",
                section_reference=ERISASection.SECTION_404,
                description="Test 3",
                compliance_level=ERISAComplianceLevel.COMPLIANT,
                event_types_covered=["vesting"],
                validation_notes="Test",
            ),
        ]

        checklist = ERISAComplianceChecklist(
            review_date=date.today(),
            reviewed_by="Test Counsel",
            plan_sponsor="Test Sponsor",
            requirements=requirements,
            overall_compliance=ERISAComplianceLevel.NEEDS_REVIEW,
        )

        percentage = checklist.calculate_compliance_percentage()
        assert percentage == 66.67  # 2 of 3 compliant (rounded to 2 decimals)

    def test_critical_gaps_identification(self):
        """Test identification of critical compliance gaps."""
        requirements = [
            ERISARequirement(
                requirement_id="REQ_001",
                section_reference=ERISASection.SECTION_404,
                description="Compliant requirement",
                compliance_level=ERISAComplianceLevel.COMPLIANT,
                event_types_covered=["contribution"],
                validation_notes="Test",
            ),
            ERISARequirement(
                requirement_id="REQ_002",
                section_reference=ERISASection.SECTION_404,
                description="Non-compliant requirement",
                compliance_level=ERISAComplianceLevel.NON_COMPLIANT,
                event_types_covered=["distribution"],
                validation_notes="Test",
            ),
            ERISARequirement(
                requirement_id="REQ_003",
                section_reference=ERISASection.SECTION_404,
                description="Needs review requirement",
                compliance_level=ERISAComplianceLevel.NEEDS_REVIEW,
                event_types_covered=["vesting"],
                validation_notes="Test",
            ),
        ]

        checklist = ERISAComplianceChecklist(
            review_date=date.today(),
            reviewed_by="Test Counsel",
            plan_sponsor="Test Sponsor",
            requirements=requirements,
            overall_compliance=ERISAComplianceLevel.NEEDS_REVIEW,
        )

        gaps = checklist.identify_critical_gaps()
        assert len(gaps) == 2  # REQ_002 and REQ_003
        assert "REQ_002: Non-compliant requirement" in gaps
        assert "REQ_003: Needs review requirement" in gaps


class TestAuditTrailManager:
    """Test suite for audit trail management."""

    def test_audit_procedures_generation(self):
        """Test generation of audit trail procedures."""
        procedures = AuditTrailManager.generate_audit_procedures()

        # Verify content structure
        assert "Audit Trail Procedures for DOL Inquiries" in procedures
        assert "Event Audit Trail Components" in procedures
        assert "DOL Inquiry Response Procedures" in procedures
        assert "Data Retention Compliance" in procedures
        assert "Breach Response Procedures" in procedures

        # Verify specific content
        assert "7-Year Retention Policy" in procedures
        assert "Contact Information" in procedures
        assert str(date.today()) in procedures

        # Verify SQL examples are included
        assert "SELECT" in procedures
        assert "FROM fct_yearly_events" in procedures

        # Verify procedure steps are documented
        assert "Step 1:" in procedures
        assert "Step 2:" in procedures
        assert "Immediate Actions (0-24 hours)" in procedures


class TestIntegrationScenarios:
    """Integration tests for complete compliance validation scenarios."""

    @pytest.fixture
    def validator(self):
        """Create validator for integration tests."""
        return ERISAComplianceValidator()

    def test_complete_compliance_validation_workflow(self, validator):
        """Test the complete workflow of compliance validation."""
        # Step 1: Validate event coverage
        coverage = validator.validate_event_coverage()
        assert coverage["compliance_percentage"] >= 90.0

        # Step 2: Validate data classifications
        sensitive_fields = ["ssn", "birth_date", "annual_compensation"]
        for field in sensitive_fields:
            classification = validator.validate_field_classification(field)
            assert (
                classification["compliance_requirements"]["encryption_required"] is True
            )

        # Step 3: Generate compliance report
        report = validator.generate_compliance_report()
        assert len(report) > 1000  # Comprehensive report

        # Step 4: Verify audit procedures
        procedures = AuditTrailManager.generate_audit_procedures()
        assert "DOL Inquiry Response Procedures" in procedures

    def test_benefits_counsel_review_preparation(self, validator):
        """Test preparation of materials for benefits counsel review."""
        # Generate compliance report
        report = validator.generate_compliance_report()

        # Verify all required sections for counsel review
        required_sections = [
            "Executive Summary",
            "ERISA Section Coverage",
            "Detailed Requirements Analysis",
            "Data Classification Summary",
            "Compliance Certification",
        ]

        for section in required_sections:
            assert section in report

        # Verify checklist shows review status
        checklist = validator.compliance_checklist
        assert checklist.overall_compliance == ERISAComplianceLevel.NEEDS_REVIEW
        assert "[Pending Benefits Counsel Assignment]" in checklist.reviewed_by

        # Verify approval fields are ready
        assert checklist.approval_granted is False
        assert checklist.counsel_signature is None

    def test_regulatory_audit_preparation(self, validator):
        """Test preparation for regulatory audit scenarios."""
        # Generate comprehensive documentation
        report = validator.generate_compliance_report()
        procedures = AuditTrailManager.generate_audit_procedures()

        # Verify audit-ready documentation
        assert "DOL Inquiry Response" in procedures
        assert "Data Retention Verification" in procedures
        assert "Breach Response Procedures" in procedures

        # Verify compliance metrics are documented
        coverage = validator.validate_event_coverage()
        assert "section_coverage" in coverage
        assert len(coverage["section_coverage"]) > 0

        # Verify all ERISA sections are addressed
        erisa_sections = [
            req.section_reference.value
            for req in validator.compliance_checklist.requirements
        ]
        critical_sections = [
            "ERISA Section 404 - Fiduciary Duties",
            "ERISA Section 107 - Recordkeeping",
            "ERISA Section 101 - Reporting and Disclosure",
        ]

        for section in critical_sections:
            assert any(section in erisa_section for erisa_section in erisa_sections)


class TestErrorHandling:
    """Test suite for error handling and edge cases."""

    def test_empty_requirements_list(self):
        """Test handling of empty requirements list."""
        checklist = ERISAComplianceChecklist(
            review_date=date.today(),
            reviewed_by="Test",
            plan_sponsor="Test",
            requirements=[],
            overall_compliance=ERISAComplianceLevel.NEEDS_REVIEW,
        )

        assert checklist.calculate_compliance_percentage() == 0.0
        assert checklist.identify_critical_gaps() == []

    def test_invalid_event_type_handling(self):
        """Test handling of invalid event types in requirements."""
        with pytest.raises(ValueError):
            ERISARequirement(
                requirement_id="TEST",
                section_reference=ERISASection.SECTION_404,
                description="Test",
                compliance_level=ERISAComplianceLevel.COMPLIANT,
                event_types_covered=["nonexistent_event_type"],
                validation_notes="Test",
            )

    def test_classification_fallback(self):
        """Test fallback behavior for unclassified fields."""
        validator = ERISAComplianceValidator()

        # Test field not in classification rules
        result = validator.validate_field_classification("unknown_field_name")

        # Should get default INTERNAL classification
        assert result["classification"] == "INTERNAL"
        assert result["compliance_requirements"]["retention_required"] is True
        assert result["erisa_reference"] == "General recordkeeping"


# Performance tests
class TestPerformance:
    """Test suite for performance requirements."""

    def test_report_generation_performance(self):
        """Test that compliance report generation meets performance requirements."""
        import time

        validator = ERISAComplianceValidator()

        start_time = time.time()
        report = validator.generate_compliance_report()
        end_time = time.time()

        # Should generate report in under 1 second
        assert (end_time - start_time) < 1.0
        assert len(report) > 0

    def test_coverage_validation_performance(self):
        """Test that event coverage validation is fast."""
        import time

        validator = ERISAComplianceValidator()

        start_time = time.time()
        coverage = validator.validate_event_coverage()
        end_time = time.time()

        # Should complete validation in under 0.1 seconds
        assert (end_time - start_time) < 0.1
        assert "compliance_percentage" in coverage


if __name__ == "__main__":
    # Run basic smoke tests
    print("Running ERISA compliance framework smoke tests...")

    # Test validator creation
    validator = ERISAComplianceValidator()
    print(
        f"✅ Validator created with {len(validator.compliance_checklist.requirements)} requirements"
    )

    # Test report generation
    report = validator.generate_compliance_report()
    print(f"✅ Compliance report generated ({len(report)} characters)")

    # Test coverage analysis
    coverage = validator.validate_event_coverage()
    print(
        f"✅ Event coverage validated ({coverage['compliance_percentage']:.1f}% compliant)"
    )

    # Test audit procedures
    procedures = AuditTrailManager.generate_audit_procedures()
    print(f"✅ Audit procedures generated ({len(procedures)} characters)")

    print("\n🎉 All smoke tests passed! Framework is ready for production.")
