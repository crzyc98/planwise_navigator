{{ config(
  materialized='table',
  tags=['FOUNDATION', 'EVENT_GENERATION']
) }}

-- Termination hazard model: computes termination probability for each combination of
-- simulation year, job level, tenure band and age band.
-- Formula: base_rate * tenure_multiplier * age_multiplier * level_discount
-- Higher-level employees get progressively lower termination rates, floored at min_level_discount_multiplier.

WITH years AS (
    SELECT DISTINCT year
    FROM {{ ref('stg_config_cola_by_year') }}
),
levels AS (
    SELECT level_id
    FROM {{ ref('stg_config_job_levels') }}
),
tenure AS (
    SELECT tenure_band, multiplier AS tenure_mult
    FROM {{ ref('stg_config_termination_hazard_tenure_multipliers') }}
),
age AS (
    SELECT age_band, multiplier AS age_mult
    FROM {{ ref('stg_config_termination_hazard_age_multipliers') }}
),
base AS (
    SELECT base_rate_for_new_hire, level_discount_factor, min_level_discount_multiplier
    FROM {{ ref('stg_config_termination_hazard_base') }}
)
SELECT
    y.year,
    l.level_id,
    t.tenure_band,
    a.age_band,
    b.base_rate_for_new_hire * t.tenure_mult * a.age_mult *
    GREATEST(b.min_level_discount_multiplier, 1 - b.level_discount_factor * (l.level_id - 1)) AS termination_rate
FROM years y
CROSS JOIN levels l
CROSS JOIN tenure t
CROSS JOIN age a
CROSS JOIN base b
