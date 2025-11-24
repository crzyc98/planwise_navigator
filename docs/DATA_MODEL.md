# PlanAlign Engine - Core Data Model

**Version:** 1.0
**Last Updated:** November 2025
**Status:** Production

---

## Overview

PlanAlign Engine implements an **event-sourced workforce simulation engine** that models employee lifecycles, compensation dynamics, and defined contribution (DC) plan administration with enterprise-grade precision. This document defines the core data entities, relationships, and architectural patterns that power the platform.

### Key Principles

1. **Immutability**: All events are permanent with UUID-stamped audit trails
2. **Type Safety**: Pydantic v2 validation ensures schema compliance at event creation
3. **Temporal Accuracy**: Point-in-time state reconstruction from event streams
4. **Scenario Isolation**: Multi-scenario modeling with complete data segregation
5. **Regulatory Compliance**: IRS and ERISA requirement support built into schema

---

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                        │
│  - Streamlit Dashboard                                       │
│  - Excel Exports (Batch Processing)                          │
│  - Audit Reports & Analytics                                 │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   ORCHESTRATION LAYER                        │
│  - PipelineOrchestrator (E072 Modular Architecture)          │
│  - PlanAlign CLI (Rich Terminal Interface)                    │
│  - Workflow Staging & Checkpointing                          │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   TRANSFORMATION LAYER                       │
│  dbt-core (1.8.8) + dbt-duckdb (1.8.1)                       │
│                                                              │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐│
│  │   STAGING      │─→│ INTERMEDIATE   │─→│     MARTS      ││
│  │   (stg_*)      │  │   (int_*)      │  │   (fct_/dim_*) ││
│  │                │  │                │  │                ││
│  │ • Census       │  │ • Events       │  │ • Yearly Events││
│  │ • Config       │  │ • Hazards      │  │ • Workforce    ││
│  │ • Parameters   │  │ • State Mgmt   │  │   Snapshot     ││
│  └────────────────┘  └────────────────┘  └────────────────┘│
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                      STORAGE LAYER                           │
│  DuckDB 1.0.0 (OLAP Column-Store)                           │
│  - Immutable Event Store                                     │
│  - Parquet Compression (E068)                                │
│  - Incremental Processing                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Entities

### 1. SimulationEvent (Event Sourcing Foundation)

**Purpose**: Unified event model for all workforce and DC plan events with discriminated union payload routing.

**Schema** (`config/events.py:353-419`):

```python
class SimulationEvent(BaseModel):
    # Core Identification
    event_id: UUID                    # Auto-generated UUID for immutability
    employee_id: str                  # Employee identifier (not null)
    effective_date: date              # When event takes effect
    created_at: datetime              # Event creation timestamp (UTC)

    # Scenario Isolation (Required)
    scenario_id: str                  # Simulation scenario identifier
    plan_design_id: str               # Plan design variant identifier
    source_system: str                # Event origination system

    # Discriminated Union Payload
    payload: Union[
        # Workforce Events
        HirePayload,                  # event_type: "hire"
        PromotionPayload,             # event_type: "promotion"
        TerminationPayload,           # event_type: "termination"
        MeritPayload,                 # event_type: "merit"

        # DC Plan Events
        EligibilityPayload,           # event_type: "eligibility"
        EnrollmentPayload,            # event_type: "enrollment"
        ContributionPayload,          # event_type: "contribution"
        VestingPayload,               # event_type: "vesting"

        # Auto-Enrollment Events (E023)
        AutoEnrollmentWindowPayload,  # event_type: "auto_enrollment_window"
        EnrollmentChangePayload,      # event_type: "enrollment_change"

        # Plan Administration Events
        ForfeiturePayload,            # event_type: "forfeiture"
        HCEStatusPayload,             # event_type: "hce_status"
        ComplianceEventPayload        # event_type: "compliance"
    ]

    # Optional Tracing
    correlation_id: Optional[str]     # For event correlation and debugging
```

**Key Characteristics**:
- Pydantic v2 with `discriminator="event_type"` for automatic payload routing
- Immutable after creation (append-only event store)
- Comprehensive validation at event creation time
- UUID-based globally unique identification
- Complete audit trail with creation timestamps

---

### 2. Workforce Events

#### 2.1 HirePayload

**Purpose**: Employee onboarding with plan eligibility context.

**Schema** (`config/events.py:49-64`):

```python
class HirePayload(BaseModel):
    event_type: Literal["hire"] = "hire"
    plan_id: Optional[str]              # Links to DC plan when applicable
    hire_date: date                     # Employment start date
    department: str                     # Organizational unit
    job_level: int                      # Compensation band (1-10)
    annual_compensation: Decimal        # Initial salary (18,6 precision)
```

**Business Rules**:
- `annual_compensation` must be > 0
- Decimal precision: 6 decimal places (e.g., $125,000.123456)
- `job_level` range: 1 (entry) to 10 (executive)
- Triggers DC plan eligibility determination

**Usage**:
```python
hire_event = WorkforceEventFactory.create_hire_event(
    employee_id="EMP_2025_001",
    scenario_id="baseline_2025",
    plan_design_id="standard_401k",
    hire_date=date(2025, 1, 15),
    department="Engineering",
    job_level=3,
    annual_compensation=Decimal("125000.00")
)
```

#### 2.2 PromotionPayload

**Purpose**: Level changes affecting contribution capacity and HCE status.

**Schema** (`config/events.py:67-80`):

```python
class PromotionPayload(BaseModel):
    event_type: Literal["promotion"] = "promotion"
    plan_id: Optional[str]
    new_job_level: int                  # Target compensation band
    new_annual_compensation: Decimal    # Post-promotion salary
    effective_date: date                # Promotion effective date
```

**Business Rules**:
- Epic E059: Configurable promotion increases (15-25% default range)
- Triggers HCE status re-determination if compensation crosses threshold
- Updates contribution limits based on new compensation
- Level progression typically sequential (level N → N+1)

#### 2.3 TerminationPayload

**Purpose**: Employment end triggering distribution eligibility.

**Schema** (`config/events.py:83-91`):

```python
class TerminationPayload(BaseModel):
    event_type: Literal["termination"] = "termination"
    plan_id: Optional[str]
    termination_reason: Literal[
        "voluntary",        # Employee-initiated departure
        "involuntary",      # Company-initiated separation
        "retirement",       # Normal retirement
        "death",           # Deceased participant
        "disability"       # Disability-related termination
    ]
    final_pay_date: date   # Last payroll date
```

**Business Rules**:
- Triggers DC plan distribution eligibility determination
- Forfeiture processing for unvested employer contributions
- Affects employer match eligibility (E061: excludes year-of-hire terminations)
- Impacts year-end active employee counts for compliance testing

#### 2.4 MeritPayload

**Purpose**: Compensation changes affecting HCE status and contribution limits.

**Schema** (`config/events.py:94-112`):

```python
class MeritPayload(BaseModel):
    event_type: Literal["merit"] = "merit"
    plan_id: Optional[str]
    new_compensation: Decimal           # Updated salary
    merit_percentage: Decimal           # Increase rate (0.0-1.0)
```

**Business Rules**:
- COLA adjustments: ~1-2% annually (configurable)
- Merit increases: ~2-4% annually (budget-constrained)
- Percentage precision: 4 decimal places (0.0001)
- Triggers contribution limit recalculation

---

### 3. DC Plan Events

#### 3.1 EligibilityPayload

**Purpose**: Plan participation qualification tracking.

**Schema** (`config/events.py:116-123`):

```python
class EligibilityPayload(BaseModel):
    event_type: Literal["eligibility"] = "eligibility"
    plan_id: str                        # DC plan identifier
    eligible: bool                      # Eligibility status
    eligibility_date: date              # When eligibility begins
    reason: Literal[
        "age_and_service",   # Standard eligibility criteria met
        "immediate",         # Immediate eligibility (no waiting period)
        "hours_requirement", # Hours-based eligibility
        "rehire"            # Rehire with previous service credit
    ]
```

**Business Rules**:
- Default waiting period: 0 days (immediate eligibility)
- Minimum age: 21 (configurable)
- Minimum service: Configurable (default 0 years)
- Triggers enrollment window opening

#### 3.2 EnrollmentPayload

**Purpose**: Deferral election and auto-enrollment handling with enhanced window tracking.

**Schema** (`config/events.py:126-163`):

```python
class EnrollmentPayload(BaseModel):
    event_type: Literal["enrollment"] = "enrollment"
    plan_id: str
    enrollment_date: date

    # Contribution Elections
    pre_tax_contribution_rate: Decimal      # Traditional 401(k) deferral (0.0-1.0)
    roth_contribution_rate: Decimal         # Roth 401(k) deferral (0.0-1.0)
    after_tax_contribution_rate: Decimal    # After-tax contributions (0.0-1.0)

    # Enhanced Auto-Enrollment Tracking (E023)
    auto_enrollment: bool                   # Auto-enrolled indicator
    opt_out_window_expires: Optional[date]  # Opt-out deadline
    enrollment_source: Literal[
        "proactive",    # Voluntary enrollment before auto-enrollment
        "auto",         # Auto-enrolled by system
        "voluntary"     # Standard voluntary enrollment
    ]
    auto_enrollment_window_start: Optional[date]
    auto_enrollment_window_end: Optional[date]
    proactive_enrollment_eligible: bool
    window_timing_compliant: bool           # Business rule validation
```

**Business Rules**:
- Epic E023: Auto-enrollment window = 45 days after hire (configurable)
- Default deferral rate: 2% for auto-enrolled participants
- Opt-out grace period: 30 days after auto-enrollment
- Total deferral rate ≤ 75% (IRS limit)
- Decimal precision: 4 decimal places (0.0001)

#### 3.3 ContributionPayload

**Purpose**: All contribution sources with IRS categorization.

**Schema** (`config/events.py:166-194`):

```python
class ContributionPayload(BaseModel):
    event_type: Literal["contribution"] = "contribution"
    plan_id: str
    source: Literal[
        "employee_pre_tax",           # Traditional 401(k) deferrals
        "employee_roth",              # Roth 401(k) deferrals
        "employee_after_tax",         # After-tax contributions
        "employee_catch_up",          # Age 50+ catch-up contributions
        "employer_match",             # Employer matching contributions
        "employer_match_true_up",     # Year-end match true-up
        "employer_nonelective",       # Safe harbor contributions
        "employer_profit_sharing",    # Discretionary profit sharing
        "forfeiture_allocation"       # Reallocated forfeitures
    ]
    amount: Decimal                   # Contribution amount (18,6 precision)
    pay_period_end: date              # Payroll period ending date
    contribution_date: date           # Fund deposit date (critical for performance)
    ytd_amount: Decimal               # Year-to-date cumulative amount
    payroll_id: str                   # Payroll batch identifier (audit trail)
    irs_limit_applied: bool           # IRS limit enforcement flag
    inferred_value: bool              # Calculated vs actual value flag
```

**Business Rules**:
- 2025 IRS limits: $23,000 elective deferral, $7,500 catch-up (age 50+)
- Annual additions limit (415c): $69,000 (2025)
- Employer match eligibility (E061): Requires active status at year-end
- Decimal precision: 6 decimal places (18,6 format)

#### 3.4 VestingPayload

**Purpose**: Service-based employer contribution vesting.

**Schema** (`config/events.py:197-227`):

```python
class VestingPayload(BaseModel):
    event_type: Literal["vesting"] = "vesting"
    plan_id: str
    vested_percentage: Decimal          # Vesting percentage (0.0-1.0)
    source_balances_vested: Dict[       # Balance vesting by source
        Literal[
            "employer_match",
            "employer_nonelective",
            "employer_profit_sharing"
        ],
        Decimal
    ]
    vesting_schedule_type: Literal[
        "graded",      # Gradual vesting (e.g., 20% per year)
        "cliff",       # All-or-nothing at threshold (e.g., 100% at 3 years)
        "immediate"    # 100% vested immediately
    ]
    service_computation_date: date      # Service calculation as-of date
    service_credited_hours: int         # Vesting service hours (audit)
    service_period_end_date: date       # Service period ending (audit)
```

**Business Rules**:
- Standard graded schedule: 20% per year (years 2-6), 100% at 6 years
- Cliff schedule: 0% until threshold, then 100%
- Employee contributions: Always 100% vested
- Service hours requirement: Typically 1,000 hours/year for vesting credit

---

### 4. Auto-Enrollment Events (E023)

#### 4.1 AutoEnrollmentWindowPayload

**Purpose**: Auto-enrollment window lifecycle tracking.

**Schema** (`config/events.py:231-248`):

```python
class AutoEnrollmentWindowPayload(BaseModel):
    event_type: Literal["auto_enrollment_window"] = "auto_enrollment_window"
    plan_id: str
    window_action: Literal["opened", "closed", "expired"]
    window_start_date: date
    window_end_date: date
    window_duration_days: int           # Typically 45 days
    default_deferral_rate: Decimal      # Auto-enrollment default rate
    eligible_for_proactive: bool        # Proactive enrollment allowed
    proactive_window_end: Optional[date] # Proactive deadline
```

#### 4.2 EnrollmentChangePayload

**Purpose**: Enrollment status changes including opt-outs and modifications.

**Schema** (`config/events.py:251-282`):

```python
class EnrollmentChangePayload(BaseModel):
    event_type: Literal["enrollment_change"] = "enrollment_change"
    plan_id: str
    change_type: Literal[
        "opt_out",          # Employee opts out of auto-enrollment
        "rate_change",      # Deferral rate modification
        "source_change",    # Change between pre-tax/Roth
        "cancellation"      # Plan enrollment cancellation
    ]
    change_reason: Literal[
        "employee_opt_out",         # Voluntary employee action
        "plan_amendment",           # Plan design change
        "compliance_correction",    # Regulatory compliance fix
        "system_correction"         # Data quality correction
    ]
    previous_enrollment_date: Optional[date]
    new_pre_tax_rate: Decimal
    new_roth_rate: Decimal
    previous_pre_tax_rate: Optional[Decimal]
    previous_roth_rate: Optional[Decimal]
    within_opt_out_window: bool         # Grace period indicator
    penalty_applied: bool               # Opt-out penalty flag
```

**Business Rules**:
- Opt-out rates by age: Young 10%, Mid-career 7%, Mature 5%, Senior 3%
- Income multipliers: Low 1.2×, Moderate 1.0×, High 0.7×, Executive 0.5×
- Grace period: 30 days for penalty-free opt-out

---

### 5. Plan Administration Events

#### 5.1 ForfeiturePayload

**Purpose**: Unvested employer contribution recapture.

**Schema** (`config/events.py:286-308`):

```python
class ForfeiturePayload(BaseModel):
    event_type: Literal["forfeiture"] = "forfeiture"
    plan_id: str
    forfeited_from_source: Literal[
        "employer_match",
        "employer_nonelective",
        "employer_profit_sharing"
    ]
    amount: Decimal                     # Forfeited amount (18,6 precision)
    reason: Literal[
        "unvested_termination",         # Termination before full vesting
        "break_in_service"              # Service break > 5 years
    ]
    vested_percentage: Decimal          # Vesting % at termination
```

**Business Rules**:
- Only employer contributions subject to forfeiture
- Employee deferrals always 100% vested
- Forfeitures reallocated to remaining participants or used for plan expenses

#### 5.2 HCEStatusPayload

**Purpose**: Highly compensated employee determination.

**Schema** (`config/events.py:311-328`):

```python
class HCEStatusPayload(BaseModel):
    event_type: Literal["hce_status"] = "hce_status"
    plan_id: str
    determination_method: Literal[
        "prior_year",       # Lookback method (standard)
        "current_year"      # Current year method (alternative)
    ]
    ytd_compensation: Decimal           # Year-to-date compensation
    annualized_compensation: Decimal    # Annualized compensation
    hce_threshold: Decimal              # IRS HCE threshold ($150,000 in 2025)
    is_hce: bool                        # HCE status determination
    determination_date: date
    prior_year_hce: Optional[bool]      # Previous year HCE status
```

**Business Rules**:
- 2025 HCE threshold: $150,000 (indexed annually)
- Prior-year lookback: Use prior year compensation
- Current-year method: Use current year projected compensation
- Affects ADP/ACP nondiscrimination testing

#### 5.3 ComplianceEventPayload

**Purpose**: Basic IRS limit monitoring.

**Schema** (`config/events.py:331-350`):

```python
class ComplianceEventPayload(BaseModel):
    event_type: Literal["compliance"] = "compliance"
    plan_id: str
    compliance_type: Literal[
        "402g_limit_approach",      # Approaching elective deferral limit
        "415c_limit_approach",      # Approaching annual additions limit
        "catch_up_eligible"         # Participant becomes catch-up eligible
    ]
    limit_type: Literal[
        "elective_deferral",        # 402(g) limit
        "annual_additions",         # 415(c) limit
        "catch_up"                  # Catch-up contribution limit
    ]
    applicable_limit: Decimal
    current_amount: Decimal
    monitoring_date: date
```

---

### 6. Configuration Entities

#### 6.1 SimulationConfig

**Purpose**: Master configuration for simulation execution.

**Location**: `config/simulation_config.yaml`

**Key Sections**:

```yaml
simulation:
  start_year: 2025
  end_year: 2029
  random_seed: 42                    # Deterministic simulation
  target_growth_rate: 0.03

workforce:
  total_termination_rate: 0.12
  new_hire_termination_rate: 0.25

compensation:
  cola_rate: 0.01                    # Cost of living adjustment
  merit_budget: 0.02                 # Merit raise budget
  calculation_methodology: "full_year_equivalent"

  promotion_compensation:
    base_increase_pct: 0.20          # 20% base promotion increase
    distribution_range: 0.05         # ±5% variance
    max_cap_pct: 0.30               # Maximum 30% increase
    max_cap_amount: 500000           # Maximum $500K increase

new_hire_compensation:
  strategy: "percentile_based"
  percentile_strategy:
    default_percentile: 0.3          # 50th percentile hiring
    level_overrides:                 # Level-specific percentiles
      1: 0.30
      2: 0.40
      3: 0.50
      4: 0.65
      5: 0.70

enrollment:
  auto_enrollment:
    enabled: true
    window_days: 45                  # Auto-enrollment window
    default_deferral_rate: 0.02      # 2% default rate
    opt_out_grace_period: 30         # Opt-out grace period
    hire_date_cutoff: "2020-01-01"   # Auto-enroll employees hired on/after

employer_match:
  active_formula: 'simple_match'
  apply_eligibility: true
  eligibility:
    minimum_tenure_years: 0
    require_active_at_year_end: true # Exclude year-of-hire terminations
    allow_new_hires: true
    allow_terminated_new_hires: false

employer_core_contribution:
  enabled: true
  contribution_rate: 0.01            # 1% core contribution
  eligibility:
    minimum_tenure_years: 0
    require_active_at_year_end: true
    allow_new_hires: true

deferral_auto_escalation:
  enabled: true
  effective_day: "01-01"
  increment_amount: 0.01             # 1% annual escalation
  maximum_rate: 0.10                 # 10% cap
  first_escalation_delay_years: 1
```

#### 6.2 Parameter Seeds

**Purpose**: Analyst-configurable simulation parameters.

**comp_levers.csv** (Parameter management):
```csv
scenario_id,fiscal_year,event_type,parameter_name,job_level,parameter_value
default,2025,RAISE,merit_base,1,0.030
default,2025,RAISE,merit_base,2,0.035
default,2025,RAISE,cola_rate,,0.025
default,2025,PROMOTION,promo_base,,0.20
```

**config_job_levels.csv** (Compensation bands):
```csv
level_id,level_name,min_salary,max_salary,midpoint_salary
1,Entry Level,40000,60000,50000
2,Professional,55000,85000,70000
3,Senior Professional,75000,115000,95000
```

**config_termination_hazard_base.csv** (Turnover probabilities):
```csv
job_level,base_termination_rate
1,0.18
2,0.15
3,0.12
4,0.10
5,0.08
```

---

### 7. Fact Tables (Marts Layer)

#### 7.1 fct_yearly_events

**Purpose**: Immutable event stream - source of truth for all workforce changes.

**Location**: `dbt/models/marts/fct_yearly_events.sql`

**Schema**:

```sql
CREATE TABLE fct_yearly_events (
    -- Event Identification
    event_id VARCHAR PRIMARY KEY,
    scenario_id VARCHAR NOT NULL,
    plan_design_id VARCHAR NOT NULL,

    -- Event Core
    employee_id VARCHAR NOT NULL,
    employee_ssn VARCHAR,
    event_type VARCHAR NOT NULL,        -- hire, termination, promotion, raise, enrollment, etc.
    simulation_year INTEGER NOT NULL,
    effective_date DATE NOT NULL,
    event_sequence INTEGER,             -- Processing order within year

    -- Event Details
    event_details VARCHAR,              -- JSON payload with event-specific data
    event_category VARCHAR,             -- Event classification

    -- Employee Attributes (denormalized for query performance)
    employee_age INTEGER,
    employee_tenure_years DECIMAL(10,2),
    level_id INTEGER,
    department VARCHAR,

    -- Compensation
    compensation_amount DECIMAL(18,6),  -- Salary or contribution amount

    -- Audit Trail
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    parameter_scenario_id VARCHAR,
    parameter_source VARCHAR,
    data_quality_flag VARCHAR,

    -- Performance Optimization
    UNIQUE (scenario_id, plan_design_id, employee_id, simulation_year, event_type, effective_date)
);
```

**Characteristics**:
- Incremental materialization with `delete+insert` strategy
- Unique key: `(scenario_id, plan_design_id, employee_id, simulation_year, event_type, effective_date)`
- E068: Supports both SQL and Polars event generation modes
- Tagged: `EVENT_GENERATION`

**Usage Patterns**:
```sql
-- Count events by type and year
SELECT simulation_year, event_type, COUNT(*) as event_count
FROM fct_yearly_events
WHERE scenario_id = 'baseline_2025'
GROUP BY simulation_year, event_type
ORDER BY simulation_year, event_type;

-- Audit trail for specific employee
SELECT event_type, effective_date, compensation_amount, event_details
FROM fct_yearly_events
WHERE employee_id = 'EMP_2025_001'
  AND scenario_id = 'baseline_2025'
ORDER BY effective_date, event_sequence;
```

#### 7.2 fct_workforce_snapshot

**Purpose**: Point-in-time workforce state reconstruction from event stream.

**Location**: `dbt/models/marts/fct_workforce_snapshot.sql`

**Schema**:

```sql
CREATE TABLE fct_workforce_snapshot (
    -- Composite Key
    scenario_id VARCHAR NOT NULL,
    plan_design_id VARCHAR NOT NULL,
    employee_id VARCHAR NOT NULL,
    simulation_year INTEGER NOT NULL,

    -- Employment Status
    employment_status VARCHAR,          -- active, terminated
    hire_date DATE,
    termination_date DATE,
    termination_reason VARCHAR,

    -- Demographics
    employee_age INTEGER,
    employee_ssn VARCHAR,
    tenure_years DECIMAL(10,2),

    -- Job Information
    level_id INTEGER,
    department VARCHAR,

    -- Compensation
    annual_compensation DECIMAL(18,6),
    annualized_compensation DECIMAL(18,6),
    prorated_compensation DECIMAL(18,6),
    compensation_periods DECIMAL(10,4),

    -- DC Plan Enrollment
    is_enrolled BOOLEAN,
    enrollment_date DATE,
    enrollment_source VARCHAR,
    current_deferral_rate DECIMAL(10,4),
    pre_tax_deferral_rate DECIMAL(10,4),
    roth_deferral_rate DECIMAL(10,4),

    -- Employer Contributions
    employer_match_amount DECIMAL(18,6),
    employer_core_amount DECIMAL(18,6),

    -- Eligibility Flags
    is_match_eligible BOOLEAN,
    is_core_eligible BOOLEAN,
    is_plan_eligible BOOLEAN,

    -- Quality Flags
    data_quality_flags VARCHAR,

    -- Audit
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (scenario_id, plan_design_id, employee_id, simulation_year)
);
```

**Characteristics**:
- Incremental materialization with year-based refresh
- Consolidates all events into point-in-time state
- E079: Optimized from 27 CTEs to 8 CTEs for 2× performance
- Tagged: `STATE_ACCUMULATION`

**Usage Patterns**:
```sql
-- Active workforce by year
SELECT simulation_year, COUNT(*) as active_employees
FROM fct_workforce_snapshot
WHERE employment_status = 'active'
  AND scenario_id = 'baseline_2025'
GROUP BY simulation_year;

-- Enrollment statistics
SELECT
    simulation_year,
    COUNT(*) as total_employees,
    SUM(CASE WHEN is_enrolled THEN 1 ELSE 0 END) as enrolled_count,
    AVG(current_deferral_rate) as avg_deferral_rate
FROM fct_workforce_snapshot
WHERE employment_status = 'active'
  AND scenario_id = 'baseline_2025'
GROUP BY simulation_year;
```

---

### 8. State Accumulator Pattern

**Purpose**: Temporal state tracking across simulation years without circular dependencies.

**Key Models**:
- `int_enrollment_state_accumulator.sql` - Enrollment status history
- `int_deferral_rate_state_accumulator_v2.sql` - Deferral rate evolution

**Pattern**:

```sql
-- Year N reads Year N-1 state + Year N events
WITH prior_year_state AS (
    SELECT *
    FROM {{ this }}  -- Self-reference to prior year
    WHERE simulation_year = {{ var('simulation_year') }} - 1
),
current_year_events AS (
    SELECT *
    FROM {{ ref('int_enrollment_events') }}
    WHERE simulation_year = {{ var('simulation_year') }}
)
SELECT
    COALESCE(e.employee_id, p.employee_id) AS employee_id,
    COALESCE(e.enrollment_date, p.enrollment_date) AS enrollment_date,
    COALESCE(e.deferral_rate, p.deferral_rate) AS current_deferral_rate,
    {{ var('simulation_year') }} AS simulation_year
FROM current_year_events e
FULL OUTER JOIN prior_year_state p
    ON e.employee_id = p.employee_id;
```

**Benefits**:
- Avoids circular dependencies (`int_*` models can't read `fct_*` models)
- Maintains temporal continuity across years
- Enables multi-year simulation with incremental processing
- Supports checkpoint/resume functionality

---

### 9. Data Relationships

```
┌──────────────────────────────────────────────────────────────────┐
│                      ENTITY RELATIONSHIPS                         │
└──────────────────────────────────────────────────────────────────┘

SimulationEvent (1) ──< (∞) fct_yearly_events
    │
    ├──> HirePayload ──────────> Creates Employee
    ├──> PromotionPayload ─────> Updates Employee.level_id
    ├──> TerminationPayload ───> Updates Employee.employment_status
    ├──> MeritPayload ─────────> Updates Employee.annual_compensation
    │
    ├──> EligibilityPayload ───> Determines Plan Participation
    ├──> EnrollmentPayload ────> Creates Enrollment Record
    ├──> ContributionPayload ──> Creates Contribution Transaction
    └──> VestingPayload ───────> Updates Vesting Schedule

Employee (1) ──< (∞) fct_yearly_events
    │
    └──> (1) fct_workforce_snapshot (per year)
         │
         ├──> (0..1) Enrollment (int_enrollment_state_accumulator)
         ├──> (0..*) Contributions (int_employee_contributions)
         ├──> (0..1) Vesting (int_vesting_schedule)
         └──> (0..*) Compliance Events (int_compliance_monitoring)

Scenario (1) ──< (∞) SimulationEvent
    │
    └──> (1) SimulationConfig
         │
         ├──> Workforce Parameters
         ├──> Compensation Parameters
         ├──> Enrollment Parameters
         └──> Plan Design Parameters
```

---

### 10. Key Design Patterns

#### 10.1 Event Sourcing

**Pattern**: All state changes captured as immutable events.

**Implementation**:
1. Event creation via Pydantic factories (`WorkforceEventFactory`, `DCPlanEventFactory`)
2. Event validation at creation time
3. Event persistence in `fct_yearly_events`
4. State reconstruction via event replay in `fct_workforce_snapshot`

**Benefits**:
- Complete audit trail
- Point-in-time state reconstruction
- Temporal queries (what-if scenarios)
- Debugging via event inspection

#### 10.2 Discriminated Unions (Pydantic v2)

**Pattern**: Type-safe payload routing based on `event_type` discriminator.

**Implementation**:
```python
payload: Union[
    Annotated[HirePayload, Field(discriminator="event_type")],
    Annotated[PromotionPayload, Field(discriminator="event_type")],
    # ... other event types
] = Field(..., discriminator="event_type")
```

**Benefits**:
- Automatic payload validation
- Type-safe event handling
- IDE autocomplete support
- Runtime type checking

#### 10.3 Temporal State Accumulators

**Pattern**: Year-over-year state propagation without circular dependencies.

**Implementation**:
- Prior year state from `{{ this }}` (self-reference)
- Current year events from event models
- Full outer join to handle new/terminated employees
- Incremental materialization with year-based deletion

**Benefits**:
- Avoids circular dependencies
- Efficient incremental processing
- Supports multi-year simulations
- Checkpoint-friendly architecture

#### 10.4 Scenario Isolation

**Pattern**: Complete data segregation by scenario and plan design.

**Implementation**:
- All tables keyed by `(scenario_id, plan_design_id, ...)`
- Parallel scenario execution without interference
- Independent configuration per scenario
- Comparative analysis across scenarios

**Benefits**:
- What-if scenario modeling
- A/B testing of plan designs
- Risk analysis (conservative vs aggressive assumptions)
- Batch scenario processing (E069)

---

### 11. Performance Optimizations

#### 11.1 E068 Fused Event Generation

**Optimization**: Single compiled query replaces multiple small event models.

**Impact**: 2× performance improvement (285s → 150s for 5-year simulation)

**Implementation**:
- `fct_yearly_events.sql` generates all event types in single query
- Eliminates intermediate materialization overhead
- Reduces I/O operations

#### 11.2 E068 Polars Vectorized Mode

**Optimization**: Bulk event generation using Polars instead of SQL.

**Impact**: 375× performance improvement (60s → 0.16s)

**Implementation**:
- `planalign_orchestrator.polars_event_factory` for vectorized operations
- Parquet file output with ZSTD compression
- dbt reads Parquet files instead of generating events in SQL

**Configuration**:
```yaml
optimization:
  event_generation:
    mode: "polars"  # Options: "sql", "polars"
    polars:
      enabled: true
      output_path: "data/parquet/events"
      enable_compression: true
```

#### 11.3 E079 Snapshot Optimization

**Optimization**: Flattened CTE structure (27 CTEs → 8 CTEs).

**Impact**: 60%+ performance improvement in state accumulation.

**Implementation**:
- Consolidated event processing
- Eliminated correlated subqueries
- Materialized intermediate computations
- Single enrichment CTE with all joins

#### 11.4 Incremental Processing

**Optimization**: Year-based incremental materialization.

**Impact**: Linear scaling for multi-year simulations.

**Implementation**:
```sql
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year']
) }}
```

**Benefits**:
- Idempotent re-runs
- Efficient year-by-year processing
- Supports checkpoint/resume
- Scales to 10+ year simulations

---

### 12. Data Quality & Validation

#### 12.1 Validation Models

**dbt Tests** (`dbt/models/schema.yml`):

```yaml
models:
  - name: fct_yearly_events
    tests:
      - unique:
          column_name: "concat(employee_id, event_type, simulation_year, effective_date)"
      - not_null:
          column_name: employee_id
      - accepted_values:
          column_name: event_type
          values: ['hire', 'termination', 'promotion', 'raise', 'enrollment']

  - name: fct_workforce_snapshot
    tests:
      - unique:
          column_name: "concat(scenario_id, plan_design_id, employee_id, simulation_year)"
      - not_null:
          column_name: employee_id
      - relationships:
          to: ref('fct_yearly_events')
          field: employee_id
```

#### 12.2 Data Quality Models

**Quality Checks** (`dbt/models/marts/data_quality/`):

- `dq_employee_id_validation.sql` - Employee ID uniqueness
- `dq_employee_contributions_validation.sql` - Contribution limits
- `dq_new_hire_termination_match_validation.sql` - Match eligibility (E061)
- `dq_deferral_rate_validation.sql` - Deferral rate consistency

---

### 13. Integration Points

#### 13.1 PipelineOrchestrator (E072)

**Purpose**: Modular workflow execution with staged processing.

**Workflow Stages**:
1. **INITIALIZATION**: Load seeds and staging data
2. **FOUNDATION**: Build baseline workforce and compensation
3. **EVENT_GENERATION**: Generate hire/termination/promotion events
4. **STATE_ACCUMULATION**: Build accumulators and snapshots
5. **VALIDATION**: Run data quality checks
6. **REPORTING**: Generate audit reports

**Integration**:
```python
from planalign_orchestrator import create_orchestrator
from planalign_orchestrator.config import load_simulation_config

config = load_simulation_config('config/simulation_config.yaml')
orchestrator = create_orchestrator(config)

summary = orchestrator.execute_multi_year_simulation(
    start_year=2025,
    end_year=2027,
    fail_on_validation_error=False
)
```

#### 13.2 PlanAlign CLI

**Purpose**: Rich terminal interface for simulation execution.

**Commands**:
```bash
planalign simulate 2025-2027              # Multi-year simulation
planalign batch --scenarios baseline      # Batch processing
planalign status --detailed               # System diagnostics
planalign checkpoints list                # Recovery points
```

---

### 14. Future Enhancements

#### 14.1 Loan & Investment Events (E021-A)

**Status**: Planned (blocked by current work)

**Proposed Events**:
- `LoanOriginationPayload` - 401(k) loan issuance
- `LoanRepaymentPayload` - Loan payment tracking
- `InvestmentElectionPayload` - Fund allocation changes
- `InvestmentPerformancePayload` - Market return application

#### 14.2 Distribution Events

**Status**: Planned

**Proposed Events**:
- `DistributionPayload` - Plan distributions
- `RolloverPayload` - Plan-to-plan transfers
- `RMDPayload` - Required minimum distributions (age 73+)

#### 14.3 Compliance Enhancements

**Status**: Planned

**Proposed Events**:
- `ADPTestPayload` - Actual Deferral Percentage test
- `ACPTestPayload` - Actual Contribution Percentage test
- `TopHeavyTestPayload` - Top-heavy determination
- `CoverageTsetPayload` - Minimum coverage testing

---

## Appendix

### A. Decimal Precision Standards

| Field Type | Precision | Example |
|------------|-----------|---------|
| Compensation | 18,6 | $125,000.123456 |
| Percentages | 4 decimal places | 0.0625 (6.25%) |
| Contribution Rates | 4 decimal places | 0.0600 (6%) |
| Contribution Amounts | 18,6 | $7,500.000000 |
| Vesting Percentage | 4 decimal places | 0.6000 (60%) |

### B. IRS Limits (2025)

| Limit | Code | Amount |
|-------|------|--------|
| Elective Deferral | 402(g) | $23,000 |
| Catch-up (Age 50+) | 414(v) | $7,500 |
| Annual Additions | 415(c) | $69,000 |
| HCE Threshold | 414(q) | $150,000 |
| Compensation Limit | 401(a)(17) | $345,000 |

### C. Event Type Reference

| Event Type | Category | Payload Class | Source System |
|------------|----------|---------------|---------------|
| hire | Workforce | HirePayload | workforce_simulation |
| promotion | Workforce | PromotionPayload | workforce_simulation |
| termination | Workforce | TerminationPayload | workforce_simulation |
| merit | Workforce | MeritPayload | workforce_simulation |
| eligibility | DC Plan | EligibilityPayload | dc_plan_administration |
| enrollment | DC Plan | EnrollmentPayload | dc_plan_administration |
| contribution | DC Plan | ContributionPayload | dc_plan_administration |
| vesting | DC Plan | VestingPayload | dc_plan_administration |
| auto_enrollment_window | Auto-Enrollment | AutoEnrollmentWindowPayload | auto_enrollment_engine |
| enrollment_change | Auto-Enrollment | EnrollmentChangePayload | enrollment_change_processing |
| forfeiture | Plan Admin | ForfeiturePayload | plan_administration |
| hce_status | Plan Admin | HCEStatusPayload | hce_determination |
| compliance | Plan Admin | ComplianceEventPayload | compliance_monitoring |

---

**Document Version**: 1.0
**Last Updated**: November 2025
**Maintained By**: PlanAlign Engine Team
**Related Documents**:
- `/docs/CLAUDE.md` - Development playbook
- `/dbt/CLAUDE.md` - dbt project guide
- `/docs/architecture/event_sourcing.md` - Event sourcing deep dive
- `/config/events.py` - Event schema implementation
