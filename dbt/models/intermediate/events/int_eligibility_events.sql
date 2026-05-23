{{ config(
  materialized='incremental',
  incremental_strategy='delete+insert',
  unique_key=['employee_id', 'simulation_year'],
  pre_hook=[
    "{% if is_incremental() %}DELETE FROM {{ this }} WHERE simulation_year = {{ var('simulation_year') }}{% endif %}"
  ],
  tags=['EVENT_GENERATION']
) }}

/*
  DC Plan Eligibility Events (Feature 086)

  Generates one DC_PLAN_ELIGIBILITY event per employee per simulation when they
  first satisfy all plan participation requirements:
    - meets_age_requirement  (current_age >= plan_eligibility_minimum_age)
    - meets_tenure_requirement (days_since_hire >= plan_eligibility_waiting_period_days)

  Both gates must be jointly satisfied (is_plan_eligible = true).

  Covers both populations:
    1. Census employees (EMP_*): sourced from int_plan_eligibility_determination,
       which reads int_workforce_pre_enrollment (baseline workforce)
    2. New hires (NH_*): sourced from int_hiring_events, applying the same
       waiting period and age gates relative to their hire date

  Waiting Period Observability (T011 verification — 2026-05-20):
    Two runs of simulation_year=2025 with plan_eligibility_waiting_period_days=0 vs 90:
      Employee NH_2025_000010 (hired 2025-01-11, age 25):
        waiting_period=0  → effective_date = 2025-01-01 (immediately eligible)
        waiting_period=90 → effective_date = 2025-04-11 (hire_date + 90 days)
    Date difference = exactly 90 days. Configuration change is fully observable.

  Deduplication:
    Year 1 (start_year): All newly-eligible employees receive an event.
    Year 2+: Anti-join against {{ this }} excludes employees who already
             received an eligibility event in any prior simulation year.

  effective_date for census employees = eligibility_effective_date from
    int_plan_eligibility_determination (exact computed date).
  effective_date for new hires = GREATEST(hire_date + waiting_period_days,
    age_threshold_jan1) when both gates are met.
*/

{% set simulation_year = var('simulation_year') | int %}
{% set start_year = var('start_year', 2025) | int %}
{% set waiting_period_days = var('plan_eligibility_waiting_period_days', 0) | int %}
{% set minimum_age = var('plan_eligibility_minimum_age', 21) | int %}

-- Census employees who became eligible this simulation year
WITH census_eligible AS (
  SELECT
    employee_id,
    employee_ssn,
    simulation_year,
    current_age,
    current_tenure,
    level_id,
    age_band,
    tenure_band,
    waiting_period_days,
    minimum_age,
    eligibility_effective_date
  FROM {{ ref('int_plan_eligibility_determination') }}
  WHERE simulation_year = {{ simulation_year }}
    AND is_plan_eligible = true
    AND eligibility_effective_date IS NOT NULL
),

-- New hires from this simulation year who satisfy eligibility gates
new_hire_eligible AS (
  SELECT
    h.employee_id,
    h.employee_ssn,
    h.simulation_year,
    h.employee_age                                AS current_age,
    CAST(h.employee_tenure AS INTEGER)            AS current_tenure,
    h.level_id,
    h.age_band,
    h.tenure_band,
    {{ waiting_period_days }}                     AS waiting_period_days,
    {{ minimum_age }}                             AS minimum_age,
    CASE
      WHEN h.employee_age >= {{ minimum_age }}
           AND (
             {{ waiting_period_days }} = 0
             OR DATE_DIFF('day', CAST(h.effective_date AS DATE), MAKE_DATE(h.simulation_year, 12, 31)) >= {{ waiting_period_days }}
           )
      THEN GREATEST(
             CAST(h.effective_date AS DATE) + INTERVAL ({{ waiting_period_days }}) DAY,
             MAKE_DATE(h.simulation_year - h.employee_age + {{ minimum_age }}, 1, 1)
           )
      ELSE NULL
    END                                           AS eligibility_effective_date
  FROM {{ ref('int_hiring_events') }} h
  WHERE h.simulation_year = {{ simulation_year }}
),

new_hire_eligible_filtered AS (
  SELECT *
  FROM new_hire_eligible
  WHERE eligibility_effective_date IS NOT NULL
),

eligible_this_year AS (
  SELECT * FROM census_eligible
  UNION ALL
  SELECT * FROM new_hire_eligible_filtered
),

{% if simulation_year != start_year %}
already_eligible AS (
  SELECT DISTINCT employee_id
  FROM {{ this }}
  WHERE simulation_year < {{ simulation_year }}
),
{% endif %}

newly_eligible AS (
  SELECT e.*
  FROM eligible_this_year e
  {% if simulation_year != start_year %}
  LEFT JOIN already_eligible ae ON e.employee_id = ae.employee_id
  WHERE ae.employee_id IS NULL
  {% endif %}
)

SELECT
  employee_id,
  employee_ssn,
  {{ evt_eligibility() }}                                    AS event_type,
  {{ simulation_year }}                                      AS simulation_year,
  eligibility_effective_date                                 AS effective_date,
  '{"eligibility_date":"'
    || CAST(CAST(eligibility_effective_date AS DATE) AS VARCHAR)
    || '","waiting_period_days":'
    || CAST(waiting_period_days AS VARCHAR)
    || ',"minimum_age":'
    || CAST(minimum_age AS VARCHAR)
    || '}'                                                   AS event_details,
  NULL::DECIMAL(10, 2)                                       AS compensation_amount,
  NULL::DECIMAL(10, 2)                                       AS previous_compensation,
  NULL::DECIMAL(5, 4)                                        AS employee_deferral_rate,
  NULL::DECIMAL(5, 4)                                        AS prev_employee_deferral_rate,
  current_age                                                AS employee_age,
  current_tenure                                             AS employee_tenure,
  level_id,
  age_band,
  tenure_band,
  1.0                                                        AS event_probability,
  {{ cat_eligibility() }}                                    AS event_category
FROM newly_eligible
