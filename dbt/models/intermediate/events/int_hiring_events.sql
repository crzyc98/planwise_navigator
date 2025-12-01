{{ config(
  materialized='table',
  tags=['EVENT_GENERATION', 'E068A_EPHEMERAL']
) }}

{% set simulation_year = var('simulation_year') %}
{% set start_year = var('start_year', 2025) | int %}

-- Generate hiring events based on centralized workforce needs calculations
-- Refactored to use int_workforce_needs as single source of truth

WITH workforce_needs AS (
  -- Get hiring requirements from centralized workforce planning
  SELECT
    workforce_needs_id,
    scenario_id,
    simulation_year,
    total_hires_needed,
    starting_workforce_count,
    target_growth_rate,
    expected_experienced_terminations,
    expected_new_hire_terminations,
    calculated_net_change,
    target_ending_workforce
  FROM {{ ref('int_workforce_needs') }}
  WHERE simulation_year = {{ simulation_year }}
    AND scenario_id = '{{ var('scenario_id', 'default') }}'
),

-- Get detailed hiring needs by level
workforce_needs_by_level AS (
  SELECT
    level_id,
    hires_needed,
    new_hire_avg_compensation
  FROM {{ ref('int_workforce_needs_by_level') }}
  WHERE simulation_year = {{ simulation_year }}
    AND scenario_id = '{{ var('scenario_id', 'default') }}'
),

-- Generate hire sequence using workforce needs by level
hire_sequence AS (
  SELECT
    ROW_NUMBER() OVER (ORDER BY wnbl.level_id, seq.i) AS hire_sequence_num,
    wnbl.level_id,
    wnbl.hires_needed,
    wnbl.new_hire_avg_compensation
  FROM workforce_needs_by_level wnbl
  CROSS JOIN UNNEST(range(1::BIGINT, CAST(wnbl.hires_needed AS BIGINT) + 1)) AS seq(i)
  WHERE wnbl.hires_needed > 0
),

-- E082: Load age distribution from configurable seed file
-- Falls back to 'default' scenario if no scenario-specific config exists
age_distribution AS (
  SELECT
    hire_age,
    age_weight,
    SUM(age_weight) OVER (ORDER BY hire_age ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_weight
  FROM {{ ref('config_new_hire_age_distribution') }}
  WHERE scenario_id = COALESCE(
    NULLIF('{{ var('scenario_id', 'default') }}', 'default'),
    'default'
  )
  -- If scenario-specific config doesn't exist, fall back to default
  OR (scenario_id = 'default' AND NOT EXISTS (
    SELECT 1 FROM {{ ref('config_new_hire_age_distribution') }}
    WHERE scenario_id = '{{ var('scenario_id', 'default') }}'
      AND scenario_id != 'default'
  ))
),

-- Get total weight for normalization (should be 1.0 but normalize just in case)
age_distribution_normalized AS (
  SELECT
    hire_age,
    age_weight,
    cumulative_weight / MAX(cumulative_weight) OVER () AS normalized_cumulative_weight
  FROM age_distribution
),


-- E082: Assign ages using weighted selection from configurable seed
-- Uses deterministic pseudo-random value based on sequence number for reproducibility
hire_sequence_with_random AS (
  SELECT
    hs.*,
    -- Generate deterministic pseudo-random value between 0 and 1
    -- Uses modulo of hash to create reproducible distribution
    -- Cast to DOUBLE first to avoid integer overflow issues
    ABS(MOD(HASH(CONCAT(CAST(hs.hire_sequence_num AS VARCHAR), '_age_', CAST({{ simulation_year }} AS VARCHAR)))::DOUBLE, 1000000.0)) / 1000000.0 AS age_random_value
  FROM hire_sequence hs
),

-- Match each hire to an age bucket based on cumulative weight
hire_with_age AS (
  SELECT
    hsr.*,
    (SELECT ad.hire_age
     FROM age_distribution_normalized ad
     WHERE ad.normalized_cumulative_weight >= hsr.age_random_value
     ORDER BY ad.normalized_cumulative_weight
     LIMIT 1
    ) AS assigned_age
  FROM hire_sequence_with_random hsr
),

-- Assign attributes to each new hire
new_hire_assignments AS (
  SELECT
    hwa.hire_sequence_num,
    hwa.level_id,

    -- Generate deterministic employee ID (no random UUID to ensure consistency)
    'NH_' || CAST({{ simulation_year }} AS VARCHAR) || '_' ||
    LPAD(CAST(hwa.hire_sequence_num AS VARCHAR), 6, '0') AS employee_id,

    -- Generate SSN using 900M range with year offsets to prevent census collisions
    -- Census uses 100M range (SSN-100000001+), new hires use 900M+ range
    -- Format: 900 + (year_offset * 100000) + sequence_num
    'SSN-' || LPAD(CAST(900000000 + ({{ simulation_year }} - {{ start_year }}) * 100000 + hwa.hire_sequence_num AS VARCHAR), 9, '0') AS employee_ssn,

    -- E082: Age from weighted distribution
    COALESCE(hwa.assigned_age, 32) AS employee_age,

    -- Birth date calculation based on assigned age
    CAST('{{ simulation_year }}-01-01' AS DATE) - INTERVAL (COALESCE(hwa.assigned_age, 32) * 365) DAY AS birth_date,

    -- Hire date evenly distributed throughout year using modulo for cycling
    CAST('{{ simulation_year }}-01-01' AS DATE) + INTERVAL (hwa.hire_sequence_num % 365) DAY AS hire_date,

    -- Use compensation from workforce needs with small variance for realism
    ROUND(hwa.new_hire_avg_compensation * (0.9 + (hwa.hire_sequence_num % 10) * 0.02), 2) AS compensation_amount

  FROM hire_with_age hwa
)

SELECT
  nha.employee_id,
  nha.employee_ssn,
  'hire' AS event_type,
  {{ simulation_year }} AS simulation_year,
  nha.hire_date AS effective_date,
  'New hire - Level ' || nha.level_id || ' employee at $' || CAST(ROUND(nha.compensation_amount, 0) AS VARCHAR) || ' annual compensation' AS event_details,
  nha.compensation_amount,
  NULL::DECIMAL(15,2) AS previous_compensation,
  NULL::DECIMAL(5,4) AS employee_deferral_rate,
  NULL::DECIMAL(5,4) AS prev_employee_deferral_rate,
  nha.employee_age,
  0.0 AS employee_tenure,
  nha.level_id,
  -- Age bands for consistency
  CASE
    WHEN nha.employee_age < 25 THEN '< 25'
    WHEN nha.employee_age < 35 THEN '25-34'
    WHEN nha.employee_age < 45 THEN '35-44'
    WHEN nha.employee_age < 55 THEN '45-54'
    WHEN nha.employee_age < 65 THEN '55-64'
    ELSE '65+'
  END AS age_band,
  '< 2' AS tenure_band,
  1.0 AS event_probability,
  'hire' AS event_category
FROM new_hire_assignments nha
ORDER BY nha.hire_sequence_num
