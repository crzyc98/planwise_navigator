{{ config(
    materialized='table',
    tags=['FOUNDATION']
) }}

{% set comp_levers = 'stg_comp_levers' %}
{% set merit_base_param = 'merit_base' %}
{% set cola_rate_param = 'cola_rate' %}
{% set merit_budget_var = 'merit_budget' %}
{% set has_overrides = var(cola_rate_param, none) is not none or var(merit_budget_var, none) is not none %}

-- Parameter resolution model that determines effective parameters per scenario, year, level, and event type

WITH scenario_selection AS (
  SELECT '{{ var("scenario_id", "default") }}' AS selected_scenario_id
),

parameter_hierarchy AS (
  -- PRIORITY 1: Configuration overrides via dbt variables (highest priority)
  {% if has_overrides %}
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
    -- cola_rate: flat override (uniform across levels, same value for all)
    {% set has_cola = var(cola_rate_param, none) is not none %}
    {% set has_merit = var(merit_budget_var, none) is not none %}
    {% if has_cola %}
    SELECT DISTINCT
      fiscal_year,
      job_level,
      {{ EVT_RAISE() }} AS event_type,
      '{{ cola_rate_param }}' AS parameter_name,
      CAST({{ var(cola_rate_param) }} AS DOUBLE) AS parameter_value
    FROM {{ ref(comp_levers) }}
    {% endif %}

    -- merit_budget: proportional scaling — preserves level differentials, shifts the average
    -- e.g. seed avg=4.5%, budget=4.92% → scale factor=1.093, L1=3.8%, L2=4.4%, L3=4.9%...
    {% if has_merit %}
    {% if has_cola %}UNION ALL{% endif %}
    SELECT
      cl.fiscal_year,
      cl.job_level,
      {{ EVT_RAISE() }} AS event_type,
      '{{ merit_base_param }}' AS parameter_name,
      cl.parameter_value * (CAST({{ var(merit_budget_var) }} AS DOUBLE) / NULLIF(yr_avg.avg_value, 0)) AS parameter_value
    FROM {{ ref(comp_levers) }} cl
    JOIN (
      SELECT fiscal_year, AVG(parameter_value) AS avg_value
      FROM {{ ref(comp_levers) }}
      WHERE parameter_name = '{{ merit_base_param }}'
        AND scenario_id = {{ default_scenario() }}
      GROUP BY fiscal_year
    ) yr_avg ON cl.fiscal_year = yr_avg.fiscal_year
    WHERE cl.parameter_name = '{{ merit_base_param }}'
      AND cl.scenario_id = {{ default_scenario() }}
    {% endif %}
  ) overrides
  CROSS JOIN scenario_selection ss

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
    {% if has_overrides %}2{% else %}1{% endif %} AS priority_rank
  FROM {{ ref(comp_levers) }} cl
  CROSS JOIN scenario_selection ss
  WHERE cl.scenario_id = ss.selected_scenario_id

  UNION ALL

  -- PRIORITY 3: Get default parameters as fallback
  SELECT
    {{ default_scenario() }} AS scenario_id,
    cl.fiscal_year,
    cl.job_level,
    cl.event_type,
    cl.parameter_name,
    cl.parameter_value,
    cl.is_locked,
    {{ default_scenario() }} AS parameter_source,
    {% if has_overrides %}3{% else %}2{% endif %} AS priority_rank
  FROM {{ ref(comp_levers) }} cl
  WHERE cl.scenario_id = {{ default_scenario() }}
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
