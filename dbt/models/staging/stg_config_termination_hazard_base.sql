{{ config(materialized='table') }}

-- Base termination hazard rates configuration

SELECT
    base_rate_for_new_hire,
    level_discount_factor,
    min_level_discount_multiplier,
    CURRENT_TIMESTAMP AS created_at
FROM {{ ref('config_termination_hazard_base') }}
