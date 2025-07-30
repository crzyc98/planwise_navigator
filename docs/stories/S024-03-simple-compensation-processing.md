# Story S024-03: Simple Compensation Processing (MVP)

## Story Overview

### Summary
Implement basic compensation processing for contribution calculations using W-2 wages as the baseline with hardcoded inclusion/exclusion rules. This MVP focuses on the most common compensation scenarios while maintaining IRS compliance.

### Business Value
- Ensures contributions are calculated on correct compensation base
- Maintains compliance with IRS compensation limits
- Provides consistent compensation definitions across the platform

### Acceptance Criteria
- ✅ W-2 wage baseline with basic inclusions (regular pay, overtime)
- ✅ Hardcoded exclusions (severance, fringe benefits)
- ✅ IRS annual compensation limit ($360,000 for 2025)
- ✅ Basic partial period proration for new hires/terminations
- ✅ Integration with workforce events from simulation

## Technical Specifications

### Implementation Approach
Create a compensation processing layer that integrates with workforce events and applies IRS rules.

```sql
-- dbt/models/intermediate/int_compensation_processing.sql
{{ config(materialized='table') }}

WITH workforce_base AS (
    SELECT
        employee_id,
        employee_ssn,
        simulation_year,
        annual_compensation,
        employee_hire_date,
        employee_termination_date,
        employment_status,
        current_age,
        level_id,

        -- Calculate employment period fractions
        CASE
            WHEN DATE_PART('year', employee_hire_date) = simulation_year THEN
                -- New hire proration
                (365 - DATE_PART('dayofyear', employee_hire_date) + 1) / 365.0
            WHEN employee_termination_date IS NOT NULL
                AND DATE_PART('year', employee_termination_date) = simulation_year THEN
                -- Termination proration
                DATE_PART('dayofyear', employee_termination_date) / 365.0
            ELSE 1.0
        END as employment_fraction

    FROM {{ ref('int_baseline_workforce') }}
    WHERE simulation_year = {{ var('current_simulation_year') }}
),

compensation_events AS (
    -- Pull in any mid-year compensation changes from events
    SELECT
        employee_id,
        simulation_year,
        event_type,
        effective_date,
        -- Extract compensation changes from raise/promotion events
        CASE
            WHEN event_type = 'raise' THEN
                CAST(json_extract_string(payload, '$.new_salary') AS DECIMAL(10,2))
            WHEN event_type = 'promotion' THEN
                CAST(json_extract_string(payload, '$.new_salary') AS DECIMAL(10,2))
            ELSE NULL
        END as new_compensation
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type IN ('raise', 'promotion')
    AND simulation_year = {{ var('current_simulation_year') }}
),

compensation_components AS (
    SELECT
        w.*,
        -- Base W-2 wages (simplified for MVP)
        w.annual_compensation as base_wages,

        -- Calculate included compensation (MVP: regular + overtime estimate)
        CASE
            WHEN {{ var('include_regular_pay', true) }} THEN w.annual_compensation
            ELSE 0
        END +
        CASE
            WHEN {{ var('include_overtime', true) }} THEN
                -- Estimate overtime as 5% for non-exempt employees (levels 1-3)
                CASE
                    WHEN w.level_id <= 3 THEN w.annual_compensation * 0.05
                    ELSE 0
                END
            ELSE 0
        END as included_compensation,

        -- Calculate excluded compensation (hardcoded for MVP)
        CASE
            WHEN w.employment_status = 'terminated' AND {{ var('exclude_severance', true) }} THEN
                -- Estimate severance as 2 weeks per year of service
                w.annual_compensation * 2/52 * LEAST(10, DATE_DIFF('year', w.employee_hire_date, CURRENT_DATE))
            ELSE 0
        END as excluded_compensation,

        -- Get latest compensation if changed mid-year
        COALESCE(
            LAST_VALUE(ce.new_compensation) OVER (
                PARTITION BY w.employee_id
                ORDER BY ce.effective_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
            ),
            w.annual_compensation
        ) as current_compensation

    FROM workforce_base w
    LEFT JOIN compensation_events ce
        ON w.employee_id = ce.employee_id
        AND w.simulation_year = ce.simulation_year
),

eligible_compensation AS (
    SELECT
        employee_id,
        employee_ssn,
        simulation_year,
        employment_status,
        employment_fraction,
        base_wages,
        included_compensation,
        excluded_compensation,
        current_compensation,

        -- Calculate gross eligible compensation
        (included_compensation - excluded_compensation) as gross_eligible_compensation,

        -- Apply employment period proration
        (included_compensation - excluded_compensation) * employment_fraction as prorated_compensation,

        -- Apply IRS compensation limit
        LEAST(
            (included_compensation - excluded_compensation) * employment_fraction,
            {{ var('irs_compensation_limit_2025', 360000) }}
        ) as final_eligible_compensation,

        -- Track if limit was applied
        CASE
            WHEN (included_compensation - excluded_compensation) * employment_fraction >
                 {{ var('irs_compensation_limit_2025', 360000) }}
            THEN true
            ELSE false
        END as irs_limit_applied

    FROM compensation_components
),

compensation_summary AS (
    SELECT
        *,
        -- Add audit fields
        CASE
            WHEN employment_fraction < 1.0 THEN 'partial_year'
            WHEN irs_limit_applied THEN 'irs_limited'
            WHEN excluded_compensation > 0 THEN 'exclusions_applied'
            ELSE 'standard'
        END as compensation_status,

        -- Calculate effective compensation rate
        final_eligible_compensation / NULLIF(base_wages * employment_fraction, 0) as effective_comp_rate

    FROM eligible_compensation
)

SELECT * FROM compensation_summary
```

### Integration with Contribution Calculations
Update the contribution calculation to use processed compensation:

```sql
-- Update int_contribution_calculation.sql to use processed compensation
WITH enrolled_employees AS (
    SELECT
        e.employee_id,
        e.simulation_year,
        e.employee_ssn,
        -- Use processed compensation instead of raw annual_compensation
        c.final_eligible_compensation as annual_compensation,
        c.employment_fraction,
        c.compensation_status,
        e.current_age,
        e.employment_status,
        en.deferral_rate,
        en.deferral_type,
        en.deferral_amount
    FROM {{ ref('int_enrollment_determination') }} en
    INNER JOIN {{ ref('int_baseline_workforce') }} e
        ON en.employee_id = e.employee_id
    INNER JOIN {{ ref('int_compensation_processing') }} c
        ON e.employee_id = c.employee_id
        AND e.simulation_year = c.simulation_year
    WHERE en.enrolled = true
    AND e.employment_status = 'active'
)
-- Continue with existing calculation logic...
```

### Compensation Audit Trail
Track compensation processing for compliance:

```sql
-- dbt/models/marts/fct_compensation_audit.sql
{{ config(
    materialized='incremental',
    unique_key=['employee_id', 'simulation_year']
) }}

SELECT
    employee_id,
    simulation_year,
    base_wages,
    included_compensation,
    excluded_compensation,
    gross_eligible_compensation,
    employment_fraction,
    prorated_compensation,
    final_eligible_compensation,
    irs_limit_applied,
    compensation_status,

    -- Detailed breakdown for audit
    json_object(
        'base_w2_wages', base_wages,
        'regular_pay_included', base_wages * {{ var('include_regular_pay', true) }},
        'overtime_estimate', included_compensation - base_wages,
        'severance_excluded',
            CASE WHEN excluded_compensation > 0 THEN excluded_compensation ELSE 0 END,
        'employment_months', ROUND(employment_fraction * 12, 1),
        'irs_limit', {{ var('irs_compensation_limit_2025', 360000) }},
        'amount_over_limit',
            GREATEST(0, prorated_compensation - {{ var('irs_compensation_limit_2025', 360000) }})
    ) as compensation_detail,

    current_timestamp as audit_timestamp

FROM {{ ref('int_compensation_processing') }}
WHERE 1=1
{% if is_incremental() %}
    AND simulation_year > (SELECT MAX(simulation_year) FROM {{ this }})
{% endif %}
```

## MVP Simplifications

### Included in MVP
- W-2 wages as compensation baseline
- Basic overtime estimation for non-exempt
- Severance exclusion for terminated employees
- IRS compensation limit enforcement
- New hire/termination proration

### Deferred to Post-MVP
- Configurable compensation definitions
- Multiple compensation types (bonuses, commissions)
- Safe harbor compensation testing
- Complex leave of absence handling
- Real payroll system integration
- Historical compensation corrections

## Test Scenarios

```yaml
# dbt/models/intermediate/schema.yml
models:
  - name: int_compensation_processing
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns:
            - employee_id
            - simulation_year
    columns:
      - name: final_eligible_compensation
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 360000
              inclusive: true
      - name: employment_fraction
        tests:
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 1
              inclusive: true
```

### Test Cases
1. **Full Year Employee**: $100,000 wages = $100,000 eligible
2. **High Earner**: $500,000 wages limited to $360,000
3. **Mid-Year Hire**: 6 months employment = 50% proration
4. **Terminated with Severance**: Severance excluded from eligible comp
5. **Overtime Inclusion**: Non-exempt with 5% overtime estimate

## Story Points: 4

### Effort Breakdown
- Compensation processing logic: 2 points
- Proration calculations: 1 point
- Testing and validation: 1 point

## Dependencies
- Workforce data with compensation (int_baseline_workforce)
- Compensation change events (raises, promotions)
- Employment status and dates
- IRS limit configuration

## Definition of Done
- [ ] W-2 compensation correctly extracted and processed
- [ ] Overtime estimates applied to non-exempt employees
- [ ] Severance properly excluded from eligible compensation
- [ ] IRS compensation limit enforced at $360,000
- [ ] Partial year proration calculates correctly
- [ ] Integration with contribution calculations working
- [ ] Audit trail captures all compensation adjustments
