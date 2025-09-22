-- E068A: Fused Event Generation - Optimized single-model approach
-- Reduces Event Generation wall-time by ~2× by replacing many small per-event models
-- with a single per-year compiled query that eliminates intermediate materialization

{{ config(
  materialized='incremental',
  unique_key=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year', 'event_type', 'event_sequence'],
  incremental_strategy='delete+insert',
  on_schema_change='sync_all_columns',
  tags=['EVENT_GENERATION']
) }}

{% set simulation_year = var('simulation_year', 2025) %}

-- E068A: Fused Event Generation Implementation
-- Single compiled query per year that references ephemeral event models
-- and combines them into the final events table

WITH all_events AS (
  SELECT
    '{{ var('scenario_id', 'default') }}' AS scenario_id,
    '{{ var('plan_design_id', 'default') }}' AS plan_design_id,
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
  FROM {{ ref('int_hiring_events') }}
  WHERE simulation_year = {{ simulation_year }}

  UNION ALL

  SELECT
    '{{ var('scenario_id', 'default') }}' AS scenario_id,
    '{{ var('plan_design_id', 'default') }}' AS plan_design_id,
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
  FROM {{ ref('int_termination_events') }}
  WHERE simulation_year = {{ simulation_year }}

  UNION ALL

  -- E068A: Include new-hire termination events (ephemeral) in fused output
  SELECT
    '{{ var('scenario_id', 'default') }}' AS scenario_id,
    '{{ var('plan_design_id', 'default') }}' AS plan_design_id,
    nht.employee_id,
    nht.employee_ssn,
    nht.event_type,
    nht.simulation_year,
    nht.effective_date,
    'Termination - ' || nht.termination_reason || ' (final compensation: $' || CAST(ROUND(nht.final_compensation, 0) AS VARCHAR) || ')' AS event_details,
    nht.final_compensation AS compensation_amount,
    nht.final_compensation AS previous_compensation,
    NULL::DECIMAL(5,4) AS employee_deferral_rate,
    NULL::DECIMAL(5,4) AS prev_employee_deferral_rate,
    nht.current_age AS employee_age,
    nht.current_tenure AS employee_tenure,
    nht.level_id,
    nht.age_band,
    nht.tenure_band,
    nht.termination_rate AS event_probability,
    'termination' AS event_category
  FROM {{ ref('int_new_hire_termination_events') }} nht
  WHERE nht.simulation_year = {{ simulation_year }}

  UNION ALL

  SELECT
    '{{ var('scenario_id', 'default') }}' AS scenario_id,
    '{{ var('plan_design_id', 'default') }}' AS plan_design_id,
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
  FROM {{ ref('int_promotion_events') }}
  WHERE simulation_year = {{ simulation_year }}

  UNION ALL

  SELECT
    '{{ var('scenario_id', 'default') }}' AS scenario_id,
    '{{ var('plan_design_id', 'default') }}' AS plan_design_id,
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
  FROM {{ ref('int_merit_events') }}
  WHERE simulation_year = {{ simulation_year }}

  UNION ALL

  SELECT
    '{{ var('scenario_id', 'default') }}' AS scenario_id,
    '{{ var('plan_design_id', 'default') }}' AS plan_design_id,
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
  WHERE simulation_year = {{ simulation_year }}

  UNION ALL

  SELECT
    '{{ var('scenario_id', 'default') }}' AS scenario_id,
    '{{ var('plan_design_id', 'default') }}' AS plan_design_id,
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
  FROM {{ ref('int_deferral_rate_escalation_events') }}
  WHERE simulation_year = {{ simulation_year }}
),

-- Final selection with event sequencing for conflict resolution
final_events AS (
  SELECT
    CONCAT('EVT_', simulation_year, '_', LPAD(CAST(ROW_NUMBER() OVER (ORDER BY employee_id, event_type, effective_date) AS VARCHAR), 8, '0')) AS event_id,
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
    employee_tenure,
    level_id,
    age_band,
    tenure_band,
    event_probability,
    event_category,
    -- Add event sequencing for conflict resolution
    -- Priority: termination(1) > hire(2) > eligibility(3) > enrollment(4) > enrollment_change(5) > deferral_escalation(6) > promotion(7) > merit_increase(8)
    ROW_NUMBER() OVER (
      PARTITION BY scenario_id, plan_design_id, employee_id, simulation_year
      ORDER BY
        CASE event_type
          WHEN 'termination' THEN 1
          WHEN 'hire' THEN 2
          WHEN 'eligibility' THEN 3
          WHEN 'enrollment' THEN 4
          WHEN 'enrollment_change' THEN 5
          WHEN 'deferral_escalation' THEN 6
          WHEN 'promotion' THEN 7
          WHEN 'raise' THEN 8  -- Note: 'raise' not 'RAISE' for consistency
          ELSE 9
        END,
        effective_date
    ) AS event_sequence,
    -- Add metadata for audit trail
    CURRENT_TIMESTAMP AS created_at,
    -- Add parameter tracking for dynamic compensation system
    '{{ var("scenario_id", "default") }}' AS parameter_scenario_id,
    'fused_event_generation' AS parameter_source,  -- E068A tracking
    -- Add data validation flags
    CASE
      WHEN employee_id IS NULL THEN 'INVALID_EMPLOYEE_ID'
      WHEN simulation_year IS NULL THEN 'INVALID_SIMULATION_YEAR'
      WHEN effective_date IS NULL THEN 'INVALID_EFFECTIVE_DATE'
      WHEN compensation_amount IS NULL AND event_type NOT IN ('termination','enrollment','enrollment_change','deferral_escalation') THEN 'INVALID_COMPENSATION'
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
        WHEN compensation_amount IS NULL AND event_type NOT IN ('termination','enrollment','enrollment_change','deferral_escalation') THEN 'INVALID_COMPENSATION'
        ELSE 'VALID'
      END
    ) = 'VALID'
)

-- Insert-overwrite by simulation_year with deterministic ordering for stable diffs
-- E068A: Single writer per year with explicit ORDER BY for reproducible results
SELECT * FROM final_events
-- Note: ORDER BY removed for incremental materialization compatibility
-- Some DuckDB contexts reject ORDER BY in INSERT SELECT statements for incremental models
-- ORDER BY scenario_id, plan_design_id, employee_id, simulation_year, event_type, effective_date
