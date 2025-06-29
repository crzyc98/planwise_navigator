{{ config(materialized='table') }}

-- Parameter resolution model that determines effective parameters per scenario, year, level, and event type

WITH scenario_selection AS (
  SELECT '{{ var("scenario_id", "default") }}' AS selected_scenario_id
),

parameter_hierarchy AS (
  -- Get parameters from comp_levers for the selected scenario
  SELECT
    cl.scenario_id,
    cl.fiscal_year,
    cl.job_level,
    cl.event_type,
    cl.parameter_name,
    cl.parameter_value,
    cl.is_locked,
    'scenario' AS parameter_source,
    1 AS priority_rank
  FROM {{ ref('stg_comp_levers') }} cl
  CROSS JOIN scenario_selection ss
  WHERE cl.scenario_id = ss.selected_scenario_id

  UNION ALL

  -- Get default parameters as fallback
  SELECT
    'default' AS scenario_id,
    cl.fiscal_year,
    cl.job_level,
    cl.event_type,
    cl.parameter_name,
    cl.parameter_value,
    cl.is_locked,
    'default' AS parameter_source,
    2 AS priority_rank
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
