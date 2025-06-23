{{ config(materialized='table') }}

-- Merit raise hazard model: calculates expected merit raise % by combination.
-- For now, apply a flat merit_base value; tenure & level adjustments can be added later.

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
base AS (
    SELECT merit_base FROM {{ ref('stg_config_raises_hazard') }}
)
SELECT
    y.year,
    l.level_id,
    t.tenure_band,
    a.age_band,
    b.merit_base AS merit_raise
FROM years y
CROSS JOIN levels l
CROSS JOIN tenure t
CROSS JOIN age a
CROSS JOIN base b
