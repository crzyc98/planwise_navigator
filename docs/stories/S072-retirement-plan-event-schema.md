# Story S072: Define Retirement Plan Event Schema [SUPERSEDED]

**Epic**: E021 - DC Plan Data Model & Events
**Story Points**: 18
**Priority**: High

## ⚠️ SUPERSEDED BY EPIC E021-A

**This story has been broken down into Epic E021-A with 7 focused stories:**

- **S072-01**: Core Event Model & Pydantic v2 Architecture (5 pts)
- **S072-02**: Workforce Event Integration (3 pts)
- **S072-03**: Core DC Plan Events (5 pts)
- **S072-04**: Plan Administration Events (5 pts)
- **S072-05**: Loan & Investment Events (3 pts)
- **S072-06**: Performance & Validation Framework (8 pts)
- **S072-07**: ERISA Compliance Review & Documentation (3 pts)

**Please refer to Epic E021-A and individual stories for current implementation.**

---

# Original Story Content (Archived)

## Story

**As a** platform architect
**I want** comprehensive event types for all DC plan activities
**So that** we can track every participant interaction and calculation with complete audit trail and regulatory compliance

## Business Context

This story establishes the foundational event schema for Defined Contribution retirement plan modeling within Fidelity PlanAlign Engine's event-sourced architecture. It creates a unified, enterprise-grade event system that supports comprehensive retirement plan transactions while maintaining backward compatibility with workforce events and meeting ERISA compliance requirements.

## Acceptance Criteria

### 1. Coverage Requirements
- [ ] **All 18 event classes** enumerated in Payload Reference appendix are supported (added loan_default and rmd_determination)
- [ ] **Complete lifecycle coverage**: enrollment, contributions, distributions, loans, rollovers, investment elections, vesting, forfeitures, compliance testing
- [ ] **Workforce integration**: hire, promotion, termination, merit events flow through same unified stream
- [ ] **Regulatory events**: HCE determination, ADP/ACP testing, IRS limit compliance

### 2. Auditability Requirements
- [ ] **Complete event reconstruction**: Given participant_id + date range, system reconstructs chronologically ordered event trail with 100% coverage
- [ ] **Immutable audit trail**: All events permanently recorded with UUID and timestamp
- [ ] **Event correlation**: All DC plan events link to triggering workforce events via correlation_id
- [ ] **5-year history reconstruction** in ≤5 seconds (dev laptop: MacBook Pro M3, 16GB)

### 3. Performance Requirements
- [ ] **Batch ingest**: ≥100K events/sec using DuckDB vectorized inserts (16-core M2, 32GB laptop)
- [ ] **Schema validation**: <10ms per event validation with Pydantic v2
- [ ] **Participant history reconstruction**: ≤5s for five-year window (MacBook Pro M3, 16GB)
- [ ] **Snapshot strategy**: Weekly balance snapshots stored for query optimization and faster reconstruction
- [ ] **Memory efficiency**: <8GB for 100K employee simulation

### 4. Compliance Requirements
- [ ] **ERISA SME review**: Data model reviewed and signed off by benefits counsel (blocking gate)
- [ ] **Story closure is blocked until ERISA SME checklist is signed**
- [ ] **IRS regulation coverage**: Unit tests for ADP/ACP, 415(c), 402(g) compliance validation
- [ ] **Data classification**: All PII fields classified (SSN=RESTRICTED, compensation=CONFIDENTIAL)
- [ ] **JSON schema validation**: ≥99% of events validated in CI (build fails if any events are invalid in CI)

## Technical Specifications

### Pydantic v2 Discriminator Pattern

```python
from typing import Annotated, Union
from pydantic import BaseModel, Field, ConfigDict, field_validator

class SimulationEvent(BaseModel):
    model_config = ConfigDict(extra='forbid', use_enum_values=True)
    payload: Union[
        Annotated[HirePayload, Field(discriminator='event_type')],
        Annotated[ContributionPayload, Field(discriminator='event_type')],
        # ... all 16 payload types
    ] = Field(..., discriminator='event_type')
```

⚠️ **No Untyped Dict**: All `Optional[Dict[str, Any]]` patterns are banned. Use well-typed Pydantic models only.

### Unified Event Model Architecture

**Core Principle**: Single `SimulationEvent` model with Pydantic v2 discriminated unions for all workforce and DC plan events.

```python
from pydantic import BaseModel, Field, field_validator
from typing import Union, Literal, List, Optional, Dict, Any
from decimal import Decimal
from datetime import date, datetime
from uuid import UUID, uuid4

# Unified Event Model - replaces both DCPlanEvent and RetirementPlanEvent
class SimulationEvent(BaseModel):
    """Unified event model for all workforce and DC plan events"""

    # Core identification
    event_id: UUID = Field(default_factory=uuid4)
    employee_id: str
    effective_date: date
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Required context fields (not optional for proper isolation)
    scenario_id: str  # Required for multi-scenario support
    plan_design_id: str  # Required for plan design versioning
    source_system: str

    # Discriminated union payload
    payload: Union[
        # Workforce Events (existing)
        'HirePayload',
        'PromotionPayload',
        'TerminationPayload',
        'MeritPayload',
        # DC Plan Events (new)
        'EligibilityPayload',
        'EnrollmentPayload',
        'ContributionPayload',
        'DistributionPayload',
        'VestingPayload',
        'ForfeiturePayload',
        'LoanInitiatedPayload',
        'LoanRepaymentPayload',
        'RolloverPayload',
        'InvestmentElectionPayload',
        'HCEStatusPayload',
        'ComplianceEventPayload',
        'PlanComplianceTestPayload',
        'LoanDefaultPayload',
        'RMDDeterminationPayload'
    ] = Field(..., discriminator='event_type')

    # Optional correlation for event tracing
    correlation_id: Optional[str] = None

    class Config:
        extra = 'forbid'  # Prevent additional fields
        use_enum_values = True
```

### Event Payload Definitions

**All monetary amounts stored as `Decimal(18,6)` - never float.**

#### Workforce Event Payloads (Enhanced)
```python
class HirePayload(BaseModel):
    event_type: Literal["hire"] = "hire"
    plan_id: Optional[str] = None
    hire_date: date
    department: str
    job_level: int
    annual_compensation: Decimal = Field(..., decimal_places=6)

class PromotionPayload(BaseModel):
    event_type: Literal["promotion"] = "promotion"
    plan_id: Optional[str] = None
    new_job_level: int
    new_annual_compensation: Decimal = Field(..., decimal_places=6)
    effective_date: date

class TerminationPayload(BaseModel):
    event_type: Literal["termination"] = "termination"
    plan_id: Optional[str] = None
    termination_reason: Literal["voluntary", "involuntary", "retirement", "death", "disability"]
    final_pay_date: date

class MeritPayload(BaseModel):
    event_type: Literal["merit"] = "merit"
    plan_id: Optional[str] = None
    new_compensation: Decimal = Field(..., decimal_places=6)
    merit_percentage: Decimal = Field(..., ge=0, le=1)
```

#### DC Plan Event Payloads (Core)
```python
class EligibilityPayload(BaseModel):
    event_type: Literal["eligibility"] = "eligibility"
    plan_id: str
    eligible: bool
    eligibility_date: date
    reason: Literal["age_and_service", "immediate", "hours_requirement", "rehire"]

class EnrollmentPayload(BaseModel):
    event_type: Literal["enrollment"] = "enrollment"
    plan_id: str
    enrollment_date: date  # Added missing field
    pre_tax_contribution_rate: Decimal = Field(..., ge=0, le=1, decimal_places=4)
    roth_contribution_rate: Decimal = Field(..., ge=0, le=1, decimal_places=4)
    after_tax_contribution_rate: Decimal = Field(default=Decimal('0'), ge=0, le=1, decimal_places=4)
    auto_enrollment: bool = False
    opt_out_window_expires: Optional[date] = None

class ContributionPayload(BaseModel):
    event_type: Literal["contribution"] = "contribution"
    plan_id: str
    source: Literal[
        "employee_pre_tax", "employee_roth", "employee_after_tax", "employee_catch_up",
        "employer_match", "employer_match_true_up", "employer_nonelective",
        "employer_profit_sharing", "forfeiture_allocation"
    ]
    amount: Decimal = Field(..., gt=0, decimal_places=6)
    pay_period_end: date
    contribution_date: date  # Date funds are deposited - critical for performance calculation
    ytd_amount: Decimal = Field(..., ge=0, decimal_places=6)
    payroll_id: str  # Required for audit trail
    irs_limit_applied: bool = False
    inferred_value: bool = False

class DistributionPayload(BaseModel):
    event_type: Literal["distribution"] = "distribution"
    plan_id: str
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
    non_taxable_amount: Decimal = Field(..., ge=0, decimal_places=6)  # Return of after-tax basis
    qdro_alternate_payee_id: Optional[str] = None  # If reason is "qdro"

    is_rollover: bool = False
    rollover_destination: Optional[Literal["ira_traditional", "ira_roth", "401k", "403b"]] = None

class VestingPayload(BaseModel):
    event_type: Literal["vesting"] = "vesting"
    plan_id: str
    vested_percentage: Decimal = Field(..., ge=0, le=1, decimal_places=4)

    # The balance in each source to which the new percentage is applied
    source_balances_vested: Dict[
        Literal["employer_match", "employer_nonelective", "employer_profit_sharing"],
        Decimal
    ]

    vesting_schedule_type: Literal["graded", "cliff", "immediate"]
    service_computation_date: date
    service_credited_hours: int  # Required for audit
    service_period_end_date: date  # Required for audit

class ForfeiturePayload(BaseModel):
    event_type: Literal["forfeiture"] = "forfeiture"
    plan_id: str
    forfeited_from_source: Literal["employer_match", "employer_nonelective", "employer_profit_sharing"]
    amount: Decimal = Field(..., gt=0, decimal_places=6)
    reason: Literal["unvested_termination", "break_in_service"]
    vested_percentage: Decimal = Field(..., ge=0, le=1, decimal_places=4)
```

#### Extended Event Payloads (Additional Critical Types)
```python
class LoanInitiatedPayload(BaseModel):
    event_type: Literal["loan_initiated"] = "loan_initiated"
    plan_id: str
    loan_id: str
    principal_amount: Decimal = Field(..., gt=0, decimal_places=6)
    interest_rate: Decimal = Field(..., gt=0, decimal_places=4)
    term_months: int = Field(..., gt=0, le=120)  # Max 10 years
    origination_date: date

    # Loan type affects compliance rules and fees are common
    loan_type: Literal["general_purpose", "primary_residence"] = "general_purpose"
    origination_fee: Decimal = Field(default=Decimal('0'), ge=0, decimal_places=6)

class LoanRepaymentPayload(BaseModel):
    event_type: Literal["loan_repayment"] = "loan_repayment"
    plan_id: str
    loan_id: str
    principal_paid: Decimal = Field(..., ge=0, decimal_places=6)
    interest_paid: Decimal = Field(..., ge=0, decimal_places=6)
    outstanding_balance: Decimal = Field(..., ge=0, decimal_places=6)
    remaining_term_months: int = Field(..., ge=0)

class RolloverPayload(BaseModel):
    event_type: Literal["rollover"] = "rollover"
    plan_id: str
    source_plan_type: Literal["401k", "403b", "457b", "ira_traditional", "ira_roth"]
    amount: Decimal = Field(..., gt=0, decimal_places=6)
    is_roth_rollover: bool = False
    rollover_source: str  # Source plan identifier

class InvestmentElectionPayload(BaseModel):
    event_type: Literal["investment_election"] = "investment_election"
    plan_id: str
    election_effective_date: date

    # Election scope and source tracking for complete audit trail
    election_scope: Literal[
        "future_contributions",
        "rebalance_existing_balance",
        "full_reallocation"  # Applies to both existing and future
    ] = "future_contributions"
    source_of_change: Literal[
        "participant",
        "advisor",
        "administrator",
        "system_default_qdia"  # Qualified Default Investment Alternative
    ] = "participant"
    model_portfolio_id: Optional[str] = None  # If plan uses model portfolios
    transaction_id: Optional[str] = None  # For reconciliation with custodian

    fund_allocations: Dict[str, Decimal]  # fund_id -> allocation_percentage

    @field_validator('fund_allocations')
    def validate_allocations_sum_to_one(cls, v):
        total = sum(v.values())
        if abs(total - Decimal('1.0')) > Decimal('0.0001'):
            raise ValueError('Fund allocations must sum to 1.0')
        return v

class HCEStatusPayload(BaseModel):
    event_type: Literal["hce_status"] = "hce_status"
    plan_id: str
    determination_method: Literal["prior_year", "current_year"]
    ytd_compensation: Decimal = Field(..., ge=0, decimal_places=6)
    annualized_compensation: Decimal = Field(..., ge=0, decimal_places=6)
    hce_threshold: Decimal = Field(..., gt=0, decimal_places=6)
    is_hce: bool
    determination_date: date
    prior_year_hce: Optional[bool] = None

class ComplianceEventPayload(BaseModel):
    event_type: Literal["compliance"] = "compliance"
    plan_id: str
    compliance_type: Literal[
        "402g_excess", "415c_excess", "catch_up_eligible", "contribution_capped",
        "compensation_capped"  # 401(a)(17) compensation limit
    ]
    limit_type: Literal["elective_deferral", "annual_additions", "catch_up", "compensation"]
    applicable_limit: Decimal = Field(..., gt=0, decimal_places=6)
    current_amount: Decimal = Field(..., ge=0, decimal_places=6)
    excess_amount: Optional[Decimal] = Field(None, ge=0, decimal_places=6)
    corrective_action: Optional[Literal["refund", "reallocation", "cap", "none"]] = None
    affected_sources: List[str]
    correction_deadline: Optional[date] = None

class PlanComplianceTestPayload(BaseModel):
    event_type: Literal["plan_compliance_test"] = "plan_compliance_test"
    plan_id: str
    test_type: Literal["ADP", "ACP", "TopHeavy"]
    plan_year: int
    test_passed: bool
    hce_group_metric: Decimal = Field(..., ge=0, le=1, decimal_places=4)
    nhce_group_metric: Decimal = Field(..., ge=0, le=1, decimal_places=4)
    corrective_action_taken: Optional[Literal["qnec", "qmac", "refunds"]] = None

# Additional Critical Event Types for Production Readiness
class LoanDefaultPayload(BaseModel):
    event_type: Literal["loan_default"] = "loan_default"
    plan_id: str
    loan_id: str
    default_date: date
    outstanding_balance_at_default: Decimal = Field(..., ge=0, decimal_places=6)
    accrued_interest_at_default: Decimal = Field(..., ge=0, decimal_places=6)

class RMDDeterminationPayload(BaseModel):
    event_type: Literal["rmd_determination"] = "rmd_determination"
    plan_id: str
    plan_year: int
    age_at_year_end: int
    required_beginning_date: date
    calculated_rmd_amount: Decimal = Field(..., ge=0, decimal_places=6)
```

### EventFactory Pattern
```python
class EventFactory:
    """Factory for creating validated simulation events"""

    @staticmethod
    def create_event(raw_data: dict[str, Any]) -> SimulationEvent:
        """Create properly validated event from raw data"""
        return SimulationEvent.model_validate(raw_data)

    @staticmethod
    def create_contribution_event(
        employee_id: str,
        plan_id: str,
        source: str,
        amount: Decimal,
        scenario_id: str,
        plan_design_id: str,
        **kwargs
    ) -> SimulationEvent:
        """Create contribution event with required context"""
        payload = ContributionPayload(
            plan_id=plan_id,
            source=source,
            amount=amount,
            **kwargs
        )
        return SimulationEvent(
            employee_id=employee_id,
            scenario_id=scenario_id,
            plan_design_id=plan_design_id,
            source_system="event_factory",
            payload=payload
        )
```

## Implementation Tasks

### Phase 1: Core Schema Unification (Sprint 1, Owner: Platform Team)
- [ ] **Replace dual event models** with single `SimulationEvent` using proper Pydantic v2 discriminated unions
- [ ] **Make `scenario_id` and `plan_design_id` required fields** (not optional)
- [ ] **Fix discriminator implementation** with `event_type` fields in each payload
- [ ] **Set decimal precision**: `Decimal(18,6)` for all monetary amounts
- [ ] **Add Pydantic v2 discriminator code snippet** to appendix for reviewer reference
- [ ] **Eliminate untyped `Dict[str, Any]`**—all payloads must be fully typed with Pydantic models

### Phase 2: Complete Event Coverage (Sprint 2, Owner: DC Plan Team)
- [ ] **Add all critical payloads** with exact enum values:
  - `DistributionPayload`: Enhanced with payment_date, taxable_amount, QDRO support
  - `VestingPayload`: Enhanced with source_balances_vested for complete audit trail
  - `LoanInitiatedPayload`: Enhanced with loan_type and origination_fee
  - `InvestmentElectionPayload`: Enhanced with election_scope and source_of_change
  - `LoanDefaultPayload`: New event for deemed distributions
  - `RMDDeterminationPayload`: New event for required minimum distribution tracking
- [ ] **Enhance existing payloads**: contribution_date, payment_date, source_balances_vested
- [ ] **Create complete 18-event-type enumeration** in Payload Reference appendix

### Phase 3: Enterprise Governance (Sprint 2-3, Owner: Compliance Team)
- [ ] **Create "Payload Reference" appendix** with all 18 event types and copy-paste-ready enum values
- [ ] **Add event_type → downstream process mapping matrix**
- [ ] **Implement 4-block acceptance criteria**: Coverage, Auditability, Performance, Compliance
- [ ] **Add data classification & encryption requirements** (SSNs=RESTRICTED, salaries=CONFIDENTIAL)
- [ ] **Require signed ERISA SME checklist** as blocking gate before Phase 4

### Phase 4: Performance & Technical Precision (Sprint 3, Owner: Platform Team)
- [ ] **Add snapshot strategy documentation** for performance optimization
- [ ] **Set hardware-specific performance targets**:
  - 100K events/sec ingest (on CI runner: 8-core, 32GB RAM)
  - 5s history reconstruction (on dev laptop: MacBook Pro M3, 16GB)
- [ ] **Include EventFactory pattern**: `SimulationEvent.model_validate()` with runtime validation
- [ ] **Implement comprehensive unit tests** for all 18 payload types with edge case coverage
- [ ] **Create integration tests with workforce events** ensuring compatibility
- [ ] **Build performance tests for vectorized processing** (100K+ employees)

### Phase 5: Updated Success Metrics (Sprint 4, Owner: QA Team)
- [ ] **JSON schema validation ≥99% in CI** (missing 1% triggers blocking alert; effectively 100% required with dev-only exceptions)
- [ ] **Complete audit trail reconstruction**: 5-year participant history in ≤5s
- [ ] **Signed compliance checklists + unit tests** for ADP/ACP, 415(c), 402(g) regulations
- [ ] **Performance benchmarks verified** on specified hardware configurations

## Dependencies

### Foundational Infrastructure
- **Existing event schema** (`config/schema.py`)
- **Event processing pipeline** (Dagster assets)
- **DuckDB event storage** (`fct_yearly_events`)
- **Employee dimension** (workforce simulation)

### External Dependencies
- **Pydantic 2.7.4+** for enhanced type safety
- **IRS regulatory limits** (annual updates)
- **Plan design configurations** (YAML/JSON)

### Story Dependencies
- **S073**: Extend dbt Models for Plan Data (consumes this event schema)
- **S074**: Create Plan Configuration Schema (provides plan_design_id validation)
- **S075**: Implement Event Validation Framework (uses discriminated union patterns)
- **S080**: IRS Compliance Enforcement Engine (consumes compliance events)
- **S081**: Regulatory Limits Service (provides validation context)

### Critical Success Dependencies
- **Golden benchmark dataset**: Required for S072 validation (blocking)
- **ERISA SME review**: Legal validation of event coverage (blocking gate)
- **Performance test infrastructure**: Required for 100K events/sec validation
- **Pydantic v2 discriminator validation**: Must pass CI with 99%+ success rate

## Success Metrics

### Functional Requirements
- [ ] **Event completeness**: All 18 DC plan event types represented in payload reference
- [ ] **Type safety**: Zero runtime type errors in event processing with Pydantic v2
- [ ] **Immutability**: Event audit trail maintains complete 5-year history
- [ ] **Scenario isolation**: Zero data leakage between scenarios via required scenario_id
- [ ] **Golden dataset validation**: 100% match with benchmark calculations (zero variance)

### Performance Requirements
- [ ] **Event ingest**: ≥100K events/sec using DuckDB vectorized inserts (CI: 8-core, 32GB)
- [ ] **History reconstruction**: 5-year participant history in ≤5s (dev: MacBook Pro M3, 16GB)
- [ ] **Schema validation**: <10ms per event validation with Pydantic v2
- [ ] **Memory efficiency**: <8GB for 100K employee simulation

### Compliance Requirements
- [ ] **JSON schema validation**: ≥99% success rate in CI (build fails if any events are invalid in CI)
- [ ] **Unit-test suite must include IRS 402(g), 415(c), and ADP/ACP pass/fail edge-cases**
- [ ] **Data classification**: All PII fields marked (SSN=RESTRICTED, compensation=CONFIDENTIAL)
- [ ] **ERISA compliance**: Signed SME checklist for event coverage completeness
- [ ] **Audit trail completeness**: Every event linked to source system with correlation_id

## Risk Mitigation

### Technical Risks
- **Complexity of discriminated unions**: Mitigated by comprehensive unit tests
- **Backward compatibility**: Mitigated by optional field strategy
- **Performance impact**: Mitigated by vectorized processing design

### Business Risks
- **Incomplete event coverage**: Mitigated by benefits counsel review
- **Regulatory compliance**: Mitigated by ERISA compliance validation

## Definition of Done

- [ ] **Schema implemented** with unified SimulationEvent model and all 18 payload types
- [ ] **Backward compatibility verified** with existing workforce events
- [ ] **Type safety validated** through comprehensive Pydantic v2 testing
- [ ] **Performance benchmarks met** for enterprise scale (100K events/sec, 5s reconstruction)
- [ ] **Integration tests passing** with event processing pipeline
- [ ] **Golden dataset validation** with zero variance tolerance
- [ ] **Documentation complete** with Payload Reference appendix and event_type mapping
- [ ] **Code review approved** following PlanWise patterns
- [ ] **ERISA SME compliance review** signed off with blocking gate approval
- [ ] **CI validation** achieving ≥99% JSON schema validation success rate

## Payload Reference Appendix

### Payload Reference Table

| Event Type | Required Fields | Sample JSON |
|------------|----------------|-------------|
| `hire` | employee_id, hire_date, department, job_level, annual_compensation | `{"event_type": "hire", "hire_date": "2025-01-01", "department": "engineering", "job_level": 3, "annual_compensation": "125000.00"}` |
| `contribution` | plan_id, source, amount, pay_period_end, ytd_amount, payroll_id | `{"event_type": "contribution", "plan_id": "401k_main", "source": "employee_pre_tax", "amount": "1000.00", "payroll_id": "PR_2025_01_15"}` |
| `distribution` | plan_id, distribution_reason, gross_amount, federal_withholding, state_withholding | `{"event_type": "distribution", "plan_id": "401k_main", "distribution_reason": "termination", "gross_amount": "50000.00"}` |
| `loan_initiated` | plan_id, loan_id, principal_amount, interest_rate, term_months, origination_date | `{"event_type": "loan_initiated", "plan_id": "401k_main", "loan_id": "L_2025_001", "principal_amount": "25000.00"}` |
| `loan_repayment` | plan_id, loan_id, principal_paid, interest_paid, outstanding_balance, remaining_term_months | `{"event_type": "loan_repayment", "plan_id": "401k_main", "loan_id": "L_2025_001", "principal_paid": "500.00"}` |
| `rollover` | plan_id, source_plan_type, amount, is_roth_rollover, rollover_source | `{"event_type": "rollover", "plan_id": "401k_main", "source_plan_type": "401k", "amount": "75000.00"}` |
| `investment_election` | plan_id, election_effective_date, fund_allocations | `{"event_type": "investment_election", "plan_id": "401k_main", "fund_allocations": {"FUND_001": "0.6", "FUND_002": "0.4"}}` |
| `plan_compliance_test` | plan_id, test_type, plan_year, test_passed, hce_group_metric, nhce_group_metric | `{"event_type": "plan_compliance_test", "plan_id": "401k_main", "test_type": "ADP", "plan_year": 2025, "test_passed": true}` |
| `loan_default` | plan_id, loan_id, default_date, outstanding_balance_at_default, accrued_interest_at_default | `{"event_type": "loan_default", "plan_id": "401k_main", "loan_id": "L_2025_001", "default_date": "2025-06-15"}` |
| `rmd_determination` | plan_id, plan_year, age_at_year_end, required_beginning_date, calculated_rmd_amount | `{"event_type": "rmd_determination", "plan_id": "401k_main", "plan_year": 2025, "age_at_year_end": 73}` |

### Complete 18-Event Enumeration

**Workforce Events (4)**:
```python
"hire"           # HirePayload - Employee onboarding with plan eligibility
"promotion"      # PromotionPayload - Level changes affecting contribution capacity
"termination"    # TerminationPayload - Employment end triggering distributions
"merit"          # MeritPayload - Compensation changes affecting HCE status
```

**DC Plan Core Events (5)**:
```python
"eligibility"    # EligibilityPayload - Plan participation qualification
"enrollment"     # EnrollmentPayload - Deferral election and auto-enrollment
"contribution"   # ContributionPayload - All contribution sources with IRS categorization
"distribution"   # DistributionPayload - 8 distribution reasons with tax withholding
"vesting"        # VestingPayload - Service-based employer contribution vesting
```

**DC Plan Extended Events (4)**:
```python
"forfeiture"         # ForfeiturePayload - Unvested employer contribution recapture
"loan_initiated"     # LoanInitiatedPayload - Participant loan origination
"loan_repayment"     # LoanRepaymentPayload - Loan payment with balance tracking
"rollover"           # RolloverPayload - External plan money movement
```

**Investment & Compliance Events (5)**:
```python
"investment_election"    # InvestmentElectionPayload - Fund allocation changes
"hce_status"            # HCEStatusPayload - Highly compensated employee determination
"compliance"            # ComplianceEventPayload - IRS limit violations and corrections
"plan_compliance_test"  # PlanComplianceTestPayload - Annual ADP/ACP/TopHeavy testing
"loan_default"          # LoanDefaultPayload - Deemed distribution from loan default
"rmd_determination"     # RMDDeterminationPayload - Required minimum distribution calculation
```

### Event → Downstream Process Mapping

| Event Type | Downstream Process |
|------------|-------------------|
| `contribution` → `402(g)/415(c) validation → account_balance_update → 5500_reporting` |
| `distribution` → `early_withdrawal_penalty_check → tax_withholding → 1099R_generation` |
| `compliance` → `irs_correction_workflow → refund_processing → dol_filing` |
| `plan_compliance_test` → `adp_acp_calculation → corrective_contributions → schedule_g_filing` |
| `hce_status` → `participant_classification → testing_group_assignment → annual_determination` |
| `vesting` → `forfeiture_calculation → account_adjustment → participant_statement` |
| `forfeiture` → `allocation_workflow → account_reallocation → annual_forfeiture_report` |
| `loan_initiated` → `loan_limit_validation → documentation_generation → repayment_schedule` |
| `rollover` → `60day_rule_tracking → contribution_processing → form_5498_generation` |
| `investment_election` → `qdia_compliance_check → fund_rebalancing → investment_statement` |
| `loan_default` → `deemed_distribution_calculation → tax_withholding → 1099R_generation` |
| `rmd_determination` → `participant_notification → distribution_requirement → compliance_tracking` |

### Snapshot Strategy

Weekly participant balance snapshots are stored in `fct_participant_balance_snapshots` to optimize query performance. Full event reconstruction is only needed for detailed audit trails, while day-to-day balance queries use pre-computed snapshots, reducing 5-year history reconstruction from minutes to seconds.

### Pydantic v2 Discriminator Implementation

```python
# Complete discriminated union with all 16 event types
from typing import Annotated, Union, Literal
from pydantic import BaseModel, Field, ConfigDict

class SimulationEvent(BaseModel):
    model_config = ConfigDict(extra='forbid', use_enum_values=True, validate_assignment=True)

    # Core fields
    event_id: UUID = Field(default_factory=uuid4)
    employee_id: str
    effective_date: date
    scenario_id: str  # Required - no Optional
    plan_design_id: str  # Required - no Optional
    source_system: str

    # Discriminated union - all 18 event types
    payload: Union[
        Annotated[HirePayload, Field(discriminator='event_type')],
        Annotated[PromotionPayload, Field(discriminator='event_type')],
        Annotated[TerminationPayload, Field(discriminator='event_type')],
        Annotated[MeritPayload, Field(discriminator='event_type')],
        Annotated[EligibilityPayload, Field(discriminator='event_type')],
        Annotated[EnrollmentPayload, Field(discriminator='event_type')],
        Annotated[ContributionPayload, Field(discriminator='event_type')],
        Annotated[DistributionPayload, Field(discriminator='event_type')],
        Annotated[VestingPayload, Field(discriminator='event_type')],
        Annotated[ForfeiturePayload, Field(discriminator='event_type')],
        Annotated[LoanInitiatedPayload, Field(discriminator='event_type')],
        Annotated[LoanRepaymentPayload, Field(discriminator='event_type')],
        Annotated[RolloverPayload, Field(discriminator='event_type')],
        Annotated[InvestmentElectionPayload, Field(discriminator='event_type')],
        Annotated[HCEStatusPayload, Field(discriminator='event_type')],
        Annotated[ComplianceEventPayload, Field(discriminator='event_type')],
        Annotated[PlanComplianceTestPayload, Field(discriminator='event_type')],
        Annotated[LoanDefaultPayload, Field(discriminator='event_type')],
        Annotated[RMDDeterminationPayload, Field(discriminator='event_type')]
    ] = Field(..., discriminator='event_type')
```

## Related Stories

- **S073**: Extend dbt Models for Plan Data (depends on this schema)
- **S074**: Create Plan Configuration Schema (parallel development)
- **S075**: Implement Event Validation Framework (uses this schema)
- **S080**: IRS Compliance Enforcement Engine (consumes compliance events)
- **S081**: Regulatory Limits Service (provides validation context)
