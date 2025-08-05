{{ config(materialized='table') }}

-- Timing validation rules configuration from seed data
-- Defines business rules for event timing validation

SELECT
    rule_name,
    rule_type,
    target_value,
    tolerance,
    enforcement_level,
    CURRENT_TIMESTAMP AS created_at
FROM {{ ref('config_timing_validation_rules') }}
ORDER BY rule_name
