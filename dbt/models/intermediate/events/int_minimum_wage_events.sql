{{ config(
  materialized='table',
  tags=['EVENT_GENERATION']
) }}

{% set simulation_year = var('simulation_year') | int %}
{% set start_year = var('start_year', 2025) | int %}
{% set step = minimum_wage_step(simulation_year) %}

{# A configured minimum wage needs rates. The orchestrator checks this before
   the first year; this stops any other path (such as calibration) here. #}
{% if step is not none and execute %}
  {% set rated = run_query(
    "SELECT COUNT(census_hourly_rate) FROM " ~ ref('int_baseline_workforce')
    ~ " WHERE simulation_year = " ~ start_year
  ).columns[0].values()[0] %}
  {% if rated == 0 %}
    {{ exceptions.raise_compiler_error(minimum_wage_needs_rates_message()) }}
  {% endif %}
{% endif %}

-- Minimum wage floor (#1229). On a step's effective date, everyone whose
-- hourly rate is below the new minimum is raised by (minimum / rate) - 1.
-- Hours stay as they were, so pay scales in proportion.
--
-- The rate is the census rate moved with pay: census rate x pay on the date /
-- census annual pay. Pay on the date includes this year's promotion and merit
-- raise when they take effect on or before it, so the floor applies after them
-- and a raise that already reaches the minimum needs no floor. The floor is
-- outside the raise budget: merit events are priced without it.
--
-- Only census staff carry a rate. Simulated hires and acquired members are
-- never in int_baseline_workforce, so they are never raised.

WITH step AS (
  SELECT
    {% if step is not none %}
    DATE '{{ step.effective_date }}' AS effective_date,
    CAST({{ step.hourly_rate }} AS DOUBLE) AS minimum_hourly_rate
    {% else %}
    CAST(NULL AS DATE) AS effective_date,
    CAST(NULL AS DOUBLE) AS minimum_hourly_rate
    WHERE FALSE
    {% endif %}
),

census_rates AS (
  SELECT
    employee_id,
    census_hourly_rate,
    current_compensation AS census_annual_pay
  FROM {{ ref('int_baseline_workforce') }}
  WHERE simulation_year = {{ start_year }}
    AND census_hourly_rate IS NOT NULL
    AND current_compensation > 0
),

opening_pay AS (
  SELECT
    comp.employee_id,
    comp.employee_ssn,
    comp.employee_compensation,
    comp.current_age,
    comp.current_tenure,
    comp.level_id,
    comp.age_band,
    comp.tenure_band,
    rates.census_hourly_rate,
    rates.census_annual_pay
  FROM {{ ref('int_employee_compensation_by_year') }} comp
  INNER JOIN census_rates rates ON comp.employee_id = rates.employee_id
  WHERE comp.simulation_year = {{ simulation_year }}
    AND comp.employment_status = 'active'
    AND comp.employee_compensation > 0
),

-- Pay on the effective date, compounded as int_workforce_state_accumulator
-- compounds a promotion and a merit raise priced from the same opening pay.
pay_on_date AS (
  SELECT
    o.*,
    s.effective_date,
    s.minimum_hourly_rate,
    p.level_id AS promoted_level_id,
    CASE
      WHEN p.employee_id IS NOT NULL AND m.employee_id IS NOT NULL
        THEN ROUND(p.compensation_amount
          * (1 + (m.compensation_amount / m.previous_compensation - 1.0)), 2)
      WHEN m.employee_id IS NOT NULL THEN m.compensation_amount
      WHEN p.employee_id IS NOT NULL THEN p.compensation_amount
      ELSE o.employee_compensation
    END AS pay_before
  FROM opening_pay o
  CROSS JOIN step s
  LEFT JOIN {{ ref('int_employee_termination_dates') }} t
    ON o.employee_id = t.employee_id
   AND t.simulation_year = {{ simulation_year }}
  LEFT JOIN {{ ref('int_promotion_events') }} p
    ON o.employee_id = p.employee_id
   AND p.simulation_year = {{ simulation_year }}
   AND p.effective_date <= s.effective_date
  LEFT JOIN {{ ref('int_merit_events') }} m
    ON o.employee_id = m.employee_id
   AND m.simulation_year = {{ simulation_year }}
   AND m.effective_date <= s.effective_date
   AND m.previous_compensation > 0
  -- Same rule as merit: someone who leaves before the date is not raised.
  WHERE t.termination_date IS NULL OR t.termination_date >= s.effective_date
),

floored AS (
  SELECT
    *,
    {{ census_hourly_rate_now('census_hourly_rate', 'census_annual_pay', 'pay_before') }}
      AS hourly_rate_before,
    ROUND(pay_before * minimum_hourly_rate
      / {{ census_hourly_rate_now('census_hourly_rate', 'census_annual_pay', 'pay_before') }}, 2)
      AS pay_after
  FROM pay_on_date
)

SELECT
  employee_id,
  employee_ssn,
  {{ evt_minimum_wage() }} AS event_type,
  {{ simulation_year }} AS simulation_year,
  effective_date,
  'Minimum wage $' || printf('%.2f', minimum_hourly_rate) || '/hr: hourly rate $'
    || printf('%.2f', hourly_rate_before) || ' to $' || printf('%.2f', minimum_hourly_rate)
    AS event_details,
  pay_after AS compensation_amount,
  pay_before AS previous_compensation,
  NULL::DECIMAL(5,4) AS employee_deferral_rate,
  NULL::DECIMAL(5,4) AS prev_employee_deferral_rate,
  current_age AS employee_age,
  current_tenure AS employee_tenure,
  COALESCE(promoted_level_id, level_id) AS level_id,
  age_band,
  tenure_band,
  NULL::DOUBLE AS event_probability,
  {{ evt_minimum_wage() }} AS event_category,
  hourly_rate_before,
  minimum_hourly_rate AS hourly_rate_after
FROM floored
-- At least a cent of annual pay, so someone already at the minimum is not
-- raised again by rounding.
WHERE pay_after > pay_before
