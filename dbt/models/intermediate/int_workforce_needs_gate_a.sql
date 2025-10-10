{{ config(
    materialized='table',
    tags=['FOUNDATION', 'validation', 'gate_a', 'E077']
) }}

-- Gate A: Workforce Needs Reconciliation (Epic E077)
-- HARD STOP: Growth equation must balance exactly (error = 0)
-- Validates that: start + hires - exp_terms - nh_terms = target_ending

{% set simulation_year = var('simulation_year') %}
{% set scenario_id = var('scenario_id', 'default') %}

WITH base_needs AS (
  SELECT *
  FROM {{ ref('int_workforce_needs') }}
  WHERE simulation_year = {{ simulation_year }}
    AND scenario_id = '{{ scenario_id }}'
),
validation AS (
  SELECT
    *,
    -- Calculate actual net change from workforce needs
    total_hires_needed - expected_experienced_terminations - expected_new_hire_terminations AS calculated_net_change,

    -- Target net change
    target_net_growth,

    -- Growth equation error (MUST BE ZERO)
    (total_hires_needed - expected_experienced_terminations - expected_new_hire_terminations) - target_net_growth AS growth_error,

    -- Alternative validation: ending workforce check
    starting_workforce_count + (total_hires_needed - expected_experienced_terminations - expected_new_hire_terminations) AS calculated_ending_workforce,
    target_ending_workforce,
    (starting_workforce_count + (total_hires_needed - expected_experienced_terminations - expected_new_hire_terminations)) - target_ending_workforce AS ending_workforce_error,

    -- Gate status
    CASE
      WHEN ABS((total_hires_needed - expected_experienced_terminations - expected_new_hire_terminations) - target_net_growth) = 0
           AND ABS((starting_workforce_count + (total_hires_needed - expected_experienced_terminations - expected_new_hire_terminations)) - target_ending_workforce) = 0
      THEN 'PASS'
      WHEN ABS((total_hires_needed - expected_experienced_terminations - expected_new_hire_terminations) - target_net_growth) <= 1
      THEN 'MINOR_VARIANCE'
      WHEN ABS((total_hires_needed - expected_experienced_terminations - expected_new_hire_terminations) - target_net_growth) <= 3
      THEN 'MODERATE_VARIANCE'
      ELSE 'FAIL'
    END AS gate_a_status,

    -- Diagnostic message
    'Year ' || simulation_year || ' Gate A: '
    || 'Target net growth: ' || target_net_growth || ', '
    || 'Calculated net change: ' || (total_hires_needed - expected_experienced_terminations - expected_new_hire_terminations) || ', '
    || 'Growth error: ' || ((total_hires_needed - expected_experienced_terminations - expected_new_hire_terminations) - target_net_growth) || ' employees. '
    || 'Formula: ' || starting_workforce_count || ' + ' || total_hires_needed || ' - ' || expected_experienced_terminations || ' - ' || expected_new_hire_terminations
    || ' = ' || (starting_workforce_count + total_hires_needed - expected_experienced_terminations - expected_new_hire_terminations)
    || ' (target: ' || target_ending_workforce || ')'
    AS gate_a_diagnostic
  FROM base_needs
)
SELECT * FROM validation
-- HARD STOP: Only allow PASS through Gate A
-- Comment out next line to see diagnostic details for failing scenarios
WHERE gate_a_status = 'PASS'
