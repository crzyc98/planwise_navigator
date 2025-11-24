# Epic E021: DC Plan Data Model & Events

## Epic Overview

### Summary
Establish the foundational data model and event schema for Defined Contribution retirement plan modeling within Fidelity PlanAlign Engine's event-sourced architecture.

### Business Value
- Creates the technical foundation for all retirement plan features
- Ensures compliance with SOX audit requirements through immutable event logging
- Enables complete reconstruction of participant account history

### Success Criteria
- ✅ Complete event schema supporting all DC plan transactions
- ✅ Integration with existing workforce event stream
- ✅ Audit trail meeting ERISA compliance requirements
- ✅ Performance benchmarks met for event processing

---

## Dependencies

This epic builds upon the existing event-sourced workforce simulation infrastructure:

### Foundational Schemas
- **`config/schema.py`**: Core simulation configuration (`SimulationConfig`, `EmployeeRecord`, `SimulationEvent`)
- **`fct_yearly_events`**: Existing workforce event table (hire, termination, promotion, RAISE)
- **`fct_workforce_snapshot`**: Point-in-time workforce state snapshots
- **`dim_hazard_table`**: Actuarial probability tables for workforce events

### Integration Points
- **Event Schema Extension**: DC plan events will extend the existing `event_type` enum from `['hire', 'promotion', 'termination', 'merit']` to include retirement plan specific events
- **Employee Linkage**: All DC plan events reference `employee_id` from the existing workforce dimension
- **Temporal Consistency**: DC plan events align with simulation year boundaries from workforce models
- **Composite Keys**: Scenario isolation (`scenario_id`, `plan_design_id`) will be added to existing event tables as **optional fields** to maintain backward compatibility

### Schema Evolution Strategy
```python
# Extends existing config/schema.py SimulationEvent
class DCPlanEvent(SimulationEvent):
    """DC plan specific event extending workforce events"""
    event_type: Literal[
        "hire", "promotion", "termination", "merit",  # Existing workforce events (preserved)
        "eligibility", "enrollment", "contribution",   # New DC plan events
        "distribution", "vesting", "forfeiture"
    ]
    plan_event_payload: Optional[Dict[str, Any]] = None  # DC-specific details
    scenario_id: Optional[str] = Field(default="baseline")  # Optional for backward compatibility
    plan_design_id: Optional[str] = Field(default="standard")  # Optional for backward compatibility
```

This approach ensures E021 leverages existing event infrastructure while adding retirement plan functionality.

---

## User Stories

### ✅ Epic E021-A: DC Plan Event Schema Foundation (Completed Stories)

**Epic E021-A breaks down the original Story 1 (18 points) into 7 focused stories:**

#### ✅ Story S072-01: Core Event Model & Pydantic v2 Architecture (5 points) [COMPLETED]
**As a** platform engineer
**I want** a unified event model with Pydantic v2 discriminated unions
**So that** all workforce and DC plan events share a consistent, type-safe architecture

**Status**: ✅ **COMPLETED** (2025-07-11)
**Implementation**: `config/events.py`
**Tests**: `tests/unit/test_simulation_event.py` (20 tests, 100% pass rate)

**Delivered**:
- Unified `SimulationEvent` model with Pydantic v2 ConfigDict pattern
- Required context fields: `scenario_id`, `plan_design_id`, `source_system`
- EventFactory pattern for validated event creation
- Automatic UUID and timestamp generation
- Field validation with proper string trimming
- Performance benchmarks exceeded (1000 events < 1s)
- Foundation ready for discriminated union payload expansion

#### Story S072-02: Workforce Event Integration (3 points) [PENDING]
**As a** platform engineer
**I want** to integrate existing workforce events into the unified model
**So that** hire, promotion, termination, and merit events use the same architecture

#### Story S072-03: Core DC Plan Events (5 points) [PENDING]
**As a** benefits analyst
**I want** core DC plan event types for contributions and distributions
**So that** we can track participant deferrals, matches, and withdrawals

#### Story S072-04: Plan Administration Events (5 points) [PENDING]
**As a** plan administrator
**I want** administrative event types for vesting and compliance
**So that** we can track forfeitures, HCE status, and regulatory compliance

#### Story S072-05: Loan & Investment Events (3 points) [PENDING]
**As a** participant services specialist
**I want** event types for loans and investment elections
**So that** we can track participant-directed transactions

#### Story S072-06: Performance & Validation Framework (8 points) [PENDING]
**As a** platform architect
**I want** high-performance event processing with comprehensive validation
**So that** we can handle 100K+ events/sec with <10ms validation

#### Story S072-07: ERISA Compliance Review & Documentation (3 points) [PENDING]
**As a** compliance officer
**I want** comprehensive ERISA compliance validation
**So that** our event schema meets all regulatory requirements

---

### Story 1: Define Retirement Plan Event Schema (18 points) [SUPERSEDED BY E021-A]
**As a** platform architect
**I want** comprehensive event types for all DC plan activities
**So that** we can track every participant interaction and calculation

**Note**: This story has been broken down into Epic E021-A with 7 focused stories (see above).

**Original Acceptance Criteria:**
- Event types cover: eligibility, enrollment, contributions, distributions, vesting, forfeitures
- Type-safe event payloads using Pydantic discriminated unions
- Events are immutable once written with complete audit trail
- Schema supports vectorized processing for 100K+ employees
- Composite key (scenario_id, plan_design_id) isolation for multi-design simulations
- Support for modeling multiple plan variations within same participant population

### Story 2: Extend dbt Models for Plan Data (13 points)
**As a** data engineer
**I want** staging and intermediate models for plan configuration
**So that** downstream models can access plan rules and parameters

**Acceptance Criteria:**
- New staging models for plan_design, irs_limits
- Intermediate models for effective plan parameters with vectorized processing
- Integration with existing employee dimension tables
- Account state snapshot models for performance optimization
- Compliance testing models for ADP/ACP and 415(c) limits
- Plan-year-specific IRS limits with annual versioning (no mid-year changes)
- Validation that IRS limits exist for each simulation year
- Automatic application of correct year's limits based on plan_year
- Historical IRS limit preservation for audit trail

### Story 3: Create Plan Configuration Schema (8 points)
**As a** benefits analyst
**I want** YAML schema for plan design parameters
**So that** I can configure plans without code changes

**Acceptance Criteria:**
- YAML schema supports all common 401(k) features including vesting
- Pydantic validation ensures configuration integrity with detailed error messages
- Documentation includes examples for common plans and regulatory patterns
- Support for effective-dated configuration changes
- Template system for standard plan designs

### Story 4: Implement Event Validation Framework (12 points)
**As a** compliance officer
**I want** automated validation of plan events
**So that** we catch data quality issues before they impact calculations

**Acceptance Criteria:**
- Events validated against business rules using Pydantic models
- Invalid events quarantined with detailed error descriptions
- Daily data quality reports generated with trend analysis
- Alert on validation failure rates >1%
- Integrated compliance testing for IRS limits and ERISA requirements
- Performance validation for vectorized operations
- Partial-year HCE determination using YTD compensation vs. plan-year thresholds
- HCE status recalculation on each payroll event
- Unit tests for HCE determination across full-year and partial-year scenarios
- **Automated IRS Compliance Validation:**
  - Real-time 402(g) and 415(c) limit checks on every contribution event
  - Pre-contribution validation to prevent limit violations
  - Automatic contribution capping when limits approached
  - Compliance event generation for audit trail
  - Integration with payroll systems for hard-stop enforcement
  - Year-specific limit retrieval from versioned irs_limits table

### Story 5: Vesting Schedule Management (5 points)
**As a** plan administrator
**I want** comprehensive vesting calculation and forfeiture tracking
**So that** terminated employees forfeit non-vested amounts correctly

**Acceptance Criteria:**
- Event types for vesting calculations and forfeitures
- Support for graded, cliff, and immediate vesting schedules
- Integration with termination events from workforce simulation
- Automated forfeiture processing for non-vested amounts
- Service computation date tracking for eligibility calculations

### Story 6: Account State Snapshots (8 points)
**As a** system architect
**I want** optimized account state reconstruction
**So that** account queries perform efficiently at enterprise scale

**Acceptance Criteria:**
- Participant account state snapshots for performance optimization
- Incremental snapshot updates from latest processed events
- Version control for state reconstruction validation
- Sub-second account balance queries for 100K+ participants
- Integration with real-time contribution processing

### Story 7: Workforce Event Integration (5 points)
**As a** compliance officer
**I want** seamless integration with workforce simulation events
**So that** vesting and eligibility respond to employment changes

**Acceptance Criteria:**
- Automatic triggering of vesting calculations on termination
- Forfeiture events for non-vested amounts upon termination
- Leave of absence impact on vesting service computations
- Rehire eligibility and vesting restoration logic
- Cross-system event correlation and audit trail

### Story 8: HCE Determination Engine (8 points)
**As a** plan administrator
**I want** accurate HCE determination for partial-year employees
**So that** ACP/ADP testing and plan compliance are correctly calculated

**Acceptance Criteria:**
- Real-time HCE status calculation using YTD compensation
- Integration with plan-year-specific IRS HCE thresholds
- Support for prior-year and current-year determination methods
- Partial-year employee compensation annualization logic
- HCE status change events when threshold crossed mid-year
- Lookback period support for prior-year determination
- Unit tests covering:
  - New hires starting mid-year
  - Terminations with partial-year compensation
  - Employees crossing HCE threshold mid-year
  - Multi-year HCE status transitions

### Story 9: IRS Compliance Enforcement Engine (13 points)
**As a** compliance officer
**I want** automated enforcement of Section 415(c) and 402(g) limits
**So that** all contributions comply with IRS regulations and avoid penalties

**Acceptance Criteria:**
- **Section 415(c) Annual Additions Limit Enforcement:**
  - Real-time tracking of aggregate contributions (EE + ER + after-tax)
  - Include all sources: deferrals, match, profit sharing, true-ups, forfeitures
  - Hard-stop constraint preventing contributions exceeding annual limit
  - Automatic allocation adjustments when approaching limits
- **Section 402(g) Elective Deferral Limit Enforcement:**
  - Track combined pre-tax + Roth deferrals against annual limit
  - Separate validation for catch-up contributions (age 50+)
  - Mid-year catch-up eligibility detection
  - Prevent excess deferrals through payroll integration
- **Compliance Event Generation:**
  - EVT_EXCESS_DEFERRAL_CORRECTION for 402(g) violations
  - EVT_ANNUAL_ADDITIONS_EXCEEDED for 415(c) violations
  - EVT_CATCH_UP_ELIGIBLE when participant reaches age 50
  - EVT_CONTRIBUTION_CAPPED when limits enforced
- **Corrective Actions:**
  - Automatic refund calculations for excess deferrals
  - Reallocation logic for employer contributions
  - Compliance correction audit trail
- **Year-Specific Limit Integration:**
  - Dynamic limit retrieval from irs_limits table by plan year
  - Support for mid-year limit changes (rare but possible)
- **Unit Tests:**
  - Employer true-up causing 415(c) excess
  - Mid-year catch-up eligibility activation
  - Multiple contribution sources aggregation
  - Year-end spillover corrections
  - Mega backdoor Roth scenario validation

### Story 10: Regulatory Limits Service & Employer Match True-Up (13 points)
**As a** plan administrator
**I want** version-controlled regulatory limits and automated true-up calculations
**So that** all compliance calculations are accurate and match benchmarks

**Acceptance Criteria:**
- **Version-Controlled Regulatory Limits Service:**
  - Ingest annual 402(g), 415(c), catch-up, and related IRS limits from YAML/CSV
  - Support mid-year effective dates for rare regulatory changes
  - Expose lookup API for validation logic with plan-year context
  - Maintain historical limits for audit trail and retroactive calculations
  - Automated alerts when new IRS limits are published
- **Employer Match True-Up Calculation During Seed Load:**
  - Calculate expected match using plan's match formula and actual deferrals
  - Compare expected match to already posted employer match amounts
  - Record `er_match_true_up = max(expected - posted, 0)` when delta ≥ $5
  - Store 0 for true-up when delta < $5 threshold
  - Allow `er_match_true_up` to be null on raw ingest
  - Populate before final schema validation
- **True-Up Integration Requirements:**
  - All compliance calculations (ADP/ACP, 402(g), 415(c)) must aggregate both `er_match` and `er_match_true_up`
  - Outputs must match current benchmark for golden seed plan with zero row-level variance
  - Support replacement of inferred values when sponsors provide actuals
- **Enhanced Ingestion Pipeline:**
  - Accept expanded money-type enum including `er_match_true_up`
  - Handle inferred true-up field with proper null handling
  - Write daily event partitions under `year=/plan=` directory structure
  - Maintain audit trail of inference vs. provided values
- **Automated Regression Tests:**
  - Validate inference logic on under-matched participants (true-up > 0)
  - Validate over-matched participants (true-up = 0)
  - Verify Section 415(c) totals include inferred true-up amounts
  - Fail CI if inference or limits lookup produces divergent results
  - Compare against golden dataset row-by-row
- **Documentation Requirements:**
  - Document deterministic true-up inference method
  - Explain audit rationale for $5 threshold
  - Provide reconciliation path for replacing inferred with actual values
  - Include examples of edge cases and their handling

### Story 11: Data Protection & PII Security (8 points)
**As a** security officer
**I want** comprehensive protection for participant PII and sensitive data
**So that** we comply with data privacy regulations and internal policies

**Acceptance Criteria:**
- **Data Classification Framework:**
  - All tables tagged with sensitivity levels (PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED)
  - Metadata includes PII field identification
  - Compensation data classified as CONFIDENTIAL minimum
  - SSN and birth dates classified as RESTRICTED
- **Encryption Standards:**
  - AES-256 encryption at rest for all PII fields
  - Field-level encryption for SSN with key rotation
  - TDE (Transparent Data Encryption) for entire database
  - Encrypted backups with separate key management
- **Data Masking & Anonymization:**
  - Dynamic data masking for non-production environments
  - Hash-based participant IDs (SHA-256) for analytics
  - Salary banding for reporting (e.g., "$100K-$125K")
  - Synthetic SSNs in format "XXX-XX-{last4}" for testing
- **Row-Level Security (RLS):**
  - Role-based access control (RBAC) implementation
  - Analyst role: aggregated data only, no individual records
  - Developer role: masked PII in non-production
  - Admin role: full access with audit logging
  - Service accounts: principle of least privilege
- **Audit & Compliance:**
  - All PII access logged with user, timestamp, purpose
  - Quarterly access reviews and certification
  - Data retention policies (7 years for ERISA)
  - Right to be forgotten workflows (where applicable)
- **Test Data Management:**
  - Synthetic data generation for all test fixtures
  - Production data scrubbing procedures
  - Referential integrity maintained in anonymized data
  - Performance-representative test datasets

---

## Technical Specifications

### Time Granularity
Events are processed at **daily resolution** to support all planned use cases:
- Same-day enrollment and contribution changes
- Daily eligibility checks
- Payroll processing alignment
- Plan sponsor batch operations

**Note**: Intra-day precision is not required as business processes (payroll, contributions, eligibility) occur in discrete daily batches, consistent with recordkeeper operations.

### Enhanced Event Schema with Type Safety
```python
from pydantic import BaseModel, Field, PositiveDecimal
from typing import Union, Literal
from decimal import Decimal
from datetime import date, datetime

class EnrollmentPayload(BaseModel):
    plan_id: str
    pre_tax_contribution_rate: float = Field(..., ge=0, le=1)
    roth_contribution_rate: float = Field(..., ge=0, le=1)
    employer_match_rate: float = Field(..., ge=0, le=1)
    auto_enrollment: bool = False
    opt_out_window_expires: Optional[date] = None

class ContributionPayload(BaseModel):
    plan_id: str
    source: Literal[
        "employee_pre_tax", "employee_roth", "employee_after_tax",
        "employer_match", "employer_match_true_up", "employer_nonelective",
        "employer_profit_sharing", "forfeiture_allocation"
    ]
    amount: PositiveDecimal
    pay_period_end: date
    ytd_amount: PositiveDecimal
    irs_limit_applied: bool = False
    inferred_value: bool = False  # Flag for calculated true-ups vs provided values

class VestingPayload(BaseModel):
    plan_id: str
    vested_percentage: float = Field(..., ge=0, le=1)
    vesting_schedule_type: Literal["graded", "cliff", "immediate"]
    service_computation_date: date

class HCEStatusPayload(BaseModel):
    plan_id: str
    determination_method: Literal["prior_year", "current_year"]
    ytd_compensation: PositiveDecimal
    annualized_compensation: PositiveDecimal
    hce_threshold: PositiveDecimal
    is_hce: bool
    determination_date: date
    prior_year_hce: Optional[bool] = None

class ComplianceEventPayload(BaseModel):
    plan_id: str
    compliance_type: Literal["402g_excess", "415c_excess", "catch_up_eligible", "contribution_capped"]
    limit_type: Literal["elective_deferral", "annual_additions", "catch_up"]
    applicable_limit: PositiveDecimal
    current_amount: PositiveDecimal
    excess_amount: Optional[PositiveDecimal] = None
    corrective_action: Optional[Literal["refund", "reallocation", "cap", "none"]] = None
    affected_sources: List[str]  # ["pre_tax", "roth", "match", "profit_sharing", etc.]
    correction_deadline: Optional[date] = None

class RetirementPlanEvent(BaseModel):
    event_id: str  # UUID
    employee_id: str
    event_type: Literal["enrollment", "contribution", "vesting", "forfeiture", "distribution", "hce_status", "compliance"]
    effective_date: date
    plan_year: int
    payload: Union[EnrollmentPayload, ContributionPayload, VestingPayload, HCEStatusPayload, ComplianceEventPayload] = Field(..., discriminator='event_type')
    created_at: datetime
    source_system: str
    scenario_id: Optional[str] = None  # For scenario isolation
    plan_design_id: Optional[str] = None  # For plan design versioning within scenario
```

### Account State Snapshot Model
```python
class ParticipantAccountState(BaseModel):
    employee_id: str
    plan_id: str
    scenario_id: str  # Required for multi-scenario support
    plan_design_id: str  # Required for plan design versioning
    as_of_date: date
    total_balance: Decimal
    vested_balance: Decimal
    employee_pre_tax_balance: Decimal
    employee_roth_balance: Decimal
    employer_match_balance: Decimal
    last_processed_event_id: str
    version: int

    @validator('total_balance')
    def validate_balance_consistency(cls, v, values):
        component_sum = (
            values.get('employee_pre_tax_balance', 0) +
            values.get('employee_roth_balance', 0) +
            values.get('employer_match_balance', 0)
        )
        if abs(v - component_sum) > Decimal('0.01'):
            raise ValueError('Total balance must equal sum of components')
        return v
```

### dbt Model Integration
```sql
-- fct_participant_account_summary.sql
{{ config(
    materialized='incremental',
    unique_key=['employee_id', 'plan_id', 'scenario_id', 'plan_design_id', 'as_of_date'],
    on_schema_change='fail',
    contract={'enforced': true},
    tags=["critical", "dc_plan", "contract"],
    indexes=[
      {'columns': ['scenario_id', 'plan_design_id'], 'type': 'hash'},
      {'columns': ['employee_id', 'plan_id'], 'type': 'hash'},
      {'columns': ['as_of_date'], 'type': 'btree'}
    ]
) }}

SELECT
  employee_id,
  plan_id,
  scenario_id,
  plan_design_id,
  as_of_date,
  SUM(CASE WHEN source = 'employee_pre_tax' THEN amount ELSE 0 END) as pre_tax_balance,
  SUM(CASE WHEN source = 'employee_roth' THEN amount ELSE 0 END) as roth_balance,
  SUM(CASE WHEN source = 'employer_match' THEN amount ELSE 0 END) as match_balance,
  SUM(amount) as total_balance,
  COUNT(*) as event_count
FROM {{ ref('fct_retirement_events') }}
WHERE event_type = 'contribution'
{% if is_incremental() %}
  AND as_of_date > (SELECT MAX(as_of_date) FROM {{ this }})
{% endif %}
GROUP BY employee_id, plan_id, scenario_id, plan_design_id, as_of_date
```

### IRS Limits Data Model
```sql
-- stg_irs_limits.sql
-- Annual IRS contribution and compensation limits
-- Source: seeds/irs_limits.csv
SELECT
    plan_year,
    employee_deferral_limit,
    catch_up_contribution_limit,
    annual_additions_limit,
    compensation_limit,
    highly_compensated_threshold,
    key_employee_threshold,
    social_security_wage_base,
    effective_date,
    created_at,
    source_document
FROM {{ ref('irs_limits') }}
WHERE effective_date = DATE_TRUNC('year', effective_date)  -- Enforce annual updates only

-- int_effective_irs_limits.sql
-- Resolve IRS limits for each plan year with validation
WITH validated_limits AS (
    SELECT
        plan_year,
        employee_deferral_limit,
        catch_up_contribution_limit,
        annual_additions_limit,
        compensation_limit,
        CASE
            WHEN plan_year >= YEAR(CURRENT_DATE)
            THEN 'projected'
            ELSE 'historical'
        END as limit_status
    FROM {{ ref('stg_irs_limits') }}
)
SELECT * FROM validated_limits
```

### HCE Determination Model
```sql
-- int_hce_determination.sql
-- Calculate HCE status for each employee based on YTD compensation
WITH ytd_compensation AS (
    SELECT
        e.employee_id,
        e.plan_year,
        e.hire_date,
        SUM(c.compensation_amount) as ytd_compensation,
        COUNT(DISTINCT c.pay_period_end) as pay_periods,
        -- Annualize for partial year employees
        CASE
            WHEN e.hire_date >= DATE_TRUNC('year', CURRENT_DATE) THEN
                SUM(c.compensation_amount) * 12.0 / COUNT(DISTINCT c.pay_period_end)
            ELSE
                SUM(c.compensation_amount)
        END as annualized_compensation
    FROM {{ ref('int_employee_demographics') }} e
    JOIN {{ ref('fct_compensation_events') }} c
        ON e.employee_id = c.employee_id
        AND c.plan_year = e.plan_year
    GROUP BY e.employee_id, e.plan_year, e.hire_date
),
hce_status AS (
    SELECT
        yc.*,
        il.hce_threshold,
        il.highly_compensated_threshold,
        yc.annualized_compensation >= il.highly_compensated_threshold as is_hce,
        LAG(yc.annualized_compensation >= il.highly_compensated_threshold)
            OVER (PARTITION BY yc.employee_id ORDER BY yc.plan_year) as prior_year_hce
    FROM ytd_compensation yc
    JOIN {{ ref('int_effective_irs_limits') }} il
        ON yc.plan_year = il.plan_year
)
SELECT
    *,
    -- Flag when HCE status changes
    CASE
        WHEN is_hce != COALESCE(prior_year_hce, FALSE) THEN TRUE
        ELSE FALSE
    END as hce_status_changed
FROM hce_status
```

### IRS Compliance Validation Models
```sql
-- int_402g_compliance_check.sql
-- Validate Section 402(g) elective deferral limits
WITH participant_deferrals AS (
    SELECT
        e.employee_id,
        e.plan_year,
        e.birth_date,
        YEAR(CURRENT_DATE) - YEAR(e.birth_date) as current_age,
        SUM(CASE WHEN c.source = 'employee_pre_tax' THEN c.amount ELSE 0 END) as pre_tax_deferrals,
        SUM(CASE WHEN c.source = 'employee_roth' THEN c.amount ELSE 0 END) as roth_deferrals,
        SUM(CASE WHEN c.source IN ('employee_pre_tax', 'employee_roth') THEN c.amount ELSE 0 END) as total_deferrals
    FROM {{ ref('int_employee_demographics') }} e
    JOIN {{ ref('fct_contribution_events') }} c
        ON e.employee_id = c.employee_id
        AND c.plan_year = e.plan_year
    WHERE c.event_type = 'contribution'
    GROUP BY e.employee_id, e.plan_year, e.birth_date
),
compliance_check AS (
    SELECT
        pd.*,
        il.employee_deferral_limit,
        il.catch_up_contribution_limit,
        -- Check if participant is catch-up eligible (age 50+ by year end)
        CASE
            WHEN pd.current_age >= 50 OR
                 (YEAR(DATE(pd.plan_year || '-12-31')) - YEAR(pd.birth_date)) >= 50
            THEN TRUE
            ELSE FALSE
        END as catch_up_eligible,
        -- Calculate applicable limit
        CASE
            WHEN pd.current_age >= 50 OR
                 (YEAR(DATE(pd.plan_year || '-12-31')) - YEAR(pd.birth_date)) >= 50
            THEN il.employee_deferral_limit + il.catch_up_contribution_limit
            ELSE il.employee_deferral_limit
        END as applicable_limit,
        -- Check for excess
        GREATEST(pd.total_deferrals - il.employee_deferral_limit, 0) as excess_amount
    FROM participant_deferrals pd
    JOIN {{ ref('int_effective_irs_limits') }} il
        ON pd.plan_year = il.plan_year
)
SELECT
    *,
    CASE
        WHEN excess_amount > 0 THEN 'VIOLATION'
        WHEN total_deferrals >= applicable_limit * 0.95 THEN 'WARNING'
        ELSE 'COMPLIANT'
    END as compliance_status
FROM compliance_check

-- int_415c_compliance_check.sql
-- Validate Section 415(c) annual additions limits
WITH annual_additions AS (
    SELECT
        e.employee_id,
        e.plan_year,
        -- Employee contributions
        SUM(CASE WHEN c.source IN ('employee_pre_tax', 'employee_roth', 'employee_after_tax')
            THEN c.amount ELSE 0 END) as employee_contributions,
        -- Employer contributions
        SUM(CASE WHEN c.source IN ('employer_match', 'employer_nonelective', 'employer_profit_sharing')
            THEN c.amount ELSE 0 END) as employer_contributions,
        -- Forfeitures allocated
        SUM(CASE WHEN c.source = 'forfeiture_allocation' THEN c.amount ELSE 0 END) as forfeitures,
        -- Total annual additions
        SUM(c.amount) as total_annual_additions
    FROM {{ ref('int_employee_demographics') }} e
    JOIN {{ ref('fct_contribution_events') }} c
        ON e.employee_id = c.employee_id
        AND c.plan_year = e.plan_year
    WHERE c.event_type IN ('contribution', 'forfeiture_allocation')
    GROUP BY e.employee_id, e.plan_year
),
compliance_check AS (
    SELECT
        aa.*,
        il.annual_additions_limit,
        il.compensation_limit,
        -- Check for excess
        GREATEST(aa.total_annual_additions - il.annual_additions_limit, 0) as excess_amount,
        -- Calculate remaining capacity
        il.annual_additions_limit - aa.total_annual_additions as remaining_capacity
    FROM annual_additions aa
    JOIN {{ ref('int_effective_irs_limits') }} il
        ON aa.plan_year = il.plan_year
)
SELECT
    *,
    CASE
        WHEN excess_amount > 0 THEN 'VIOLATION'
        WHEN remaining_capacity <= annual_additions_limit * 0.05 THEN 'WARNING'
        ELSE 'COMPLIANT'
    END as compliance_status,
    -- Suggest corrective action
    CASE
        WHEN excess_amount > 0 AND excess_amount <= employer_contributions
            THEN 'REDUCE_EMPLOYER_CONTRIBUTION'
        WHEN excess_amount > 0
            THEN 'REFUND_EMPLOYEE_CONTRIBUTION'
        ELSE NULL
    END as suggested_correction
FROM compliance_check
```

### Census Data Schema Requirements

Based on E021 modeling requirements, the `census_preprocessed.parquet` file must contain the following 20 fields to support all DC plan functionality:

#### Core Demographics (Required for E021 Stories)
```python
# Field mappings for census_preprocessed.parquet
census_schema = {
    # Core identifiers
    "employee_id": "VARCHAR",  # Primary key, maps to all event models
    "employee_ssn": "VARCHAR",  # RESTRICTED - PII field, hash_sha256 masking

    # Demographics (Story 1: Event Schema, Story 4: HCE Determination)
    "birth_date": "TIMESTAMP",  # RESTRICTED - Age calculations, catch-up eligibility
    "hire_date": "TIMESTAMP",   # Service computation, vesting calculations
    "gender": "VARCHAR",        # Demographics analysis
    "level_id": "INTEGER",      # Job level for merit calculations
    "employment_status": "VARCHAR",  # Active/terminated status

    # Compensation (Story 4: HCE Determination, Story 2: IRS Compliance)
    "current_compensation": "DOUBLE",  # CONFIDENTIAL - Annual compensation base
    "ytd_compensation": "DOUBLE",      # CONFIDENTIAL - HCE determination
    "hours_ytd": "INTEGER",           # Plan eligibility (1000 hour rule)

    # Prior-Year Contribution History (Story 1: Event Schema)
    # Maps directly to ContributionPayload.source enum values
    "prior_employee_pre_tax": "DOUBLE",      # 401(k) pre-tax deferrals
    "prior_employee_roth": "DOUBLE",         # Roth 401(k) deferrals
    "prior_employee_after_tax": "DOUBLE",    # After-tax contributions
    "prior_employer_match": "DOUBLE",        # Employer matching contributions
    "prior_employer_match_true_up": "DOUBLE", # True-up match calculations
    "prior_employer_nonelective": "DOUBLE",  # Safe harbor/nonelective
    "prior_employer_profit_sharing": "DOUBLE", # Profit sharing contributions
    "prior_forfeiture_allocation": "DOUBLE", # Forfeiture allocations

    # Additional Required Fields
    "vested_percentage": "DOUBLE",  # Story 5: Vesting calculations (0.0-1.0)
    "termination_date": "TIMESTAMP" # Story 5: Forfeiture processing (nullable)
}
```

#### Field Validation Rules
```python
class CensusValidation(BaseModel):
    """Validation rules for census_preprocessed.parquet"""

    # Required fields (cannot be null)
    required_fields = [
        "employee_id", "birth_date", "hire_date", "employment_status",
        "current_compensation", "level_id", "vested_percentage"
    ]

    # Conditional requirements
    conditional_rules = {
        "ytd_compensation": "Required if hire_date >= plan_year_start",
        "hours_ytd": "Required for eligibility determination",
        "termination_date": "Required if employment_status = 'terminated'"
    }

    # Data quality checks
    validation_rules = [
        "birth_date < hire_date",
        "hire_date <= CURRENT_DATE",
        "current_compensation > 0",
        "vested_percentage BETWEEN 0.0 AND 1.0",
        "hours_ytd >= 0"
    ]
```

#### Integration with E021 Event Models
```sql
-- Example: Loading census data into event stream
-- stg_census_baseline.sql
WITH census_validation AS (
    SELECT
        employee_id,
        employee_ssn,
        birth_date,
        hire_date,
        current_compensation,
        vested_percentage,
        -- Validate required fields
        CASE
            WHEN employee_id IS NULL THEN 'MISSING_EMPLOYEE_ID'
            WHEN birth_date IS NULL THEN 'MISSING_BIRTH_DATE'
            WHEN current_compensation <= 0 THEN 'INVALID_COMPENSATION'
            WHEN vested_percentage NOT BETWEEN 0.0 AND 1.0 THEN 'INVALID_VESTING'
            ELSE 'VALID'
        END as validation_status
    FROM read_parquet('data/census_preprocessed.parquet')
)
SELECT
    *,
    -- Generate baseline events for prior contributions
    ARRAY[
        {'source': 'employee_pre_tax', 'amount': prior_employee_pre_tax},
        {'source': 'employee_roth', 'amount': prior_employee_roth},
        {'source': 'employer_match', 'amount': prior_employer_match}
    ] as baseline_contributions
FROM census_validation
WHERE validation_status = 'VALID'
```

#### Data Security Classification
- **RESTRICTED**: `employee_ssn`, `birth_date` (PII fields requiring encryption)
- **CONFIDENTIAL**: All compensation and contribution fields
- **INTERNAL**: Demographics, employment status, job levels
- **PUBLIC**: None (all census data requires access controls)

This schema ensures the census file supports all E021 user stories while maintaining data security standards and regulatory compliance requirements.

### Data Classification & Security Schema
```python
from enum import Enum
from typing import List, Optional

class DataClassification(str, Enum):
    PUBLIC = "PUBLIC"  # Non-sensitive, shareable data
    INTERNAL = "INTERNAL"  # Internal use only
    CONFIDENTIAL = "CONFIDENTIAL"  # Sensitive business data
    RESTRICTED = "RESTRICTED"  # PII, requires encryption

class FieldSecurity(BaseModel):
    field_name: str
    classification: DataClassification
    contains_pii: bool
    encryption_required: bool
    masking_strategy: Optional[str] = None
    retention_years: int = 7  # ERISA default

class TableSecurity(BaseModel):
    table_name: str
    schema_name: str = "main"
    classification: DataClassification
    row_level_security: bool
    field_security: List[FieldSecurity]
    audit_required: bool = True

# Example: Participant table security definition
participant_security = TableSecurity(
    table_name="fct_participant_account_summary",
    classification=DataClassification.RESTRICTED,
    row_level_security=True,
    field_security=[
        FieldSecurity(
            field_name="employee_ssn",
            classification=DataClassification.RESTRICTED,
            contains_pii=True,
            encryption_required=True,
            masking_strategy="hash_sha256"
        ),
        FieldSecurity(
            field_name="current_compensation",
            classification=DataClassification.CONFIDENTIAL,
            contains_pii=False,
            encryption_required=True,
            masking_strategy="salary_band"
        ),
        FieldSecurity(
            field_name="birth_date",
            classification=DataClassification.RESTRICTED,
            contains_pii=True,
            encryption_required=True,
            masking_strategy="age_band"
        )
    ]
)
```

### Scenario Isolation Architecture
```python
class PlanDesignVariation(BaseModel):
    """Represents a specific plan design configuration within a scenario"""
    scenario_id: str  # Base scenario for participant population
    plan_design_id: str  # Unique identifier for this design variation
    design_name: str  # Human-readable name (e.g., "Enhanced Match Formula")
    base_plan_id: str  # Reference to base plan configuration
    variations: Dict[str, Any]  # Specific parameter overrides

class ScenarioIsolationKey(BaseModel):
    """Composite key for complete data isolation"""
    scenario_id: str
    plan_design_id: str

    @property
    def composite_key(self) -> str:
        return f"{self.scenario_id}:{self.plan_design_id}"
```

```sql
-- int_scenario_plan_designs.sql
-- Map scenario variations to plan configurations
WITH plan_variations AS (
    SELECT
        scenario_id,
        plan_design_id,
        plan_id,
        design_name,
        JSON_EXTRACT(variations, '$.matching.formula') as match_formula,
        JSON_EXTRACT(variations, '$.features.auto_enrollment') as auto_enrollment,
        JSON_EXTRACT(variations, '$.features.auto_escalation') as auto_escalation,
        effective_date
    FROM {{ ref('scenario_plan_designs') }}
)
SELECT
    pv.*,
    pd.plan_type,
    pd.vesting_schedule,
    -- Apply variations to base plan parameters
    COALESCE(pv.match_formula, pd.match_formula) as effective_match_formula,
    COALESCE(pv.auto_enrollment, pd.auto_enrollment) as effective_auto_enrollment
FROM plan_variations pv
JOIN {{ ref('plan_designs') }} pd ON pv.plan_id = pd.plan_id
```

### DuckDB-Compatible Security Implementation
```sql
-- DuckDB-compatible data masking views for developers
CREATE OR REPLACE VIEW masked_participant_accounts AS
SELECT
    -- Hash employee ID for privacy (DuckDB compatible)
    hash(employee_id) as hashed_employee_id,
    plan_id,
    scenario_id,
    plan_design_id,
    as_of_date,
    -- Band salary data
    CASE
        WHEN total_balance < 50000 THEN '<$50K'
        WHEN total_balance < 100000 THEN '$50K-$100K'
        WHEN total_balance < 250000 THEN '$100K-$250K'
        WHEN total_balance < 500000 THEN '$250K-$500K'
        WHEN total_balance < 1000000 THEN '$500K-$1M'
        ELSE '$1M+'
    END as balance_band,
    -- Mask exact amounts
    ROUND(total_balance / 5000) * 5000 as rounded_balance,
    -- Keep ratios for analytics
    vested_balance / NULLIF(total_balance, 0) as vesting_percentage,
    -- Age bands instead of birth date
    CASE
        WHEN employee_age < 30 THEN '<30'
        WHEN employee_age < 40 THEN '30-39'
        WHEN employee_age < 50 THEN '40-49'
        WHEN employee_age < 60 THEN '50-59'
        ELSE '60+'
    END as age_band
FROM fct_participant_account_summary;

-- Analyst-safe aggregated view
CREATE OR REPLACE VIEW aggregate_participant_metrics AS
SELECT
    plan_id,
    scenario_id,
    plan_design_id,
    as_of_date,
    COUNT(*) as participant_count,
    AVG(total_balance) as avg_balance,
    MEDIAN(total_balance) as median_balance,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY total_balance) as p25_balance,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY total_balance) as p75_balance,
    SUM(total_balance) as total_plan_assets
FROM fct_participant_account_summary
GROUP BY plan_id, scenario_id, plan_design_id, as_of_date;
```

**Python-Based Access Control**: Since DuckDB doesn't support row-level security policies, access control will be implemented in Dagster assets and Python utilities:

```python
# Application-level security enforcement
class DataAccessManager:
    """Role-based data access control for DuckDB"""

    def get_participant_data(self, user_role: str, employee_ids: Optional[List[str]] = None) -> str:
        if user_role == 'admin':
            # Full access with audit logging
            self._log_access(user_role, employee_ids)
            return "SELECT * FROM fct_participant_account_summary"
        elif user_role == 'analyst':
            # Aggregated data only
            return "SELECT * FROM aggregate_participant_metrics"
        elif user_role == 'developer':
            # Masked data
            return "SELECT * FROM masked_participant_accounts"
        else:
            raise PermissionError(f"Role {user_role} not authorized for participant data")

    def _log_access(self, user_role: str, employee_ids: Optional[List[str]]):
        # Audit logging implementation
        pass
```

### Regulatory Limits Service API
```python
class RegulatoryLimitsService:
    """Version-controlled service for IRS regulatory limits lookup"""

    def get_limits(self, plan_year: int, effective_date: date = None) -> IRSLimits:
        """Get IRS limits for specific plan year and date"""
        pass

    def get_limits_range(self, start_year: int, end_year: int) -> List[IRSLimits]:
        """Get limits for multiple years for multi-year simulations"""
        pass

    def validate_contribution(self, employee_id: str, contribution: ContributionPayload) -> ComplianceResult:
        """Validate contribution against applicable limits"""
        pass

class IRSLimits(BaseModel):
    plan_year: int
    effective_date: date
    employee_deferral_limit: Decimal
    catch_up_contribution_limit: Decimal
    annual_additions_limit: Decimal
    compensation_limit: Decimal
    hce_threshold: Decimal
    key_employee_threshold: Decimal
    social_security_wage_base: Decimal
    source_document: str  # e.g., "IRS Notice 2024-80"

class TrueUpCalculation(BaseModel):
    """Employer match true-up calculation logic"""
    employee_id: str
    plan_year: int
    expected_match: Decimal
    posted_match: Decimal
    true_up_amount: Decimal
    threshold_met: bool  # True if delta >= $5
    calculation_method: str
    audit_trail: Dict[str, Any]

# True-up inference during seed load
def calculate_match_true_up(
    employee_id: str,
    plan_formula: Dict[str, Any],
    actual_deferrals: Decimal,
    posted_match: Decimal
) -> TrueUpCalculation:
    """
    Calculate employer match true-up during historical data ingestion.

    Args:
        employee_id: Participant identifier
        plan_formula: Match formula configuration
        actual_deferrals: Combined pre-tax + Roth + after-tax deferrals
        posted_match: Already recorded employer match amount

    Returns:
        TrueUpCalculation with inferred true-up amount
    """
    # Apply plan match formula to actual deferrals
    expected_match = apply_match_formula(plan_formula, actual_deferrals)

    # Calculate delta
    delta = expected_match - posted_match

    # Apply $5 threshold
    true_up_amount = max(delta, 0) if delta >= 5 else 0

    return TrueUpCalculation(
        employee_id=employee_id,
        expected_match=expected_match,
        posted_match=posted_match,
        true_up_amount=true_up_amount,
        threshold_met=delta >= 5,
        calculation_method="inferred_from_deferrals",
        audit_trail={
            "plan_formula": plan_formula,
            "actual_deferrals": actual_deferrals,
            "delta": delta,
            "threshold_applied": 5
        }
    )
```

### Enhanced Plan Configuration
```yaml
plan_config:
  plan_id: "401k_standard"
  plan_year: 2025
  plan_type: "401(k)"
  effective_date: "2025-01-01"

  features:
    roth: enabled
    after_tax: enabled
    catch_up: enabled
    hardship_withdrawals: enabled
    in_service_distributions: disabled

  eligibility:
    minimum_age: 21
    minimum_service_months: 12
    entry_dates: quarterly  # immediate, monthly, quarterly, semi-annual
    hours_requirement: 1000

  vesting:
    type: "graded"  # graded, cliff, immediate
    schedule:
      - years: 2
        percentage: 0.2
      - years: 3
        percentage: 0.4
      - years: 4
        percentage: 0.6
      - years: 5
        percentage: 0.8
      - years: 6
        percentage: 1.0

  matching:
    formula: "100% on first 3%, 50% on next 2%"
    tiers:
      - employee_max: 0.03
        match_rate: 1.00
      - employee_max: 0.05
        match_rate: 0.50
    max_match_percentage: 0.04
    true_up: enabled

  limits:
    employee_deferral: 23000
    catch_up: 7500
    annual_additions: 69000
    compensation: 345000

```

---

## Data Encryption & Masking Standards

### Encryption at Rest
```python
# DuckDB encryption configuration
class EncryptionConfig(BaseModel):
    encryption_method: Literal["AES256-GCM", "AES256-CTR"] = "AES256-GCM"
    key_management_service: Literal["AWS_KMS", "Azure_KeyVault", "Local"] = "AWS_KMS"
    key_rotation_days: int = 90

    # Field-level encryption for highest sensitivity
    field_encryption_keys: Dict[str, str] = {
        "employee_ssn": "arn:aws:kms:us-east-1:123456789:key/ssn-key",
        "birth_date": "arn:aws:kms:us-east-1:123456789:key/pii-key",
        "bank_account": "arn:aws:kms:us-east-1:123456789:key/financial-key"
    }
```

### Python-Based Data Masking Utilities
```python
# DuckDB-compatible masking implemented in Python
class DataMaskingUtils:
    """Data masking utilities for PII protection"""

    @staticmethod
    def mask_ssn(ssn: str, user_role: str) -> str:
        """Mask SSN based on user role"""
        if user_role == 'admin':
            return ssn  # Full access for admins
        elif user_role in ['developer', 'analyst']:
            return f'XXX-XX-{ssn[-4:]}'  # Last 4 only
        else:
            return 'XXX-XX-XXXX'  # Fully masked

    @staticmethod
    def mask_compensation(amount: float, user_role: str) -> str:
        """Mask compensation based on user role"""
        if user_role == 'admin':
            return str(amount)
        elif user_role == 'analyst':
            # Return salary band
            if amount < 50000:
                return '<$50K'
            elif amount < 100000:
                return '$50K-$100K'
            elif amount < 150000:
                return '$100K-$150K'
            elif amount < 200000:
                return '$150K-$200K'
            elif amount < 250000:
                return '$200K-$250K'
            else:
                return '$250K+'
        else:
            return 'MASKED'

    @staticmethod
    def generate_salary_band_sql() -> str:
        """Generate DuckDB-compatible salary banding SQL"""
        return """
        CASE
            WHEN current_compensation < 50000 THEN '<$50K'
            WHEN current_compensation < 100000 THEN '$50K-$100K'
            WHEN current_compensation < 150000 THEN '$100K-$150K'
            WHEN current_compensation < 200000 THEN '$150K-$200K'
            WHEN current_compensation < 250000 THEN '$200K-$250K'
            ELSE '$250K+'
        END as compensation_band
        """
```

### Encryption in Transit
- TLS 1.3 minimum for all database connections
- Certificate pinning for service accounts
- Mutual TLS (mTLS) for inter-service communication
- Encrypted connection strings with runtime decryption

### Key Management
```yaml
key_management:
  master_key:
    provider: AWS_KMS
    rotation: automatic
    frequency_days: 90

  data_encryption_keys:
    generation: on_demand
    cache_ttl_minutes: 60
    max_cache_size: 1000

  access_control:
    - role: admin_role
      permissions: [encrypt, decrypt, rotate]
    - role: service_account_role
      permissions: [decrypt]
    - role: developer_role
      permissions: []  # No direct key access
```

### Compliance Validation
```python
@pytest.mark.security
def test_pii_encryption():
    """Verify all PII fields are encrypted at rest"""
    sensitive_fields = ['employee_ssn', 'birth_date', 'bank_account']

    for field in sensitive_fields:
        # Verify field is encrypted in storage
        assert is_field_encrypted('fct_participant_account_summary', field)

        # Verify encryption key exists
        assert get_encryption_key(field) is not None

        # Verify key rotation is configured
        assert get_key_rotation_period(field) <= 90
```

## Performance Requirements

| Metric | Requirement | Implementation Strategy |
|--------|-------------|------------------------|
| Event Processing | <100ms for 1M participant-years | Vectorized operations using Polars/Pandas |
| State Reconstruction | <1s from latest snapshot | Optimized snapshot + delta processing |
| Account Balance Queries | <100ms for 100K participants | Materialized account summary views |
| Scenario Isolation | Zero data leakage between scenarios | Composite key (scenario_id, plan_design_id) partitioning |
| Plan Design Variations | Support 10+ designs per scenario | Efficient variation overlay on base configurations |
| Memory Usage | <8GB for 100K employee simulation | Efficient data types and streaming processing |

## Dependencies
- Existing event sourcing infrastructure
- Employee master data from workforce simulation
- IRS limit tables (annual updates required)
- Pydantic 2.7.4+ for enhanced type safety
- **Phase 1**: Standard Python libraries (pandas, numpy) for initial implementation
- **Phase 2**: Polars integration for vectorized processing (after Epic E020 completion)
- ERISA compliance validation rules, ADP, ACP
- Golden dataset for true-up validation benchmarks

**Implementation Strategy**: E021 will be implemented in phases to avoid dependencies on other epics:
- **Phase 1**: Core DC plan functionality using existing Python libraries
- **Phase 2**: Performance optimization with Polars (post-E020)

## Risks
- **Risk**: Complex ERISA compliance requirements
- **Mitigation**: Partner with benefits counsel for validation

## Estimated Effort
**Total Story Points**: 93 points (including HCE determination, IRS compliance, regulatory limits service, and data security)
**Estimated Duration**: 6-7 sprints

---

## Unit Test Examples

### tests/test_hce_determination.py
```python
import pytest
from decimal import Decimal
from datetime import date
from models.hce_determination import calculate_hce_status

class TestHCEDetermination:

    def test_full_year_employee_below_threshold(self):
        """Full-year employee with compensation below HCE threshold"""
        result = calculate_hce_status(
            employee_id="EMP001",
            ytd_compensation=Decimal("150000"),
            hire_date=date(2024, 1, 1),
            pay_periods=24,
            plan_year=2025,
            hce_threshold=Decimal("160000")
        )
        assert result.is_hce is False
        assert result.annualized_compensation == Decimal("150000")

    def test_full_year_employee_above_threshold(self):
        """Full-year employee with compensation above HCE threshold"""
        result = calculate_hce_status(
            employee_id="EMP002",
            ytd_compensation=Decimal("175000"),
            hire_date=date(2024, 1, 1),
            pay_periods=24,
            plan_year=2025,
            hce_threshold=Decimal("160000")
        )
        assert result.is_hce is True
        assert result.annualized_compensation == Decimal("175000")

    def test_partial_year_new_hire_annualization(self):
        """New hire mid-year with annualized compensation above threshold"""
        result = calculate_hce_status(
            employee_id="EMP003",
            ytd_compensation=Decimal("85000"),  # 6 months
            hire_date=date(2025, 7, 1),
            pay_periods=12,
            plan_year=2025,
            hce_threshold=Decimal("160000")
        )
        assert result.is_hce is True
        assert result.annualized_compensation == Decimal("170000")  # 85k * 12/6

    def test_termination_partial_year(self):
        """Terminated employee with partial year compensation"""
        result = calculate_hce_status(
            employee_id="EMP004",
            ytd_compensation=Decimal("100000"),  # 8 months
            hire_date=date(2023, 1, 1),
            termination_date=date(2025, 8, 31),
            pay_periods=16,
            plan_year=2025,
            hce_threshold=Decimal("160000")
        )
        assert result.is_hce is False
        assert result.annualized_compensation == Decimal("150000")  # 100k * 12/8

    def test_hce_status_transition(self):
        """Employee crossing HCE threshold between years"""
        # 2024 - Not HCE
        result_2024 = calculate_hce_status(
            employee_id="EMP005",
            ytd_compensation=Decimal("150000"),
            plan_year=2024,
            hce_threshold=Decimal("155000")
        )
        assert result_2024.is_hce is False

        # 2025 - Becomes HCE
        result_2025 = calculate_hce_status(
            employee_id="EMP005",
            ytd_compensation=Decimal("165000"),
            plan_year=2025,
            hce_threshold=Decimal("160000"),
            prior_year_hce=False
        )
        assert result_2025.is_hce is True
        assert result_2025.hce_status_changed is True
```

### tests/test_irs_compliance.py
```python
import pytest
from decimal import Decimal
from datetime import date
from models.compliance_engine import ComplianceEngine

class TestIRSComplianceEnforcement:

    def test_402g_basic_limit_enforcement(self):
        """Test basic 402(g) limit enforcement without catch-up"""
        engine = ComplianceEngine(plan_year=2024)

        # Attempt to contribute exactly at limit
        result = engine.validate_elective_deferral(
            employee_id="EMP001",
            birth_date=date(1980, 1, 1),
            current_deferrals=Decimal("22000"),
            new_deferral=Decimal("1000")
        )
        assert result.compliance_status == "COMPLIANT"
        assert result.allowed_amount == Decimal("1000")

        # Attempt to exceed limit
        result = engine.validate_elective_deferral(
            employee_id="EMP001",
            birth_date=date(1980, 1, 1),
            current_deferrals=Decimal("23000"),
            new_deferral=Decimal("1000")
        )
        assert result.compliance_status == "VIOLATION"
        assert result.allowed_amount == Decimal("0")
        assert result.excess_amount == Decimal("1000")

    def test_catch_up_eligibility_mid_year(self):
        """Test catch-up contribution eligibility when turning 50 mid-year"""
        engine = ComplianceEngine(plan_year=2024)

        # Employee turns 50 on July 1, 2024
        result = engine.validate_elective_deferral(
            employee_id="EMP002",
            birth_date=date(1974, 7, 1),
            current_deferrals=Decimal("23000"),
            new_deferral=Decimal("7500"),
            contribution_date=date(2024, 8, 1)
        )
        assert result.compliance_status == "COMPLIANT"
        assert result.catch_up_eligible is True
        assert result.allowed_amount == Decimal("7500")

    def test_415c_multiple_source_aggregation(self):
        """Test 415(c) limit with multiple contribution sources"""
        engine = ComplianceEngine(plan_year=2024)

        contributions = {
            "employee_pre_tax": Decimal("23000"),
            "employee_roth": Decimal("0"),
            "employer_match": Decimal("15000"),
            "employer_profit_sharing": Decimal("25000"),
            "forfeiture_allocation": Decimal("5000")
        }

        result = engine.validate_annual_additions(
            employee_id="EMP003",
            current_contributions=contributions,
            new_contribution_source="employer_true_up",
            new_contribution_amount=Decimal("2000")
        )

        assert result.total_annual_additions == Decimal("68000")
        assert result.compliance_status == "WARNING"  # At 98.5% of limit
        assert result.remaining_capacity == Decimal("1000")
        assert result.allowed_amount == Decimal("1000")  # Capped at remaining

    def test_employer_true_up_causing_415c_excess(self):
        """Test employer true-up causing 415(c) violation"""
        engine = ComplianceEngine(plan_year=2024)

        contributions = {
            "employee_pre_tax": Decimal("20000"),
            "employer_match": Decimal("10000"),
            "employer_profit_sharing": Decimal("35000")
        }

        # Year-end true-up calculation
        true_up_amount = Decimal("5000")

        result = engine.validate_annual_additions(
            employee_id="EMP004",
            current_contributions=contributions,
            new_contribution_source="employer_true_up",
            new_contribution_amount=true_up_amount
        )

        assert result.compliance_status == "VIOLATION"
        assert result.excess_amount == Decimal("1000")
        assert result.corrective_action == "REDUCE_EMPLOYER_CONTRIBUTION"
        assert result.allowed_amount == Decimal("4000")

    def test_mega_backdoor_roth_scenario(self):
        """Test mega backdoor Roth contribution scenario"""
        engine = ComplianceEngine(plan_year=2024)

        # High earner maximizing all contribution types
        contributions = {
            "employee_pre_tax": Decimal("23000"),  # Max 402(g)
            "employee_after_tax": Decimal("35000"), # For mega backdoor
            "employer_match": Decimal("10000"),
            "employer_profit_sharing": Decimal("0")
        }

        result = engine.validate_annual_additions(
            employee_id="EMP005",
            current_contributions=contributions,
            new_contribution_source="employee_after_tax",
            new_contribution_amount=Decimal("2000")
        )

        assert result.total_annual_additions == Decimal("68000")
        assert result.remaining_capacity == Decimal("1000")
        assert result.allowed_amount == Decimal("1000")  # Capped
        assert result.supports_mega_backdoor is True

    def test_compensation_limit_impact_on_contributions(self):
        """Test how compensation limit affects contribution calculations"""
        engine = ComplianceEngine(plan_year=2024)

        # Employee with compensation above IRS limit
        result = engine.calculate_maximum_contributions(
            employee_id="EMP006",
            actual_compensation=Decimal("500000"),
            deferral_percentage=Decimal("0.10"),
            match_formula="100% of first 6%"
        )

        assert result.compensation_limit == Decimal("345000")
        assert result.max_employee_deferral == Decimal("23000")  # 402(g) limit
        assert result.max_employer_match == Decimal("20700")  # 6% of 345k
        assert result.max_annual_additions == Decimal("69000")

    def test_year_end_spillover_correction(self):
        """Test year-end spillover correction for excess deferrals"""
        engine = ComplianceEngine(plan_year=2024)

        # December contribution causing excess
        result = engine.process_year_end_contribution(
            employee_id="EMP007",
            ytd_deferrals=Decimal("22500"),
            final_payroll_deferral=Decimal("1500"),
            correction_deadline=date(2025, 3, 15)
        )

        assert result.excess_amount == Decimal("1000")
        assert result.correction_type == "REFUND"
        assert result.taxable_year == 2024
        assert result.correction_deadline == date(2025, 3, 15)

        # Generate correction event
        event = result.generate_correction_event()
        assert event.event_type == "compliance"
        assert event.payload.compliance_type == "402g_excess"
        assert event.payload.corrective_action == "refund"
```

### tests/test_true_up_calculation.py
```python
import pytest
from decimal import Decimal
from datetime import date
from models.true_up_engine import calculate_match_true_up, TrueUpCalculation

class TestTrueUpCalculation:

    def test_under_matched_participant_with_true_up(self):
        """Test participant with match shortfall requiring true-up"""
        plan_formula = {
            "formula": "100% on first 3%, 50% on next 2%",
            "tiers": [
                {"employee_max": 0.03, "match_rate": 1.00},
                {"employee_max": 0.05, "match_rate": 0.50}
            ]
        }

        # Employee deferred 5% of $100k salary = $5000
        # Expected match: 100% of $3000 + 50% of $2000 = $4000
        # Posted match: $3500 (shortfall of $500)
        result = calculate_match_true_up(
            employee_id="EMP001",
            plan_formula=plan_formula,
            actual_deferrals=Decimal("5000"),  # 5% of $100k
            posted_match=Decimal("3500")
        )

        assert result.expected_match == Decimal("4000")
        assert result.posted_match == Decimal("3500")
        assert result.true_up_amount == Decimal("500")
        assert result.threshold_met is True  # $500 >= $5
        assert result.calculation_method == "inferred_from_deferrals"

    def test_over_matched_participant_no_true_up(self):
        """Test participant with excess match (no true-up needed)"""
        plan_formula = {
            "formula": "100% on first 3%",
            "tiers": [{"employee_max": 0.03, "match_rate": 1.00}]
        }

        # Employee deferred 2% of $100k = $2000
        # Expected match: $2000
        # Posted match: $2100 (over-matched by $100)
        result = calculate_match_true_up(
            employee_id="EMP002",
            plan_formula=plan_formula,
            actual_deferrals=Decimal("2000"),
            posted_match=Decimal("2100")
        )

        assert result.expected_match == Decimal("2000")
        assert result.posted_match == Decimal("2100")
        assert result.true_up_amount == Decimal("0")  # No negative true-ups
        assert result.threshold_met is False

    def test_small_shortfall_below_threshold(self):
        """Test shortfall below $5 threshold (no true-up)"""
        plan_formula = {
            "formula": "50% on first 6%",
            "tiers": [{"employee_max": 0.06, "match_rate": 0.50}]
        }

        # Shortfall of $3 (below $5 threshold)
        result = calculate_match_true_up(
            employee_id="EMP003",
            plan_formula=plan_formula,
            actual_deferrals=Decimal("3000"),  # Expected match: $1500
            posted_match=Decimal("1497")      # Shortfall: $3
        )

        assert result.expected_match == Decimal("1500")
        assert result.true_up_amount == Decimal("0")  # Below threshold
        assert result.threshold_met is False
        assert result.audit_trail["delta"] == Decimal("3")
        assert result.audit_trail["threshold_applied"] == 5

    def test_415c_compliance_includes_true_up(self):
        """Test that 415(c) calculations include inferred true-up"""
        from models.compliance_engine import ComplianceEngine

        engine = ComplianceEngine(plan_year=2024)

        # Participant with inferred true-up
        contributions = {
            "employee_pre_tax": Decimal("20000"),
            "employer_match": Decimal("8000"),
            "employer_match_true_up": Decimal("500"),  # Inferred
            "employer_profit_sharing": Decimal("40000")
        }

        result = engine.validate_annual_additions(
            employee_id="EMP004",
            current_contributions=contributions
        )

        # Total should include true-up: 20k + 8k + 0.5k + 40k = 68.5k
        assert result.total_annual_additions == Decimal("68500")
        assert result.compliance_status == "WARNING"  # Close to limit

    def test_golden_dataset_benchmark_match(self):
        """Test that true-up calculations match golden benchmark exactly"""
        # Load golden dataset participant records
        golden_participants = load_golden_dataset()

        for participant in golden_participants:
            calculated_true_up = calculate_match_true_up(
                employee_id=participant["employee_id"],
                plan_formula=participant["plan_formula"],
                actual_deferrals=participant["actual_deferrals"],
                posted_match=participant["posted_match"]
            )

            # Must match golden benchmark exactly (zero variance)
            expected_true_up = participant["expected_true_up"]
            assert calculated_true_up.true_up_amount == expected_true_up, \
                f"True-up mismatch for {participant['employee_id']}: " \
                f"calculated={calculated_true_up.true_up_amount}, expected={expected_true_up}"

    def test_audit_trail_completeness(self):
        """Test that audit trail captures all calculation inputs"""
        plan_formula = {"formula": "Dollar for dollar up to 6%"}

        result = calculate_match_true_up(
            employee_id="EMP005",
            plan_formula=plan_formula,
            actual_deferrals=Decimal("6000"),
            posted_match=Decimal("5990")
        )

        # Verify audit trail completeness
        audit = result.audit_trail
        assert "plan_formula" in audit
        assert "actual_deferrals" in audit
        assert "delta" in audit
        assert "threshold_applied" in audit
        assert audit["actual_deferrals"] == Decimal("6000")
        assert audit["delta"] == Decimal("10")
        assert audit["threshold_applied"] == 5
```

---

## Test Fixture Examples (Anonymized)

### tests/fixtures/participant_test_data.csv
```csv
hashed_employee_id,synthetic_ssn,birth_year_band,hire_date,compensation_band,employment_status
a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3,XXX-XX-1234,1970-1979,2020-01-15,$100K-$125K,active
b3a8e0e1f9ab1a3e5c5f3e5d3e5c5f3e5d3e5c5f3e5d3e5c5f3e5d3e5c5f3e5d,XXX-XX-5678,1980-1989,2018-07-01,$75K-$100K,active
c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4,XXX-XX-9012,1960-1969,2015-03-20,$150K-$175K,active
d2e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5,XXX-XX-3456,1990-1999,2022-09-01,$50K-$75K,active
```

### tests/fixtures/contribution_test_events.json
```json
[
  {
    "event_id": "550e8400-e29b-41d4-a716-446655440001",
    "hashed_employee_id": "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
    "event_type": "contribution",
    "effective_date": "2024-01-15",
    "plan_year": 2024,
    "payload": {
      "plan_id": "401k_test",
      "source": "employee_pre_tax",
      "amount": 958.33,
      "pay_period_end": "2024-01-15",
      "ytd_amount": 958.33,
      "irs_limit_applied": false
    },
    "scenario_id": "test_scenario_001",
    "plan_design_id": "standard_match"
  },
  {
    "event_id": "550e8400-e29b-41d4-a716-446655440002",
    "hashed_employee_id": "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
    "event_type": "contribution",
    "effective_date": "2024-01-15",
    "plan_year": 2024,
    "payload": {
      "plan_id": "401k_test",
      "source": "employer_match",
      "amount": 479.17,
      "pay_period_end": "2024-01-15",
      "ytd_amount": 479.17,
      "irs_limit_applied": false
    },
    "scenario_id": "test_scenario_001",
    "plan_design_id": "standard_match"
  }
]
```

### tests/fixtures/synthetic_data_generator.py
```python
import hashlib
import random
from datetime import date, timedelta
from faker import Faker

fake = Faker()

def generate_hashed_id(original_id: str) -> str:
    """Generate SHA-256 hash of employee ID"""
    return hashlib.sha256(original_id.encode()).hexdigest()

def generate_synthetic_ssn() -> str:
    """Generate synthetic SSN in masked format"""
    last_four = f"{random.randint(0, 9999):04d}"
    return f"XXX-XX-{last_four}"

def generate_salary_band(base_salary: float) -> str:
    """Convert exact salary to band"""
    bands = [
        (0, 50000, "<$50K"),
        (50000, 75000, "$50K-$75K"),
        (75000, 100000, "$75K-$100K"),
        (100000, 125000, "$100K-$125K"),
        (125000, 150000, "$125K-$150K"),
        (150000, 175000, "$150K-$175K"),
        (175000, 200000, "$175K-$200K"),
        (200000, 250000, "$200K-$250K"),
        (250000, float('inf'), "$250K+")
    ]

    for min_sal, max_sal, band in bands:
        if min_sal <= base_salary < max_sal:
            return band
    return "$250K+"

def generate_test_participant(index: int) -> dict:
    """Generate anonymized test participant"""
    original_id = f"EMP{index:06d}"
    birth_year = random.randint(1955, 2000)
    hire_date = fake.date_between(start_date='-20y', end_date='today')
    base_salary = random.uniform(40000, 300000)

    return {
        "hashed_employee_id": generate_hashed_id(original_id),
        "synthetic_ssn": generate_synthetic_ssn(),
        "birth_year_band": f"{(birth_year // 10) * 10}-{(birth_year // 10) * 10 + 9}",
        "hire_date": hire_date.isoformat(),
        "compensation_band": generate_salary_band(base_salary),
        "employment_status": random.choice(["active", "active", "active", "terminated"]),
        # Store original values encrypted for validation only
        "_encrypted_original": {
            "employee_id": original_id,  # Would be encrypted
            "ssn": None,  # Never store real SSN
            "birth_date": None,  # Never store exact date
            "salary": None  # Never store exact amount
        }
    }

# Generate test dataset
test_participants = [generate_test_participant(i) for i in range(1000)]
```

---

## Seed File Examples

### seeds/irs_limits.csv
```csv
plan_year,employee_deferral_limit,catch_up_contribution_limit,annual_additions_limit,compensation_limit,highly_compensated_threshold,hce_threshold,key_employee_threshold,social_security_wage_base,effective_date,created_at,source_document
2024,23000,7500,69000,345000,155000,155000,220000,168600,2024-01-01,2023-11-01,IRS Notice 2023-75
2025,23500,7500,70000,350000,160000,160000,230000,176100,2025-01-01,2024-11-01,IRS Notice 2024-80
2026,24000,7500,71000,355000,165000,165000,235000,180000,2026-01-01,2025-11-01,PROJECTED
```

---

## Required Census Schema

### Summary
Based on E021 requirements analysis, the `census_preprocessed.parquet` file requires **20 core fields** to support comprehensive DC plan modeling and integration with existing workforce events.

### Core Demographic Fields (10 fields)
```python
# Fields validated against existing census data structure
employee_id: str                    # Primary key, links to workforce events
ssn: str                           # PII field, encryption required
birth_date: date                   # Age calculations, HCE determination
hire_date: date                    # Tenure calculations, eligibility rules
current_compensation: float        # Base for contribution calculations
gender: str                        # Optional for demographic analysis
job_level: int                     # Links to hazard tables (1-5 scale)
employment_status: str             # Active/terminated status
termination_date: Optional[date]   # If employment_status = terminated
department: Optional[str]          # Optional for plan segmentation
```

### Contribution History Fields (8 fields)
```python
# Expanded money-type enum supporting all contribution sources
employee_pre_tax_ytd: float        # Section 402(g) limit tracking
employee_roth_ytd: float           # Section 402(g) combined with pre-tax
employee_after_tax_ytd: float      # Non-deductible contributions
employer_match_ytd: float          # Basic match contributions
employer_match_true_up_ytd: float  # Year-end true-up corrections
employer_nonelective_ytd: float    # Safe harbor contributions
employer_profit_sharing_ytd: float # Discretionary contributions
forfeiture_allocation_ytd: float   # Forfeited account redistributions
```

### Additional Required Fields (2 fields)
```python
vested_percentage: float           # Current vesting percentage (0.0-1.0)
plan_id: str                      # Links to plan_designs table
```

### Data Quality Requirements
- **PII Encryption**: `ssn` field must use AES-256 encryption at rest
- **Date Validation**: All date fields validated for business logic consistency
- **Money Type Validation**: All contribution fields ≥ 0, sum validation against compensation
- **Primary Key**: `employee_id` must be unique across census dataset
- **Referential Integrity**: `employee_id` must exist in workforce dimension tables

### Integration Points
- **Workforce Events**: `employee_id` links to existing `fct_yearly_events.employee_id`
- **Hazard Tables**: `job_level` maps to existing `dim_hazard_table.level_id`
- **IRS Limits**: Contribution fields validate against `irs_limits` by plan year
- **Plan Design**: `plan_id` links to plan configuration for eligibility and match rules
- **Scenario Support**: All fields support scenario isolation via composite keys

### Census Loading SQL Example
```sql
-- stg_census_raw.sql
-- Initial census data validation and cleaning
WITH census_validation AS (
    SELECT
        employee_id,
        ssn,
        birth_date,
        hire_date,
        current_compensation,
        gender,
        job_level,
        employment_status,
        termination_date,
        department,
        -- Contribution history fields
        employee_pre_tax_ytd,
        employee_roth_ytd,
        employee_after_tax_ytd,
        employer_match_ytd,
        employer_match_true_up_ytd,
        employer_nonelective_ytd,
        employer_profit_sharing_ytd,
        forfeiture_allocation_ytd,
        vested_percentage,
        plan_id,
        -- Validate required fields
        CASE
            WHEN employee_id IS NULL THEN 'MISSING_EMPLOYEE_ID'
            WHEN ssn IS NULL THEN 'MISSING_SSN'
            WHEN birth_date IS NULL THEN 'MISSING_BIRTH_DATE'
            WHEN current_compensation <= 0 THEN 'INVALID_COMPENSATION'
            WHEN vested_percentage NOT BETWEEN 0.0 AND 1.0 THEN 'INVALID_VESTING'
            WHEN job_level NOT BETWEEN 1 AND 5 THEN 'INVALID_JOB_LEVEL'
            ELSE 'VALID'
        END as validation_status,
        -- Calculate total contribution amounts
        (employee_pre_tax_ytd + employee_roth_ytd + employee_after_tax_ytd) as total_employee_contributions,
        (employer_match_ytd + employer_match_true_up_ytd + employer_nonelective_ytd +
         employer_profit_sharing_ytd + forfeiture_allocation_ytd) as total_employer_contributions
    FROM read_parquet('data/census_preprocessed.parquet')
)
SELECT
    *,
    -- Generate baseline events for prior contributions
    ARRAY[
        {'source': 'employee_pre_tax', 'amount': employee_pre_tax_ytd},
        {'source': 'employee_roth', 'amount': employee_roth_ytd},
        {'source': 'employee_after_tax', 'amount': employee_after_tax_ytd},
        {'source': 'employer_match', 'amount': employer_match_ytd},
        {'source': 'employer_match_true_up', 'amount': employer_match_true_up_ytd, 'inferred': true},
        {'source': 'employer_nonelective', 'amount': employer_nonelective_ytd},
        {'source': 'employer_profit_sharing', 'amount': employer_profit_sharing_ytd},
        {'source': 'forfeiture_allocation', 'amount': forfeiture_allocation_ytd}
    ] as baseline_contribution_events
FROM census_validation
WHERE validation_status = 'VALID'
```

### Data Security Classification
- **RESTRICTED**: `ssn`, `birth_date` (PII fields requiring encryption)
- **CONFIDENTIAL**: All compensation and contribution fields
- **INTERNAL**: Demographics, employment status, job levels
- **PUBLIC**: None (all census data requires access controls)

This schema ensures the census file supports all E021 user stories while maintaining data security standards and regulatory compliance requirements. The 20-field structure provides comprehensive coverage for DC plan modeling while integrating seamlessly with existing workforce simulation infrastructure.

---

## Incremental Implementation Strategy

### Phase 1: Foundation (No Breaking Changes)
**Timeline**: Sprint 1-2 (Minimal risk)
- [ ] Extend `config/schema.py` event types to include DC plan events
- [ ] Add `scenario_id` and `plan_design_id` as **optional** fields to existing tables
- [ ] Create basic dbt staging models for `irs_limits` and `plan_designs`
- [ ] Implement core event validation using existing Pydantic patterns
- [ ] Create Python-based masking utilities (DuckDB compatible)

### Phase 2: Core DC Plan Features
**Timeline**: Sprint 3-4 (Low risk)
- [ ] Implement DC plan event processing in Dagster
- [ ] Create `fct_retirement_events` table with contract enforcement
- [ ] Build HCE determination models using existing workforce data
- [ ] Add basic IRS compliance validation (402g, 415c)
- [ ] Implement census schema extensions (backward compatible)

### Phase 3: Advanced Features
**Timeline**: Sprint 5-6 (Medium risk)
- [ ] Complete regulatory limits service
- [ ] Implement true-up calculation engine
- [ ] Add scenario isolation capabilities
- [ ] Create advanced compliance reporting
- [ ] Optimize performance using existing patterns

### Compatibility Validation Checklist
- [ ] **Event Schema**: New event types extend existing enum without replacing
- [ ] **Database**: All SQL uses DuckDB-compatible syntax only
- [ ] **Dependencies**: No circular dependencies with other epics
- [ ] **dbt Contracts**: All new models have `contract: {enforced: true}`
- [ ] **Security**: Application-level access control (no PostgreSQL RLS)
- [ ] **Performance**: Meets requirements using pandas/numpy (Phase 1)
- [ ] **Backward Compatibility**: Existing workforce events continue to work
- [ ] **Migration Scripts**: All schema changes include migration paths

## Definition of Done
- [ ] **Compatibility**: All items in compatibility validation checklist verified
- [ ] **Phase 1 Complete**: Foundation implemented without breaking changes
- [ ] **Integration Tests**: New events work alongside existing workforce events
- [ ] **dbt Models**: All models pass tests and have proper contracts
- [ ] **Census Schema**: 20-field schema implemented with migration path
- [ ] **Performance**: Meets benchmarks using existing technology stack
- [ ] **Security**: Python-based access control and masking implemented
- [ ] **Documentation**: Complete implementation guide and API docs
- [ ] **Code Review**: All code follows existing patterns and conventions
