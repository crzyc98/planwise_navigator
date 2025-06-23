{{ config(materialized='table') }}

-- Age-based multipliers for promotion hazard rates

SELECT
    age_band,
    multiplier,
    CURRENT_TIMESTAMP AS created_at
FROM {{ ref('config_promotion_hazard_age_multipliers') }}
ORDER BY age_band
