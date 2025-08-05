{{ config(materialized='table') }}

-- Raise timing distribution configuration from seed data
-- Defines probability distribution for when raises occur during the year

SELECT
    month,
    percentage as probability,
    CURRENT_TIMESTAMP AS created_at
FROM {{ ref('config_raise_timing_distribution') }}
ORDER BY month
