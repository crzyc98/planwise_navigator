{{ config(materialized='table') }}

-- Master hazard dimension table: joined view of termination, promotion, and merit hazards.

WITH term AS (
    SELECT * FROM {{ ref('int_hazard_termination') }}
),
prom AS (
    SELECT * FROM {{ ref('int_hazard_promotion') }}
),
merit AS (
    SELECT * FROM {{ ref('int_hazard_merit') }}
)
SELECT
    term.year,
    term.level_id,
    term.tenure_band,
    term.age_band,
    term.termination_rate,
    prom.promotion_rate,
    merit.merit_raise
FROM term
JOIN prom USING (year, level_id, tenure_band, age_band)
JOIN merit USING (year, level_id, tenure_band, age_band)
