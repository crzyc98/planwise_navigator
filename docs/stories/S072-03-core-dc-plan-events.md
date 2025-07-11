# Story S072-03: Core DC Plan Events

**Epic**: E021-A - DC Plan Event Schema Foundation
**Story Points**: 5
**Priority**: High
**Sprint**: 2
**Owner**: DC Plan Team

## Story

**As a** DC plan administrator
**I want** core retirement plan events for participant lifecycle management
**So that** I can track eligibility, enrollment, contributions, distributions, and vesting with complete audit trail

## Business Context

This story implements the 5 most critical DC plan events that form the core of participant lifecycle management: eligibility determination, plan enrollment, contribution processing, distribution handling, and vesting calculations. These events represent the primary participant interactions with the retirement plan.

## Acceptance Criteria

### Core Event Coverage
- [ ] **EligibilityPayload**: Plan participation qualification tracking
- [ ] **EnrollmentPayload**: Deferral elections and auto-enrollment handling
- [ ] **ContributionPayload**: All contribution sources with IRS categorization
- [ ] **DistributionPayload**: 8 distribution reasons with tax withholding support
- [ ] **VestingPayload**: Service-based employer contribution vesting

### Regulatory Compliance
- [ ] **Contribution source tracking** for 9 different types (employee/employer/forfeiture)
- [ ] **Distribution reason codes** including RMD, QDRO, hardship handling
- [ ] **Tax withholding fields** for federal and state requirements
- [ ] **Vesting calculation support** with service hours and balance tracking

### Enterprise Features
- [ ] **Payroll integration** with contribution_date and payroll_id
- [ ] **QDRO support** with alternate payee tracking
- [ ] **Monetary precision** using Decimal(18,6) for all amounts
- [ ] **Complete audit trail** with effective dates and source tracking

## Technical Specifications

### Core DC Plan Event Payloads

```python
from typing import Literal, Optional, Dict
from pydantic import BaseModel, Field, field_validator
from datetime import date
from decimal import Decimal

class EligibilityPayload(BaseModel):
    """Plan participation qualification tracking"""

    event_type: Literal["eligibility"] = "eligibility"
    plan_id: str = Field(..., min_length=1)
    eligible: bool
    eligibility_date: date
    reason: Literal[
        "age_and_service",
        "immediate",
        "hours_requirement",
        "rehire"
    ]

class EnrollmentPayload(BaseModel):
    """Deferral election and auto-enrollment handling"""

    event_type: Literal["enrollment"] = "enrollment"
    plan_id: str = Field(..., min_length=1)
    enrollment_date: date
    pre_tax_contribution_rate: Decimal = Field(..., ge=0, le=1, decimal_places=4)
    roth_contribution_rate: Decimal = Field(..., ge=0, le=1, decimal_places=4)
    after_tax_contribution_rate: Decimal = Field(
        default=Decimal('0'), ge=0, le=1, decimal_places=4
    )
    auto_enrollment: bool = False
    opt_out_window_expires: Optional[date] = None

class ContributionPayload(BaseModel):
    """All contribution sources with IRS categorization"""

    event_type: Literal["contribution"] = "contribution"
    plan_id: str = Field(..., min_length=1)
    source: Literal[
        "employee_pre_tax", "employee_roth", "employee_after_tax", "employee_catch_up",
        "employer_match", "employer_match_true_up", "employer_nonelective",
        "employer_profit_sharing", "forfeiture_allocation"
    ]
    amount: Decimal = Field(..., gt=0, decimal_places=6)
    pay_period_end: date
    contribution_date: date  # Date funds are deposited - critical for performance
    ytd_amount: Decimal = Field(..., ge=0, decimal_places=6)
    payroll_id: str = Field(..., min_length=1)  # Required for audit trail
    irs_limit_applied: bool = False
    inferred_value: bool = False

class DistributionPayload(BaseModel):
    """8 distribution reasons with tax withholding support"""

    event_type: Literal["distribution"] = "distribution"
    plan_id: str = Field(..., min_length=1)
    distribution_reason: Literal[
        "termination", "retirement", "disability", "death",
        "hardship", "in_service_withdrawal", "qdro", "rmd"
    ]
    gross_amount: Decimal = Field(..., gt=0, decimal_places=6)
    federal_withholding: Decimal = Field(..., ge=0, decimal_places=6)
    state_withholding: Decimal = Field(..., ge=0, decimal_places=6)

    # Critical fields for tax reporting (1099-R) and QDRO processing
    payment_date: date
    taxable_amount: Decimal = Field(..., ge=0, decimal_places=6)
    non_taxable_amount: Decimal = Field(..., ge=0, decimal_places=6)
    qdro_alternate_payee_id: Optional[str] = None  # If reason is "qdro"

    is_rollover: bool = False
    rollover_destination: Optional[Literal[
        "ira_traditional", "ira_roth", "401k", "403b"
    ]] = None

class VestingPayload(BaseModel):
    """Service-based employer contribution vesting"""

    event_type: Literal["vesting"] = "vesting"
    plan_id: str = Field(..., min_length=1)
    vested_percentage: Decimal = Field(..., ge=0, le=1, decimal_places=4)

    # The balance in each source to which the new percentage is applied
    source_balances_vested: Dict[
        Literal["employer_match", "employer_nonelective", "employer_profit_sharing"],
        Decimal
    ]

    vesting_schedule_type: Literal["graded", "cliff", "immediate"]
    service_computation_date: date
    service_credited_hours: int = Field(..., ge=0)  # Required for audit
    service_period_end_date: date  # Required for audit
```

### DC Plan Event Factory

```python
class DCPlanEventFactory(EventFactory):
    """Factory for creating DC plan events with validation"""

    @staticmethod
    def create_contribution_event(
        employee_id: str,
        plan_id: str,
        scenario_id: str,
        plan_design_id: str,
        source: str,
        amount: Decimal,
        pay_period_end: date,
        contribution_date: date,
        ytd_amount: Decimal,
        payroll_id: str,
        **kwargs
    ) -> SimulationEvent:
        """Create contribution event with required audit fields"""

        payload = ContributionPayload(
            plan_id=plan_id,
            source=source,
            amount=amount,
            pay_period_end=pay_period_end,
            contribution_date=contribution_date,
            ytd_amount=ytd_amount,
            payroll_id=payroll_id,
            **kwargs
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=contribution_date,
            source_system="dc_plan_administration",
            payload=payload
        )

    @staticmethod
    def create_distribution_event(
        employee_id: str,
        plan_id: str,
        scenario_id: str,
        plan_design_id: str,
        distribution_reason: str,
        gross_amount: Decimal,
        payment_date: date,
        taxable_amount: Decimal,
        federal_withholding: Decimal = Decimal('0'),
        state_withholding: Decimal = Decimal('0'),
        **kwargs
    ) -> SimulationEvent:
        """Create distribution event with tax reporting fields"""

        # Calculate non-taxable amount
        non_taxable_amount = gross_amount - taxable_amount

        payload = DistributionPayload(
            plan_id=plan_id,
            distribution_reason=distribution_reason,
            gross_amount=gross_amount,
            federal_withholding=federal_withholding,
            state_withholding=state_withholding,
            payment_date=payment_date,
            taxable_amount=taxable_amount,
            non_taxable_amount=non_taxable_amount,
            **kwargs
        )

        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            effective_date=payment_date,
            source_system="dc_plan_administration",
            payload=payload
        )
```

## Implementation Tasks

### Phase 1: Core Payload Implementation
- [ ] **Create 5 core payload classes** with proper validation
- [ ] **Implement Literal event_type** fields for discriminator
- [ ] **Add all required fields** with appropriate constraints
- [ ] **Set Decimal precision** to (18,6) for monetary amounts

### Phase 2: Enhanced Features
- [ ] **Add contribution_date field** to ContributionPayload
- [ ] **Implement QDRO support** in DistributionPayload
- [ ] **Add source_balances_vested** to VestingPayload
- [ ] **Create comprehensive enum values** for all Literal fields

### Phase 3: Factory Methods & Integration
- [ ] **Create DCPlanEventFactory** with helper methods
- [ ] **Implement validation logic** in factory methods
- [ ] **Extend SimulationEvent discriminated union** with 5 new payloads
- [ ] **Test integration** with core event model

### Phase 4: Validation & Testing
- [ ] **Add field validators** for complex business rules
- [ ] **Test all enum combinations** for Literal fields
- [ ] **Validate Decimal precision** requirements
- [ ] **Test discriminator routing** for all 5 event types

## Dependencies

### Story Dependencies
- **S072-01**: Core Event Model & Pydantic v2 Architecture (blocking)

### Domain Dependencies
- **Plan configuration**: Plan_id validation and lookup
- **Employee demographics**: Employee_id validation
- **Payroll system**: Payroll_id format and validation
- **IRS limits**: Contribution source categorization

## Success Metrics

### Functionality
- [ ] **All 5 event types working** in unified model
- [ ] **Contribution processing** with all 9 source types
- [ ] **Distribution handling** with tax calculation support
- [ ] **Vesting calculations** with service hour tracking

### Data Quality
- [ ] **Monetary precision maintained** with Decimal(18,6)
- [ ] **Audit trail complete** with all required tracking fields
- [ ] **Tax reporting ready** with 1099-R field coverage
- [ ] **Payroll integration** with contribution_date tracking

## Testing Strategy

### Unit Tests
- [ ] **Each payload creation** with valid/invalid data
- [ ] **Field validation** for all constraints
- [ ] **Enum value validation** for Literal fields
- [ ] **Decimal precision** testing for monetary fields

### Business Logic Tests
- [ ] **Contribution source categorization** correctness
- [ ] **Distribution reason handling** for all 8 types
- [ ] **Vesting calculation** with service hours
- [ ] **QDRO processing** with alternate payee support

### Integration Tests
- [ ] **Discriminated union routing** to correct payloads
- [ ] **Factory method integration** with core event model
- [ ] **Serialization/deserialization** for all 5 types
- [ ] **Event correlation** between related events

## Regulatory Compliance

### IRS Requirements
- [ ] **Contribution source tracking** meets IRS categorization
- [ ] **Distribution reason codes** support IRS reporting
- [ ] **Tax withholding fields** support 1099-R generation
- [ ] **Vesting calculations** meet ERISA requirements

### ERISA Requirements
- [ ] **Complete audit trail** for fiduciary compliance
- [ ] **Service hour tracking** for vesting calculations
- [ ] **Participant account accuracy** with balance tracking
- [ ] **Distribution eligibility** properly documented

## Definition of Done

- [ ] **All 5 core DC plan payloads** implemented and tested
- [ ] **SimulationEvent discriminated union** extended with new payloads
- [ ] **DCPlanEventFactory** provides creation methods for all types
- [ ] **Regulatory compliance verified** for IRS and ERISA requirements
- [ ] **Integration tests passing** for all DC plan scenarios
- [ ] **Documentation complete** with usage examples and business rules
- [ ] **Code review approved** with DC plan team validation
- [ ] **Performance benchmarks met** for event creation and validation

## Notes

These 5 core events represent the primary participant interactions with DC plans and form the foundation for more complex plan administration features. The enhanced payloads include all fields necessary for regulatory compliance and enterprise-grade audit trails.
