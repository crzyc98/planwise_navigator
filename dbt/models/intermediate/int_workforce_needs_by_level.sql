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
    CAST(AVG(employee_compensation) AS DOUBLE) AS avg_compensation,
    CAST(SUM(employee_compensation) AS DOUBLE) AS total_compensation,
    CAST(MIN(employee_compensation) AS DOUBLE) AS min_compensation,
    CAST(MAX(employee_compensation) AS DOUBLE) AS max_compensation,
    CAST(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY employee_compensation) AS DOUBLE) AS median_compensation,
    CAST(STDDEV(employee_compensation) AS DOUBLE) AS compensation_std_dev
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
    CAST(wbl.experienced_headcount * wns.experienced_termination_rate AS DOUBLE) AS expected_terminations_decimal,
    CAST(ROUND(wbl.experienced_headcount * wns.experienced_termination_rate) AS INTEGER) AS expected_terminations,
    CAST(ROUND(wbl.experienced_headcount * wns.experienced_termination_rate) * wbl.avg_compensation AS DOUBLE) AS termination_compensation_cost
  FROM workforce_by_level wbl
  CROSS JOIN workforce_needs_summary wns
),

-- Hiring distribution by level
hiring_by_level AS (
  -- Allocate hires using deterministic largest-remainder logic with exact total reconciliation
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
  level_stats AS (
    SELECT
      SUM(raw_weight) AS total_weight,
      COUNT(*) AS level_count
    FROM level_weights
  ),
  shares AS (
    SELECT
      lw.level_id,
      CASE
        WHEN ls.total_weight > 0 THEN lw.raw_weight / ls.total_weight
        WHEN ls.level_count > 0 THEN 1.0 / ls.level_count
        ELSE 0.0
      END AS share
    FROM level_weights lw
    CROSS JOIN level_stats ls
  ),
  share_bounds AS (
    SELECT
      level_id,
      share,
      SUM(share) OVER (ORDER BY level_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS upper_bound
    FROM shares
  ),
  share_boundaries AS (
    SELECT
      level_id,
      share,
      upper_bound,
      LAG(upper_bound, 1, 0.0) OVER (ORDER BY level_id) AS lower_bound
    FROM share_bounds
  ),
  total_requirements AS (
    SELECT
      CAST(COALESCE(MAX(wns.total_hires_needed), 0) AS BIGINT) AS total_hires_needed,
      COALESCE(MAX(wns.new_hire_termination_rate), 0.0) AS new_hire_termination_rate
    FROM workforce_needs_summary wns
  ),
  hire_slots AS (
    SELECT
      slots.slot_number,
      (CAST(slots.slot_number AS DOUBLE) - 0.5) / NULLIF(tr.total_hires_needed, 0) AS slot_position
    FROM total_requirements tr
    CROSS JOIN LATERAL (
      SELECT seq AS slot_number
      FROM UNNEST(range(1, tr.total_hires_needed + 1)) AS r(seq)
    ) slots
  ),
  allocated AS (
    SELECT
      sb.level_id,
      COUNT(*) AS hires_needed
    FROM hire_slots hs
    JOIN share_boundaries sb
      ON hs.slot_position > sb.lower_bound
     AND hs.slot_position <= sb.upper_bound
    GROUP BY sb.level_id
  )
  SELECT
    sb.level_id,
    sb.share AS hiring_distribution,
    CAST(COALESCE(a.hires_needed, 0) AS INTEGER) AS hires_needed,
    -- New hire terminations by level
    ROUND(COALESCE(a.hires_needed, 0) * tr.new_hire_termination_rate) AS expected_new_hire_terminations
  FROM share_boundaries sb
  CROSS JOIN total_requirements tr
  LEFT JOIN allocated a ON sb.level_id = a.level_id
),

-- Compensation ranges and new hire costs
compensation_planning AS (
  SELECT
    cr.level_id,
    CAST(cr.min_compensation AS DOUBLE) AS min_compensation,
    CAST(cr.max_compensation AS DOUBLE) AS max_compensation,
    wbl.avg_compensation AS current_avg_compensation,
    -- New hire compensation using configurable percentiles (Epic E056)
    -- Calculate percentile-based compensation with market adjustments
    CAST((cr.min_compensation +
     (cr.max_compensation - cr.min_compensation) *
     COALESCE({{ resolve_parameter('cr.level_id', 'HIRE', 'compensation_percentile', simulation_year) }}, 0.50) *
     COALESCE({{ resolve_parameter('cr.level_id', 'HIRE', 'market_adjustment_multiplier', simulation_year) }}, 1.0)
    ) AS DOUBLE) AS new_hire_avg_compensation,
    -- Merit increase planning - use variable-based parameters for consistency
    CAST(wbl.total_compensation * {{ var('merit_budget', 0.03) }} AS DOUBLE) AS merit_increase_cost,
    -- COLA planning - use variable-based parameters for consistency
    CAST(wbl.total_compensation * {{ var('cola_rate', 0.025) }} AS DOUBLE) AS cola_cost,
    -- Promotion cost estimate - use safe defaults temporarily
    CAST(wbl.current_headcount * 0.05 AS DOUBLE) AS expected_promotions,
    CAST(wbl.avg_compensation * 0.12 * (wbl.current_headcount * 0.05) AS DOUBLE) AS promotion_cost
  FROM {{ ref('stg_config_job_levels') }} cr
  LEFT JOIN workforce_by_level wbl ON cr.level_id = wbl.level_id
),

-- Additional costs (hiring, training, severance)
additional_costs AS (
  SELECT
    hbl.level_id,
    -- Hiring costs (recruiting, onboarding)
    CAST(hbl.hires_needed * cp.new_hire_avg_compensation * 0.20 AS DOUBLE) AS recruiting_costs,
    -- Training and ramp-up costs
    CAST(hbl.hires_needed * cp.new_hire_avg_compensation * 0.25 AS DOUBLE) AS training_costs,
    -- Severance costs (2 weeks per year, avg 5 years tenure)
    CAST(tbl.expected_terminations * wbl.avg_compensation * (5.0 * 2.0 / 52.0) AS DOUBLE) AS severance_costs,
    -- Benefits continuation and outplacement
    CAST(tbl.expected_terminations * wbl.avg_compensation * 0.15 AS DOUBLE) AS additional_termination_costs
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
  (CAST(hbl.hires_needed AS DOUBLE) * cp.new_hire_avg_compensation) AS total_new_hire_compensation,
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
  (CAST(hbl.hires_needed AS DOUBLE) * cp.new_hire_avg_compensation + ac.recruiting_costs + ac.training_costs) AS total_hiring_costs,
  (tbl.termination_compensation_cost + ac.severance_costs + ac.additional_termination_costs) AS total_termination_costs,
  (cp.merit_increase_cost + cp.cola_cost + cp.promotion_cost) AS total_compensation_change_costs,

  -- Net financial impact
  ((CAST(hbl.hires_needed AS DOUBLE) * cp.new_hire_avg_compensation + cp.merit_increase_cost + cp.cola_cost + cp.promotion_cost) -
  tbl.termination_compensation_cost) AS net_compensation_change,

  -- Total budget impact
  (CAST(hbl.hires_needed AS DOUBLE) * cp.new_hire_avg_compensation + ac.recruiting_costs + ac.training_costs +
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
