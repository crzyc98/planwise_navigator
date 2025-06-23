{{ config(materialized='table') }}

-- Tenure-based multipliers for termination hazard rates

SELECT
    tenure_band,
    multiplier,
    CURRENT_TIMESTAMP AS created_at
FROM {{ ref('config_termination_hazard_tenure_multipliers') }}
ORDER BY tenure_band
