{{ config(materialized='table') }}

-- Merit raises hazard configuration

SELECT
    merit_base,
    CURRENT_TIMESTAMP AS created_at
FROM {{ ref('config_raises_hazard') }}
