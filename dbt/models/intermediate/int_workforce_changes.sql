{{ config(
    materialized='table'
) }}

-- Simplified workforce changes model (troubleshooting version)
-- All records are treated as NEW_EMPLOYEE for now

SELECT
    employee_id,
    simulation_year,
    current_compensation,
    prorated_annual_compensation,
    full_year_equivalent_compensation,
    level_id,
    employment_status,
    termination_date,
    termination_reason,
    detailed_status_code,
    snapshot_created_at,
    COALESCE(record_hash, 'no_hash') as record_hash,
    'NEW_EMPLOYEE' as change_type
FROM {{ ref('int_partitioned_workforce_data') }}
