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

-- E077: Single-Rounding Algebraic Solver (ADR E077-A)
-- Strategic rounding: ROUND (target), FLOOR (exp terms), CEILING (hires), residual (implied NH terms)
exact_math AS (
  SELECT
    sc.target_growth_rate,
    sc.experienced_termination_rate,
    sc.new_hire_termination_rate,
    cw.total_active_workforce AS n_start,
    cw.experienced_workforce,
    cw.current_year_hires AS prior_year_new_hires,
    cw.avg_compensation,
    -- Exact algebra (no rounding until strategic points)
    CAST(cw.total_active_workforce * (1 + sc.target_growth_rate) AS DOUBLE) AS target_ending_exact,
    -- Expected terminations from truly experienced employees (12% rate)
    CAST(cw.experienced_workforce * sc.experienced_termination_rate AS DOUBLE) AS exp_terms_from_experienced,
    -- Expected terminations from prior year's new hires (25% rate - still elevated risk)
    CAST(cw.current_year_hires * sc.new_hire_termination_rate AS DOUBLE) AS exp_terms_from_prior_new_hires,
    -- Total expected experienced terminations (combines both cohorts)
    CAST((cw.experienced_workforce * sc.experienced_termination_rate +
          cw.current_year_hires * sc.new_hire_termination_rate) AS DOUBLE) AS exp_terms_exact
  FROM current_workforce cw
  CROSS JOIN simulation_config sc
),
strategic_rounding AS (
  SELECT
    *,
    -- Step 1: Target ending (banker's rounding)
    CAST(ROUND(target_ending_exact) AS INTEGER) AS target_ending_workforce,
    -- Step 2: Experienced terminations (FLOOR for conservative)
    CAST(FLOOR(exp_terms_exact) AS INTEGER) AS expected_experienced_terminations,
    -- Step 3: Survivors
    n_start - CAST(FLOOR(exp_terms_exact) AS INTEGER) AS survivors,
    -- Step 4: Net new hires needed
    CAST(ROUND(target_ending_exact) AS INTEGER) - (n_start - CAST(FLOOR(exp_terms_exact) AS INTEGER)) AS net_from_hires
  FROM exact_math
),
feasibility_checks AS (
  SELECT
    *,
    -- Guard 1: NH term rate feasibility
    CASE WHEN (1 - new_hire_termination_rate) <= 0.01
      THEN 'FAIL_NH_TERM_RATE'
      ELSE 'PASS'
    END AS nh_term_rate_check,
    -- Guard 2: Growth rate bounds
    CASE WHEN ABS(target_growth_rate) > 1.0
      THEN 'FAIL_GROWTH_BOUNDS'
      ELSE 'PASS'
    END AS growth_bounds_check
  FROM strategic_rounding
),
hire_calculation AS (
  SELECT
    *,
    -- RIF branch (negative/zero growth)
    CASE
      WHEN net_from_hires <= 0 THEN 0
      ELSE CAST(CEILING(CAST(net_from_hires AS DOUBLE) / (1 - new_hire_termination_rate)) AS INTEGER)
    END AS total_hires_needed,
    -- RIF additional terminations
    CASE
      WHEN net_from_hires <= 0 THEN ABS(net_from_hires)
      ELSE 0
    END AS additional_rif_terms
  FROM feasibility_checks
),
implied_nh_terms_calculation AS (
  SELECT
    *,
    -- Step 5: Implied NH terms (residual to force exact balance)
    CASE
      WHEN net_from_hires <= 0 THEN 0  -- No NH terms in RIF
      ELSE total_hires_needed - net_from_hires
    END AS implied_new_hire_terminations,
    -- Total exp terms (includes RIF)
    expected_experienced_terminations + additional_rif_terms AS total_exp_terms
  FROM hire_calculation
),
final_validation AS (
  SELECT
    *,
    -- Guard 3: Hire ratio feasibility (default 50%)
    CASE
      WHEN total_hires_needed > n_start * 0.50
      THEN 'FAIL_HIRE_RATIO'
      ELSE 'PASS'
    END AS hire_ratio_check,
    -- Guard 4: Implied NH terms validity
    CASE
      WHEN implied_new_hire_terminations < 0 OR implied_new_hire_terminations > total_hires_needed
      THEN 'FAIL_IMPLIED_NH_TERMS'
      ELSE 'PASS'
    END AS implied_nh_terms_check,
    -- Step 6: Validate exact balance
    n_start + total_hires_needed - total_exp_terms - implied_new_hire_terminations AS calculated_ending,
    (n_start + total_hires_needed - total_exp_terms - implied_new_hire_terminations) - target_ending_workforce AS reconciliation_error
  FROM implied_nh_terms_calculation
),
-- Reformat for downstream compatibility
growth_targets AS (
  SELECT
    target_growth_rate,
    n_start AS total_active_workforce,
    net_from_hires AS target_growth_amount_decimal,
    net_from_hires AS target_net_growth,
    target_ending_workforce
  FROM final_validation
),
termination_forecasts AS (
  SELECT
    experienced_termination_rate,
    n_start AS experienced_workforce,
    total_exp_terms AS expected_experienced_terminations,
    total_exp_terms * avg_compensation AS expected_termination_compensation_cost
  FROM final_validation
),
hiring_requirements AS (
  SELECT
    net_from_hires AS target_net_growth,
    total_exp_terms AS expected_experienced_terminations,
    new_hire_termination_rate,
    total_hires_needed,
    implied_new_hire_terminations AS expected_new_hire_terminations
  FROM final_validation
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

-- E077: Workforce balance validation (exact reconciliation required)
workforce_balance AS (
  SELECT
    hr.total_hires_needed,
    hr.expected_new_hire_terminations,
    tf.expected_experienced_terminations,
    hr.total_hires_needed - tf.expected_experienced_terminations - hr.expected_new_hire_terminations AS calculated_net_change,
    gt.target_net_growth,
    -- E077: Reconciliation error (MUST be 0)
    fv.reconciliation_error AS growth_variance,
    CASE
      WHEN fv.reconciliation_error = 0 THEN 'EXACT_MATCH'
      WHEN ABS(fv.reconciliation_error) <= 1 THEN 'MINOR_VARIANCE'
      WHEN ABS(fv.reconciliation_error) <= 3 THEN 'MODERATE_VARIANCE'
      ELSE 'SIGNIFICANT_VARIANCE'
    END AS balance_status,
    -- E077: Feasibility guard results
    fv.nh_term_rate_check,
    fv.growth_bounds_check,
    fv.hire_ratio_check,
    fv.implied_nh_terms_check
  FROM hiring_requirements hr
  CROSS JOIN termination_forecasts tf
  CROSS JOIN growth_targets gt
  CROSS JOIN final_validation fv
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

  -- Workforce balance validation (E077)
  wb.calculated_net_change,
  wb.growth_variance,
  wb.balance_status,

  -- E077: Feasibility guard results
  wb.nh_term_rate_check,
  wb.growth_bounds_check,
  wb.hire_ratio_check,
  wb.implied_nh_terms_check,

  -- Calculated rates
  ROUND(hr.total_hires_needed::DECIMAL / NULLIF(cw.total_active_workforce, 0), 4) AS hiring_rate,
  ROUND((tf.expected_experienced_terminations + hr.expected_new_hire_terminations)::DECIMAL / NULLIF(cw.total_active_workforce, 0), 4) AS total_turnover_rate,
  ROUND(wb.calculated_net_change::DECIMAL / NULLIF(cw.total_active_workforce, 0), 4) AS actual_growth_rate,

  -- Audit metadata
  'workforce_planning_engine_e077' AS created_by,
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
