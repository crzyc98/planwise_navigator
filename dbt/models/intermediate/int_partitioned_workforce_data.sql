{{ config(
    materialized='table',
    indexes=[
        {'columns': ['employee_id'], 'type': 'btree'},
        {'columns': ['simulation_year'], 'type': 'btree'},
        {'columns': ['employee_id', 'simulation_year'], 'type': 'btree'},
        {'columns': ['record_hash'], 'type': 'btree'}
    ]
) }}

-- Optimized partitioned workforce data with proper indexing and data types
-- This model serves as a performance-optimized base for SCD processing

WITH optimized_workforce AS (
    SELECT
        employee_id::VARCHAR(50) as employee_id,  -- Optimize data types
        simulation_year::INTEGER as simulation_year,
        current_compensation::DECIMAL(12,2) as current_compensation,
        prorated_annual_compensation::DECIMAL(12,2) as prorated_annual_compensation,
        full_year_equivalent_compensation::DECIMAL(12,2) as full_year_equivalent_compensation,
        level_id::INTEGER as level_id,
        employment_status::VARCHAR(20) as employment_status,
        termination_date::DATE as termination_date,
        termination_reason::VARCHAR(255) as termination_reason,
        detailed_status_code::VARCHAR(50) as detailed_status_code,
        snapshot_created_at::TIMESTAMP as snapshot_created_at,
        -- Pre-calculate hash for efficient change detection
        {{ dbt_utils.generate_surrogate_key([
            'current_compensation',
            'level_id',
            'employment_status',
            'termination_date'
        ]) }} as record_hash
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE simulation_year = {{ var('simulation_year', 2025) }}
)

SELECT * FROM optimized_workforce
