{{ config(materialized='table') }}

-- Scenario metadata staging model

SELECT
    scenario_id,
    scenario_name,
    description,
    created_by,
    status,
    base_scenario_id,
    CAST(created_at AS DATE) AS created_at,
    CAST(updated_at AS DATE) AS updated_at,
    CURRENT_TIMESTAMP AS processed_at
FROM {{ ref('scenario_meta') }}
WHERE scenario_id IS NOT NULL
  AND scenario_name IS NOT NULL
  AND status IN ('draft', 'published', 'archived')
