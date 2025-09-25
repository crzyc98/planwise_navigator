{{ config(
  materialized='table',
  tags=['FOUNDATION', 'EVENT_GENERATION']
) }}

-- Termination hazard model: computes termination probability for each combination of
-- simulation year, job level, tenure band and age band.
-- Formula is currently simplified to: base_rate * tenure_multiplier * age_multiplier.
-- TODO: incorporate level discount factor once legacy logic is fully analysed.

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
    SELECT base_rate_for_new_hire
    FROM {{ ref('stg_config_termination_hazard_base') }}
)
SELECT
    y.year,
    l.level_id,
    t.tenure_band,
    a.age_band,
    b.base_rate_for_new_hire * t.tenure_mult * a.age_mult AS termination_rate
FROM years y
CROSS JOIN levels l
CROSS JOIN tenure t
CROSS JOIN age a
CROSS JOIN base b
