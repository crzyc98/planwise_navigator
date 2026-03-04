# Quickstart: ERISA 1,000-Hour Eligibility Rules

**Feature**: `063-1000-hr-eligibility` | **Date**: 2026-03-03

## Prerequisites

```bash
source .venv/bin/activate
cd dbt
dbt seed --threads 1    # Load configuration seeds
dbt build --threads 1 --select int_baseline_workforce+ --fail-fast  # Build foundation
```

## New Files to Create

### dbt Models (SQL)

| File | Purpose | Materialization |
|------|---------|-----------------|
| `dbt/models/intermediate/int_eligibility_computation_period.sql` | IECP/plan-year periods with 1,000-hour threshold | table |
| `dbt/models/intermediate/int_service_credit_accumulator.sql` | Temporal accumulator for eligibility + vesting service years | incremental (delete+insert) |

### dbt Macros

| File | Purpose |
|------|---------|
| `dbt/macros/classify_service_hours.sql` | Reusable macro for 1,000-hour threshold classification |

### dbt Tests

| File | Purpose |
|------|---------|
| `dbt/tests/data_quality/test_iecp_computation.sql` | IECP window spans correct 12 months from hire date |
| `dbt/tests/data_quality/test_hours_threshold.sql` | Boundary values: 0, 999, 1000, 2080 |
| `dbt/tests/data_quality/test_eligibility_vs_vesting_independence.sql` | Eligibility and vesting credits can differ |

### Configuration

| File | Change |
|------|--------|
| `config/simulation_config.yaml` | Add `erisa_eligibility` section |
| `dbt/models/intermediate/schema.yml` | Add schema tests for new models |

## Build & Test

```bash
cd dbt

# Build new models only
dbt run --select int_eligibility_computation_period int_service_credit_accumulator --vars "simulation_year: 2025" --threads 1

# Run tests for new models
dbt test --select int_eligibility_computation_period int_service_credit_accumulator --threads 1

# Run custom data quality tests
dbt test --select tag:erisa --threads 1

# Full validation build
dbt build --threads 1 --fail-fast
```

## Key Patterns

### Temporal Accumulator (int_service_credit_accumulator.sql)

```sql
{{ config(
  materialized='incremental',
  incremental_strategy='delete+insert',
  unique_key=['employee_id', 'simulation_year'],
  tags=['eligibility', 'erisa', 'STATE_ACCUMULATION']
) }}

{% set simulation_year = var('simulation_year') %}
{% set start_year = var('start_year', simulation_year) %}

{% if simulation_year == start_year %}
  -- First year: baseline + current year computation periods
  SELECT ... FROM {{ ref('int_baseline_workforce') }} bw
  LEFT JOIN {{ ref('int_eligibility_computation_period') }} ecp
    ON bw.employee_id = ecp.employee_id
{% else %}
  -- Subsequent years: prior year state + current year computation periods
  SELECT ... FROM {{ this }} prev
    WHERE prev.simulation_year = {{ simulation_year - 1 }}
  FULL OUTER JOIN {{ ref('int_eligibility_computation_period') }} ecp
    ON prev.employee_id = ecp.employee_id
{% endif %}
```

### Hours Threshold Macro

```sql
-- dbt/macros/classify_service_hours.sql
{% macro classify_service_hours(hours_column) %}
CASE
    WHEN {{ hours_column }} >= 1000 THEN 'year_of_service'
    ELSE 'no_credit'
END
{% endmacro %}
```

### IECP Boundary Calculation

```sql
-- Hire date defines IECP boundary
hire_date_anniversary = hire_date + INTERVAL '1 year'

-- IECP Year 1 hours (hire_date to year_end)
iecp_year1_hours = DATEDIFF('day', hire_date, year_end) / year_days * 2080.0

-- IECP Year 2 hours (year_start to anniversary)
iecp_year2_hours = DATEDIFF('day', year_start, hire_date_anniversary) / year_days * 2080.0

-- Total IECP hours
iecp_total_hours = iecp_year1_hours + iecp_year2_hours
```

## Verification Checklist

- [X] `int_eligibility_computation_period` produces correct IECP for mid-year hires
- [X] `int_eligibility_computation_period` switches to plan year after first anniversary
- [X] Overlap/double-credit rule awards 2 years when both IECP and plan year meet 1,000 hours
- [X] `int_service_credit_accumulator` correctly accumulates across multi-year simulation
- [X] Eligibility and vesting service credits are independently tracked
- [X] Plan entry dates comply with IRC 410(a)(4) — max 6 months or next plan year start
- [X] All boundary values (0, 999, 1000, 2080) classify correctly
- [X] Jan 1 hires: IECP and plan year coincide without double-counting
- [X] No modifications to existing `int_employer_eligibility.sql`
