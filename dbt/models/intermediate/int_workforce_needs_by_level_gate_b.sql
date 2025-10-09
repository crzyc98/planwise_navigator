{{ config(
    materialized='table',
    tags=['FOUNDATION', 'validation', 'gate_b', 'E077']
) }}

-- Gate B: Level Allocation Reconciliation (Epic E077)
-- HARD STOP: Sum of level quotas must equal global totals exactly
-- Validates three quota types: hires, experienced terminations, new hire terminations

{% set simulation_year = var('simulation_year') %}
{% set scenario_id = var('scenario_id', 'default') %}

WITH base_level_needs AS (
  SELECT *
  FROM {{ ref('int_workforce_needs_by_level') }}
  WHERE simulation_year = {{ simulation_year }}
    AND scenario_id = '{{ scenario_id }}'
),
global_needs AS (
  SELECT
    simulation_year,
    scenario_id,
    total_hires_needed,
    expected_experienced_terminations,
    expected_new_hire_terminations
  FROM {{ ref('int_workforce_needs_gate_a') }}
  WHERE simulation_year = {{ simulation_year }}
    AND scenario_id = '{{ scenario_id }}'
),
level_totals AS (
  SELECT
    simulation_year,
    scenario_id,
    SUM(hires_needed) AS allocated_hires,
    SUM(expected_terminations) AS allocated_exp_terms,
    SUM(expected_new_hire_terminations) AS allocated_nh_terms
  FROM base_level_needs
  GROUP BY simulation_year, scenario_id
),
reconciliation AS (
  SELECT
    lt.simulation_year,
    lt.scenario_id,
    -- Hires reconciliation
    lt.allocated_hires,
    gn.total_hires_needed,
    lt.allocated_hires - gn.total_hires_needed AS hires_error,
    -- Experienced terminations reconciliation
    lt.allocated_exp_terms,
    gn.expected_experienced_terminations,
    lt.allocated_exp_terms - gn.expected_experienced_terminations AS exp_terms_error,
    -- New hire terminations reconciliation
    lt.allocated_nh_terms,
    gn.expected_new_hire_terminations,
    lt.allocated_nh_terms - gn.expected_new_hire_terminations AS nh_terms_error,
    -- Gate status
    CASE
      WHEN lt.allocated_hires != gn.total_hires_needed THEN 'FAIL_HIRES'
      WHEN lt.allocated_exp_terms != gn.expected_experienced_terminations THEN 'FAIL_EXP_TERMS'
      WHEN lt.allocated_nh_terms != gn.expected_new_hire_terminations THEN 'FAIL_NH_TERMS'
      ELSE 'PASS'
    END AS gate_b_status,
    -- Diagnostic message
    'Year ' || lt.simulation_year || ' Gate B: '
    || 'Hires (allocated: ' || lt.allocated_hires || ', target: ' || gn.total_hires_needed || ', error: ' || (lt.allocated_hires - gn.total_hires_needed) || '), '
    || 'Exp Terms (allocated: ' || lt.allocated_exp_terms || ', target: ' || gn.expected_experienced_terminations || ', error: ' || (lt.allocated_exp_terms - gn.expected_experienced_terminations) || '), '
    || 'NH Terms (allocated: ' || lt.allocated_nh_terms || ', target: ' || gn.expected_new_hire_terminations || ', error: ' || (lt.allocated_nh_terms - gn.expected_new_hire_terminations) || ')'
    AS gate_b_diagnostic
  FROM level_totals lt
  JOIN global_needs gn USING (simulation_year, scenario_id)
)
SELECT
  bln.*,
  r.gate_b_status,
  r.hires_error,
  r.exp_terms_error,
  r.nh_terms_error,
  r.gate_b_diagnostic
FROM base_level_needs bln
JOIN reconciliation r
  ON bln.simulation_year = r.simulation_year
  AND bln.scenario_id = r.scenario_id
-- HARD STOP: Only allow PASS through Gate B
-- Comment out next line to see diagnostic details for failing scenarios
WHERE r.gate_b_status = 'PASS'
