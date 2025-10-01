{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['simulation_year', 'scenario_id', 'level_id'],
    on_schema_change='sync_all_columns',
    indexes=[
        {'columns': ['simulation_year', 'level_id'], 'type': 'btree'},
        {'columns': ['scenario_id', 'simulation_year', 'level_id'], 'type': 'btree'}
    ],
    tags=['workforce_planning', 'cost_modeling', 'level_detail']
) }}

-- Detailed workforce needs by level with comprehensive cost modeling
-- Provides granular visibility into hiring, termination, and financial impact by job level

{% set simulation_year = var('simulation_year') %}
{% set scenario_id = var('scenario_id', 'default') %}

WITH workforce_needs_summary AS (
  SELECT *
  FROM {{ ref('int_workforce_needs') }}
  WHERE simulation_year = {{ simulation_year }}
    AND scenario_id = '{{ scenario_id }}'
),

-- Current workforce by level
workforce_by_level AS (
  SELECT
    level_id,
    COUNT(*) AS current_headcount,
    -- For first year, all employees are considered experienced
    COUNT(*) AS experienced_headcount,
    0 AS new_hire_headcount,
    AVG(employee_compensation) AS avg_compensation,
    SUM(employee_compensation) AS total_compensation,
    MIN(employee_compensation) AS min_compensation,
    MAX(employee_compensation) AS max_compensation,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY employee_compensation) AS median_compensation,
    STDDEV(employee_compensation) AS compensation_std_dev
  FROM {{ ref('int_employee_compensation_by_year') }}
  WHERE simulation_year = {{ simulation_year }}
    AND employment_status = 'active'
  GROUP BY level_id
),

-- Termination distribution by level (using hazard rates if available)
termination_by_level AS (
  SELECT
    wbl.level_id,
    wbl.experienced_headcount,
    -- Apply level-specific termination rates if available, otherwise use overall rate
    wbl.experienced_headcount * wns.experienced_termination_rate AS expected_terminations_decimal,
    ROUND(wbl.experienced_headcount * wns.experienced_termination_rate) AS expected_terminations,
    ROUND(wbl.experienced_headcount * wns.experienced_termination_rate) * wbl.avg_compensation AS termination_compensation_cost
  FROM workforce_by_level wbl
  CROSS JOIN workforce_needs_summary wns
),

-- Hiring distribution by level
hiring_by_level AS (
  -- Normalize target distribution across present levels and allocate hires using the largest remainder method
  WITH level_weights AS (
    SELECT
      level_id,
      CASE
        WHEN level_id = 1 THEN 0.40
        WHEN level_id = 2 THEN 0.30
        WHEN level_id = 3 THEN 0.20
        WHEN level_id = 4 THEN 0.08
        WHEN level_id = 5 THEN 0.02
        ELSE 0.0
      END AS raw_weight
    FROM (SELECT DISTINCT level_id FROM workforce_by_level)
  ),
  normalization AS (
    SELECT SUM(raw_weight) AS total_weight FROM level_weights
  ),
  shares AS (
    SELECT
      lw.level_id,
      CASE WHEN n.total_weight = 0 THEN 0.0 ELSE lw.raw_weight / n.total_weight END AS share
    FROM level_weights lw
    CROSS JOIN normalization n
  ),
  base_alloc AS (
    SELECT
      s.level_id,
      s.share,
      wns.total_hires_needed AS total_hires_needed,
      FLOOR(wns.total_hires_needed * s.share) AS base_hires,
      (wns.total_hires_needed * s.share) - FLOOR(wns.total_hires_needed * s.share) AS remainder
    FROM shares s
    CROSS JOIN workforce_needs_summary wns
  ),
  totals AS (
    SELECT
      SUM(base_hires) AS sum_base,
      MAX(total_hires_needed) AS total_hires_needed
    FROM base_alloc
  ),
  ranked AS (
    SELECT
      ba.*,
      ROW_NUMBER() OVER (ORDER BY remainder DESC, level_id) AS remainder_rank
    FROM base_alloc ba
  )
  SELECT
    r.level_id,
    r.share AS hiring_distribution,
    CAST(
      r.base_hires + CASE WHEN r.remainder_rank <= (t.total_hires_needed - t.sum_base) THEN 1 ELSE 0 END
      AS INTEGER
    ) AS hires_needed,
    -- New hire terminations by level
    ROUND(
      (r.base_hires + CASE WHEN r.remainder_rank <= (t.total_hires_needed - t.sum_base) THEN 1 ELSE 0 END) * wns.new_hire_termination_rate
    ) AS expected_new_hire_terminations
  FROM ranked r
  CROSS JOIN totals t
  CROSS JOIN workforce_needs_summary wns
),

-- Compensation ranges and new hire costs
compensation_planning AS (
  SELECT
    cr.level_id,
    cr.min_compensation,
    cr.max_compensation,
    wbl.avg_compensation AS current_avg_compensation,
    -- New hire compensation using configurable percentiles (Epic E056)
    -- Calculate percentile-based compensation with market adjustments
    (cr.min_compensation +
     (cr.max_compensation - cr.min_compensation) *
     COALESCE({{ resolve_parameter('cr.level_id', 'HIRE', 'compensation_percentile', simulation_year) }}, 0.50) *
     COALESCE({{ resolve_parameter('cr.level_id', 'HIRE', 'market_adjustment_multiplier', simulation_year) }}, 1.0)
    ) AS new_hire_avg_compensation,
    -- Merit increase planning - use variable-based parameters for consistency
    wbl.total_compensation * {{ var('merit_budget', 0.03) }} AS merit_increase_cost,
    -- COLA planning - use variable-based parameters for consistency
    wbl.total_compensation * {{ var('cola_rate', 0.025) }} AS cola_cost,
    -- Promotion cost estimate - use safe defaults temporarily
    wbl.current_headcount * 0.05 AS expected_promotions,
    wbl.avg_compensation * 0.12 * (wbl.current_headcount * 0.05) AS promotion_cost
  FROM {{ ref('stg_config_job_levels') }} cr
  LEFT JOIN workforce_by_level wbl ON cr.level_id = wbl.level_id
),

-- Additional costs (hiring, training, severance)
additional_costs AS (
  SELECT
    hbl.level_id,
    -- Hiring costs (recruiting, onboarding)
    hbl.hires_needed * cp.new_hire_avg_compensation * 0.20 AS recruiting_costs,
    -- Training and ramp-up costs
    hbl.hires_needed * cp.new_hire_avg_compensation * 0.25 AS training_costs,
    -- Severance costs (2 weeks per year, avg 5 years tenure)
    tbl.expected_terminations * wbl.avg_compensation * (5.0 * 2.0 / 52.0) AS severance_costs,
    -- Benefits continuation and outplacement
    tbl.expected_terminations * wbl.avg_compensation * 0.15 AS additional_termination_costs
  FROM hiring_by_level hbl
  JOIN compensation_planning cp ON hbl.level_id = cp.level_id
  JOIN termination_by_level tbl ON hbl.level_id = tbl.level_id
  JOIN workforce_by_level wbl ON hbl.level_id = wbl.level_id
)

-- Final detailed output by level
SELECT
  -- Identifiers
  wns.workforce_needs_id,
  wns.scenario_id,
  wns.simulation_year,
  wbl.level_id,

  -- Current state
  wbl.current_headcount,
  wbl.experienced_headcount,
  wbl.new_hire_headcount,
  wbl.avg_compensation,
  wbl.median_compensation,
  wbl.total_compensation,
  wbl.compensation_std_dev,

  -- Terminations
  tbl.expected_terminations,
  tbl.termination_compensation_cost,

  -- Hiring
  hbl.hiring_distribution,
  hbl.hires_needed,
  hbl.expected_new_hire_terminations,

  -- Net workforce change
  hbl.hires_needed - tbl.expected_terminations - hbl.expected_new_hire_terminations AS net_headcount_change,
  wbl.current_headcount + (hbl.hires_needed - tbl.expected_terminations - hbl.expected_new_hire_terminations) AS projected_ending_headcount,

  -- Compensation planning
  cp.new_hire_avg_compensation,
  hbl.hires_needed * cp.new_hire_avg_compensation AS total_new_hire_compensation,
  cp.merit_increase_cost,
  cp.cola_cost,
  cp.expected_promotions,
  cp.promotion_cost,

  -- Additional costs
  ac.recruiting_costs,
  ac.training_costs,
  ac.severance_costs,
  ac.additional_termination_costs,

  -- Total costs by category
  (hbl.hires_needed * cp.new_hire_avg_compensation + ac.recruiting_costs + ac.training_costs) AS total_hiring_costs,
  (tbl.termination_compensation_cost + ac.severance_costs + ac.additional_termination_costs) AS total_termination_costs,
  (cp.merit_increase_cost + cp.cola_cost + cp.promotion_cost) AS total_compensation_change_costs,

  -- Net financial impact
  (hbl.hires_needed * cp.new_hire_avg_compensation + cp.merit_increase_cost + cp.cola_cost + cp.promotion_cost) -
  tbl.termination_compensation_cost AS net_compensation_change,

  -- Total budget impact
  (hbl.hires_needed * cp.new_hire_avg_compensation + ac.recruiting_costs + ac.training_costs +
   cp.merit_increase_cost + cp.cola_cost + cp.promotion_cost +
   ac.severance_costs + ac.additional_termination_costs) AS total_budget_impact,

  -- Rates and ratios
  ROUND(hbl.hires_needed::DECIMAL / NULLIF(wbl.current_headcount, 0), 4) AS level_hiring_rate,
  ROUND(tbl.expected_terminations::DECIMAL / NULLIF(wbl.current_headcount, 0), 4) AS level_termination_rate,
  ROUND((hbl.hires_needed - tbl.expected_terminations - hbl.expected_new_hire_terminations)::DECIMAL / NULLIF(wbl.current_headcount, 0), 4) AS level_growth_rate,

  -- Audit metadata
  CURRENT_TIMESTAMP AS created_at,
  'workforce_planning_engine' AS created_by

FROM workforce_needs_summary wns
CROSS JOIN workforce_by_level wbl
LEFT JOIN termination_by_level tbl ON wbl.level_id = tbl.level_id
LEFT JOIN hiring_by_level hbl ON wbl.level_id = hbl.level_id
LEFT JOIN compensation_planning cp ON wbl.level_id = cp.level_id
LEFT JOIN additional_costs ac ON wbl.level_id = ac.level_id

{% if is_incremental() %}
WHERE wns.simulation_year = {{ var('simulation_year') }}
  AND wns.scenario_id = '{{ var('scenario_id', 'default') }}'
{% endif %}

ORDER BY wbl.level_id
