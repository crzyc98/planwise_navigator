{{ config(materialized='table') }}

-- Tenure-based multipliers for promotion hazard rates

SELECT
    tenure_band,
    multiplier,
    CURRENT_TIMESTAMP AS created_at
FROM {{ ref('config_promotion_hazard_tenure_multipliers') }}
ORDER BY tenure_band
