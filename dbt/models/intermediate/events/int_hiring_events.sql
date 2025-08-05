{{ config(materialized='table') }}

{% set simulation_year = var('simulation_year') %}

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


-- Assign attributes to each new hire
new_hire_assignments AS (
  SELECT
    hs.hire_sequence_num,
    hs.level_id,

    -- Generate deterministic employee ID (no random UUID to ensure consistency)
    'NH_' || CAST({{ simulation_year }} AS VARCHAR) || '_' ||
    LPAD(CAST(hs.hire_sequence_num AS VARCHAR), 6, '0') AS employee_id,

    -- Generate SSN using 900M range with year offsets to prevent census collisions
    -- Census uses 100M range (SSN-100000001+), new hires use 900M+ range
    -- Format: 900 + (year_offset * 100000) + sequence_num
    'SSN-' || LPAD(CAST(900000000 + ({{ simulation_year }} - 2025) * 100000 + hs.hire_sequence_num AS VARCHAR), 9, '0') AS employee_ssn,

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

    -- Hire date evenly distributed throughout year using modulo for cycling
    CAST('{{ simulation_year }}-01-01' AS DATE) + INTERVAL (hs.hire_sequence_num % 365) DAY AS hire_date,

    -- Use compensation from workforce needs with small variance for realism
    ROUND(hs.new_hire_avg_compensation * (0.9 + (hs.hire_sequence_num % 10) * 0.02), 2) AS compensation_amount

  FROM hire_sequence hs
)

SELECT
  nha.employee_id,
  nha.employee_ssn,
  'hire' AS event_type,
  {{ simulation_year }} AS simulation_year,
  nha.hire_date AS effective_date,
  nha.employee_age,
  nha.birth_date,
  nha.level_id,
  nha.compensation_amount,
  'external_hire' AS hire_source,
  CURRENT_TIMESTAMP AS created_at,
  -- Add reference to workforce planning using subquery to avoid CROSS JOIN amplification
  (SELECT workforce_needs_id FROM workforce_needs LIMIT 1) AS workforce_needs_id,
  (SELECT scenario_id FROM workforce_needs LIMIT 1) AS scenario_id
FROM new_hire_assignments nha
ORDER BY nha.hire_sequence_num
