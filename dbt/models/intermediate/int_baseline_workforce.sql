{{ config(
    materialized='incremental',
    unique_key="employee_id || '_' || simulation_year",
    incremental_strategy='delete+insert',
    on_schema_change='sync_all_columns',
    indexes=[
        {'columns': ['simulation_year'], 'type': 'btree'},
        {'columns': ['employee_id', 'simulation_year'], 'type': 'btree'}
    ],
    tags=['FOUNDATION']
) }}

-- Simplified Baseline Workforce Preparation
-- Creates baseline workforce directly from census data without complex cold start detection

{% set simulation_year = var('simulation_year', 2025) %}
{% set simulation_effective_date_str = var('simulation_effective_date', '2024-12-31') %}

WITH base_employees AS (
    SELECT
        stg.employee_id,
        stg.employee_ssn,
        stg.employee_birth_date,
        stg.employee_hire_date,
        -- Annual salary rate from staging (equals employee_gross_compensation per data contract)
        stg.employee_annualized_compensation AS current_compensation,
        -- Calculate age based on the simulation_effective_date
        EXTRACT(YEAR FROM '{{ simulation_effective_date_str }}'::DATE) - EXTRACT(YEAR FROM stg.employee_birth_date) AS current_age,
        -- **E020 FIX**: Use day-based tenure calculation: floor((12/31/simulation_year - hire_date) / 365.25)
        -- This replaces year-only subtraction for accurate tenure values
        {{ calculate_tenure('stg.employee_hire_date', "MAKE_DATE(" ~ simulation_year ~ ", 12, 31)") }} AS current_tenure,
        -- Dynamically assign level_id with fallback for unmatched compensation ranges
        COALESCE(level_match.level_id, 1) AS level_id,
        -- Add eligibility and enrollment fields from census
        stg.employee_eligibility_date,
        stg.waiting_period_days,
        stg.current_eligibility_status,
        stg.employee_enrollment_date,
        -- Epic E049: Census deferral rate integration - preserve exact census rates
        stg.employee_deferral_rate
    FROM {{ ref('stg_census_data') }} stg
    -- Use a subquery to find the best matching level_id for each employee
    LEFT JOIN (
        SELECT
            stg_inner.employee_id,
            -- Select the level with the smallest min_compensation that still matches
            MIN(levels.level_id) as level_id
        FROM {{ ref('stg_census_data') }} stg_inner
        LEFT JOIN {{ ref('stg_config_job_levels') }} levels
            ON stg_inner.employee_gross_compensation >= levels.min_compensation
           AND (stg_inner.employee_gross_compensation < levels.max_compensation OR levels.max_compensation IS NULL)
        GROUP BY stg_inner.employee_id
    ) level_match ON stg.employee_id = level_match.employee_id
    WHERE stg.employee_termination_date IS NULL
)

SELECT
    employee_id,
    employee_ssn,
    employee_birth_date,
    employee_hire_date,
    current_compensation,
    current_age,
    current_tenure,
    level_id,
    -- Calculate age and tenure bands using centralized macros
    {{ assign_age_band('current_age') }} AS age_band,
    {{ assign_tenure_band('current_tenure') }} AS tenure_band,
    'active' AS employment_status,
    NULL AS termination_date,
    NULL AS termination_reason,
    -- Add eligibility and enrollment fields from census
    employee_eligibility_date,
    waiting_period_days,
    current_eligibility_status,
    employee_enrollment_date,
    -- Epic E049: Census deferral rate integration - preserve exact census rates
    employee_deferral_rate,
    CASE
        WHEN employee_deferral_rate > 0 THEN true
        ELSE false
    END as is_enrolled_at_census,
    {{ simulation_year }} AS simulation_year,
    CURRENT_TIMESTAMP AS snapshot_created_at,
    true as is_from_census,
    -- Simplified: assume this is always a cold start from census data
    true as is_cold_start,
    ({{ simulation_year }} - 1) as last_completed_year
FROM base_employees

{% if is_incremental() %}
    -- Note: This model generates baseline data for the current simulation_year only
    -- No additional filtering needed as baseline is created fresh for each year
{% endif %}

ORDER BY employee_id
