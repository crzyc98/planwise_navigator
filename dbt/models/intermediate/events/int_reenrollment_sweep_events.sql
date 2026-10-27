{{ config(materialized='ephemeral', tags=['EVENT_GENERATION']) }}

-- A plan-initiated rate election, independent of the one VOLUNTARY change/year.
-- Emit even when the rate is unchanged: that event records the AIP election.
SELECT
  employee_id, employee_ssn, 'deferral_change' AS event_type, simulation_year,
  effective_date,
  ('Re-enrollment sweep - ' || ROUND(rate_at_sweep * 100, 2) || '% -> '
    || ROUND(sweep_rate * 100, 2) || '% deferral; method=' || method) AS event_details,
  current_compensation AS compensation_amount,
  current_compensation AS previous_compensation,
  sweep_rate AS employee_deferral_rate,
  rate_at_sweep::DECIMAL(5,4) AS prev_employee_deferral_rate,
  current_age AS employee_age, current_tenure AS employee_tenure,
  level_id, age_band, tenure_band,
  (1 - decline_probability)::DECIMAL(5,4) AS event_probability,
  'reenrollment_sweep' AS event_category
FROM {{ ref('int_reenrollment_sweep_candidates') }}
WHERE simulation_year = {{ var('simulation_year') }}
  AND scenario_id = '{{ var("scenario_id", "default") }}'
  AND NOT declined
