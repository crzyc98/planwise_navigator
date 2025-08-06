{{ config(
  materialized='table'
) }}

{% set simulation_year = var('simulation_year', none) %}

-- Unified fact table containing all workforce events across simulation years
-- Consolidates terminations, promotions, hires, and merit increases with common schema
-- Following PRD v3.0 requirements and CLAUDE.md DuckDB patterns
--
-- Materialization Strategy: TABLE for multi-year data persistence
-- - Accumulates events across all simulation years
-- - Enables year-over-year workforce transition analysis
-- - Use simulation_year variable to filter for specific years when needed

WITH termination_events AS (
  SELECT
    employee_id,
    employee_ssn,
    event_type,
    simulation_year,
    effective_date,
    termination_reason AS event_details,
    final_compensation AS compensation_amount,
    NULL AS previous_compensation,
    NULL::decimal(5,4) AS employee_deferral_rate,
    NULL::decimal(5,4) AS prev_employee_deferral_rate,
    current_age AS employee_age,
    current_tenure AS employee_tenure,
    level_id,
    age_band,
    tenure_band,
    termination_rate AS event_probability,
    'experienced_termination' AS event_category
  FROM {{ ref('int_termination_events') }}
  {%- if simulation_year %}
  WHERE simulation_year = {{ simulation_year }}
  {%- endif %}
),

new_hire_termination_events AS (
  SELECT
    employee_id,
    employee_ssn,
    event_type,
    simulation_year,
    effective_date,
    termination_reason AS event_details,
    final_compensation AS compensation_amount,
    NULL AS previous_compensation,
    NULL::decimal(5,4) AS employee_deferral_rate,
    NULL::decimal(5,4) AS prev_employee_deferral_rate,
    current_age AS employee_age,
    current_tenure AS employee_tenure,
    level_id,
    age_band,
    tenure_band,
    termination_rate AS event_probability,
    'new_hire_termination' AS event_category
  FROM {{ ref('int_new_hire_termination_events') }}
  {%- if simulation_year %}
  WHERE simulation_year = {{ simulation_year }}
  {%- endif %}
),

promotion_events AS (
  SELECT
    employee_id,
    employee_ssn,
    event_type,
    simulation_year,
    effective_date,
    'Level ' || from_level || ' -> ' || to_level AS event_details,
    new_salary AS compensation_amount,
    previous_salary AS previous_compensation,
    NULL::decimal(5,4) AS employee_deferral_rate,
    NULL::decimal(5,4) AS prev_employee_deferral_rate,
    current_age AS employee_age,
    current_tenure AS employee_tenure,
    to_level AS level_id,
    age_band,
    tenure_band,
    promotion_rate AS event_probability,
    'promotion' AS event_category
  FROM {{ ref('int_promotion_events') }}
  {%- if simulation_year %}
  WHERE simulation_year = {{ simulation_year }}
  {%- endif %}
),

hiring_events AS (
  SELECT
    employee_id,
    employee_ssn,
    event_type,
    simulation_year,
    effective_date,
    'New hire - Level ' || level_id AS event_details,
    compensation_amount,
    NULL AS previous_compensation,
    NULL::decimal(5,4) AS employee_deferral_rate,
    NULL::decimal(5,4) AS prev_employee_deferral_rate,
    employee_age,
    0 AS employee_tenure, -- New hires have 0 tenure
    level_id,
    -- Calculate age/tenure bands for new hires
    CASE
      WHEN employee_age < 25 THEN '< 25'
      WHEN employee_age < 35 THEN '25-34'
      WHEN employee_age < 45 THEN '35-44'
      WHEN employee_age < 55 THEN '45-54'
      WHEN employee_age < 65 THEN '55-64'
      ELSE '65+'
    END AS age_band,
    '< 2' AS tenure_band, -- All new hires start in lowest tenure band
    NULL AS event_probability, -- Hiring is deterministic based on departures
    'hiring' AS event_category
  FROM {{ ref('int_hiring_events') }}
  {%- if simulation_year %}
  WHERE simulation_year = {{ simulation_year }}
  {%- endif %}
),

merit_events AS (
  SELECT
    employee_id,
    employee_ssn,
    event_type,
    simulation_year,
    effective_date,
    'Merit: ' || ROUND(merit_percentage * 100, 1) || '% + COLA: ' ||
    ROUND(cola_percentage * 100, 1) || '%' AS event_details,
    new_salary AS compensation_amount,
    previous_salary AS previous_compensation,
    NULL::decimal(5,4) AS employee_deferral_rate,
    NULL::decimal(5,4) AS prev_employee_deferral_rate,
    current_age AS employee_age,
    current_tenure AS employee_tenure,
    level_id,
    age_band,
    tenure_band,
    merit_percentage AS event_probability,
    'RAISE' AS event_category
  FROM {{ ref('int_merit_events') }}
  {%- if simulation_year %}
  WHERE simulation_year = {{ simulation_year }}
  {%- endif %}
),

-- E023 Enrollment Events: Auto-enrollment, proactive enrollment, and opt-outs
enrollment_events AS (
  SELECT
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
    employee_tenure,
    level_id,
    age_band,
    tenure_band,
    event_probability,
    event_category
  FROM {{ ref('int_enrollment_events') }}
  {%- if simulation_year %}
  WHERE simulation_year = {{ simulation_year }}
  {%- endif %}
),

-- For full refresh, create empty eligibility events CTE (will be regenerated by orchestrator)
existing_eligibility_events AS (
  SELECT
    CAST(NULL AS VARCHAR) AS employee_id,
    CAST(NULL AS VARCHAR) AS employee_ssn,
    CAST(NULL AS VARCHAR) AS event_type,
    CAST(NULL AS INTEGER) AS simulation_year,
    CAST(NULL AS DATE) AS effective_date,
    CAST(NULL AS VARCHAR) AS event_details,
    CAST(NULL AS DECIMAL(18,2)) AS compensation_amount,
    CAST(NULL AS DECIMAL(18,2)) AS previous_compensation,
    CAST(NULL AS DECIMAL(5,4)) AS employee_deferral_rate,
    CAST(NULL AS DECIMAL(5,4)) AS prev_employee_deferral_rate,
    CAST(NULL AS INTEGER) AS employee_age,
    CAST(NULL AS DECIMAL(10,2)) AS employee_tenure,
    CAST(NULL AS INTEGER) AS level_id,
    CAST(NULL AS VARCHAR) AS age_band,
    CAST(NULL AS VARCHAR) AS tenure_band,
    CAST(NULL AS DECIMAL(10,4)) AS event_probability,
    CAST(NULL AS VARCHAR) AS event_category
  WHERE FALSE
),

-- Use the same logic for preserved eligibility events
preserved_eligibility_events AS (
  SELECT * FROM existing_eligibility_events
),

-- Union all event types with consistent schema
all_events AS (
  SELECT
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
    employee_tenure,
    level_id,
    age_band,
    tenure_band,
    event_probability,
    event_category
  FROM termination_events

  UNION ALL

  SELECT
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
    employee_tenure,
    level_id,
    age_band,
    tenure_band,
    event_probability,
    event_category
  FROM new_hire_termination_events

  UNION ALL

  SELECT
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
    employee_tenure,
    level_id,
    age_band,
    tenure_band,
    event_probability,
    event_category
  FROM promotion_events

  UNION ALL

  SELECT
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
    employee_tenure,
    level_id,
    age_band,
    tenure_band,
    event_probability,
    event_category
  FROM hiring_events

  UNION ALL

  SELECT
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
    employee_tenure,
    level_id,
    age_band,
    tenure_band,
    event_probability,
    event_category
  FROM merit_events

  UNION ALL

  SELECT
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
    employee_tenure,
    level_id,
    age_band,
    tenure_band,
    event_probability,
    event_category
  FROM enrollment_events

  UNION ALL

  SELECT
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
    employee_tenure,
    level_id,
    age_band,
    tenure_band,
    event_probability,
    event_category
  FROM preserved_eligibility_events
)

-- Final selection with event sequencing for conflict resolution
SELECT
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
  employee_tenure,
  level_id,
  age_band,
  tenure_band,
  event_probability,
  event_category,
  -- Add event sequencing for conflict resolution
  -- Priority: termination(1) > hire(2) > eligibility(3) > enrollment(4) > enrollment_change(5) > promotion(6) > merit_increase(7)
  ROW_NUMBER() OVER (
    PARTITION BY employee_id, simulation_year
    ORDER BY
      CASE event_type
        WHEN 'termination' THEN 1
        WHEN 'hire' THEN 2
        WHEN 'eligibility' THEN 3
        WHEN 'enrollment' THEN 4
        WHEN 'enrollment_change' THEN 5
        WHEN 'promotion' THEN 6
        WHEN 'RAISE' THEN 7
        ELSE 8
      END,
      effective_date
  ) AS event_sequence,
  -- Add metadata for audit trail
  CURRENT_TIMESTAMP AS created_at,
  -- Add parameter tracking for dynamic compensation system
  '{{ var("scenario_id", "default") }}' AS parameter_scenario_id,
  'dynamic' AS parameter_source,
  -- Add data validation flags
  CASE
    WHEN employee_id IS NULL THEN 'INVALID_EMPLOYEE_ID'
    WHEN simulation_year IS NULL THEN 'INVALID_SIMULATION_YEAR'
    WHEN effective_date IS NULL THEN 'INVALID_EFFECTIVE_DATE'
    WHEN compensation_amount IS NULL AND event_type != 'termination' THEN 'INVALID_COMPENSATION'
    ELSE 'VALID'
  END AS data_quality_flag
FROM all_events
{%- if simulation_year %}
WHERE simulation_year = {{ simulation_year }}
{%- endif %}
ORDER BY employee_id, effective_date, event_sequence
