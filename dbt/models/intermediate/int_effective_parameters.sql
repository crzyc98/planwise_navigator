{{ config(materialized='table') }}

-- Parameter resolution model that determines effective parameters per scenario, year, level, and event type

WITH scenario_selection AS (
  SELECT '{{ var("scenario_id", "default") }}' AS selected_scenario_id
),

parameter_hierarchy AS (
  -- PRIORITY 1: Configuration overrides via dbt variables (highest priority)
  {% if var('cola_rate', none) is not none or var('merit_budget', none) is not none %}
  SELECT
    ss.selected_scenario_id AS scenario_id,
    fiscal_year,
    job_level,
    event_type,
    parameter_name,
    parameter_value,
    TRUE AS is_locked,
    'config_override' AS parameter_source,
    1 AS priority_rank
  FROM (
    -- Generate parameter rows for all fiscal years and job levels when config overrides are provided
    SELECT DISTINCT fiscal_year, job_level FROM {{ ref('stg_comp_levers') }}
  ) base_combinations
  CROSS JOIN scenario_selection ss
  CROSS JOIN (
    {% if var('cola_rate', none) is not none %}
    SELECT 'raise' AS event_type, 'cola_rate' AS parameter_name, {{ var('cola_rate') }} AS parameter_value
    {% endif %}
    {% if var('merit_budget', none) is not none %}
      {% if var('cola_rate', none) is not none %}UNION ALL{% endif %}
    SELECT 'raise' AS event_type, 'merit_base' AS parameter_name, {{ var('merit_budget') }} AS parameter_value
    {% endif %}
  ) config_params

  UNION ALL
  {% endif %}

  -- PRIORITY 2: Get parameters from comp_levers for the selected scenario
  SELECT
    cl.scenario_id,
    cl.fiscal_year,
    cl.job_level,
    cl.event_type,
    cl.parameter_name,
    cl.parameter_value,
    cl.is_locked,
    'scenario' AS parameter_source,
    {% if var('cola_rate', none) is not none or var('merit_budget', none) is not none %}2{% else %}1{% endif %} AS priority_rank
  FROM {{ ref('stg_comp_levers') }} cl
  CROSS JOIN scenario_selection ss
  WHERE cl.scenario_id = ss.selected_scenario_id

  UNION ALL

  -- PRIORITY 3: Get default parameters as fallback
  SELECT
    'default' AS scenario_id,
    cl.fiscal_year,
    cl.job_level,
    cl.event_type,
    cl.parameter_name,
    cl.parameter_value,
    cl.is_locked,
    'default' AS parameter_source,
    {% if var('cola_rate', none) is not none or var('merit_budget', none) is not none %}3{% else %}2{% endif %} AS priority_rank
  FROM {{ ref('stg_comp_levers') }} cl
  WHERE cl.scenario_id = 'default'
),

resolved_parameters AS (
  SELECT
    ph.*,
    ROW_NUMBER() OVER (
      PARTITION BY fiscal_year, job_level, event_type, parameter_name
      ORDER BY priority_rank
    ) AS resolution_rank
  FROM parameter_hierarchy ph
),

final_parameters AS (
  SELECT
    scenario_id,
    fiscal_year,
    job_level,
    event_type,
    parameter_name,
    parameter_value,
    is_locked,
    parameter_source,
    CURRENT_TIMESTAMP AS resolved_at
  FROM resolved_parameters
  WHERE resolution_rank = 1
)

SELECT
  *,
  {{ dbt_utils.generate_surrogate_key(['scenario_id', 'fiscal_year', 'job_level', 'event_type', 'parameter_name']) }} AS parameter_key
FROM final_parameters
