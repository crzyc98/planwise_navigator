{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['simulation_year', 'scenario_id'],
    on_schema_change='sync_all_columns',
    indexes=[
        {'columns': ['simulation_year', 'scenario_id'], 'type': 'btree'},
        {'columns': ['level_id'], 'type': 'btree'}
    ],
    tags=['FOUNDATION', 'workforce_planning', 'core_calculations']
) }}

-- Centralized workforce planning calculations
-- Single source of truth for hiring targets, termination expectations, and growth goals
-- Eliminates redundancy and provides transparency into workforce planning logic

{% set simulation_year = var('simulation_year') %}
{% set scenario_id = var('scenario_id', 'default') %}
{% set start_year = var('start_year', 2025) | int %}
{% set is_first_year = (simulation_year | int) == start_year %}

WITH simulation_config AS (
  SELECT
    {{ simulation_year }} AS simulation_year,
    '{{ scenario_id }}' AS scenario_id,
    {{ var('target_growth_rate', 0.03) }} AS target_growth_rate,
    {{ var('total_termination_rate', 0.12) }} AS experienced_termination_rate,
    {{ var('new_hire_termination_rate', 0.25) }} AS new_hire_termination_rate,
    CURRENT_TIMESTAMP AS calculation_timestamp,
    gen_random_uuid() AS workforce_needs_id
),

-- Current workforce baseline (switch source based on first year vs subsequent years)
current_workforce AS (
  {% if is_first_year %}
  -- Year 1: Use baseline workforce only (do NOT include staging new hires)
  SELECT
    COUNT(*) AS total_active_workforce,
    COUNT(*) AS experienced_workforce,
    0 AS current_year_hires,
    AVG(current_compensation) AS avg_compensation,
    SUM(current_compensation) AS total_compensation
  FROM {{ ref('int_baseline_workforce') }}
  WHERE simulation_year = {{ simulation_year }}
    AND employment_status = 'active'
  {% else %}
  -- Subsequent years: Use helper model to get previous year's ending workforce
  -- FIX: Read from int_prev_year_workforce_summary instead of int_employee_compensation_by_year
  -- to capture all surviving employees including new hires from prior year
  -- Helper model uses adapter.get_relation() to avoid circular dependency
  SELECT
    total_active_workforce,
    experienced_workforce,
    current_year_hires,
    avg_compensation,
    total_compensation
  FROM {{ ref('int_prev_year_workforce_summary') }}
  WHERE simulation_year = {{ simulation_year }}
  {% endif %}
),

-- Workforce by level for detailed planning
workforce_by_level AS (
  {% if is_first_year %}
  -- Year 1: Use baseline workforce
  SELECT
    level_id,
    COUNT(*) AS level_headcount,
    AVG(current_compensation) AS avg_level_compensation,
    SUM(current_compensation) AS total_level_compensation
  FROM {{ ref('int_baseline_workforce') }}
  WHERE simulation_year = {{ simulation_year }}
    AND employment_status = 'active'
  GROUP BY level_id
  {% else %}
  -- Subsequent years: Use helper model to get previous year's level-specific workforce
  -- FIX: Read from int_prev_year_workforce_by_level to capture all surviving employees
  -- Helper model uses adapter.get_relation() to avoid circular dependency
  SELECT
    level_id,
    level_headcount,
    avg_level_compensation,
    total_level_compensation
  FROM {{ ref('int_prev_year_workforce_by_level') }}
  WHERE simulation_year = {{ simulation_year }}
  {% endif %}
),

-- Growth target calculations
growth_targets AS (
  SELECT
    sc.target_growth_rate,
    cw.total_active_workforce,
    cw.total_active_workforce * sc.target_growth_rate AS target_growth_amount_decimal,
    ROUND(cw.total_active_workforce * sc.target_growth_rate) AS target_net_growth,
    ROUND(cw.total_active_workforce * (1 + sc.target_growth_rate)) AS target_ending_workforce
  FROM current_workforce cw
  CROSS JOIN simulation_config sc
),

-- Termination forecasts (experienced employees only)
termination_forecasts AS (
  SELECT
    sc.experienced_termination_rate,
    cw.experienced_workforce,
    ROUND(cw.experienced_workforce * sc.experienced_termination_rate) AS expected_experienced_terminations,
    cw.experienced_workforce * sc.experienced_termination_rate * cw.avg_compensation AS expected_termination_compensation_cost
  FROM current_workforce cw
  CROSS JOIN simulation_config sc
),

-- Hiring requirements calculation (accounting for new hire attrition)
hiring_requirements AS (
  SELECT
    gt.target_net_growth,
    tf.expected_experienced_terminations,
    sc.new_hire_termination_rate,
    -- Core hiring formula: total hires needed accounting for NH attrition
    ROUND(
      (gt.target_net_growth + tf.expected_experienced_terminations) /
      (1 - sc.new_hire_termination_rate)
    ) AS total_hires_needed,
    -- Identity-based NH attrition to avoid double rounding drift:
    -- hires - experienced_terms - nh_terms = target_net_growth ⇒
    -- nh_terms = hires - experienced_terms - target_net_growth
    GREATEST(
      ROUND(
        ROUND(
          (gt.target_net_growth + tf.expected_experienced_terminations) /
          (1 - sc.new_hire_termination_rate)
        )
        - tf.expected_experienced_terminations
        - gt.target_net_growth
      ),
      0
    ) AS expected_new_hire_terminations
  FROM growth_targets gt
  CROSS JOIN termination_forecasts tf
  CROSS JOIN simulation_config sc
),

-- Financial impact calculations
financial_impact AS (
  SELECT
    hr.total_hires_needed,
    cw.avg_compensation,
    -- New hire compensation (with market adjustment)
    cw.avg_compensation * COALESCE({{ get_parameter_value(1, 'hire', 'new_hire_salary_adjustment', simulation_year) }}, 1.0) AS avg_new_hire_compensation,
    -- Total compensation costs
    hr.total_hires_needed * cw.avg_compensation * COALESCE({{ get_parameter_value(1, 'hire', 'new_hire_salary_adjustment', simulation_year) }}, 1.0) AS total_new_hire_compensation_cost,
    tf.expected_termination_compensation_cost,
    -- Net compensation change
    (hr.total_hires_needed * cw.avg_compensation * COALESCE({{ get_parameter_value(1, 'hire', 'new_hire_salary_adjustment', simulation_year) }}, 1.0)) -
    tf.expected_termination_compensation_cost AS net_compensation_change_forecast
  FROM hiring_requirements hr
  CROSS JOIN current_workforce cw
  CROSS JOIN termination_forecasts tf
),

-- Workforce balance validation
workforce_balance AS (
  SELECT
    hr.total_hires_needed,
    hr.expected_new_hire_terminations,
    tf.expected_experienced_terminations,
    hr.total_hires_needed - tf.expected_experienced_terminations - hr.expected_new_hire_terminations AS calculated_net_change,
    gt.target_net_growth,
    ABS(
      (hr.total_hires_needed - tf.expected_experienced_terminations - hr.expected_new_hire_terminations) -
      gt.target_net_growth
    ) AS growth_variance,
    CASE
      WHEN ABS((hr.total_hires_needed - tf.expected_experienced_terminations - hr.expected_new_hire_terminations) - gt.target_net_growth) <= 1 THEN 'BALANCED'
      WHEN ABS((hr.total_hires_needed - tf.expected_experienced_terminations - hr.expected_new_hire_terminations) - gt.target_net_growth) <= 3 THEN 'MINOR_VARIANCE'
      ELSE 'SIGNIFICANT_VARIANCE'
    END AS balance_status
  FROM hiring_requirements hr
  CROSS JOIN termination_forecasts tf
  CROSS JOIN growth_targets gt
),

-- Hiring distribution by level
hiring_by_level AS (
  SELECT
    level_id,
    -- Use same distribution as int_hiring_events.sql
    CASE
      WHEN level_id = 1 THEN 0.40
      WHEN level_id = 2 THEN 0.30
      WHEN level_id = 3 THEN 0.20
      WHEN level_id = 4 THEN 0.08
      WHEN level_id = 5 THEN 0.02
      ELSE 0
    END AS hiring_distribution,
    CEIL(hr.total_hires_needed *
      CASE
        WHEN level_id = 1 THEN 0.40
        WHEN level_id = 2 THEN 0.30
        WHEN level_id = 3 THEN 0.20
        WHEN level_id = 4 THEN 0.08
        WHEN level_id = 5 THEN 0.02
        ELSE 0
      END
    ) AS level_hires_needed
  FROM (SELECT DISTINCT level_id FROM workforce_by_level) levels
  CROSS JOIN hiring_requirements hr
)

-- Final workforce needs output
SELECT
  -- Identifiers
  sc.workforce_needs_id,
  sc.scenario_id,
  sc.simulation_year,
  sc.calculation_timestamp,

  -- Current workforce state
  cw.total_active_workforce AS starting_workforce_count,
  cw.experienced_workforce AS starting_experienced_count,
  cw.current_year_hires AS starting_new_hire_count,
  cw.avg_compensation AS avg_current_compensation,
  cw.total_compensation AS total_current_compensation,

  -- Growth targets
  sc.target_growth_rate,
  gt.target_net_growth,
  gt.target_ending_workforce,

  -- Termination forecasts
  sc.experienced_termination_rate,
  tf.expected_experienced_terminations,
  sc.new_hire_termination_rate,
  hr.expected_new_hire_terminations,
  tf.expected_experienced_terminations + hr.expected_new_hire_terminations AS total_expected_terminations,

  -- Hiring requirements
  hr.total_hires_needed,

  -- Financial impact
  fi.avg_new_hire_compensation,
  fi.total_new_hire_compensation_cost,
  fi.expected_termination_compensation_cost,
  fi.net_compensation_change_forecast,

  -- Workforce balance validation
  wb.calculated_net_change,
  wb.growth_variance,
  wb.balance_status,

  -- Calculated rates
  ROUND(hr.total_hires_needed::DECIMAL / NULLIF(cw.total_active_workforce, 0), 4) AS hiring_rate,
  ROUND((tf.expected_experienced_terminations + hr.expected_new_hire_terminations)::DECIMAL / NULLIF(cw.total_active_workforce, 0), 4) AS total_turnover_rate,
  ROUND(wb.calculated_net_change::DECIMAL / NULLIF(cw.total_active_workforce, 0), 4) AS actual_growth_rate,

  -- Audit metadata
  'workforce_planning_engine' AS created_by,
  '{{ invocation_id }}' AS dbt_invocation_id

FROM simulation_config sc
CROSS JOIN current_workforce cw
CROSS JOIN growth_targets gt
CROSS JOIN termination_forecasts tf
CROSS JOIN hiring_requirements hr
CROSS JOIN financial_impact fi
CROSS JOIN workforce_balance wb

{% if is_incremental() %}
    WHERE sc.simulation_year = {{ var('simulation_year') }}
{% endif %}
