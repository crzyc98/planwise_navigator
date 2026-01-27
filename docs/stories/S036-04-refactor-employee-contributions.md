# Story S036-04: Refactor int_employee_contributions Model

**Epic**: E036 - Deferral Rate State Accumulator Architecture
**Story Points**: 4
**Priority**: Critical
**Sprint**: Infrastructure Fix
**Owner**: Technical Architecture Team
**Status**: 🔵 Ready for Implementation
**Type**: Refactoring

## Story

**As a** platform engineer
**I want** to refactor the `int_employee_contributions` model to use the deferral rate state accumulator
**So that** the circular dependency with `fct_yearly_events` is eliminated while maintaining calculation accuracy

## Business Context

The current `int_employee_contributions` model has a critical circular dependency that prevents multi-year simulation execution. It attempts to read `employee_deferral_rate` from `fct_yearly_events`, but `fct_yearly_events` depends on contribution calculations. This story refactors the model to use the new `int_deferral_rate_state_accumulator`, breaking the circular dependency while preserving all existing calculation logic and audit trail fields.

## Problem Statement

### Current Broken Pattern
```sql
-- BROKEN: Creates circular dependency
SELECT
  employee_id,
  employee_deferral_rate,
  -- ... other calculations
FROM {{ ref('fct_yearly_events') }}  -- ❌ CIRCULAR DEPENDENCY
WHERE employee_deferral_rate IS NOT NULL
```

### Target Fixed Pattern
```sql
-- FIXED: Uses state accumulator (no circular dependency)
SELECT
  employee_id,
  current_deferral_rate as employee_deferral_rate,
  -- ... same calculations
FROM {{ ref('int_deferral_rate_state_accumulator') }}  -- ✅ CLEAN DEPENDENCY
WHERE current_deferral_rate IS NOT NULL
```

## Acceptance Criteria

### Circular Dependency Elimination
- [ ] **Remove dependency on `fct_yearly_events`** completely from `int_employee_contributions`
- [ ] **Update to use `int_deferral_rate_state_accumulator`** as the source for deferral rates
- [ ] **Verify no circular dependencies** in the updated model dependency graph
- [ ] **Maintain proper orchestration order** with accumulator running before contributions

### Calculation Accuracy Preservation & Enhancement
- [ ] **Implement temporal proration** for partial-year employment (hire/termination mid-year)
- [ ] **Define limits precedence order** (plan max rate → IRS dollar limits → catch-up)
- [ ] **Fix catch-up contribution logic** to calculate incremental amount above IRS base limit
- [ ] **Preserve all audit trail fields** with enhanced monthly grain alignment
- [ ] **Validate calculation results** including new proration and corrected catch-up logic

### Data Quality & Integration
- [ ] **Ensure data completeness** - all active employees have contribution calculations
- [ ] **Maintain referential integrity** with other models that depend on contributions
- [ ] **Preserve schema compatibility** for downstream consumers
- [ ] **Add data quality checks** for contribution calculation consistency

## Current Model Analysis

Let me first examine the current `int_employee_contributions` model to understand the exact refactoring needed:

```sql
-- Current problematic pattern (example structure)
WITH employee_deferral_rates AS (
  SELECT
    employee_id,
    employee_deferral_rate,
    effective_date,
    scenario_id,
    plan_design_id
  FROM {{ ref('fct_yearly_events') }}  -- ❌ CIRCULAR DEPENDENCY
  WHERE event_type = 'enrollment'
    AND employee_deferral_rate IS NOT NULL
    AND simulation_year = {{ var('simulation_year') }}
),

-- Rest of contribution calculations...
```

## Refactoring Implementation

### Updated Source Pattern
```sql
-- dbt/models/intermediate/events/int_employee_contributions.sql
-- REFACTORED: Source from state accumulator to eliminate circular dependency

{{ config(
    materialized='incremental',
    unique_key=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year'],
    incremental_strategy='delete+insert',
    on_schema_change='sync_all_columns'
) }}

WITH employee_deferral_rates AS (
  SELECT
    scenario_id,
    plan_design_id,
    employee_id,
    current_deferral_rate as employee_deferral_rate,
    effective_date,
    as_of_month,
    source_type,
    source_event_ids,
    is_active,
    simulation_year
  FROM {{ ref('int_deferral_rate_state_accumulator') }}  -- ✅ CLEAN SOURCE
  WHERE simulation_year = {{ var('simulation_year') }}
    AND is_current = TRUE
    AND is_active = TRUE
    AND current_deferral_rate IS NOT NULL
    AND current_deferral_rate > 0.0000  -- Only employees with positive deferral rates
),

compensation_data AS (
  SELECT
    scenario_id,
    plan_design_id,
    employee_id,
    annual_salary,
    pay_frequency,
    simulation_year
  FROM {{ ref('int_employee_compensation_by_year') }}
  WHERE simulation_year = {{ var('simulation_year') }}
),

employee_demographics AS (
  SELECT
    scenario_id,
    plan_design_id,
    employee_id,
    employee_age,
    employee_hire_date,
    termination_date,
    simulation_year
  FROM {{ ref('int_baseline_workforce') }}
  WHERE simulation_year = {{ var('simulation_year') }}
),

plan_limits AS (
  SELECT
    plan_design_id,
    employee_max_deferral_rate,
    annual_contribution_limit,
    catch_up_contribution_limit,
    plan_year_start_date
  FROM {{ ref('dim_plan_designs') }}
  -- TODO: Add year scoping if plan limits vary by year
  -- WHERE effective_date <= DATE('{{ var("simulation_year") }}-12-31')
  --   AND (end_date IS NULL OR end_date >= DATE('{{ var("simulation_year") }}-01-01'))
),

-- Calculate proration for partial-year employment
employment_proration AS (
  SELECT
    scenario_id,
    plan_design_id,
    employee_id,
    -- Count active months in the simulation year
    CASE
      WHEN employee_hire_date > DATE('{{ var("simulation_year") }}-01-01') AND
           (termination_date IS NULL OR termination_date >= DATE('{{ var("simulation_year") }}-12-31'))
      THEN DATE_PART('month', DATE('{{ var("simulation_year") }}-12-31') - employee_hire_date) + 1
      WHEN termination_date IS NOT NULL AND termination_date < DATE('{{ var("simulation_year") }}-12-31')
      THEN DATE_PART('month', termination_date - DATE('{{ var("simulation_year") }}-01-01')) + 1
      ELSE 12  -- Full year
    END as active_months,
    employee_hire_date,
    termination_date
  FROM employee_demographics
),

-- Core contribution calculations with temporal alignment and proper limits precedence
employee_contributions AS (
  SELECT
    edr.scenario_id,
    edr.plan_design_id,
    edr.employee_id,
    edr.simulation_year,
    ed.employee_age,
    edr.employee_deferral_rate,
    cd.annual_salary,
    cd.pay_frequency,
    ep.active_months,

    -- Apply plan max deferral rate constraint first (precedence rule)
    LEAST(edr.employee_deferral_rate, pl.employee_max_deferral_rate) as effective_deferral_rate,

    -- Calculate prorated annual salary based on active months
    ROUND(cd.annual_salary * (ep.active_months / 12.0), 2) as prorated_annual_salary,

    -- Calculate base contribution amount using effective (plan-capped) rate
    ROUND(ROUND(cd.annual_salary * (ep.active_months / 12.0), 2) *
          LEAST(edr.employee_deferral_rate, pl.employee_max_deferral_rate), 2) as base_contribution_amount,

    -- Apply IRS base limit
    LEAST(
      ROUND(ROUND(cd.annual_salary * (ep.active_months / 12.0), 2) *
            LEAST(edr.employee_deferral_rate, pl.employee_max_deferral_rate), 2),
      pl.annual_contribution_limit
    ) as irs_base_limited_contribution,

    -- Calculate catch-up contribution (incremental amount above IRS base limit)
    CASE
      WHEN ed.employee_age >= 50 THEN
        LEAST(
          GREATEST(
            ROUND(ROUND(cd.annual_salary * (ep.active_months / 12.0), 2) *
                  LEAST(edr.employee_deferral_rate, pl.employee_max_deferral_rate), 2) -
            pl.annual_contribution_limit,
            0
          ),
          pl.catch_up_contribution_limit
        )
      ELSE 0.00
    END as catch_up_contribution_amount,

    -- Calculate per-pay-period contribution (using pay frequency dimension)
    ROUND(
      (
        LEAST(
          ROUND(ROUND(cd.annual_salary * (ep.active_months / 12.0), 2) *
                LEAST(edr.employee_deferral_rate, pl.employee_max_deferral_rate), 2),
          pl.annual_contribution_limit
        ) +
        CASE
          WHEN ed.employee_age >= 50 THEN
            LEAST(
              GREATEST(
                ROUND(ROUND(cd.annual_salary * (ep.active_months / 12.0), 2) *
                      LEAST(edr.employee_deferral_rate, pl.employee_max_deferral_rate), 2) -
                pl.annual_contribution_limit,
                0
              ),
              pl.catch_up_contribution_limit
            )
          ELSE 0.00
        END
      ) /
      CASE cd.pay_frequency
        WHEN 'weekly' THEN 52
        WHEN 'bi-weekly' THEN 26
        WHEN 'semi-monthly' THEN 24
        WHEN 'monthly' THEN 12
        ELSE 26  -- Default bi-weekly
      END, 2
    ) as per_pay_period_contribution,

    -- Flag if plan constraint was applied
    CASE
      WHEN edr.employee_deferral_rate > pl.employee_max_deferral_rate THEN TRUE
      ELSE FALSE
    END as plan_constraint_applied,

    -- Audit trail fields (enhanced with accumulator source info)
    edr.effective_date as deferral_rate_effective_date,
    edr.source_type as deferral_rate_source,
    edr.source_event_ids,
    edr.as_of_month,
    CURRENT_TIMESTAMP as calculated_at

  FROM employee_deferral_rates edr
  JOIN compensation_data cd
    ON edr.scenario_id = cd.scenario_id
    AND edr.plan_design_id = cd.plan_design_id
    AND edr.employee_id = cd.employee_id
    AND edr.simulation_year = cd.simulation_year
  JOIN employee_demographics ed
    ON edr.scenario_id = ed.scenario_id
    AND edr.plan_design_id = ed.plan_design_id
    AND edr.employee_id = ed.employee_id
    AND edr.simulation_year = ed.simulation_year
  JOIN employment_proration ep
    ON edr.scenario_id = ep.scenario_id
    AND edr.plan_design_id = ep.plan_design_id
    AND edr.employee_id = ep.employee_id
  JOIN plan_limits pl
    ON edr.plan_design_id = pl.plan_design_id
),

-- Calculate final contribution amounts (already includes plan rate constraints)
final_contributions AS (
  SELECT *,
    -- Final annual contribution = IRS base limited + catch-up
    irs_base_limited_contribution + catch_up_contribution_amount as final_annual_contribution_amount
  FROM employee_contributions
)

-- Final output with all preserved fields and enhanced audit trail
SELECT
  scenario_id,
  plan_design_id,
  employee_id,
  simulation_year,
  employee_age,
  employee_deferral_rate,
  effective_deferral_rate,
  prorated_annual_salary,
  active_months,

  -- Contribution amounts
  base_contribution_amount as annual_contribution_amount,
  per_pay_period_contribution,
  irs_base_limited_contribution,
  catch_up_contribution_amount,
  final_annual_contribution_amount,
  plan_constraint_applied,

  -- Enhanced audit trail from accumulator
  deferral_rate_effective_date,
  deferral_rate_source,
  source_event_ids,
  as_of_month,
  calculated_at,

  -- Data quality metadata
  'state_accumulator' as calculation_method,
  'v2_refactored' as model_version

FROM final_contributions

-- Data quality checks: ensure valid contributions
WHERE final_annual_contribution_amount >= 0.00
  AND final_annual_contribution_amount <= prorated_annual_salary * effective_deferral_rate + 0.01  -- Allow rounding
```

### Schema Updates

```yaml
# dbt/models/intermediate/events/schema.yml
version: 2

models:
  - name: int_employee_contributions
    description: "Employee contribution calculations using deferral rate state accumulator (v2 refactored)"

    config:
      contract:
        enforced: true

    columns:
      - name: scenario_id
        description: "Simulation scenario identifier"
        data_type: varchar(50)
        constraints:
          - type: not_null

      - name: plan_design_id
        description: "DC plan design identifier"
        data_type: varchar(50)
        constraints:
          - type: not_null

      - name: employee_id
        description: "Unique employee identifier"
        data_type: varchar(50)
        constraints:
          - type: not_null

      - name: simulation_year
        description: "Simulation year for these calculations"
        data_type: integer
        constraints:
          - type: not_null

      - name: employee_age
        description: "Employee's age for catch-up contribution eligibility"
        data_type: integer
        constraints:
          - type: not_null

      - name: employee_deferral_rate
        description: "Employee's original deferral rate from state accumulator"
        data_type: decimal(5,4)
        constraints:
          - type: not_null

      - name: effective_deferral_rate
        description: "Deferral rate after applying plan maximum constraints"
        data_type: decimal(5,4)
        constraints:
          - type: not_null

      - name: prorated_annual_salary
        description: "Annual salary prorated for active months in simulation year"
        data_type: decimal(10,2)
        constraints:
          - type: not_null

      - name: active_months
        description: "Number of active months in simulation year for proration"
        data_type: decimal(4,2)
        constraints:
          - type: not_null

      - name: annual_contribution_amount
        description: "Calculated annual contribution amount before limits"
        data_type: decimal(10,2)
        constraints:
          - type: not_null

      - name: per_pay_period_contribution
        description: "Contribution amount per pay period"
        data_type: decimal(10,2)
        constraints:
          - type: not_null

      - name: irs_limited_annual_contribution
        description: "Annual contribution after applying IRS limits"
        data_type: decimal(10,2)
        constraints:
          - type: not_null

      - name: catch_up_contribution_eligible
        description: "Additional catch-up contribution amount for 50+ employees"
        data_type: decimal(10,2)
        constraints:
          - type: not_null

      - name: plan_constrained_annual_contribution
        description: "Final contribution after applying plan maximum constraints"
        data_type: decimal(10,2)
        constraints:
          - type: not_null

      - name: plan_constraint_applied
        description: "Flag indicating if plan maximum constraint was applied"
        data_type: boolean
        constraints:
          - type: not_null

      - name: deferral_rate_effective_date
        description: "Date when the deferral rate became effective (from accumulator)"
        data_type: date
        constraints:
          - type: not_null

      - name: deferral_rate_source
        description: "Source of deferral rate: enrollment, escalation, baseline, carryforward"
        data_type: varchar(20)
        constraints:
          - type: not_null

      - name: source_event_ids
        description: "JSON array of source event UUIDs for audit trail"
        data_type: json

      - name: simulation_year
        description: "Simulation year for these calculations"
        data_type: integer
        constraints:
          - type: not_null

      - name: calculated_at
        description: "Timestamp when contributions were calculated"
        data_type: timestamp
        constraints:
          - type: not_null

      - name: calculation_method
        description: "Method used for calculation (state_accumulator)"
        data_type: varchar(50)
        constraints:
          - type: not_null

      - name: model_version
        description: "Model version identifier (v2_refactored)"
        data_type: varchar(20)
        constraints:
          - type: not_null

    tests:
      - unique:
          column_name: "employee_id"
      - not_null:
          column_name: "employee_deferral_rate"
      - dbt_expectations.expect_column_values_to_be_between:
          column: "employee_deferral_rate"
          min_value: 0.0000
          max_value: 1.0000
          strictly: false
      - dbt_expectations.expect_column_values_to_be_between:
          column: "annual_contribution_amount"
          min_value: 0.00
          max_value: 100000.00  # Reasonable upper bound
          strictly: false
```

## Implementation Tasks

### Phase 1: Model Analysis & Preparation
- [ ] **Analyze current `int_employee_contributions` model** to understand exact structure and dependencies
- [ ] **Document all calculation formulas** that must be preserved
- [ ] **Identify all downstream consumers** that depend on this model's output
- [ ] **Create test cases** with known input/output pairs for validation

### Phase 2: Refactoring Implementation
- [ ] **Update source dependency** from `fct_yearly_events` to `int_deferral_rate_state_accumulator`
- [ ] **Refactor all deferral rate references** to use accumulator fields
- [ ] **Preserve all calculation logic** including IRS limits and plan constraints
- [ ] **Enhance audit trail** with accumulator source information

### Phase 3: Validation & Testing
- [ ] **Validate calculation accuracy** by comparing outputs for test scenarios
- [ ] **Test with multiple simulation years** to ensure multi-year consistency
- [ ] **Verify downstream model compatibility** with updated schema
- [ ] **Performance testing** to ensure no regression in execution time

### Phase 4: Integration & Documentation
- [ ] **Update model documentation** reflecting the refactoring changes
- [ ] **Verify orchestration compatibility** with new dependency structure
- [ ] **Add data quality tests** specific to contribution calculations
- [ ] **Document migration notes** for future reference

## Data Quality Validations

### Contribution Calculation Integrity
```sql
-- Test: All active employees with deferral rates have contributions calculated
SELECT COUNT(*) as employees_missing_contributions
FROM {{ ref('int_deferral_rate_state_accumulator') }} acc
LEFT JOIN {{ ref('int_employee_contributions') }} contrib
  ON acc.scenario_id = contrib.scenario_id
  AND acc.plan_design_id = contrib.plan_design_id
  AND acc.employee_id = contrib.employee_id
  AND acc.simulation_year = contrib.simulation_year
WHERE acc.simulation_year = {{ var('simulation_year') }}
  AND acc.is_current = TRUE
  AND acc.is_active = TRUE
  AND acc.current_deferral_rate > 0.0000
  AND contrib.employee_id IS NULL
HAVING COUNT(*) = 0  -- Should be zero
```

### Calculation Accuracy Validation
```sql
-- Test: Base contribution = prorated salary * effective deferral rate (before IRS limits)
SELECT COUNT(*) as calculation_errors
FROM {{ ref('int_employee_contributions') }} contrib
WHERE ABS(
  contrib.annual_contribution_amount -
  (contrib.prorated_annual_salary * contrib.effective_deferral_rate)
) > 0.01  -- Allow for rounding differences
HAVING COUNT(*) = 0  -- Should be zero

-- Test: Catch-up contribution logic (incremental above IRS base limit)
SELECT COUNT(*) as catch_up_errors
FROM {{ ref('int_employee_contributions') }} contrib
JOIN {{ ref('dim_plan_designs') }} plan
  ON contrib.plan_design_id = plan.plan_design_id
WHERE contrib.employee_age >= 50
  AND contrib.catch_up_contribution_amount !=
      LEAST(
        GREATEST(contrib.annual_contribution_amount - plan.annual_contribution_limit, 0),
        plan.catch_up_contribution_limit
      )
HAVING COUNT(*) = 0  -- Should be zero

-- Test: Final contribution compliance with all limits
SELECT COUNT(*) as limit_violations
FROM {{ ref('int_employee_contributions') }} contrib
JOIN {{ ref('dim_plan_designs') }} plan
  ON contrib.plan_design_id = plan.plan_design_id
WHERE contrib.final_annual_contribution_amount > (
  plan.annual_contribution_limit +
  CASE WHEN contrib.employee_age >= 50 THEN plan.catch_up_contribution_limit ELSE 0 END
)
   OR contrib.final_annual_contribution_amount > (
     contrib.prorated_annual_salary * plan.employee_max_deferral_rate + 0.01
   )
HAVING COUNT(*) = 0  -- Should be zero
```

### Audit Trail Completeness
```sql
-- Test: All contributions have audit trail from accumulator
SELECT COUNT(*) as missing_audit_trail
FROM {{ ref('int_employee_contributions') }}
WHERE deferral_rate_source IS NULL
   OR deferral_rate_effective_date IS NULL
   OR calculation_method IS NULL
HAVING COUNT(*) = 0  -- Should be zero
```

## Dependencies

### Story Dependencies
- **S036-03**: Temporal State Tracking Implementation (needs working accumulator)

### Model Dependencies
- `int_deferral_rate_state_accumulator` (new source replacing `fct_yearly_events`)
- `int_employee_compensation_by_year` (salary and pay frequency data)
- `int_baseline_workforce` (employee age, hire date, termination date for proration)
- `dim_plan_designs` (plan limits and constraints - may need year scoping)

### Blocking for Other Stories
- **S036-05**: Update Orchestrator Workflow (needs refactored model ready)
- **S036-06**: Data Quality Validation (needs working contribution calculations)

## Success Metrics

### Circular Dependency Elimination
- [ ] **Zero dependencies on `fct_yearly_events`** in refactored model
- [ ] **Successful model compilation** without circular dependency errors
- [ ] **Multi-year simulation execution** works without runtime errors
- [ ] **Orchestration runs in correct order** without dependency conflicts

### Calculation Accuracy
- [ ] **100% accuracy match** for test scenarios (before/after refactoring)
- [ ] **All IRS limit calculations preserved** with identical results
- [ ] **Plan constraint logic intact** with same business rules applied
- [ ] **Audit trail enhanced** with accumulator source information

### Performance & Quality
- [ ] **No performance regression** in model execution time
- [ ] **Data completeness maintained** for all active employee scenarios
- [ ] **Schema compatibility preserved** for downstream consumers
- [ ] **Data quality tests pass** for contribution calculation integrity

## Testing Strategy

### Regression Testing
```sql
-- Create test dataset with known scenarios
INSERT INTO test_scenarios (employee_id, deferral_rate, salary, expected_contribution)
VALUES
  ('EMP001', 0.0600, 50000.00, 3000.00),  -- 6% of $50K = $3K
  ('EMP002', 0.1000, 75000.00, 7500.00),  -- 10% of $75K = $7.5K
  ('EMP003', 0.2000, 200000.00, 22500.00) -- 20% of $200K, but limited to $22.5K IRS limit

-- Compare before/after results
SELECT
  employee_id,
  old_contribution,
  new_contribution,
  ABS(old_contribution - new_contribution) as difference
FROM test_results_comparison
WHERE ABS(old_contribution - new_contribution) > 0.01
```

### Integration Testing
- Test with real multi-year simulation data
- Validate downstream model compatibility
- Test orchestration execution order
- Verify audit trail completeness

## Definition of Done

- [ ] **`int_employee_contributions` model refactored** with no dependency on `fct_yearly_events`
- [ ] **All calculation accuracy preserved** with identical results for test scenarios
- [ ] **Audit trail enhanced** with accumulator source information
- [ ] **Schema updated** with proper contracts and data quality tests
- [ ] **Comprehensive testing completed** with regression and integration tests
- [ ] **Performance validated** with no execution time regression
- [ ] **Downstream compatibility verified** with all consuming models
- [ ] **Ready for orchestration integration** in subsequent story

## Migration Notes

### Before Refactoring
```sql
-- OLD: Circular dependency pattern
FROM {{ ref('fct_yearly_events') }}
WHERE employee_deferral_rate IS NOT NULL
```

### After Refactoring
```sql
-- NEW: Clean dependency pattern
FROM {{ ref('int_deferral_rate_state_accumulator') }}
WHERE current_deferral_rate IS NOT NULL
  AND is_current = TRUE
  AND is_active = TRUE
```

### Breaking Changes
- **None expected** - schema maintained for downstream compatibility
- Enhanced audit trail provides additional information
- Calculation method tagged as 'state_accumulator' for tracking

## Implementation Notes & Design Decisions

### Temporal Proration Strategy
The refactored model implements **monthly proration** for partial-year employment:
- **Hire mid-year**: Prorate salary based on months from hire date to year-end
- **Termination mid-year**: Prorate salary based on months from year-start to termination
- **Full year**: Use full annual salary (12 months active)
- This ensures contribution calculations align with actual employment periods

### Limits Precedence Order (Critical Fix)
The implementation enforces this **explicit precedence order**:
1. **Plan maximum deferral rate** applied first (caps the effective rate)
2. **IRS annual dollar limits** applied to contribution amount
3. **Catch-up contributions** calculated as incremental above IRS base limit

This prevents over-contribution scenarios where plan rates exceed reasonable bounds.

### Catch-Up Contribution Logic (Corrected)
- **Base calculation**: `min(prorated_salary * effective_rate, IRS_limit)`
- **Catch-up amount**: `min(max(base_contribution - IRS_limit, 0), catch_up_limit)`
- **Final contribution**: `base_IRS_limited + catch_up_amount`

This correctly calculates the **incremental amount** above the IRS base limit, not the full catch-up limit.

### Composite Key Strategy
All joins and uniqueness constraints use the **complete composite key**:
- `(scenario_id, plan_design_id, employee_id, simulation_year)`
- This prevents data corruption from partial key matches and enables multi-scenario processing

### Monthly Grain Alignment
The model reads `as_of_month` from the state accumulator to support future monthly contribution calculations while currently outputting annual aggregates. This prepares for payroll-period aware calculations if needed.

### DuckDB Compatibility
- **Incremental strategy**: Uses `delete+insert` for reliable year-over-year updates
- **JSON fields**: `source_event_ids` stored as VARCHAR with DuckDB-compatible JSON
- **No unsupported features**: Avoids DuckDB-incompatible partitioning or indexing configs

### Data Quality Enhancements
- **Bounds validation**: Multiple tests ensure contributions don't exceed salary * rate or IRS + catch-up limits
- **Completeness checks**: All active employees with positive rates get contribution calculations
- **Audit trail preservation**: Enhanced with monthly grain and source event tracking

### Open Questions Addressed
- **Output frequency**: Currently annual output; monthly capability prepared via `as_of_month` field
- **Employee age source**: Sourced from `int_baseline_workforce` with year scoping
- **Plan limits**: Currently assumes year-agnostic; TODO added for year-scoped plan parameters if needed

This refactoring eliminates the circular dependency while significantly improving calculation accuracy, temporal handling, and data quality validation compared to the original implementation.
