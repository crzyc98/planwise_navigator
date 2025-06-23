{{ config(materialized='table') }}

-- Age-based multipliers for termination hazard rates

SELECT
    age_band,
    multiplier,
    CURRENT_TIMESTAMP AS created_at
FROM {{ ref('config_termination_hazard_age_multipliers') }}
ORDER BY age_band
