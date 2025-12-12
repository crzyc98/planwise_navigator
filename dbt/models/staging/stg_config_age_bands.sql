{{
    config(
        materialized='table'
    )
}}

-- Staging model for age band configuration
-- Single source of truth for age band definitions
-- Bands use [min_value, max_value) interval convention (lower bound inclusive, upper bound exclusive)

SELECT
    band_id,
    band_label,
    min_value,
    max_value,
    display_order
FROM {{ ref('config_age_bands') }}
ORDER BY display_order
