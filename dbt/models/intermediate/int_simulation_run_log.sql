{{ config(
    materialized='incremental',
    unique_key='simulation_year',
    on_schema_change='fail'
) }}

-- Simulation Run Log for Tracking Completed Years
-- Only insert when a simulation year completes successfully

SELECT
    {{ var('simulation_year') }} as simulation_year,
    CURRENT_TIMESTAMP as completion_timestamp,
    'COMPLETED' as run_status,
    COUNT(*) as total_employees_processed
FROM {{ ref('fct_workforce_snapshot') }}
WHERE simulation_year = {{ var('simulation_year') }}
HAVING COUNT(*) > 0  -- Ensure we actually processed employees

{% if is_incremental() %}
    AND {{ var('simulation_year') }} NOT IN (
        SELECT simulation_year FROM {{ this }}
    )
{% endif %}
