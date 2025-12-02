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

-- Current workforce by level (from previous year's ending state)
workforce_by_level AS (
  SELECT
    level_id,
    -- Use FILTER to count only employees who existed at start of year (for planning purposes)
    -- This excludes employees who will be hired during the current year
    COUNT(*) FILTER (WHERE employee_hire_date < DATE '{{ simulation_year }}-01-01') AS current_headcount,
    -- Experienced: employees hired BEFORE the current year
    COUNT(*) FILTER (WHERE employee_hire_date < DATE '{{ simulation_year }}-01-01') AS experienced_headcount,
    -- New hire headcount: employees hired DURING the current year (should be 0 for planning)
    COUNT(*) FILTER (WHERE employee_hire_date >= DATE '{{ simulation_year }}-01-01') AS new_hire_headcount,
    -- Aggregate only over employees existing at start of year
    CAST(AVG(employee_compensation) FILTER (WHERE employee_hire_date < DATE '{{ simulation_year }}-01-01') AS DOUBLE) AS avg_compensation,
    CAST(SUM(employee_compensation) FILTER (WHERE employee_hire_date < DATE '{{ simulation_year }}-01-01') AS DOUBLE) AS total_compensation,
    CAST(MIN(employee_compensation) FILTER (WHERE employee_hire_date < DATE '{{ simulation_year }}-01-01') AS DOUBLE) AS min_compensation,
    CAST(MAX(employee_compensation) FILTER (WHERE employee_hire_date < DATE '{{ simulation_year }}-01-01') AS DOUBLE) AS max_compensation,
    CAST(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY employee_compensation) FILTER (WHERE employee_hire_date < DATE '{{ simulation_year }}-01-01') AS DOUBLE) AS median_compensation,
    CAST(STDDEV(employee_compensation) FILTER (WHERE employee_hire_date < DATE '{{ simulation_year }}-01-01') AS DOUBLE) AS compensation_std_dev
  FROM {{ ref('int_employee_compensation_by_year') }}
  WHERE simulation_year = {{ simulation_year }}
    AND employment_status = 'active'
  GROUP BY level_id
  -- Filter out levels that have no employees at start of year
  HAVING COUNT(*) FILTER (WHERE employee_hire_date < DATE '{{ simulation_year }}-01-01') > 0
),

-- E077: Experienced Termination Quotas by Level (ADR E077-B with edge cases)
termination_by_level AS (
  WITH level_populations AS (
    -- Get experienced employee counts by level (exclude empty levels)
    SELECT
      level_id,
      experienced_headcount,
      experienced_headcount * 1.0 / SUM(experienced_headcount) OVER () AS level_weight
    FROM workforce_by_level
    WHERE experienced_headcount > 0  -- Edge Case 2: Exclude empty levels
  ),
  fractional_allocation AS (
    SELECT
      lp.level_id,
      lp.experienced_headcount,
      lp.level_weight,
      wns.expected_experienced_terminations,
      wns.expected_experienced_terminations * lp.level_weight AS fractional_quota_uncapped,
      -- Edge Case 1: Cap quota at available population
      LEAST(
        wns.expected_experienced_terminations * lp.level_weight,
        lp.experienced_headcount
      ) AS fractional_quota,
      FLOOR(LEAST(
        wns.expected_experienced_terminations * lp.level_weight,
        lp.experienced_headcount
      )) AS floor_quota,
      (LEAST(
        wns.expected_experienced_terminations * lp.level_weight,
        lp.experienced_headcount
      )) - FLOOR(LEAST(
        wns.expected_experienced_terminations * lp.level_weight,
        lp.experienced_headcount
      )) AS fractional_remainder
    FROM level_populations lp
    CROSS JOIN workforce_needs_summary wns
  ),
  remainder_allocation AS (
    SELECT
      fa.level_id,
      fa.experienced_headcount,
      fa.floor_quota,
      fa.fractional_remainder,
      -- Edge Case 1: Only levels with available capacity can receive remainder
      CASE WHEN fa.floor_quota < fa.experienced_headcount THEN 1 ELSE 0 END AS has_capacity,
      ROW_NUMBER() OVER (
        ORDER BY
          CASE WHEN fa.floor_quota < fa.experienced_headcount THEN 1 ELSE 2 END,  -- Capacity first
          fa.fractional_remainder DESC,  -- Then by remainder size (Edge Case 3)
          fa.level_id ASC  -- Deterministic tiebreaker
      ) AS remainder_rank,
      (SELECT ANY_VALUE(expected_experienced_terminations) - SUM(floor_quota) FROM fractional_allocation) AS remainder_slots
    FROM fractional_allocation fa
  )
  SELECT
    ra.level_id,
    ra.experienced_headcount,
    -- Allocate remainder only to levels with capacity
    ra.floor_quota + CASE
      WHEN ra.has_capacity = 1 AND ra.remainder_rank <= ra.remainder_slots THEN 1
      ELSE 0
    END AS expected_terminations,
    -- Compensation cost
    (ra.floor_quota + CASE
      WHEN ra.has_capacity = 1 AND ra.remainder_rank <= ra.remainder_slots THEN 1
      ELSE 0
    END) * wbl.avg_compensation AS termination_compensation_cost
  FROM remainder_allocation ra
  JOIN workforce_by_level wbl ON ra.level_id = wbl.level_id
),

-- E082: Check if fixed level distribution is enabled for this scenario
fixed_level_config AS (
  SELECT
    level_id,
    distribution_pct,
    use_fixed_distribution
  FROM {{ ref('config_new_hire_level_distribution') }}
  WHERE scenario_id = COALESCE(
    NULLIF('{{ scenario_id }}', 'default'),
    'default'
  )
  -- Fall back to default if no scenario-specific config exists
  OR (scenario_id = 'default' AND NOT EXISTS (
    SELECT 1 FROM {{ ref('config_new_hire_level_distribution') }}
    WHERE scenario_id = '{{ scenario_id }}'
      AND scenario_id != 'default'
  ))
),

-- Determine if we should use fixed distribution (any row has use_fixed_distribution = true)
use_fixed_distribution_flag AS (
  SELECT COALESCE(BOOL_OR(use_fixed_distribution), false) AS use_fixed
  FROM fixed_level_config
),

-- E077: Hiring Quotas by Level (ADR E077-B with adaptive distribution)
-- E082: Optionally override with fixed percentages
hiring_by_level AS (
  -- Allocate hires using adaptive OR fixed distribution based on config
  WITH level_weights AS (
    SELECT
      wbl.level_id,
      wbl.current_headcount,
      -- E082: Use fixed distribution from seed if enabled, otherwise use adaptive
      CASE
        WHEN (SELECT use_fixed FROM use_fixed_distribution_flag) THEN
          COALESCE(flc.distribution_pct, 0.0)
        ELSE
          wbl.current_headcount * 1.0 / NULLIF(SUM(wbl.current_headcount) OVER (), 0)
      END AS raw_weight
    FROM workforce_by_level wbl
    LEFT JOIN fixed_level_config flc ON wbl.level_id = flc.level_id
    WHERE wbl.current_headcount > 0  -- Exclude empty levels for weight calculation
      OR (SELECT use_fixed FROM use_fixed_distribution_flag)  -- Include all levels if fixed distribution
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

-- E082: Get job level compensation ranges from config variables (if provided)
-- Falls back to seed file values if variables not set
job_level_comp_config AS (
  SELECT
    level_id,
    min_compensation AS seed_min,
    max_compensation AS seed_max
  FROM {{ ref('stg_config_job_levels') }}
),

-- E082: Parse job level compensation from dbt variable (JSON array format)
-- Variable format: [{"level":1,"min":50000,"max":80000}, ...]
{% set job_level_comp_var = var('job_level_compensation', none) %}

job_level_comp_overrides AS (
  {% if job_level_comp_var is not none and job_level_comp_var | length > 0 %}
  -- Use config overrides from scenario
  SELECT
    jlc.level AS level_id,
    CAST(jlc.min AS DOUBLE) AS min_compensation,
    CAST(jlc.max AS DOUBLE) AS max_compensation
  FROM (
    VALUES
    {% for item in job_level_comp_var %}
      ({{ item.level }}, {{ item.min_compensation }}, {{ item.max_compensation }}){% if not loop.last %},{% endif %}
    {% endfor %}
  ) AS jlc(level, min, max)
  {% else %}
  -- No overrides, return empty to use seed values
  SELECT
    NULL::INTEGER AS level_id,
    NULL::DOUBLE AS min_compensation,
    NULL::DOUBLE AS max_compensation
  WHERE 1 = 0
  {% endif %}
),

-- Merge overrides with seed defaults
job_level_comp_merged AS (
  SELECT
    jc.level_id,
    COALESCE(jo.min_compensation, jc.seed_min) AS min_compensation,
    COALESCE(jo.max_compensation, jc.seed_max) AS max_compensation
  FROM job_level_comp_config jc
  LEFT JOIN job_level_comp_overrides jo ON jc.level_id = jo.level_id
),

-- Compensation ranges and new hire costs
compensation_planning AS (
  SELECT
    jlm.level_id,
    CAST(jlm.min_compensation AS DOUBLE) AS min_compensation,
    CAST(jlm.max_compensation AS DOUBLE) AS max_compensation,
    wbl.avg_compensation AS current_avg_compensation,
    -- New hire compensation using configurable percentiles (Epic E056)
    -- Calculate percentile-based compensation with market adjustments
    -- E082: Apply market scenario adjustment
    CAST((jlm.min_compensation +
     (jlm.max_compensation - jlm.min_compensation) *
     COALESCE({{ resolve_parameter('jlm.level_id', 'HIRE', 'compensation_percentile', simulation_year) }}, 0.50) *
     COALESCE({{ resolve_parameter('jlm.level_id', 'HIRE', 'market_adjustment_multiplier', simulation_year) }}, 1.0) *
     (1 + {{ var('market_scenario_adjustment', 0) }} / 100.0)
    ) AS DOUBLE) AS new_hire_avg_compensation,
    -- Merit increase planning - use variable-based parameters for consistency
    CAST(wbl.total_compensation * {{ var('merit_budget', 0.03) }} AS DOUBLE) AS merit_increase_cost,
    -- COLA planning - use variable-based parameters for consistency
    CAST(wbl.total_compensation * {{ var('cola_rate', 0.025) }} AS DOUBLE) AS cola_cost,
    -- Promotion cost estimate - use safe defaults temporarily
    CAST(wbl.current_headcount * 0.05 AS DOUBLE) AS expected_promotions,
    CAST(wbl.avg_compensation * 0.12 * (wbl.current_headcount * 0.05) AS DOUBLE) AS promotion_cost
  FROM job_level_comp_merged jlm
  LEFT JOIN workforce_by_level wbl ON jlm.level_id = wbl.level_id
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
