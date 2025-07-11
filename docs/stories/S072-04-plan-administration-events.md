# Story S072-04: Plan Administration Events

**Epic**: E021-A - DC Plan Event Schema Foundation
**Story Points**: 5
**Priority**: High
**Sprint**: 2
**Owner**: DC Plan Team

## Story

**As a** plan administrator
**I want** administrative and compliance events for comprehensive plan management
**So that** I can track forfeitures, HCE determinations, IRS compliance violations, and annual plan testing

## Business Context

This story implements critical plan administration and compliance events that ensure proper plan governance and regulatory compliance. These events handle complex administrative scenarios including forfeiture processing, compliance monitoring, HCE status determination, and annual plan testing required by IRS regulations.

## Acceptance Criteria

### Administrative Event Coverage
- [ ] **ForfeiturePayload**: Unvested employer contribution recapture
- [ ] **HCEStatusPayload**: Highly compensated employee determination
- [ ] **ComplianceEventPayload**: IRS limit violations and corrections
- [ ] **PlanComplianceTestPayload**: Annual ADP/ACP/TopHeavy testing

### Regulatory Compliance Features
- [ ] **Forfeiture source validation** for employer contributions only
- [ ] **HCE determination methods** supporting prior-year and current-year
- [ ] **IRS compliance types** including 402(g), 415(c), and compensation limits
- [ ] **Plan testing coverage** for ADP, ACP, and TopHeavy requirements

### Enterprise Administration
- [ ] **Corrective action tracking** with deadlines and affected sources
- [ ] **Annual determination** processes with calculation details
- [ ] **Plan year context** for all compliance and testing events
- [ ] **Compensation limit handling** including 401(a)(17) tracking

## Technical Specifications

### Plan Administration Event Payloads

```python
from typing import Literal, Optional, List
from pydantic import BaseModel, Field
from datetime import date
from decimal import Decimal

class ForfeiturePayload(BaseModel):
    """Unvested employer contribution recapture"""

    event_type: Literal["forfeiture"] = "forfeiture"
    plan_id: str = Field(..., min_length=1)
    forfeited_from_source: Literal[
        "employer_match",
        "employer_nonelective",
        "employer_profit_sharing"
    ]
    amount: Decimal = Field(..., gt=0, decimal_places=6)
    reason: Literal["unvested_termination", "break_in_service"]
    vested_percentage: Decimal = Field(..., ge=0, le=1, decimal_places=4)

class HCEStatusPayload(BaseModel):
    """Highly compensated employee determination"""

    event_type: Literal["hce_status"] = "hce_status"
    plan_id: str = Field(..., min_length=1)
    determination_method: Literal["prior_year", "current_year"]
    ytd_compensation: Decimal = Field(..., ge=0, decimal_places=6)
    annualized_compensation: Decimal = Field(..., ge=0, decimal_places=6)
    hce_threshold: Decimal = Field(..., gt=0, decimal_places=6)
    is_hce: bool
    determination_date: date
    prior_year_hce: Optional[bool] = None

class ComplianceEventPayload(BaseModel):
    """IRS limit violations and corrections"""

    event_type: Literal["compliance"] = "compliance"
    plan_id: str = Field(..., min_length=1)
    compliance_type: Literal[
        "402g_excess",           # Elective deferral limit exceeded
        "415c_excess",           # Annual additions limit exceeded
        "catch_up_eligible",     # Participant becomes catch-up eligible
        "contribution_capped",   # Contribution capped at limit
        "compensation_capped"    # 401(a)(17) compensation limit applied
    ]
    limit_type: Literal[
        "elective_deferral",
        "annual_additions",
        "catch_up",
        "compensation"
    ]
    applicable_limit: Decimal = Field(..., gt=0, decimal_places=6)
    current_amount: Decimal = Field(..., ge=0, decimal_places=6)
    excess_amount: Optional[Decimal] = Field(None, ge=0, decimal_places=6)
    corrective_action: Optional[Literal[
        "refund",        # Return excess to participant
        "reallocation",  # Reallocate employer contributions
        "cap",           # Cap future contributions
        "none"           # No action required
    ]] = None
    affected_sources: List[str] = Field(default_factory=list)
    correction_deadline: Optional[date] = None

class PlanComplianceTestPayload(BaseModel):
    """Annual ADP/ACP/TopHeavy testing"""

    event_type: Literal["plan_compliance_test"] = "plan_compliance_test"
    plan_id: str = Field(..., min_length=1)
    test_type: Literal["ADP", "ACP", "TopHeavy"]
    plan_year: int = Field(..., ge=2020, le=2050)
    test_passed: bool
    hce_group_metric: Decimal = Field(..., ge=0, le=1, decimal_places=4)
    nhce_group_metric: Decimal = Field(..., ge=0, le=1, decimal_places=4)
    corrective_action_taken: Optional[Literal[
        "qnec",     # Qualified non-elective contribution
        "qmac",     # Qualified matching contribution
        "refunds"   # Excess contribution refunds
    ]] = None

# Additional Critical Event Types for Production Readiness
class LoanDefaultPayload(BaseModel):
    """Deemed distribution from loan default"""

    event_type: Literal["loan_default"] = "loan_default"
    plan_id: str = Field(..., min_length=1)
    loan_id: str = Field(..., min_length=1)
    default_date: date
    outstanding_balance_at_default: Decimal = Field(..., ge=0, decimal_places=6)
    accrued_interest_at_default: Decimal = Field(..., ge=0, decimal_places=6)

class RMDDeterminationPayload(BaseModel):
    """Required minimum distribution calculation"""

    event_type: Literal["rmd_determination"] = "rmd_determination"
    plan_id: str = Field(..., min_length=1)
    plan_year: int = Field(..., ge=2020, le=2050)
    age_at_year_end: int = Field(..., ge=70, le=120)
    required_beginning_date: date
    calculated_rmd_amount: Decimal = Field(..., ge=0, decimal_places=6)
```

### Plan Administration Event Factory

```python
class PlanAdministrationEventFactory(EventFactory):
    """Factory for creating plan administration events"""

    @staticmethod
    def create_forfeiture_event(
        employee_id: str,
        plan_id: str,
        scenario_id: str,
        plan_design_id: str,
        forfeited_from_source: str,
        amount: Decimal,
        reason: str,
        vested_percentage: Decimal,
        effective_date: date
    ) -> SimulationEvent:
        """Create forfeiture event for unvested contributions"""

        payload = ForfeiturePayload(
            plan_id=plan_id,
            forfeited_from_source=forfeited_from_source,
            amount=amount,
            reason=reason,
            vested_percentage=vested_percentage
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=effective_date,
            source_system="plan_administration",
            payload=payload
        )

    @staticmethod
    def create_compliance_event(
        employee_id: str,
        plan_id: str,
        scenario_id: str,
        plan_design_id: str,
        compliance_type: str,
        limit_type: str,
        applicable_limit: Decimal,
        current_amount: Decimal,
        effective_date: date,
        excess_amount: Optional[Decimal] = None,
        corrective_action: Optional[str] = None,
        affected_sources: Optional[List[str]] = None,
        correction_deadline: Optional[date] = None
    ) -> SimulationEvent:
        """Create compliance event for IRS violations"""

        payload = ComplianceEventPayload(
            plan_id=plan_id,
            compliance_type=compliance_type,
            limit_type=limit_type,
            applicable_limit=applicable_limit,
            current_amount=current_amount,
            excess_amount=excess_amount,
            corrective_action=corrective_action,
            affected_sources=affected_sources or [],
            correction_deadline=correction_deadline
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=effective_date,
            source_system="compliance_engine",
            payload=payload
        )

    @staticmethod
    def create_plan_test_event(
        plan_id: str,
        scenario_id: str,
        plan_design_id: str,
        test_type: str,
        plan_year: int,
        test_passed: bool,
        hce_group_metric: Decimal,
        nhce_group_metric: Decimal,
        effective_date: date,
        corrective_action_taken: Optional[str] = None
    ) -> SimulationEvent:
        """Create plan compliance test event"""

        payload = PlanComplianceTestPayload(
            plan_id=plan_id,
            test_type=test_type,
            plan_year=plan_year,
            test_passed=test_passed,
            hce_group_metric=hce_group_metric,
            nhce_group_metric=nhce_group_metric,
            corrective_action_taken=corrective_action_taken
        )

        return SimulationEvent(
            employee_id="PLAN_LEVEL_EVENT",  # Plan-level events use special employee_id
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=effective_date,
            source_system="compliance_testing",
            payload=payload
        )
```

## Implementation Tasks

### Phase 1: Administrative Payload Implementation
- [ ] **Create 4 core administrative payloads** (Forfeiture, HCE, Compliance, PlanTest)
- [ ] **Add 2 additional payloads** (LoanDefault, RMDDetermination)
- [ ] **Implement Literal event_type** fields for all 6 payloads
- [ ] **Add comprehensive field validation** with business rule constraints

### Phase 2: Compliance Features
- [ ] **Implement 5 compliance_type options** including compensation_capped
- [ ] **Add corrective action tracking** with deadlines and affected sources
- [ ] **Create HCE determination** with prior/current year methods
- [ ] **Add plan testing logic** for ADP/ACP/TopHeavy requirements

### Phase 3: Factory Methods & Integration
- [ ] **Create PlanAdministrationEventFactory** with all helper methods
- [ ] **Handle plan-level events** with special employee_id handling
- [ ] **Extend SimulationEvent discriminated union** with 6 new payloads
- [ ] **Test integration** with existing event infrastructure

### Phase 4: Advanced Features
- [ ] **Add loan default handling** with deemed distribution logic
- [ ] **Implement RMD determination** with age-based calculations
- [ ] **Create compliance deadline tracking** with automatic alerts
- [ ] **Add plan year validation** for time-sensitive operations

## Dependencies

### Story Dependencies
- **S072-01**: Core Event Model & Pydantic v2 Architecture (blocking)

### Domain Dependencies
- **IRS limits service**: For compliance threshold determination
- **Plan configuration**: For plan-specific rules and testing requirements
- **HCE engine**: For highly compensated employee calculations
- **Compliance engine**: For automated violation detection

## Success Metrics

### Administrative Functionality
- [ ] **Forfeiture processing** with source validation
- [ ] **HCE determination** with annualization support
- [ ] **Compliance monitoring** with automatic violation detection
- [ ] **Plan testing** with pass/fail determination

### Regulatory Compliance
- [ ] **IRS compliance coverage** for major violation types
- [ ] **ERISA plan testing** for ADP/ACP/TopHeavy
- [ ] **Corrective action tracking** with deadline management
- [ ] **Audit trail completeness** for all administrative actions

## Testing Strategy

### Unit Tests
- [ ] **Each administrative payload** creation and validation
- [ ] **Compliance type validation** for all 5 violation types
- [ ] **Plan testing logic** for ADP/ACP/TopHeavy scenarios
- [ ] **Factory method validation** for all administrative events

### Business Logic Tests
- [ ] **Forfeiture calculations** with vesting percentage accuracy
- [ ] **HCE determination** with compensation thresholds
- [ ] **Compliance violation** detection and correction logic
- [ ] **Plan testing calculations** with group metrics

### Integration Tests
- [ ] **Plan-level event handling** with special employee_id
- [ ] **Compliance deadline tracking** with automatic alerts
- [ ] **Administrative workflow** end-to-end testing
- [ ] **Event correlation** between compliance and corrective actions

## Regulatory Coverage

### IRS Requirements
- [ ] **402(g) limit enforcement** with excess deferral handling
- [ ] **415(c) limit enforcement** with annual additions tracking
- [ ] **401(a)(17) compensation limits** with capping logic
- [ ] **Catch-up contribution eligibility** with age-based determination

### ERISA Requirements
- [ ] **Plan testing compliance** for non-discrimination
- [ ] **Forfeiture allocation** according to plan terms
- [ ] **HCE determination** with proper calculation methods
- [ ] **Corrective action documentation** for audit compliance

## Definition of Done

- [ ] **All 6 administrative payloads** implemented and tested
- [ ] **SimulationEvent discriminated union** extended with administrative events
- [ ] **PlanAdministrationEventFactory** provides creation methods for all types
- [ ] **Regulatory compliance verified** for IRS and ERISA requirements
- [ ] **Plan-level event handling** working correctly
- [ ] **Integration tests passing** for all administrative scenarios
- [ ] **Documentation complete** with compliance examples and regulatory references
- [ ] **Code review approved** with compliance team validation

## Notes

These administrative events handle the most complex regulatory scenarios in DC plan management. The compliance and testing events are particularly critical for maintaining plan qualification status and avoiding IRS penalties. The factory methods include special handling for plan-level events that don't belong to individual participants.
