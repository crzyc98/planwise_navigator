{{ config(materialized='table') }}

-- Cost of Living Adjustment (COLA) rates by year
-- Used for annual compensation adjustments in the simulation

SELECT
    year,
    cola_rate,
    CURRENT_TIMESTAMP AS created_at
FROM {{ ref('config_cola_by_year') }}
ORDER BY year
