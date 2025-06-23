{{ config(materialized='table') }}

-- Promotion hazard model: computes promotion probability for each combination
-- of year, level, tenure band, and age band.

WITH years AS (
    SELECT DISTINCT year FROM {{ ref('stg_config_cola_by_year') }}
),
levels AS (
    SELECT level_id FROM {{ ref('stg_config_job_levels') }}
),
tenure AS (
    SELECT tenure_band, multiplier AS tenure_mult
    FROM {{ ref('stg_config_promotion_hazard_tenure_multipliers') }}
),
age AS (
    SELECT age_band, multiplier AS age_mult
    FROM {{ ref('stg_config_promotion_hazard_age_multipliers') }}
),
base AS (
    SELECT base_rate, level_dampener_factor FROM {{ ref('stg_config_promotion_hazard_base') }}
)
SELECT
    y.year,
    l.level_id,
    t.tenure_band,
    a.age_band,
    b.base_rate * t.tenure_mult * a.age_mult *
    GREATEST(0, 1 - b.level_dampener_factor * (l.level_id - 1)) AS promotion_rate
FROM years y
CROSS JOIN levels l
CROSS JOIN tenure t
CROSS JOIN age a
CROSS JOIN base b
