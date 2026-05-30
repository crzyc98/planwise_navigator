# Contract: int_eligibility_events

**Type**: dbt incremental model
**Produces**: `DC_PLAN_ELIGIBILITY` events for `fct_yearly_events` UNION ALL
**Consumers**: `fct_yearly_events`

---

## Column Contract

Must match the UNION ALL schema in `fct_yearly_events.sql` exactly:

```sql
SELECT
  employee_id,          -- VARCHAR NOT NULL
  employee_ssn,         -- VARCHAR
  event_type,           -- VARCHAR = 'eligibility'
  simulation_year,      -- INT NOT NULL
  effective_date,       -- DATE NOT NULL (eligibility_effective_date)
  event_details,        -- VARCHAR NOT NULL
  compensation_amount,  -- DECIMAL(10,2) = NULL
  previous_compensation,-- DECIMAL(10,2) = NULL
  employee_deferral_rate,      -- DECIMAL(5,4) = NULL
  prev_employee_deferral_rate, -- DECIMAL(5,4) = NULL
  employee_age,         -- DECIMAL
  employee_tenure,      -- DECIMAL
  level_id,             -- INT
  age_band,             -- VARCHAR
  tenure_band,          -- VARCHAR
  event_probability,    -- DECIMAL = 1.0
  event_category        -- VARCHAR = 'eligibility'
FROM int_eligibility_events
WHERE simulation_year = {{ var('simulation_year') }}
```

---

## Uniqueness Guarantee

- One row per `(employee_id, simulation_year)` — enforced by `unique_key` in incremental config
- No employee appears in more than one simulation year — enforced by the self-reference anti-join

---

## Invariants

1. `event_type = 'eligibility'` for every row
2. `effective_date` is never NULL (all eligible employees have a computable date)
3. `effective_date >= employee_hire_date` (eligibility cannot precede hire)
4. `event_probability = 1.0` (deterministic eligibility determination)
5. `event_category = 'eligibility'` (matches `int_workforce_snapshot_optimized` filter)

---

## Prerequisite Chain Contract

**Downstream enforcement** (via `test_enrollment_requires_prior_eligibility.sql`):

```
∀ enrollment events in fct_yearly_events:
  ∃ eligibility event in fct_yearly_events
    WHERE employee_id = enrollment.employee_id
      AND simulation_year = enrollment.simulation_year
      AND effective_date ≤ enrollment.effective_date
```

This test returns rows when the contract is violated. A non-empty result fails the dbt test.

---

## Incremental Config

```sql
{{ config(
  materialized='incremental',
  incremental_strategy='delete+insert',
  unique_key=['employee_id', 'simulation_year'],
  pre_hook=[
    "{% if is_incremental() %}DELETE FROM {{ this }}
     WHERE simulation_year = {{ var('simulation_year') }}{% endif %}"
  ],
  tags=['EVENT_GENERATION']
) }}
```

---

## Data Quality Tests (schema.yml)

```yaml
- name: int_eligibility_events
  data_tests:
    - dbt_utils.unique_combination_of_columns:
        combination_of_columns:
          - employee_id
          - simulation_year
  columns:
    - name: employee_id
      data_tests: [not_null]
    - name: event_type
      data_tests:
        - accepted_values:
            values: ['eligibility']
    - name: effective_date
      data_tests: [not_null]
    - name: event_category
      data_tests:
        - accepted_values:
            values: ['eligibility']
```
