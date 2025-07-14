# Story S072-07: ERISA Compliance Review & Documentation

**Epic**: E021-A - DC Plan Event Schema Foundation
**Status**: ✅ Completed
**Priority**: High
**Dependencies**: S072-06 (Completed)
**Completion Date**: 2025-07-14

## 1\. Story Definition

**As a** compliance officer,
**I want** comprehensive ERISA compliance validation and documentation for the event schema
**So that** we meet all fiduciary requirements and can pass regulatory audits with complete confidence.

## 2\. Core Objectives & Acceptance Criteria

### ERISA Compliance Validation

  - [ ] **Benefits Counsel Review**: A qualified ERISA attorney completes a review and signs the approval checklist.
  - [ ] **Fiduciary Compliance**: All administrative event types are verified for fiduciary compliance.
  - [ ] **Audit Trail Coverage**: The event schema provides a complete audit trail to ensure participant protection.
  - [ ] **DOL Reporting**: The event schema's design addresses all Department of Labor (DOL) reporting requirements.

### Regulatory & Security Coverage

  - [ ] **IRS & ERISA Codes**: Events are correctly categorized for IRS (402(g), 415(c)) and ERISA (404(c)) compliance.
  - [ ] **Data Retention**: Data retention policies for the 7-year ERISA requirement are established.
  - [ ] **PII Classification**: Personally Identifiable Information (PII) is classified, with SSN as "RESTRICTED" and compensation as "CONFIDENTIAL".
  - [ ] **Security Standards**: Data encryption and role-based access controls are documented and verified.

### Audit Readiness & Documentation

  - [ ] **Compliance Documentation**: A complete compliance document with regulatory references is created.
  - [ ] **Audit Procedures**: Procedures for responding to DOL inquiries using the event audit trail are documented.
  - [ ] **Breach Response**: Procedures for handling compliance violations are documented.

## 3\. Technical Specifications

### ERISA Compliance Checklist Model

```python
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import date, datetime
from enum import Enum

class ERISAComplianceLevel(str, Enum):
    COMPLIANT = "compliant"
    NEEDS_REVIEW = "needs_review"
    NON_COMPLIANT = "non_compliant"
    NOT_APPLICABLE = "not_applicable"

class ERISARequirement(BaseModel):
    """Defines an individual ERISA compliance requirement."""
    requirement_id: str
    section_reference: str  # e.g., "ERISA Section 404(c)"
    description: str
    compliance_level: ERISAComplianceLevel
    event_types_covered: List[str]
    validation_notes: str
    reviewer_name: Optional[str] = None
    review_date: Optional[date] = None
    remediation_required: bool = False
    remediation_notes: Optional[str] = None

class ERISAComplianceChecklist(BaseModel):
    """Represents the complete ERISA compliance validation checklist for the event schema."""
    checklist_version: str = "1.0"
    review_date: date
    reviewed_by: str  # Name of the benefits counsel
    plan_sponsor: str
    requirements: List[ERISARequirement] = Field(default_factory=list)
    overall_compliance: ERISAComplianceLevel
    approval_granted: bool = False
    approval_conditions: List[str] = Field(default_factory=list)
    counsel_signature: Optional[str] = None
    signature_date: Optional[datetime] = None
    next_review_date: Optional[date] = None
```

### Data Classification & Security Model

```python
class DataClassificationManager:
    """Manages data classification and security rules for ERISA compliance."""
    def __init__(self):
        self.classification_rules = self._get_classification_rules()

    def _get_classification_rules(self) -> Dict[str, Dict[str, Any]]:
        """Initializes data classification rules for sensitive event fields."""
        return {
            # Restricted PII - Highest protection level
            "ssn": {
                "classification": "RESTRICTED", "encryption_required": True,
                "access_roles": ["admin", "auditor"], "retention_years": 7,
                "erisa_reference": "ERISA Section 107 - Recordkeeping"
            },
            "birth_date": {
                "classification": "RESTRICTED", "encryption_required": True,
                "access_roles": ["admin", "auditor"], "retention_years": 7,
                "erisa_reference": "ERISA Section 107 - Recordkeeping"
            },
            # Confidential Data
            "annual_compensation": {
                "classification": "CONFIDENTIAL", "encryption_required": True,
                "access_roles": ["admin", "analyst", "auditor"], "retention_years": 7,
                "erisa_reference": "ERISA Section 204 - HCE determination"
            },
            "contribution_amount": {
                "classification": "CONFIDENTIAL", "encryption_required": True,
                "access_roles": ["admin", "analyst", "auditor"], "retention_years": 7,
                "erisa_reference": "ERISA Section 101 - Benefit statements"
            },
            # Internal Administrative Data
            "employee_id": {
                "classification": "INTERNAL", "encryption_required": False,
                "access_roles": ["admin", "analyst", "developer"], "retention_years": 7,
                "erisa_reference": "ERISA Section 107 - Recordkeeping"
            }
        }

    def validate_field(self, field_name: str) -> Dict[str, Any]:
        """Validates a field against its classification requirements."""
        default_classification = {
            "classification": "INTERNAL", "encryption_required": False,
            "access_roles": ["admin", "developer"], "retention_years": 7,
            "erisa_reference": "General recordkeeping"
        }
        classification = self.classification_rules.get(field_name, default_classification)

        return {
            "field_name": field_name,
            "classification": classification["classification"],
            "requirements": {
                "encryption": classification["encryption_required"],
                "retention_years": classification["retention_years"],
                "access_roles": classification["access_roles"]
            },
            "erisa_reference": classification["erisa_reference"]
        }
```

## 4\. Implementation Plan

### Phase 1: Analysis and Validation

  - [ ] **Map Requirements**: Map all event types to the specific ERISA sections they cover.
  - [ ] **Analyze Gaps**: Identify and document any gaps in compliance.
  - [ ] **Document References**: Create a regulatory reference map for each requirement.

### Phase 2: Legal and Counsel Review

  - [ ] **Schedule Review**: Schedule a formal consultation with a qualified ERISA attorney.
  - [ ] **Present Schema**: Present the event schema design and compliance analysis to counsel.
  - [ ] **Incorporate Feedback**: Address all feedback from counsel and implement required changes.
  - [ ] **Obtain Sign-off**: Secure a signed compliance approval, documenting any conditions.

### Phase 3: Documentation and Procedure Development

  - [ ] **Create Compliance Guide**: Develop a comprehensive guide with all regulatory references.
  - [ ] **Document Audit Procedures**: Create formal procedures for using the audit trail to respond to DOL inquiries.
  - [ ] **Establish Policies**: Finalize and document data retention and breach response policies.

## 5\. Dependencies

  * **Story S072-06**: Requires the completed Performance & Validation Framework.
  * **External**: Dependent on the availability of a qualified ERISA attorney for benefits counsel review.

## 6\. Definition of Done

  - [ ] **Checklist Complete**: The ERISA compliance checklist is fully populated and validated.
  - [ ] **Counsel Approval**: The benefits counsel review is complete, with signed approval obtained.
  - [ ] **Gaps Remediated**: All identified compliance gaps have been addressed with documented solutions.
  - [ ] **PII Classified**: All sensitive data fields have been classified according to the security framework.
  - [ ] **Procedures Documented**: Audit, data retention, and breach response procedures are finalized and documented.
