{{ config(
    materialized='table',
    indexes=[
        {'columns': ['employee_id']},
        {'columns': ['simulation_year']}
    ],
    tags=["foundation", "critical", "circular_dependency_resolution"]
) }}

/*
  Primary helper model for circular dependency resolution.
  Provides active employee data from the previous year's completed workforce snapshot.

  This model creates a temporal dependency (year N depends on year N-1) instead of
  a circular dependency within the same year.

  V2 Fix: Uses a dynamic relation reference (`adapter.get_relation`) instead of a static
  `ref()` to prevent dbt's parser from detecting a false circular dependency.
  The orchestrator script MUST ensure that year N-1 is complete before running year N.
*/

{% set simulation_year = var('simulation_year') %}
{% set previous_year = simulation_year - 1 %}
{% set is_first_simulation_year = (simulation_year == 2025) %}


-- This model should only execute for years after the baseline year.
{% if not is_first_simulation_year %}

with previous_year_snapshot as (
  select
    *
  -- This creates a dynamic, runtime reference to the table, bypassing the static DAG parser.
  from {{ adapter.get_relation(database=this.database, schema=this.schema, identifier='fct_workforce_snapshot') }}
  where simulation_year = {{ previous_year }}
    and employment_status = 'active'
),

enriched_snapshot as (
  select
    employee_id,
    employee_ssn,
    employee_birth_date,
    employee_hire_date,
    current_compensation as employee_gross_compensation,
    current_age + 1 as current_age, -- Increment age for the new year
    current_tenure + 1 as current_tenure, -- Increment tenure for the new year
    level_id,
    'active' as employment_status, -- Employees from previous year are active at start of new year
    null::date as termination_date, -- Reset termination date for the new year

    -- Recalculate age band for the new, incremented age
    case
      when current_age + 1 < 25 then 'Under 25'
      when current_age + 1 < 35 then '25-34'
      when current_age + 1 < 45 then '35-44'
      when current_age + 1 < 55 then '45-54'
      when current_age + 1 < 65 then '55-64'
      else '65+'
    end as age_band,

    -- Recalculate tenure band for the new, incremented tenure
    case
      when current_tenure + 1 < 1 then 'Less than 1 year'
      when current_tenure + 1 < 3 then '1-2 years'
      when current_tenure + 1 < 5 then '3-4 years'
      when current_tenure + 1 < 10 then '5-9 years'
      when current_tenure + 1 < 20 then '10-19 years'
      else '20+ years'
    end as tenure_band,

    -- Metadata fields
    {{ simulation_year }} as simulation_year,
    'previous_year_snapshot' as data_source,

    -- Data quality validation flags
    case
      when employee_id is null then false
      when employee_ssn is null then false
      when employee_birth_date is null then false
      when employee_hire_date is null then false
      when employee_gross_compensation <= 0 then false
      when current_age < 0 or current_age > 100 then false
      when current_tenure < 0 then false
      else true
    end as data_quality_valid

  from previous_year_snapshot
)

select *
from enriched_snapshot
where data_quality_valid = true

{% else %}

-- For the first year (e.g., 2025), this model should produce no records,
-- as the `fct_workforce_snapshot` will be built from the baseline model.
-- Returning an empty set with the correct columns ensures schema consistency downstream.
select
    null::varchar as employee_id,
    null::varchar as employee_ssn,
    null::date as employee_birth_date,
    null::date as employee_hire_date,
    null::numeric(18, 2) as employee_gross_compensation,
    null::integer as current_age,
    null::integer as current_tenure,
    null::varchar as level_id,
    null::varchar as employment_status,
    null::date as termination_date,
    null::varchar as age_band,
    null::varchar as tenure_band,
    {{ simulation_year }} as simulation_year,
    'no_previous_year' as data_source,
    false as data_quality_valid
limit 0

{% endif %}
