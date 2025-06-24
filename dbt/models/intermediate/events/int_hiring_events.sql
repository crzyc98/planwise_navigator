{{ config(materialized='table') }}

{% set simulation_year = var('simulation_year') %}

-- Generate hiring events to replace departures and achieve target growth
-- Epic 11.5 Step f: Calculate net new hires needed based on departures and growth target

WITH simulation_config AS (
  SELECT
    {{ simulation_year }} AS current_year,
    {{ var('target_growth_rate', 0.03) }} AS target_growth_rate
),

-- Get previous year workforce count for growth calculation
-- For 2025, use baseline. For subsequent years, use previous year's active workforce
previous_year_workforce_count AS (
{% if simulation_year == 2025 %}
  SELECT COUNT(*) AS workforce_count
  FROM {{ ref('int_baseline_workforce') }}
  WHERE employment_status = 'active'
{% else %}
  SELECT COUNT(*) AS workforce_count
  FROM {{ ref('int_workforce_previous_year') }}
  WHERE employment_status = 'active'
{% endif %}
),

-- Calculate total expected departures including both experienced and new hire terminations
-- This is the key fix: account for new hire terminations that will happen AFTER hiring
total_expected_departures AS (
  SELECT
    pywc.workforce_count,
    -- Align with int_termination_events.sql's CEIL behavior for experienced terminations
    CEIL(pywc.workforce_count * {{ var('total_termination_rate', 0.12) }}) AS expected_experienced_terminations_count,
    pywc.workforce_count * {{ var('target_growth_rate', 0.03) }} AS target_growth_amount_decimal,
    -- We need to solve for total_hires such that:
    -- workforce_next = workforce_current - experienced_terms + total_hires - (total_hires * new_hire_term_rate)
    -- workforce_next = workforce_current * (1 + growth_rate)
    -- This gives us: total_hires = (experienced_terms + workforce_current * growth_rate) / (1 - new_hire_term_rate)
    -- Use CEIL here to mirror actual terminations from int_termination_events.sql
    CEIL(
      (CEIL(pywc.workforce_count * {{ var('total_termination_rate', 0.12) }}) + -- Use CEIL here to mirror actual terms
       pywc.workforce_count * {{ var('target_growth_rate', 0.03) }}) /
      (1 - {{ var('new_hire_termination_rate', 0.25) }})
    ) AS total_hires_needed
  FROM previous_year_workforce_count pywc
),

-- Calculate hiring target
hiring_calculation AS (
  SELECT
    pywc.workforce_count AS starting_active_workforce, -- Rename for clarity
    td.expected_experienced_terminations_count AS experienced_terminations, -- Use the CEILed value
    td.total_hires_needed,
    sc.target_growth_rate,

    -- Expected new hire terminations - use ROUND for better balance (this matches int_new_hire_termination_events logic)
    ROUND(td.total_hires_needed * {{ var('new_hire_termination_rate', 0.25) }}) AS expected_new_hire_terminations,

    -- Calculate net change based on these aligned values
    (td.total_hires_needed - td.expected_experienced_terminations_count -
     ROUND(td.total_hires_needed * {{ var('new_hire_termination_rate', 0.25) }})) AS net_workforce_change_actual,

    -- Target ending workforce based purely on growth rate, for comparison
    ROUND(pywc.workforce_count * (1 + sc.target_growth_rate)) AS target_ending_workforce_count

  FROM previous_year_workforce_count pywc
  CROSS JOIN total_expected_departures td
  CROSS JOIN simulation_config sc
),

-- Generate level distribution for new hires (weighted toward entry levels)
level_distribution AS (
  SELECT * FROM (VALUES
    (1, 0.40), -- 40% Level 1 (entry level)
    (2, 0.30), -- 30% Level 2
    (3, 0.20), -- 20% Level 3
    (4, 0.08), -- 8% Level 4
    (5, 0.02)  -- 2% Level 5 (senior)
  ) AS t(level_id, distribution_weight)
),

-- Calculate hires per level
hires_per_level AS (
  SELECT
    ld.level_id,
    ld.distribution_weight,
    CEIL(hc.total_hires_needed * ld.distribution_weight) AS hires_for_level
  FROM hiring_calculation hc
  CROSS JOIN level_distribution ld
),

-- Generate age distribution for new hires (realistic hiring age profile)
age_distribution AS (
  SELECT * FROM (VALUES
    (22, 0.05), -- Recent college graduates
    (25, 0.15), -- Early career
    (28, 0.20), -- Established early career
    (32, 0.25), -- Mid-career switchers
    (35, 0.15), -- Experienced hires
    (40, 0.10), -- Senior experienced
    (45, 0.08), -- Mature professionals
    (50, 0.02)  -- Late career changes
  ) AS t(hire_age, age_weight)
),

-- Get compensation ranges by level for salary assignment
compensation_ranges AS (
  SELECT
    level_id,
    min_compensation,
    -- Cap max compensation at reasonable levels to avoid extreme outliers
    CASE
      WHEN level_id <= 3 THEN max_compensation
      WHEN level_id = 4 THEN LEAST(max_compensation, 250000)  -- Cap Level 4 at $250K
      WHEN level_id = 5 THEN LEAST(max_compensation, 350000)  -- Cap Level 5 at $350K
      ELSE max_compensation
    END AS max_compensation,
    -- Calculate average based on capped values to prevent extreme compensation assignments
    (min_compensation +
     CASE
       WHEN level_id <= 3 THEN max_compensation
       WHEN level_id = 4 THEN LEAST(max_compensation, 250000)
       WHEN level_id = 5 THEN LEAST(max_compensation, 350000)
       ELSE max_compensation
     END) / 2 AS avg_compensation
  FROM {{ ref('stg_config_job_levels') }}
),

-- Generate hire sequence using GENERATE_SERIES to handle arbitrary hire counts
hire_sequence AS (
  SELECT
    ROW_NUMBER() OVER (ORDER BY hpl.level_id, s.i) AS hire_sequence_num,
    hpl.level_id
  FROM hires_per_level hpl
  CROSS JOIN GENERATE_SERIES(
      1,
      (SELECT MAX(hires_for_level) FROM hires_per_level)
  ) AS s(i)
  WHERE s.i <= hpl.hires_for_level
),

-- Assign attributes to each new hire
new_hire_assignments AS (
  SELECT
    hs.hire_sequence_num,
    hs.level_id,

    -- Generate globally unique employee ID for new hire across all simulation years
    'NH_' || CAST((SELECT current_year FROM simulation_config) AS VARCHAR) || '_' || LPAD(CAST(hs.hire_sequence_num AS VARCHAR), 6, '0') AS employee_id,

    -- Generate SSN
    'SSN-' || LPAD(CAST(100000000 + hs.hire_sequence_num AS VARCHAR), 9, '0') AS employee_ssn,

    -- Simple age assignment (deterministic based on sequence)
    CASE
      WHEN hs.hire_sequence_num % 5 = 0 THEN 25
      WHEN hs.hire_sequence_num % 5 = 1 THEN 28
      WHEN hs.hire_sequence_num % 5 = 2 THEN 32
      WHEN hs.hire_sequence_num % 5 = 3 THEN 35
      ELSE 40
    END AS employee_age,

    -- Simple birth date calculation
    CAST('{{ simulation_year }}-01-01' AS DATE) - INTERVAL (
      CASE
        WHEN hs.hire_sequence_num % 5 = 0 THEN 25
        WHEN hs.hire_sequence_num % 5 = 1 THEN 28
        WHEN hs.hire_sequence_num % 5 = 2 THEN 32
        WHEN hs.hire_sequence_num % 5 = 3 THEN 35
        ELSE 40
      END * 365
    ) DAY AS birth_date,

    -- Hire date spread throughout year, capped at year end
    LEAST(
        CAST('{{ simulation_year }}-01-01' AS DATE) + INTERVAL (hs.hire_sequence_num * 30) DAY,
        CAST('{{ simulation_year }}-12-31' AS DATE)
    ) AS hire_date,

    -- Simple compensation assignment (based on level with small variance)
    ROUND(cr.avg_compensation * (0.9 + (hs.hire_sequence_num % 10) * 0.02), 2) AS compensation_amount

  FROM hire_sequence hs
  LEFT JOIN compensation_ranges cr ON hs.level_id = cr.level_id
)

SELECT
  nha.employee_id,
  nha.employee_ssn,
  'hire' AS event_type,
  (SELECT current_year FROM simulation_config) AS simulation_year,
  nha.hire_date AS effective_date,
  nha.employee_age,
  nha.birth_date,
  nha.level_id,
  nha.compensation_amount,
  'external_hire' AS hire_source,
  CURRENT_TIMESTAMP AS created_at
FROM new_hire_assignments nha
ORDER BY nha.hire_sequence_num
