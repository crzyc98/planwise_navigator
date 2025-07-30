# Story S024-01: Basic Contribution Calculations (MVP)

## Story Overview

### Summary
Build a high-performance SQL/dbt contribution calculator that processes 100K+ employees in <10 seconds using DuckDB columnar operations. This MVP implementation focuses on essential deferral calculations while deferring complex scenarios.

### Business Value
- Automates contribution calculations for 95% of standard cases
- Ensures accurate payroll deductions based on employee elections
- Provides reproducible calculations for audit compliance

### Acceptance Criteria
- ✅ SQL-based employee deferral calculations for 100K employees in <10 seconds
- ✅ Percentage-based and dollar-based deferral elections via dbt variables
- ✅ Basic pay frequency handling (bi-weekly, monthly)
- ✅ Generate CONTRIBUTION events in existing event model
- ✅ Deterministic calculations for reproducibility
- ✅ Integration with enrollment determination from E023

## Technical Specifications

### Implementation Approach
Following the proven E022/E023 pattern, use SQL/dbt for maximum performance.

```sql
-- dbt/models/intermediate/int_contribution_calculation.sql
{{ config(materialized='table') }}

WITH enrolled_employees AS (
    SELECT
        e.employee_id,
        e.simulation_year,
        e.employee_ssn,
        e.annual_compensation,
        e.current_age,
        e.employment_status,
        -- Get enrollment data
        en.deferral_rate,
        COALESCE(en.deferral_type, 'percentage') as deferral_type,
        COALESCE(en.deferral_amount, 0.0) as deferral_amount,
        en.enrolled_date
    FROM {{ ref('int_enrollment_determination') }} en
    INNER JOIN {{ ref('int_baseline_workforce') }} e
        ON en.employee_id = e.employee_id
        AND en.simulation_year = e.simulation_year
    WHERE en.enrolled = true
    AND e.employment_status = 'active'
),

pay_period_calculations AS (
    SELECT
        *,
        -- Determine pay frequency (MVP: simplified to monthly/bi-weekly)
        CASE
            WHEN MOD(ABS(HASH(employee_id)), 3) = 0 THEN 'monthly'
            ELSE 'biweekly'
        END as pay_frequency,

        -- Calculate periods per year
        CASE
            WHEN MOD(ABS(HASH(employee_id)), 3) = 0 THEN {{ var('monthly_periods_per_year', 12) }}
            ELSE {{ var('biweekly_periods_per_year', 26) }}
        END as periods_per_year

    FROM enrolled_employees
),

deferral_calculations AS (
    SELECT
        *,
        -- Calculate annual deferral based on election type
        CASE
            WHEN deferral_type = 'percentage'
                THEN annual_compensation * deferral_rate
            WHEN deferral_type = 'dollar'
                THEN deferral_amount * periods_per_year
            ELSE 0
        END AS annual_deferral_amount,

        -- Calculate per-period deferral
        CASE
            WHEN deferral_type = 'percentage'
                THEN (annual_compensation / periods_per_year) * deferral_rate
            WHEN deferral_type = 'dollar'
                THEN deferral_amount
            ELSE 0
        END AS period_deferral_amount

    FROM pay_period_calculations
),

contribution_events AS (
    SELECT
        employee_id,
        simulation_year,
        employee_ssn,
        pay_frequency,
        periods_per_year,
        deferral_rate,
        deferral_type,
        annual_compensation,
        annual_deferral_amount,
        period_deferral_amount,

        -- Generate deterministic contribution date based on pay frequency
        CASE
            WHEN pay_frequency = 'monthly' THEN
                DATE_TRUNC('month', DATE(simulation_year || '-01-01')) +
                INTERVAL '1 month' * MOD(ABS(HASH(employee_id || simulation_year)), 12)
            ELSE  -- biweekly
                DATE(simulation_year || '-01-01') +
                INTERVAL '14 days' * MOD(ABS(HASH(employee_id || simulation_year)), 26)
        END as contribution_date,

        -- Deterministic random seed for reproducibility
        (ABS(HASH(employee_id || simulation_year || 'contribution')) % 1000000) / 1000000.0 as contribution_random_seed

    FROM deferral_calculations
    WHERE period_deferral_amount > 0
)

SELECT * FROM contribution_events
```

### Event Generation Pattern
Generate contribution events integrated with existing event sourcing:

```sql
-- dbt/models/marts/fct_contribution_events.sql
{{ config(materialized='incremental') }}

WITH contribution_data AS (
    SELECT * FROM {{ ref('int_contribution_calculation') }}
    {% if is_incremental() %}
    WHERE simulation_year > (SELECT MAX(simulation_year) FROM {{ this }})
    {% endif %}
)

SELECT
    gen_random_uuid() as event_id,
    employee_id,
    'contribution' as event_type,
    contribution_date as effective_date,
    simulation_year,
    '{{ var("scenario_id", "default") }}' as scenario_id,
    '{{ var("plan_design_id", "standard") }}' as plan_design_id,
    json_object(
        'event_type', 'contribution',
        'plan_id', 'plan_001',
        'source', 'employee_pre_tax',
        'amount', period_deferral_amount,
        'annual_amount', annual_deferral_amount,
        'deferral_rate', deferral_rate,
        'deferral_type', deferral_type,
        'pay_frequency', pay_frequency,
        'pay_period_end', contribution_date,
        'contribution_date', contribution_date + INTERVAL '5 days',
        'payroll_id', employee_id || '_' || simulation_year || '_' || pay_frequency,
        'inferred_value', false
    ) as payload,
    current_timestamp as created_at,
    'dbt' as created_by
FROM contribution_data
```

### Integration Points
1. **Data Source**: Uses `int_enrollment_determination` and `int_baseline_workforce`
2. **dbt Models**: Creates `int_contribution_calculation` and `fct_contribution_events`
3. **Configuration**: Uses dbt variables for pay frequencies and calculation methods
4. **Event Storage**: Integrates with `fct_yearly_events` table
5. **Orchestration**: Run as part of dbt asset materialization

## MVP Simplifications

### Included in MVP
- Basic percentage and dollar deferral elections
- Simple pay frequency determination (monthly/bi-weekly)
- Annual compensation-based calculations
- Deterministic contribution date generation
- Event generation for downstream processing

### Deferred to Post-MVP
- Real payroll calendar integration
- Complex pay frequency rules
- Bonus deferral elections
- Mid-year election changes
- True-up contributions
- Retroactive adjustments

## Test Scenarios

```yaml
# dbt/models/intermediate/schema.yml
models:
  - name: int_contribution_calculation
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns:
            - employee_id
            - simulation_year
            - contribution_date
    columns:
      - name: period_deferral_amount
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              inclusive: true
      - name: annual_deferral_amount
        tests:
          - dbt_utils.expression_is_true:
              expression: "annual_deferral_amount >= 0"
```

### Test Cases
1. **Percentage Deferral**: 6% of $60,000 salary = $3,600/year
2. **Dollar Deferral**: $500/period × 26 periods = $13,000/year
3. **Zero Deferral**: Non-enrolled employees excluded
4. **Pay Frequency**: Verify monthly vs bi-weekly calculations
5. **Bulk Performance**: 100K employee processing in <10 seconds

## Story Points: 8

### Effort Breakdown
- Core calculation logic: 3 points
- Event generation: 2 points
- Pay frequency handling: 2 points
- Testing and validation: 1 point

## Dependencies
- Story S023-01: Basic enrollment data (deferral elections)
- Existing event model (ContributionPayload in config/events.py)
- Workforce compensation data (int_baseline_workforce)
- Event storage infrastructure (fct_yearly_events)

## Definition of Done
- [ ] Contribution calculation model processes 100K employees in <10 seconds
- [ ] Percentage and dollar deferrals calculate correctly
- [ ] Pay frequency logic distributes contributions appropriately
- [ ] Events generated in correct format with all required fields
- [ ] dbt tests achieve 100% pass rate
- [ ] Integration test with sample data validates calculations
- [ ] Performance benchmark documented
