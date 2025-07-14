{{ config(
    materialized='table',
    indexes=[
        {'columns': ['employee_id'], 'type': 'btree'},
        {'columns': ['change_type'], 'type': 'btree'},
        {'columns': ['employee_id', 'change_type'], 'type': 'btree'}
    ]
) }}

-- Hash-based change detection for efficient SCD processing
-- Only processes employees with actual changes since last snapshot

WITH current_workforce AS (
    SELECT * FROM {{ ref('int_partitioned_workforce_data') }}
),

previous_state AS (
    SELECT
        employee_id,
        record_hash as previous_hash,
        dbt_valid_from,
        dbt_valid_to
    FROM {{ ref('scd_workforce_state_optimized') }}
    WHERE dbt_valid_to IS NULL  -- Current records only
),

change_detection AS (
    SELECT
        c.employee_id,
        c.simulation_year,
        c.current_compensation,
        c.prorated_annual_compensation,
        c.full_year_equivalent_compensation,
        c.level_id,
        c.employment_status,
        c.termination_date,
        c.termination_reason,
        c.detailed_status_code,
        c.snapshot_created_at,
        c.record_hash,
        p.previous_hash,
        CASE
            WHEN p.previous_hash IS NULL THEN 'NEW_EMPLOYEE'
            WHEN c.record_hash != p.previous_hash THEN 'CHANGED'
            ELSE 'UNCHANGED'
        END as change_type
    FROM current_workforce c
    LEFT JOIN previous_state p ON c.employee_id = p.employee_id
),

-- Return only changed records for processing
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
    record_hash,
    change_type
FROM change_detection
WHERE change_type IN ('NEW_EMPLOYEE', 'CHANGED')
