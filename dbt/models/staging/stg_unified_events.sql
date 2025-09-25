{{
  config(
    materialized='view',
    enabled=false
  )
}}

/*
 * E068G Hybrid Pipeline Event Unification
 *
 * This model provides a unified interface for event data regardless of whether
 * events were generated using SQL-based dbt models or Polars bulk event factory.
 *
 * The model automatically switches between sources based on the event_generation_mode
 * variable, providing seamless integration for downstream models.
 */

{% set event_mode = var('event_generation_mode', 'sql') %}
{% set polars_enabled = var('polars_enabled', false) %}

{% if event_mode == 'polars' and polars_enabled %}

  -- Polars Mode: Read from Polars bulk event factory output
  SELECT
    event_id,
    scenario_id,
    plan_design_id,
    employee_id,
    event_type,
    simulation_year,
    event_date as effective_date,
    event_payload::text as event_details,

    -- Extract compensation information from event payload
    CASE
      WHEN event_type = 'hire' THEN
        COALESCE(
          CAST(json_extract_string(event_payload, '$.starting_salary') AS DECIMAL(10,2)),
          50000.0
        )
      WHEN event_type IN ('promotion', 'merit') THEN
        COALESCE(
          CAST(json_extract_string(event_payload, '$.new_salary') AS DECIMAL(10,2)),
          0.0
        )
      ELSE NULL
    END as compensation_amount,

    CASE
      WHEN event_type IN ('promotion', 'merit') THEN
        COALESCE(
          CAST(json_extract_string(event_payload, '$.old_salary') AS DECIMAL(10,2)),
          0.0
        )
      ELSE NULL
    END as previous_compensation,

    -- Extract deferral rate information
    CASE
      WHEN event_type = 'benefit_enrollment' THEN
        COALESCE(
          CAST(json_extract_string(event_payload, '$.initial_deferral_rate') AS DECIMAL(5,4)),
          0.0
        )
      ELSE NULL
    END as employee_deferral_rate,

    NULL as prev_employee_deferral_rate,
    NULL as employee_age,
    NULL as employee_tenure,

    -- Extract level information
    COALESCE(
      CAST(json_extract_string(event_payload, '$.level') AS INTEGER),
      CAST(json_extract_string(event_payload, '$.new_level') AS INTEGER),
      1
    ) as level_id,

    NULL as age_band,
    NULL as tenure_band,
    event_probability,

    -- Categorize events
    CASE
      WHEN event_type IN ('hire', 'termination') THEN 'workforce_changes'
      WHEN event_type IN ('promotion', 'merit') THEN 'compensation_changes'
      WHEN event_type LIKE '%enrollment%' THEN 'benefit_events'
      ELSE 'other'
    END as event_category,

    ROW_NUMBER() OVER (
      PARTITION BY employee_id, simulation_year
      ORDER BY event_date, event_type
    ) as event_sequence,

    created_at,
    'polars_factory' as parameter_source,
    'VALID' as data_quality_flag

  FROM {{ source('polars_events', 'fct_yearly_events_polars') }}

  {% if var('simulation_year') is defined %}
  WHERE simulation_year = {{ var('simulation_year') }}
  {% endif %}

{% else %}

  -- SQL Mode: Read from traditional dbt-generated event tables
  SELECT
    event_id,
    scenario_id,
    plan_design_id,
    employee_id,
    event_type,
    simulation_year,
    effective_date,
    event_details,
    compensation_amount,
    previous_compensation,
    employee_deferral_rate,
    prev_employee_deferral_rate,
    employee_age,
    employee_tenure,
    level_id,
    age_band,
    tenure_band,
    event_probability,
    event_category,
    event_sequence,
    created_at,
    'sql_dbt_models' as parameter_source,
    data_quality_flag

  FROM {{ ref('fct_yearly_events') }}

  {% if var('simulation_year') is defined %}
  WHERE simulation_year = {{ var('simulation_year') }}
  {% endif %}

{% endif %}
