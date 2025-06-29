{{ config(materialized='table') }}

-- Compensation targets staging model

SELECT
    scenario_id,
    fiscal_year,
    metric_name,
    target_value,
    tolerance_pct,
    priority,
    description,
    CURRENT_TIMESTAMP AS processed_at
FROM {{ ref('comp_targets') }}
WHERE target_value IS NOT NULL
  AND target_value > 0
  AND tolerance_pct >= 0
  AND priority IN ('high', 'medium', 'low')
