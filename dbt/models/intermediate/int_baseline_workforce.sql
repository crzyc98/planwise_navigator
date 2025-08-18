{{ config(
    materialized='incremental',
    unique_key=['employee_id', 'simulation_year'],
    incremental_strategy='delete+insert',
    on_schema_change='sync_all_columns',
    indexes=[
        {'columns': ['simulation_year'], 'type': 'btree'},
        {'columns': ['employee_id', 'simulation_year'], 'type': 'btree'}
    ]
) }}

-- Simplified Baseline Workforce Preparation
-- Creates baseline workforce directly from census data without complex cold start detection

{% set simulation_year = var('simulation_year', 2025) %}
{% set simulation_effective_date_str = var('simulation_effective_date', '2024-12-31') %}

SELECT
    stg.employee_id,
    stg.employee_ssn,
    stg.employee_birth_date,
    stg.employee_hire_date,
    -- Use annualized compensation for more accurate baseline
    COALESCE(stg.employee_annualized_compensation, stg.employee_gross_compensation) AS current_compensation,
    -- Calculate age and tenure based on the simulation_effective_date
    EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_birth_date) AS current_age,
    EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_hire_date) AS current_tenure,
    -- Dynamically assign level_id with fallback for unmatched compensation ranges
    COALESCE(level_match.level_id, 1) AS level_id,
    -- Calculate age and tenure bands
    CASE
        WHEN (EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_birth_date)) < 25 THEN '< 25'
        WHEN (EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_birth_date)) < 35 THEN '25-34'
        WHEN (EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_birth_date)) < 45 THEN '35-44'
        WHEN (EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_birth_date)) < 55 THEN '45-54'
        WHEN (EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_birth_date)) < 65 THEN '55-64'
        ELSE '65+'
    END AS age_band,
    CASE
        WHEN (EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_hire_date)) < 2 THEN '< 2'
        WHEN (EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_hire_date)) < 5 THEN '2-4'
        WHEN (EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_hire_date)) < 10 THEN '5-9'
        WHEN (EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_hire_date)) < 20 THEN '10-19'
        ELSE '20+'
    END AS tenure_band,
    'active' AS employment_status,
    NULL AS termination_date,
    NULL AS termination_reason,
    -- Add eligibility and enrollment fields from census
    stg.employee_eligibility_date,
    stg.waiting_period_days,
    stg.current_eligibility_status,
    stg.employee_enrollment_date,
    {{ simulation_year }} AS simulation_year,
    CURRENT_TIMESTAMP AS snapshot_created_at,
    true as is_from_census,
    -- Simplified: assume this is always a cold start from census data
    true as is_cold_start,
    ({{ simulation_year }} - 1) as last_completed_year
FROM {{ ref('stg_census_data') }} stg
-- Use a subquery to find the best matching level_id for each employee
LEFT JOIN (
    SELECT
        stg_inner.employee_id,
        -- Select the level with the smallest min_compensation that still matches
        MIN(levels.level_id) as level_id
    FROM {{ ref('stg_census_data') }} stg_inner
    LEFT JOIN {{ ref('stg_config_job_levels') }} levels
        ON COALESCE(stg_inner.employee_annualized_compensation, stg_inner.employee_gross_compensation) >= levels.min_compensation
       AND (COALESCE(stg_inner.employee_annualized_compensation, stg_inner.employee_gross_compensation) < levels.max_compensation OR levels.max_compensation IS NULL)
    GROUP BY stg_inner.employee_id
) level_match ON stg.employee_id = level_match.employee_id
WHERE stg.employee_termination_date IS NULL

{% if is_incremental() %}
    -- Note: This model generates baseline data for the current simulation_year only
    -- No additional filtering needed as baseline is created fresh for each year
{% endif %}

ORDER BY stg.employee_id
