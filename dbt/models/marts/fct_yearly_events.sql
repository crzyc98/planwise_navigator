-- depends_on: {{ ref('int_deferral_rate_escalation_events') }}

{{ config(
  materialized='incremental',
  unique_key=['employee_id', 'simulation_year', 'event_sequence'],
  incremental_strategy='delete+insert',
  on_schema_change='sync_all_columns',
  pre_hook=[
    "{% if adapter.get_relation(database=this.database, schema=this.schema, identifier=this.identifier) %}DELETE FROM {{ this }} WHERE simulation_year = {{ var('simulation_year', 2025) }};{% endif %}"
  ]
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

WITH nh_termination_base AS (
  SELECT t.*, ROW_NUMBER() OVER (
      PARTITION BY employee_id, simulation_year
      ORDER BY effective_date DESC
  ) AS rn
  FROM {{ ref('int_new_hire_termination_events') }} t
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
  FROM nh_termination_base
  WHERE rn = 1
),

termination_base AS (
  SELECT t.*, ROW_NUMBER() OVER (
      PARTITION BY employee_id, simulation_year
      ORDER BY effective_date DESC
  ) AS rn
  FROM {{ ref('int_termination_events') }} t
  {%- if simulation_year %}
  WHERE simulation_year = {{ simulation_year }}
  {%- endif %}
),

termination_events AS (
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
  FROM termination_base tb
  WHERE tb.rn = 1
    AND tb.employee_id NOT IN (
      SELECT employee_id FROM new_hire_termination_events
    )
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
  FROM (
    SELECT h.*, ROW_NUMBER() OVER (
      PARTITION BY employee_id, simulation_year
      ORDER BY effective_date ASC
    ) AS rn
    FROM {{ ref('int_hiring_events') }} h
    {%- if simulation_year %}
    WHERE simulation_year = {{ simulation_year }}
    {%- endif %}
  )
  WHERE rn = 1
),

merit_events AS (
  SELECT
    employee_id,
    employee_ssn,
    event_type,
    simulation_year,
    effective_date,
    event_details,  -- Use the pre-built event_details from int_merit_events
    compensation_amount,
    previous_compensation,
    NULL::decimal(5,4) AS employee_deferral_rate,
    NULL::decimal(5,4) AS prev_employee_deferral_rate,
    employee_age,
    employee_tenure,
    level_id,
    age_band,
    tenure_band,
    event_probability,
    event_category
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

-- E025 Match Events: Removed to break circular dependency
-- Match events are now maintained in separate fct_employer_match_events table
-- This eliminates the circular dependency while preserving match event tracking
employer_match_events AS (
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
  WHERE FALSE  -- Empty result set - no match events in main yearly events
),

-- Epic E035: Deferral Rate Escalation Events
-- Use try-catch pattern to handle missing escalation events gracefully
deferral_escalation_events AS (
  SELECT
    e.employee_id,
    e.employee_ssn,
    'DEFERRAL_ESCALATION' AS event_type,
    e.simulation_year,
    e.effective_date,
    e.event_details,
    CAST(NULL AS DECIMAL(18,2)) AS compensation_amount,
    CAST(NULL AS DECIMAL(18,2)) AS previous_compensation,
    e.new_deferral_rate::DECIMAL(5,4) AS employee_deferral_rate,
    e.previous_deferral_rate::DECIMAL(5,4) AS prev_employee_deferral_rate,
    e.current_age AS employee_age,
    e.current_tenure AS employee_tenure,
    e.level_id,
    e.age_band,
    e.tenure_band,
    CAST(NULL AS DECIMAL(10,4)) AS event_probability,
    'deferral_escalation' AS event_category
  FROM {{ ref('int_deferral_rate_escalation_events') }} e
  {%- if simulation_year %}
  WHERE e.simulation_year = {{ simulation_year }}
  {%- endif %}
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
  FROM employer_match_events

  UNION ALL

  -- Deferral escalation events (Epic E035 - FIXED)
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
  FROM deferral_escalation_events

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
),

-- Final selection with event sequencing for conflict resolution
final_events AS (
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
  -- Priority: termination(1) > hire(2) > eligibility(3) > enrollment(4) > enrollment_change(5) > DEFERRAL_ESCALATION(6) > promotion(7) > merit_increase(8)
  ROW_NUMBER() OVER (
    PARTITION BY employee_id, simulation_year
    ORDER BY
      CASE event_type
        WHEN 'termination' THEN 1
        WHEN 'hire' THEN 2
        WHEN 'eligibility' THEN 3
        WHEN 'enrollment' THEN 4
        WHEN 'enrollment_change' THEN 5
        WHEN 'DEFERRAL_ESCALATION' THEN 6
        WHEN 'promotion' THEN 7
        WHEN 'RAISE' THEN 8
        ELSE 9
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
    WHEN compensation_amount IS NULL AND event_type NOT IN ('termination','enrollment','enrollment_change','DEFERRAL_ESCALATION') THEN 'INVALID_COMPENSATION'
    ELSE 'VALID'
  END AS data_quality_flag
FROM all_events
WHERE 1=1
{%- if simulation_year %}
  AND simulation_year = {{ simulation_year }}
{%- endif %}
  -- Exclude records with data quality issues
  AND (
    CASE
      WHEN employee_id IS NULL THEN 'INVALID_EMPLOYEE_ID'
      WHEN simulation_year IS NULL THEN 'INVALID_SIMULATION_YEAR'
      WHEN effective_date IS NULL THEN 'INVALID_EFFECTIVE_DATE'
      WHEN compensation_amount IS NULL AND event_type NOT IN ('termination','enrollment','enrollment_change','DEFERRAL_ESCALATION') THEN 'INVALID_COMPENSATION'
      ELSE 'VALID'
    END
  ) = 'VALID'
)

-- Insert-overwrite by simulation_year: only current year's rows are produced here.
-- dbt-duckdb will overwrite the target partition (simulation_year) and preserve others.
SELECT * FROM final_events
