-- Durable, single-writer publication of the current year's immutable events.

{{ config(
  materialized='incremental',
  incremental_strategy='append',
  pre_hook=[
    "{% if is_incremental() %}DELETE FROM {{ this }} WHERE scenario_id = '{{ var('scenario_id', 'default') }}' AND plan_design_id = '{{ var('plan_design_id', 'default') }}' AND simulation_year = {{ var('simulation_year', 2025) }}{% endif %}"
  ],
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
