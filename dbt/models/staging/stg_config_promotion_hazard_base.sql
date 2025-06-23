{{ config(materialized='table') }}

-- Base promotion hazard rates configuration

SELECT
    base_rate,
    level_dampener_factor,
    CURRENT_TIMESTAMP AS created_at
FROM {{ ref('config_promotion_hazard_base') }}
