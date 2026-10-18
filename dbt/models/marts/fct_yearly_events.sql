-- Durable, single-writer publication of the current year's immutable events.

{{ config(
  materialized='incremental',
  incremental_strategy='replace_simulation_year',
  on_schema_change='sync_all_columns',
  tags=['EVENT_GENERATION']
) }}

SELECT
  event_id,
  scenario_id,
  plan_design_id,
  employee_id,
  employee_ssn,
  event_type,
  simulation_year,
  effective_date,
  event_details,
  compensation_amount,
  previous_compensation,
  employee_deferral_rate,
  prev_employee_deferral_rate,
  employee_age,
  CAST(employee_tenure AS DECIMAL(12,2)) AS employee_tenure,
  level_id,
  age_band,
  tenure_band,
  event_probability,
  event_category,
  event_sequence,
  created_at,
  parameter_scenario_id,
  parameter_source,
  data_quality_flag
FROM {{ ref('int_current_year_events') }}
