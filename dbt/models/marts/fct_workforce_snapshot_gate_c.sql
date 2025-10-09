{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['simulation_year', 'scenario_id', 'employee_id'],
    tags=['marts', 'validation', 'gate_c', 'E077']
) }}

-- Gate C: Final Snapshot Reconciliation (Epic E077)
-- HARD STOP: Actual ending workforce must equal target exactly (error = 0)
-- Validates complete workforce balance after all events processed

{% set simulation_year = var('simulation_year') %}
{% set scenario_id = var('scenario_id', 'default') %}

WITH base_snapshot AS (
  SELECT *
  FROM {{ ref('fct_workforce_snapshot') }}
  WHERE simulation_year = {{ simulation_year }}
    AND scenario_id = '{{ scenario_id }}'
),
global_needs AS (
  SELECT
    simulation_year,
    scenario_id,
    starting_workforce_count,
    target_ending_workforce,
    target_net_growth,
    total_hires_needed,
    expected_experienced_terminations,
    expected_new_hire_terminations
  FROM {{ ref('int_workforce_needs_gate_a') }}
  WHERE simulation_year = {{ simulation_year }}
    AND scenario_id = '{{ scenario_id }}'
),
actual_counts AS (
  SELECT
    simulation_year,
    scenario_id,
    COUNT(*) FILTER (WHERE employment_status = 'active') AS actual_ending_workforce,
    COUNT(*) FILTER (WHERE detailed_status_code = 'continuous_active') AS actual_continuous_active,
    COUNT(*) FILTER (WHERE detailed_status_code = 'experienced_termination') AS actual_exp_terms,
    COUNT(*) FILTER (WHERE detailed_status_code = 'new_hire_active') AS actual_nh_active,
    COUNT(*) FILTER (WHERE detailed_status_code = 'new_hire_termination') AS actual_nh_terms,
    COUNT(*) AS total_snapshot_rows
  FROM base_snapshot
  GROUP BY simulation_year, scenario_id
),
validation AS (
  SELECT
    ac.simulation_year,
    ac.scenario_id,
    -- Actual vs expected ending workforce
    ac.actual_ending_workforce,
    gn.target_ending_workforce,
    ac.actual_ending_workforce - gn.target_ending_workforce AS ending_workforce_error,
    -- Cohort breakdowns
    ac.actual_continuous_active,
    gn.starting_workforce_count - gn.expected_experienced_terminations AS expected_continuous_active,
    ac.actual_continuous_active - (gn.starting_workforce_count - gn.expected_experienced_terminations) AS continuous_active_error,
    ac.actual_exp_terms,
    gn.expected_experienced_terminations,
    ac.actual_exp_terms - gn.expected_experienced_terminations AS exp_terms_error,
    ac.actual_nh_active,
    gn.total_hires_needed - gn.expected_new_hire_terminations AS expected_nh_active,
    ac.actual_nh_active - (gn.total_hires_needed - gn.expected_new_hire_terminations) AS nh_active_error,
    ac.actual_nh_terms,
    gn.expected_new_hire_terminations,
    ac.actual_nh_terms - gn.expected_new_hire_terminations AS nh_terms_error,
    -- Growth rates
    ROUND(100.0 * (ac.actual_ending_workforce - gn.starting_workforce_count) / NULLIF(gn.starting_workforce_count, 0), 2) AS actual_growth_pct,
    ROUND(100.0 * gn.target_net_growth / NULLIF(gn.starting_workforce_count, 0), 2) AS target_growth_pct,
    -- Gate status
    CASE
      WHEN ac.actual_ending_workforce = gn.target_ending_workforce THEN 'PASS'
      WHEN ABS(ac.actual_ending_workforce - gn.target_ending_workforce) <= 1 THEN 'MINOR_VARIANCE'
      WHEN ABS(ac.actual_ending_workforce - gn.target_ending_workforce) <= 5 THEN 'MODERATE_VARIANCE'
      WHEN ABS(ac.actual_ending_workforce - gn.target_ending_workforce) <= 10 THEN 'SEVERE_VARIANCE'
      ELSE 'FAIL'
    END AS gate_c_status,
    -- Diagnostic message
    'Year ' || ac.simulation_year || ' Gate C: '
    || 'Target ending: ' || gn.target_ending_workforce || ', '
    || 'Actual ending: ' || ac.actual_ending_workforce || ', '
    || 'Error: ' || (ac.actual_ending_workforce - gn.target_ending_workforce) || ' employees '
    || '(' || ROUND(100.0 * (ac.actual_ending_workforce - gn.target_ending_workforce) / NULLIF(gn.target_ending_workforce, 0), 2) || '%). '
    || 'Breakdown errors: '
    || 'Continuous=' || (ac.actual_continuous_active - (gn.starting_workforce_count - gn.expected_experienced_terminations)) || ', '
    || 'ExpTerms=' || (ac.actual_exp_terms - gn.expected_experienced_terminations) || ', '
    || 'NHActive=' || (ac.actual_nh_active - (gn.total_hires_needed - gn.expected_new_hire_terminations)) || ', '
    || 'NHTerms=' || (ac.actual_nh_terms - gn.expected_new_hire_terminations)
    AS gate_c_diagnostic
  FROM actual_counts ac
  JOIN global_needs gn USING (simulation_year, scenario_id)
)
SELECT
  bs.*,
  v.gate_c_status,
  v.ending_workforce_error,
  v.actual_growth_pct,
  v.target_growth_pct,
  v.gate_c_diagnostic
FROM base_snapshot bs
LEFT JOIN validation v
  ON bs.simulation_year = v.simulation_year
  AND bs.scenario_id = v.scenario_id
-- HARD STOP: Only allow PASS through Gate C
-- Comment out next line to see diagnostic details for failing scenarios
WHERE v.gate_c_status = 'PASS'

{% if is_incremental() %}
  AND bs.simulation_year = {{ var('simulation_year') }}
  AND bs.scenario_id = '{{ var('scenario_id', 'default') }}'
{% endif %}
