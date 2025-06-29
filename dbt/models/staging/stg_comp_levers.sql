{{ config(materialized='table') }}

-- Compensation parameter levers staging model

SELECT
    scenario_id,
    fiscal_year,
    job_level,
    event_type,
    parameter_name,
    parameter_value,
    CAST(is_locked AS BOOLEAN) AS is_locked,
    CAST(created_at AS DATE) AS created_at,
    created_by,
    CURRENT_TIMESTAMP AS processed_at
FROM {{ ref('comp_levers') }}
WHERE parameter_value IS NOT NULL
  AND parameter_value >= 0
