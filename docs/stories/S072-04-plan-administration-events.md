# Story S072-04: Plan Administration Events

**Epic**: E021-A - DC Plan Event Schema Foundation
**Story Points**: 5
**Priority**: High
**Sprint**: 2
**Owner**: DC Plan Team

## Story

**As a** plan administrator
**I want** administrative and compliance events for essential plan management
**So that** I can track forfeitures, HCE determinations, and basic compliance monitoring

## Business Context

This story implements essential plan administration events that support basic plan governance and compliance monitoring. These events handle core administrative scenarios including forfeiture processing and HCE status determination for regulatory compliance.

## Acceptance Criteria

### Administrative Event Coverage
- [ ] **ForfeiturePayload**: Unvested employer contribution recapture
- [ ] **HCEStatusPayload**: Highly compensated employee determination
- [ ] **ComplianceEventPayload**: Basic IRS limit monitoring

### Core Features
- [ ] **Forfeiture source validation** for employer contributions only
- [ ] **HCE determination methods** supporting prior-year and current-year
- [ ] **Basic compliance monitoring** for essential IRS limits

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
    """Basic IRS limit monitoring"""

    event_type: Literal["compliance"] = "compliance"
    plan_id: str = Field(..., min_length=1)
    compliance_type: Literal[
        "402g_limit_approach",    # Approaching elective deferral limit
        "415c_limit_approach",    # Approaching annual additions limit
        "catch_up_eligible"       # Participant becomes catch-up eligible
    ]
    limit_type: Literal[
        "elective_deferral",
        "annual_additions",
        "catch_up"
    ]
    applicable_limit: Decimal = Field(..., gt=0, decimal_places=6)
    current_amount: Decimal = Field(..., ge=0, decimal_places=6)
    monitoring_date: date
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
    def create_hce_status_event(
        employee_id: str,
        plan_id: str,
        scenario_id: str,
        plan_design_id: str,
        determination_method: str,
        ytd_compensation: Decimal,
        annualized_compensation: Decimal,
        hce_threshold: Decimal,
        is_hce: bool,
        determination_date: date,
        prior_year_hce: Optional[bool] = None
    ) -> SimulationEvent:
        """Create HCE status determination event"""

        payload = HCEStatusPayload(
            plan_id=plan_id,
            determination_method=determination_method,
            ytd_compensation=ytd_compensation,
            annualized_compensation=annualized_compensation,
            hce_threshold=hce_threshold,
            is_hce=is_hce,
            determination_date=determination_date,
            prior_year_hce=prior_year_hce
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=determination_date,
            source_system="hce_determination",
            payload=payload
        )

    @staticmethod
    def create_compliance_monitoring_event(
        employee_id: str,
        plan_id: str,
        scenario_id: str,
        plan_design_id: str,
        compliance_type: str,
        limit_type: str,
        applicable_limit: Decimal,
        current_amount: Decimal,
        monitoring_date: date
    ) -> SimulationEvent:
        """Create compliance monitoring event for limit tracking"""

        payload = ComplianceEventPayload(
            plan_id=plan_id,
            compliance_type=compliance_type,
            limit_type=limit_type,
            applicable_limit=applicable_limit,
            current_amount=current_amount,
            monitoring_date=monitoring_date
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=monitoring_date,
            source_system="compliance_monitoring",
            payload=payload
        )
```

## Implementation Tasks

### Phase 1: Core Payload Implementation
- [ ] **Create 3 core administrative payloads** (Forfeiture, HCE, Compliance)
- [ ] **Implement Literal event_type** fields for all 3 payloads
- [ ] **Add essential field validation** with business rule constraints

### Phase 2: Basic Features
- [ ] **Implement 3 compliance_type options** for basic monitoring
- [ ] **Create HCE determination** with prior/current year methods
- [ ] **Add forfeiture source validation** for employer contributions

### Phase 3: Factory Methods & Integration
- [ ] **Create PlanAdministrationEventFactory** with 3 helper methods
- [ ] **Extend SimulationEvent discriminated union** with 3 new payloads
- [ ] **Test integration** with existing event infrastructure

## Dependencies

### Story Dependencies
- **S072-01**: Core Event Model & Pydantic v2 Architecture (blocking)

### Domain Dependencies
- **Plan configuration**: For plan-specific rules and HCE thresholds
- **Compensation data**: For HCE calculations and limit monitoring

## Success Metrics

### Administrative Functionality
- [ ] **Forfeiture processing** with source validation
- [ ] **HCE determination** with annualization support
- [ ] **Basic compliance monitoring** for essential IRS limits

### Data Quality
- [ ] **Audit trail completeness** for all administrative actions
- [ ] **Accurate HCE determinations** with proper compensation tracking
- [ ] **Valid forfeiture calculations** with vesting percentage accuracy

## Testing Strategy

### Unit Tests
- [ ] **Each administrative payload** creation and validation
- [ ] **Compliance type validation** for basic monitoring types
- [ ] **Factory method validation** for all 3 administrative events

### Business Logic Tests
- [ ] **Forfeiture calculations** with vesting percentage accuracy
- [ ] **HCE determination** with compensation thresholds
- [ ] **Compliance monitoring** for limit tracking

### Integration Tests
- [ ] **Administrative event integration** with core event model
- [ ] **Discriminated union routing** to correct payload types
- [ ] **Event serialization/deserialization** for all 3 types

## Regulatory Coverage

### IRS Requirements
- [ ] **402(g) limit monitoring** for elective deferral tracking
- [ ] **415(c) limit monitoring** for annual additions tracking
- [ ] **Catch-up contribution eligibility** with age-based determination

### ERISA Requirements
- [ ] **Forfeiture allocation** according to plan terms
- [ ] **HCE determination** with proper calculation methods
- [ ] **Administrative audit trail** for compliance documentation

## Definition of Done

- [ ] **All 3 administrative payloads** implemented and tested
- [ ] **SimulationEvent discriminated union** extended with administrative events
- [ ] **PlanAdministrationEventFactory** provides creation methods for all types
- [ ] **Basic regulatory compliance verified** for IRS requirements
- [ ] **Integration tests passing** for all administrative scenarios
- [ ] **Documentation complete** with usage examples
- [ ] **Code review approved** with plan administration team validation

## Notes

These administrative events handle essential plan governance scenarios including forfeiture processing and HCE determination. The simplified scope focuses on core functionality without complex compliance tracking, corrective actions, or plan testing features.
