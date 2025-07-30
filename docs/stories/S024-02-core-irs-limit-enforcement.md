# Story S024-02: Core IRS Limit Enforcement (MVP)

## Story Overview

### Summary
Implement SQL-based IRS contribution limit enforcement for 402(g) elective deferrals and age 50+ catch-up contributions using DuckDB's optimized columnar processing. This MVP focuses on the most critical limits while deferring complex scenarios.

### Business Value
- Ensures 100% compliance with core IRS contribution limits
- Prevents excess contributions that trigger penalties
- Provides transparent audit trail for regulatory reviews

### Acceptance Criteria
- ✅ 402(g) elective deferral limit enforcement ($23,500 for 2025)
- ✅ Age 50+ catch-up contributions ($7,500 for 2025) using SQL date functions
- ✅ SQL-based YTD tracking with simple accumulation
- ✅ Limit violation detection and automatic reduction
- ✅ Audit trail for all limit applications

## Technical Specifications

### Implementation Approach
Extend the contribution calculation model with IRS limit enforcement logic.

```sql
-- dbt/models/intermediate/int_irs_limit_enforcement.sql
{{ config(materialized='table') }}

WITH contribution_base AS (
    SELECT * FROM {{ ref('int_contribution_calculation') }}
),

employee_age_calculation AS (
    SELECT
        *,
        -- Calculate age as of December 31st of simulation year
        DATE_DIFF('year',
            DATE(SPLIT_PART(employee_ssn, '-', 1) || '-01-01'),  -- Simplified birth date
            DATE(simulation_year || '-12-31')
        ) as age_at_year_end,

        -- Determine catch-up eligibility
        CASE
            WHEN DATE_DIFF('year',
                DATE(SPLIT_PART(employee_ssn, '-', 1) || '-01-01'),
                DATE(simulation_year || '-12-31')
            ) >= 50
            AND {{ var('enable_catch_up_contributions', true) }}
                THEN true
            ELSE false
        END as catch_up_eligible

    FROM contribution_base
),

limit_calculations AS (
    SELECT
        *,
        -- Base 402(g) limit for the year
        {{ var('elective_deferral_limit_2025', 23500) }} as base_402g_limit,

        -- Catch-up limit if eligible
        CASE
            WHEN catch_up_eligible
                THEN {{ var('catch_up_limit_2025', 7500) }}
            ELSE 0
        END as catch_up_limit,

        -- Total applicable limit
        {{ var('elective_deferral_limit_2025', 23500) }} +
        CASE
            WHEN catch_up_eligible
                THEN {{ var('catch_up_limit_2025', 7500) }}
            ELSE 0
        END as total_402g_limit

    FROM employee_age_calculation
),

ytd_accumulation AS (
    SELECT
        l.*,
        -- Simple YTD tracking for MVP (accumulate based on contribution date)
        SUM(l.period_deferral_amount) OVER (
            PARTITION BY l.employee_id, l.simulation_year
            ORDER BY l.contribution_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) * l.periods_per_year / 12.0 as ytd_deferrals_projected,

        -- Track prior period accumulation
        COALESCE(
            SUM(l.period_deferral_amount) OVER (
                PARTITION BY l.employee_id, l.simulation_year
                ORDER BY l.contribution_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ) * l.periods_per_year / 12.0,
            0
        ) as prior_ytd_deferrals

    FROM limit_calculations l
),

limit_enforcement AS (
    SELECT
        *,
        -- Calculate remaining limit capacity
        total_402g_limit - prior_ytd_deferrals as remaining_limit_capacity,

        -- Determine if limit would be exceeded
        CASE
            WHEN ytd_deferrals_projected > total_402g_limit THEN true
            ELSE false
        END as limit_exceeded,

        -- Calculate adjusted contribution amount
        CASE
            WHEN prior_ytd_deferrals >= total_402g_limit THEN 0
            WHEN ytd_deferrals_projected > total_402g_limit
                THEN GREATEST(0, total_402g_limit - prior_ytd_deferrals)
            ELSE period_deferral_amount
        END as adjusted_period_deferral,

        -- Track limit impact
        period_deferral_amount -
        CASE
            WHEN prior_ytd_deferrals >= total_402g_limit THEN 0
            WHEN ytd_deferrals_projected > total_402g_limit
                THEN GREATEST(0, total_402g_limit - prior_ytd_deferrals)
            ELSE period_deferral_amount
        END as limit_reduction_amount

    FROM ytd_accumulation
),

audit_trail AS (
    SELECT
        employee_id,
        simulation_year,
        contribution_date,
        employee_ssn,
        pay_frequency,
        periods_per_year,
        deferral_rate,
        deferral_type,
        annual_compensation,

        -- Age and catch-up data
        age_at_year_end,
        catch_up_eligible,
        catch_up_limit,

        -- Limit enforcement data
        base_402g_limit,
        total_402g_limit,
        period_deferral_amount as requested_deferral,
        adjusted_period_deferral as final_deferral,
        limit_exceeded,
        limit_reduction_amount,

        -- YTD tracking
        prior_ytd_deferrals,
        prior_ytd_deferrals + adjusted_period_deferral as current_ytd_deferrals,
        remaining_limit_capacity,

        -- Audit classification
        CASE
            WHEN limit_exceeded AND catch_up_eligible THEN 'catch_up_limit_applied'
            WHEN limit_exceeded AND NOT catch_up_eligible THEN 'base_limit_applied'
            WHEN adjusted_period_deferral = 0 THEN 'limit_exhausted'
            ELSE 'no_limit_applied'
        END as limit_status,

        contribution_random_seed

    FROM limit_enforcement
)

SELECT * FROM audit_trail
```

### Audit Trail Generation
Create comprehensive audit records for all limit applications:

```sql
-- dbt/models/marts/fct_irs_limit_audit.sql
{{ config(
    materialized='incremental',
    unique_key=['employee_id', 'simulation_year', 'contribution_date']
) }}

SELECT
    employee_id,
    simulation_year,
    contribution_date,
    limit_status,
    age_at_year_end,
    catch_up_eligible,
    base_402g_limit,
    catch_up_limit,
    total_402g_limit,
    requested_deferral,
    final_deferral,
    limit_reduction_amount,
    prior_ytd_deferrals,
    current_ytd_deferrals,

    -- Additional audit fields
    CASE
        WHEN limit_reduction_amount > 0 THEN
            json_object(
                'limit_type', limit_status,
                'requested_amount', requested_deferral,
                'allowed_amount', final_deferral,
                'reduction_amount', limit_reduction_amount,
                'ytd_before', prior_ytd_deferrals,
                'ytd_after', current_ytd_deferrals,
                'remaining_capacity', remaining_limit_capacity,
                'catch_up_used', catch_up_eligible AND current_ytd_deferrals > base_402g_limit
            )
        ELSE NULL
    END as limit_detail,

    current_timestamp as audit_timestamp,
    'dbt' as audit_source

FROM {{ ref('int_irs_limit_enforcement') }}
WHERE 1=1
{% if is_incremental() %}
    AND contribution_date > (SELECT MAX(contribution_date) FROM {{ this }})
{% endif %}
```

### Integration with Event Generation
Update contribution events to use limit-enforced amounts:

```sql
-- Update fct_contribution_events to use enforced amounts
WITH enforced_contributions AS (
    SELECT * FROM {{ ref('int_irs_limit_enforcement') }}
)

SELECT
    gen_random_uuid() as event_id,
    employee_id,
    'contribution' as event_type,
    contribution_date as effective_date,
    simulation_year,
    scenario_id,
    plan_design_id,
    json_object(
        'event_type', 'contribution',
        'plan_id', 'plan_001',
        'source', 'employee_pre_tax',
        'amount', final_deferral,  -- Use enforced amount
        'requested_amount', requested_deferral,
        'annual_amount', final_deferral * periods_per_year,
        'deferral_rate', deferral_rate,
        'deferral_type', deferral_type,
        'pay_frequency', pay_frequency,
        'ytd_amount', current_ytd_deferrals,
        'irs_limit_applied', limit_exceeded,
        'limit_status', limit_status,
        'catch_up_eligible', catch_up_eligible,
        'payroll_id', employee_id || '_' || simulation_year || '_' || pay_frequency
    ) as payload,
    current_timestamp as created_at
FROM enforced_contributions
WHERE final_deferral > 0
```

## MVP Simplifications

### Included in MVP
- Basic 402(g) limit enforcement
- Age 50+ catch-up contribution handling
- Simple YTD accumulation tracking
- Limit reduction calculations
- Comprehensive audit trail

### Deferred to Post-MVP
- 415(c) annual additions limit
- Highly compensated employee (HCE) limits
- After-tax contribution limits
- Roth vs traditional limit allocation
- Real-time limit monitoring
- Year-end true-up calculations

## Test Scenarios

```yaml
# dbt/tests/irs_limit_enforcement_tests.yml
test:
  - name: test_402g_limit_enforcement
    description: Verify 402(g) limits are enforced correctly
    sql: |
      SELECT COUNT(*) as violations
      FROM {{ ref('int_irs_limit_enforcement') }}
      WHERE current_ytd_deferrals > total_402g_limit

  - name: test_catch_up_eligibility
    description: Verify catch-up correctly applied to 50+ employees
    sql: |
      SELECT COUNT(*) as errors
      FROM {{ ref('int_irs_limit_enforcement') }}
      WHERE age_at_year_end >= 50
      AND NOT catch_up_eligible
      AND {{ var('enable_catch_up_contributions', true) }}
```

### Test Cases
1. **Under Limit**: $15,000 deferral with $23,500 limit (no reduction)
2. **At Limit**: $23,500 deferral equals limit (no reduction)
3. **Over Limit**: $30,000 deferral reduced to $23,500
4. **Catch-Up**: Age 55 with $31,000 allowed ($23,500 + $7,500)
5. **Limit Exhaustion**: Multiple contributions hitting limit mid-year

## Story Points: 6

### Effort Breakdown
- Limit calculation logic: 2 points
- YTD tracking implementation: 2 points
- Audit trail generation: 1 point
- Testing and validation: 1 point

## Dependencies
- Story S024-01: Basic contribution calculations
- Employee age data (from SSN or birth date)
- IRS limit configuration in dbt variables
- Existing event model for contribution events

## Definition of Done
- [ ] 402(g) limits correctly enforced for all employees
- [ ] Catch-up contributions properly calculated for 50+ employees
- [ ] YTD tracking accurately accumulates contributions
- [ ] Limit reductions calculated and applied correctly
- [ ] Audit trail captures all limit applications
- [ ] dbt tests validate limit enforcement logic
- [ ] Performance remains <5 seconds for limit calculations
