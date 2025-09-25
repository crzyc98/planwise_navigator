{{ config(
  materialized='table',
  tags=['FOUNDATION', 'EVENT_GENERATION']
) }}

-- Merit raise hazard model: calculates expected merit raise % by combination.
-- Enhanced to use dynamic parameter system with job-level specific merit rates.

WITH years AS (
    SELECT DISTINCT year FROM {{ ref('stg_config_cola_by_year') }}
),
levels AS (
    SELECT level_id FROM {{ ref('stg_config_job_levels') }}
),
tenure AS (
    SELECT DISTINCT tenure_band FROM {{ ref('stg_config_termination_hazard_tenure_multipliers') }}
),
age AS (
    SELECT DISTINCT age_band FROM {{ ref('stg_config_termination_hazard_age_multipliers') }}
),
-- Dynamic parameter resolution for merit rates by job level
parameter_resolution AS (
    SELECT
        y.year,
        l.level_id,
        -- Use dynamic parameter lookup with fallback to hardcoded defaults
        {{ get_parameter_value('l.level_id', 'RAISE', 'merit_base', 'y.year') }} AS merit_rate
    FROM years y
    CROSS JOIN levels l
)
SELECT
    y.year,
    l.level_id,
    t.tenure_band,
    a.age_band,
    pr.merit_rate AS merit_raise
FROM years y
CROSS JOIN levels l
CROSS JOIN tenure t
CROSS JOIN age a
JOIN parameter_resolution pr
    ON y.year = pr.year
    AND l.level_id = pr.level_id
