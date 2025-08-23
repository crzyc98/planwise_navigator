{{ config(
    materialized='table',
    indexes=[
        {'columns': ['simulation_year'], 'type': 'btree'},
        {'columns': ['employee_id', 'simulation_year'], 'type': 'btree'}
    ],
    tags=['staging', 'compensation', 'new_hires']
) }}

-- New Hire Compensation Staging Model (Dependency-Free)
--
-- **Purpose:**
-- Breaks the circular dependency by generating new hires independently of workforce_needs.
-- Uses hardcoded parameters for Year 1 to avoid the circular dependency loop.
-- This allows new hires to be included in Year 1 compensation calculations.
--
-- **Dependency Flow (No Circular Dependencies):**
-- int_baseline_workforce → int_new_hire_compensation_staging → int_employee_compensation_by_year
--
-- **Usage:**
-- Only used in Year 1 to union with baseline workforce compensation.
-- For subsequent years, new hires come through the standard workforce snapshot flow.

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}
{% set is_first_year = (simulation_year == start_year) %}

-- Only generate new hires for Year 1 to break circular dependency
{% if is_first_year %}

WITH baseline_metrics AS (
  -- Get baseline workforce stats without depending on other models
  SELECT
    COUNT(*) AS baseline_workforce_count,
    AVG(current_compensation) AS avg_compensation
  FROM {{ ref('int_baseline_workforce') }}
  WHERE employment_status = 'active'
),

hiring_targets AS (
  -- Calculate hiring needs using hardcoded parameters for Year 1
  SELECT
    bm.baseline_workforce_count,
    bm.avg_compensation,
    -- Hardcoded parameters to break circular dependency
    0.03 AS target_growth_rate,                    -- 3% growth target
    0.12 AS experienced_termination_rate,          -- 12% termination rate
    0.25 AS new_hire_termination_rate,             -- 25% new hire termination rate

    -- Calculate hiring needs directly
    ROUND(bm.baseline_workforce_count * 0.03) AS target_net_growth,
    ROUND(bm.baseline_workforce_count * 0.12) AS expected_terminations,

    -- Calculate total hires needed (accounting for new hire attrition)
    ROUND(
      (ROUND(bm.baseline_workforce_count * 0.03) + ROUND(bm.baseline_workforce_count * 0.12)) /
      (1 - 0.25)
    ) AS total_hires_needed
  FROM baseline_metrics bm
),

-- Generate hire sequence using simplified distribution
hire_sequence AS (
  SELECT
    ROW_NUMBER() OVER (ORDER BY level_dist.level_id, seq.i) AS hire_sequence_num,
    level_dist.level_id,
    level_dist.hires_for_level
  FROM (
    -- Simplified level distribution (matches int_hiring_events logic)
    SELECT level_id, hires_for_level FROM (VALUES
      (1, CEIL((SELECT total_hires_needed FROM hiring_targets) * 0.40)),
      (2, CEIL((SELECT total_hires_needed FROM hiring_targets) * 0.30)),
      (3, CEIL((SELECT total_hires_needed FROM hiring_targets) * 0.20)),
      (4, CEIL((SELECT total_hires_needed FROM hiring_targets) * 0.08)),
      (5, CEIL((SELECT total_hires_needed FROM hiring_targets) * 0.02))
    ) AS t(level_id, hires_for_level)
    WHERE hires_for_level > 0
  ) level_dist
  CROSS JOIN UNNEST(range(1::BIGINT, CAST(level_dist.hires_for_level AS BIGINT) + 1)) AS seq(i)
),

-- Get compensation by level from config using configurable percentiles (Epic E056)
level_compensation AS (
  SELECT
    level_id,
    min_compensation,
    max_compensation,
    -- Use configurable percentile instead of hardcoded midpoint
    (min_compensation +
     (COALESCE(max_compensation, min_compensation * 2) - min_compensation) *
     COALESCE({{ get_parameter_value('level_id', 'HIRE', 'compensation_percentile', simulation_year) }}, 0.50) *
     COALESCE({{ get_parameter_value('level_id', 'HIRE', 'market_adjustment_multiplier', simulation_year) }}, 1.0)
    ) AS avg_level_compensation
  FROM {{ ref('stg_config_job_levels') }}
),

-- Generate new hire assignments
new_hire_assignments AS (
  SELECT
    hs.hire_sequence_num,
    hs.level_id,

    -- Generate deterministic employee ID (matches int_hiring_events format)
    'NH_' || CAST({{ simulation_year }} AS VARCHAR) || '_' ||
    LPAD(CAST(hs.hire_sequence_num AS VARCHAR), 6, '0') AS employee_id,

    -- Generate SSN using 900M range with year offsets to prevent census collisions
    'SSN-' || LPAD(CAST(900000000 + ({{ simulation_year }} - {{ start_year }}) * 100000 + hs.hire_sequence_num AS VARCHAR), 9, '0') AS employee_ssn,

    -- Simple age assignment (deterministic based on sequence)
    CASE
      WHEN hs.hire_sequence_num % 5 = 0 THEN 25
      WHEN hs.hire_sequence_num % 5 = 1 THEN 28
      WHEN hs.hire_sequence_num % 5 = 2 THEN 32
      WHEN hs.hire_sequence_num % 5 = 3 THEN 35
      ELSE 40
    END AS employee_age,

    -- Birth date calculation
    CAST('{{ simulation_year }}-01-01' AS DATE) - INTERVAL (
      CASE
        WHEN hs.hire_sequence_num % 5 = 0 THEN 25
        WHEN hs.hire_sequence_num % 5 = 1 THEN 28
        WHEN hs.hire_sequence_num % 5 = 2 THEN 32
        WHEN hs.hire_sequence_num % 5 = 3 THEN 35
        ELSE 40
      END * 365
    ) DAY AS birth_date,

    -- Hire date evenly distributed throughout year
    CAST('{{ simulation_year }}-01-01' AS DATE) + INTERVAL (hs.hire_sequence_num % 365) DAY AS hire_date,

    -- Use level-based compensation with small variance
    ROUND(lc.avg_level_compensation * (0.9 + (hs.hire_sequence_num % 10) * 0.02), 2) AS compensation_amount

  FROM hire_sequence hs
  LEFT JOIN level_compensation lc ON hs.level_id = lc.level_id
)

-- Transform new hire assignments into compensation format
SELECT
    {{ simulation_year }} AS simulation_year,
    nha.employee_id,
    nha.employee_ssn,
    nha.birth_date AS employee_birth_date,
    nha.hire_date AS employee_hire_date,
    nha.compensation_amount AS employee_compensation,
    nha.employee_age AS current_age,
    -- Calculate tenure as 0 for new hires (they start the year)
    0 AS current_tenure,
    nha.level_id,

    -- Calculate age band based on employee_age
    CASE
        WHEN nha.employee_age < 25 THEN '< 25'
        WHEN nha.employee_age < 35 THEN '25-34'
        WHEN nha.employee_age < 45 THEN '35-44'
        WHEN nha.employee_age < 55 THEN '45-54'
        WHEN nha.employee_age < 65 THEN '55-64'
        ELSE '65+'
    END AS age_band,

    -- Tenure band is always '< 2' for new hires
    '< 2' AS tenure_band,

    'active' AS employment_status,

    -- Enrollment fields - new hires will get enrollment events separately
    -- For staging purposes, assume not enrolled initially
    NULL AS employee_enrollment_date,
    FALSE AS is_enrolled_flag,

    'new_hire_staging_independent' AS data_source,

    -- Additional metadata for validation
    nha.compensation_amount AS starting_year_compensation,
    nha.compensation_amount AS ending_year_compensation,  -- Will be updated after events
    FALSE AS has_compensation_events

FROM new_hire_assignments nha
ORDER BY nha.employee_id

{% else %}

-- For subsequent years, return empty result set
-- New hires come through the standard workforce snapshot flow
SELECT
    {{ simulation_year }} AS simulation_year,
    NULL::VARCHAR AS employee_id,
    NULL::VARCHAR AS employee_ssn,
    NULL::DATE AS employee_birth_date,
    NULL::DATE AS employee_hire_date,
    NULL::DECIMAL AS employee_compensation,
    NULL::INTEGER AS current_age,
    NULL::INTEGER AS current_tenure,
    NULL::INTEGER AS level_id,
    NULL::VARCHAR AS age_band,
    NULL::VARCHAR AS tenure_band,
    NULL::VARCHAR AS employment_status,
    NULL::DATE AS employee_enrollment_date,
    NULL::BOOLEAN AS is_enrolled_flag,
    NULL::VARCHAR AS data_source,
    NULL::DECIMAL AS starting_year_compensation,
    NULL::DECIMAL AS ending_year_compensation,
    NULL::BOOLEAN AS has_compensation_events
WHERE 1 = 0  -- Empty result set

{% endif %}
